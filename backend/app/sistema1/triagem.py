"""Chamada ao modelo N1 (triagem).

Especificação: §5 (Sistema 1 usa sempre o N1 mais rápido que o usuário conectou), §6.1 (chama o
modelo pelo LangChain, com saída estruturada) e prompts 03 (temperatura 0; não roda quando o
usuário escolheu "Agente independente"). O prompt vem de ``backend/prompts/`` (nunca no código).

Fluxo de ``triar``: regras → N1 → validar; JSON inválido: um conserto (o próprio N1 recebe os
erros e corrige); falhou de novo: reenvia o pedido ao N2 (``escalou = True``); falhou também:
levanta ``SaidaInvalida``. O risco final é o maior entre regras, Laya e N1. Erro de provedor
(429, 5xx, prazo) passa para o próximo modelo da lista do seletor e vira ``EventoTroca``.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from functools import cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agentes.prompts import PASTA_PROMPTS, VERSOES
from app.llm.custo import CustoChamada, PrecoModelo, calcular_custo, extrair_uso
from app.llm.fabrica import criar_chat_model
from app.llm.provedores import ConfigProvedor
from app.llm.troca import EventoTroca, classificar_erro
from app.seletor.politica import Politica, obter_politica
from app.seletor.seletor import AvisoSeletor, escolher_modelos
from app.seletor.tipos import Capacidade, ContextoSeletor, ModeloCandidato, PapelModelo
from app.sistema1.esquemas import (
    CapacidadeTriagem,
    Especialista,
    ModoTriagem,
    SaidaSistema1,
)
from app.sistema1.regras import ResultadoRegras, aplicar_regras, juntar_risco
from app.sistema1.saida_json import SaidaInvalida, validar_saida_com_conserto

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

# Nomes no registro de ``app/agentes/prompts.py`` (VERSOES): arquivos ``prompts/<nome>.v<n>.md``.
PROMPT_SISTEMA1 = "sistema1"
PROMPT_CONSERTO = "sistema1_conserto"

PRAZO_TRIAGEM_S = 20.0
MAX_TOKENS_TRIAGEM = 800
_CHAVES_DO_PROMPT = re.compile(
    r"\{(tem_modelo_de_imagem|lista_de_agentes|lista_de_conectores|ultimas_mensagens|pedido)\}"
)

FabricaDeChat = Callable[[ModeloCandidato, ConfigProvedor], "BaseChatModel"]


class SemModeloDisponivel(Exception):
    """O seletor não achou modelo para o Sistema 1 (a API responde 412 antes de chegar aqui)."""


class AgenteIndividualResumo(BaseModel):
    id: str
    nome: str
    funcao: str


class ContextoTriagem(BaseModel):
    """Variáveis do prompt do Sistema 1."""

    agentes_individuais: list[AgenteIndividualResumo] = Field(default_factory=list)
    conectores: list[str] = Field(default_factory=list)
    ultimas_mensagens: list[str] = Field(default_factory=list)
    tem_modelo_de_imagem: bool = False
    em_conversa_com_agente: bool = False  # restringe modo a direto | cadeia


class ResultadoTriagem(BaseModel):
    """A decisão mais os dados que vão para ``roteamentos`` e para a linha do tempo."""

    saida: SaidaSistema1
    modelo: str
    provedor_id: UUID | None = None
    latencia_ms: int
    escalou: bool = False  # True quando precisou do N2
    consertou: bool = False  # True quando precisou do conserto (local ou pelo modelo)
    ambiguo: bool = False  # confiança abaixo do mínimo da política: a Sora deve perguntar
    regras: ResultadoRegras
    chamadas: list[CustoChamada] = Field(default_factory=list)  # uma por chamada ao modelo
    trocas: list[EventoTroca] = Field(default_factory=list)  # falhas de provedor no caminho
    avisos: list[AvisoSeletor] = Field(default_factory=list)


@cache
def _ler_prompt(nome: str) -> str:
    return (PASTA_PROMPTS / f"{nome}.v{VERSOES.get(nome, 1)}.md").read_text(encoding="utf-8")


def _estimar_tokens(texto: str) -> int:
    return max(len(texto) // 3, 1)


def montar_prompt(pedido: str, contexto: ContextoTriagem) -> str:
    """Lê ``prompts/sistema1.v1.md`` e preenche as variáveis. O pedido entra como dado.

    Preenche numa passada só: um ``{pedido}`` escrito dentro do texto do usuário não é trocado.
    """
    agentes = "\n".join(f"- {a.id}: {a.nome} ({a.funcao})" for a in contexto.agentes_individuais)
    valores = {
        "tem_modelo_de_imagem": "sim" if contexto.tem_modelo_de_imagem else "não",
        "lista_de_agentes": agentes or "(nenhum)",
        "lista_de_conectores": ", ".join(contexto.conectores) or "(nenhum)",
        "ultimas_mensagens": "\n".join(contexto.ultimas_mensagens) or "(nenhuma)",
        "pedido": pedido,
    }
    return _CHAVES_DO_PROMPT.sub(lambda m: valores[m.group(1)], _ler_prompt(PROMPT_SISTEMA1))


def capacidades_para_seletor(saida: SaidaSistema1) -> set[Capacidade]:
    """Capacidades que o MODELO de chat precisa ter, a partir da triagem.

    ``imagem`` não entra (é do modelo de imagem, escolhido à parte) nem ``contexto_longo``
    (o seletor já compara o contexto com o tamanho do prompt).
    """
    mapa = {
        CapacidadeTriagem.FERRAMENTAS: Capacidade.FERRAMENTAS,
        CapacidadeTriagem.VISAO: Capacidade.VISAO,
    }
    return {mapa[c] for c in saida.capacidades if c in mapa}


def _texto_da_resposta(resposta: AIMessage) -> str:
    conteudo = resposta.content
    if isinstance(conteudo, str):
        return conteudo
    return "".join(
        bloco if isinstance(bloco, str) else str(bloco.get("text", ""))
        for bloco in conteudo
        if isinstance(bloco, str | dict)
    )


def _fabrica_padrao(candidato: ModeloCandidato, config: ConfigProvedor) -> BaseChatModel:
    return criar_chat_model(
        candidato.modelo,
        config,
        papel=PapelModelo.SISTEMA1.value,
        temperatura=0.0,
        max_tokens=MAX_TOKENS_TRIAGEM,
        timeout_s=PRAZO_TRIAGEM_S,
    )


class _Chamador:
    """Chama a lista de modelos do seletor em ordem, trocando em falha de provedor."""

    def __init__(
        self,
        provedores: Mapping[str, ConfigProvedor],
        fabrica: FabricaDeChat,
    ) -> None:
        self.provedores = provedores
        self.fabrica = fabrica
        self.chamadas: list[CustoChamada] = []
        self.trocas: list[EventoTroca] = []

    async def chamar(
        self, modelos: list[ModeloCandidato], mensagens: list[Any]
    ) -> tuple[str, ModeloCandidato]:
        usaveis = [m for m in modelos if str(m.provedor.id) in self.provedores]
        ultimo_erro: Exception | None = None
        for posicao, candidato in enumerate(usaveis):
            chat = self.fabrica(candidato, self.provedores[str(candidato.provedor.id)])
            inicio = time.perf_counter()
            try:
                resposta = await chat.ainvoke(mensagens)
            except Exception as erro:
                motivo = classificar_erro(erro)
                if motivo is None:
                    raise
                proximo = usaveis[posicao + 1].modelo if posicao + 1 < len(usaveis) else None
                self.trocas.append(
                    EventoTroca(de_modelo=candidato.modelo, para_modelo=proximo, motivo=motivo)
                )
                ultimo_erro = erro
                continue
            uso = extrair_uso(resposta)
            self.chamadas.append(
                CustoChamada(
                    modelo=candidato.modelo,
                    provedor_id=candidato.provedor.id,
                    papel=PapelModelo.SISTEMA1.value,
                    nivel=str(candidato.nivel),
                    tokens_entrada=uso.tokens_entrada,
                    tokens_saida=uso.tokens_saida,
                    custo_usd=calcular_custo(
                        candidato.modelo,
                        uso,
                        PrecoModelo(entrada=candidato.preco_entrada, saida=candidato.preco_saida),
                    ),
                    latencia_ms=int((time.perf_counter() - inicio) * 1000),
                )
            )
            return _texto_da_resposta(resposta), candidato
        if ultimo_erro is not None:
            raise ultimo_erro
        raise SemModeloDisponivel("Nenhum modelo da lista tem provedor com chave disponível.")


def _pos_processar(
    saida: SaidaSistema1,
    regras: ResultadoRegras,
    contexto: ContextoTriagem,
    politica: Politica,
) -> SaidaSistema1:
    """Regras de código sobre a decisão do N1: o risco só sobe; modo e lista coerentes."""
    risco = juntar_risco(regras.risco, saida.risco)
    modo = saida.modo
    especialistas = list(saida.especialistas)
    agente = saida.agente_sugerido
    if agente is not None and agente not in {a.id for a in contexto.agentes_individuais}:
        agente = None

    sem_agente = agente is None or contexto.em_conversa_com_agente
    if modo is ModoTriagem.AGENTE_INDIVIDUAL and sem_agente:
        # Sem agente para rotear (ou conversa já com um agente): cadeia se houver especialistas.
        modo = ModoTriagem.CADEIA if especialistas else ModoTriagem.DIRETO
    if modo is not ModoTriagem.AGENTE_INDIVIDUAL:
        agente = None

    if modo is not ModoTriagem.CADEIA:
        especialistas = []
    else:
        if not contexto.tem_modelo_de_imagem:
            especialistas = [e for e in especialistas if e is not Especialista.DESIGNER]
        maximo = politica.limites.especialistas_por_cadeia
        if len(especialistas) > 1 and Especialista.VERIFICADOR not in especialistas:
            especialistas.append(Especialista.VERIFICADOR)
        if len(especialistas) > maximo:
            sem_verificador = [e for e in especialistas if e is not Especialista.VERIFICADOR]
            tem_verificador = len(sem_verificador) != len(especialistas)
            especialistas = sem_verificador[: maximo - (1 if tem_verificador else 0)]
            if tem_verificador:
                especialistas.append(Especialista.VERIFICADOR)

    resposta_direta = saida.resposta_direta if modo is ModoTriagem.DIRETO else None
    return saida.model_copy(
        update={
            "risco": risco,
            "modo": modo,
            "especialistas": especialistas,
            "agente_sugerido": agente,
            "resposta_direta": resposta_direta,
        }
    )


async def triar(
    pedido: str,
    contexto: ContextoTriagem,
    seletor: ContextoSeletor,
    provedores: Mapping[str, ConfigProvedor],
    *,
    politica: Politica | None = None,
    agora: datetime | None = None,
    fabrica_de_chat: FabricaDeChat | None = None,
) -> ResultadoTriagem:
    """Triagem completa de um pedido. ``provedores`` mapeia ``str(provedor_id)`` → config com a
    chave decifrada (só na hora da chamada). Sem nenhum modelo servindo, levanta
    ``SemModeloDisponivel``; JSON inválido mesmo depois do N2, ``SaidaInvalida``.

    ``fabrica_de_chat`` troca a criação do modelo (testes); o padrão é ``criar_chat_model``.
    """
    inicio = time.perf_counter()
    politica = politica or obter_politica()
    regras = aplicar_regras(pedido)
    prompt = montar_prompt(pedido, contexto)
    tokens = _estimar_tokens(prompt)

    selecao = escolher_modelos(
        seletor, PapelModelo.SISTEMA1, 1, set(), tokens, politica=politica, agora=agora
    )
    avisos = list(selecao.avisos)
    if not selecao.modelos:
        raise SemModeloDisponivel("Nenhum modelo conectado serve para o Sistema 1.")

    chamador = _Chamador(provedores, fabrica_de_chat or _fabrica_padrao)
    texto, modelo = await chamador.chamar(selecao.modelos, [HumanMessage(prompt)])

    consertou = False
    escalou = False
    try:
        saida, consertou = validar_saida_com_conserto(texto)
    except SaidaInvalida as primeiro:
        # Conserto único: o próprio modelo recebe os erros e devolve o JSON corrigido.
        pedido_de_conserto = _ler_prompt(PROMPT_CONSERTO).replace("{erros}", primeiro.erros)
        texto, modelo = await chamador.chamar(
            [modelo],
            [HumanMessage(prompt), AIMessage(texto), HumanMessage(pedido_de_conserto)],
        )
        consertou = True
        try:
            saida, _ = validar_saida_com_conserto(texto)
        except SaidaInvalida:
            # Não deu: manda o pedido original para o N2 (resposta_direta com dificuldade 2).
            escalada = escolher_modelos(
                seletor,
                PapelModelo.RESPOSTA_DIRETA,
                2,
                {Capacidade.JSON},
                tokens,
                politica=politica,
                agora=agora,
            )
            avisos.extend(escalada.avisos)
            outros = [m for m in escalada.modelos if m.modelo != modelo.modelo]
            candidatos = outros or escalada.modelos
            texto, modelo = await chamador.chamar(candidatos, [HumanMessage(prompt)])
            escalou = True
            saida, _ = validar_saida_com_conserto(texto)

    saida = _pos_processar(saida, regras, contexto, politica)
    return ResultadoTriagem(
        saida=saida,
        modelo=modelo.modelo,
        provedor_id=modelo.provedor.id,
        latencia_ms=int((time.perf_counter() - inicio) * 1000),
        escalou=escalou,
        consertou=consertou,
        ambiguo=saida.confianca < politica.limites.confianca_minima_s1,
        regras=regras,
        chamadas=chamador.chamadas,
        trocas=chamador.trocas,
        avisos=avisos,
    )
