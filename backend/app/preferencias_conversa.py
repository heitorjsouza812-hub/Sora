"""Seletor do campo de mensagem: provedor, modelo, nível de raciocínio e modo de permissão.

Vale por conversa (Sora ou bot 1:1) e por grupo (``preferencias_conversa``, chave = id da conversa
ou do grupo) e, como padrão, por bot (``agentes.provedor_padrao_id``, ``modelo_padrao``,
``raciocinio_padrao``, ``permissao_padrao``). Ordem: a escolha da conversa; sem ela, o padrão do
bot; sem os dois, o automático (o seletor de sempre e o modo ``perguntar``).

- ``modelo`` + ``provedor_id``: o worker usa só esse modelo em todas as chamadas da conversa e
  **não troca sozinho** se ele falhar; a conversa recebe o aviso de qual modelo falhou.
- ``raciocinio``: ``auto`` ou um nível de ``app/llm/raciocinio.py``. No automático o nível vale
  para o modelo que o seletor achar (o aceito mais próximo).
- ``permissao``: ``perguntar`` (como sempre), ``automatico`` (ações de risco baixo passam
  sozinhas) e ``total`` (tudo o que a política permitiria aprovar). Regra em
  ``app/revisor/decisoes.py``; rotina sem supervisão é sempre ``perguntar``.

Contrato com o app: ``.maestri/contrato-etapa5.md``, "Seletor de modelo e permissão".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.raciocinio import AUTO, NIVEIS, niveis_de_raciocinio
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import (
    Agente,
    CanalEquipe,
    Conversa,
    ModeloDisponivel,
    PreferenciaConversa,
    Provedor,
)

RACIOCINIOS: tuple[str, ...] = (AUTO, *NIVEIS)
PERGUNTAR, AUTOMATICO, TOTAL = "perguntar", "automatico", "total"
PERMISSOES: tuple[str, ...] = (PERGUNTAR, AUTOMATICO, TOTAL)
ROTULO_DO_MODO = {PERGUNTAR: "perguntar", AUTOMATICO: "automático", TOTAL: "total"}
ROTULO_DO_NIVEL = {
    "baixo": "baixo",
    "medio": "médio",
    "alto": "alto",
    "extra_alto": "extra alto",
    "maximo": "máximo",
}

Origem = Literal["conversa", "bot", "automatico"]
TipoAlvo = Literal["conversa", "grupo"]

CHAVE_ESCOLHA = "sora_escolha"
"""Chave em ``chat.metadata`` do modelo escolhido pelo usuário (o worker não troca sozinho)."""


class ErroPreferencia(ValueError):
    """Escolha inválida: a API responde 422 com esta mensagem."""


class ModeloEscolhidoIndisponivel(RuntimeError):
    """O modelo escolhido sumiu (provedor apagado, modelo desligado, teto do mês)."""


class FalhaDoModeloEscolhido(RuntimeError):
    """O modelo escolhido falhou na chamada; ``str(erro)`` é o aviso em PT-BR para o usuário."""


@dataclass(frozen=True, slots=True)
class EscolhaModelo:
    provedor_id: UUID | None = None
    modelo: str | None = None
    raciocinio: str = AUTO
    permissao: str = PERGUNTAR
    origem: Origem = "automatico"

    @property
    def modelo_fixo(self) -> bool:
        return self.modelo is not None and self.provedor_id is not None


AUTOMATICA = EscolhaModelo()


# ---------- esquemas HTTP ----------


class PreferenciaSaida(BaseModel):
    provedor_id: UUID | None
    modelo: str | None
    raciocinio: str
    permissao: str
    origem: Origem
    """De onde veio: ``conversa`` (escolhida aqui), ``bot`` (padrão do bot) ou ``automatico``."""
    tipo: TipoAlvo


class PreferenciaAtualizacao(BaseModel):
    """PATCH parcial: só os campos enviados mudam. ``null``/``"auto"`` = automático."""

    provedor_id: UUID | None = None
    modelo: str | None = Field(default=None, max_length=200)
    raciocinio: str | None = Field(default=None, max_length=20)
    permissao: str | None = Field(default=None, max_length=20)
    confirmar_total: bool = False


CAMPOS_DA_PREFERENCIA = ("provedor_id", "modelo", "raciocinio", "permissao")


def saida(escolha: EscolhaModelo, tipo: TipoAlvo) -> PreferenciaSaida:
    return PreferenciaSaida(
        provedor_id=escolha.provedor_id if escolha.modelo_fixo else None,
        modelo=escolha.modelo if escolha.modelo_fixo else None,
        raciocinio=escolha.raciocinio,
        permissao=escolha.permissao,
        origem=escolha.origem,
        tipo=tipo,
    )


# ---------- leitura ----------


def _de_linha(linha: PreferenciaConversa) -> EscolhaModelo:
    return EscolhaModelo(
        provedor_id=linha.provedor_id if linha.modelo else None,
        modelo=linha.modelo if linha.provedor_id else None,
        raciocinio=linha.raciocinio if linha.raciocinio in RACIOCINIOS else AUTO,
        permissao=linha.permissao if linha.permissao in PERMISSOES else PERGUNTAR,
        origem="conversa",
    )


def padrao_do_bot(agente: Agente | None) -> EscolhaModelo:
    """O padrão gravado no bot. ``modelo_padrao`` sem provedor (campo antigo) não fixa nada."""
    if agente is None or agente.tipo == TipoAgente.SORA:
        return AUTOMATICA
    fixo = agente.provedor_padrao_id is not None and bool(agente.modelo_padrao)
    escolha = EscolhaModelo(
        provedor_id=agente.provedor_padrao_id if fixo else None,
        modelo=agente.modelo_padrao if fixo else None,
        raciocinio=agente.raciocinio_padrao if agente.raciocinio_padrao in RACIOCINIOS else AUTO,
        permissao=agente.permissao_padrao if agente.permissao_padrao in PERMISSOES else PERGUNTAR,
    )
    if escolha == AUTOMATICA:
        return AUTOMATICA
    return replace(escolha, origem="bot")


async def alvo_do_usuario(
    sessao: AsyncSession, usuario_id: UUID, alvo_id: UUID
) -> tuple[TipoAlvo, Agente | None] | None:
    """A conversa (com o bot dela) ou o grupo do usuário; ``None`` = não existe para ele."""
    conversa = await sessao.scalar(
        select(Conversa).where(Conversa.id == alvo_id, Conversa.usuario_id == usuario_id)
    )
    if conversa is not None:
        return "conversa", await sessao.get(Agente, conversa.agente_id)
    grupo = await sessao.scalar(
        select(CanalEquipe.id).where(
            CanalEquipe.id == alvo_id, CanalEquipe.usuario_id == usuario_id
        )
    )
    if grupo is not None:
        return "grupo", None
    return None


async def escolha_efetiva(
    sessao: AsyncSession,
    usuario_id: UUID,
    *,
    conversa_id: UUID | None = None,
    agente_id: UUID | None = None,
) -> EscolhaModelo:
    """O que vale numa chamada: escolha da conversa (ou do grupo), senão o padrão do bot, senão o
    automático. Linha de outro usuário é ignorada (isolamento)."""
    if conversa_id is not None:
        linha = await sessao.scalar(
            select(PreferenciaConversa).where(
                PreferenciaConversa.alvo_id == conversa_id,
                PreferenciaConversa.usuario_id == usuario_id,
            )
        )
        if isinstance(linha, PreferenciaConversa):
            return _de_linha(linha)
    if agente_id is not None:
        agente = await sessao.scalar(
            select(Agente).where(Agente.id == agente_id, Agente.usuario_id == usuario_id)
        )
        if isinstance(agente, Agente):
            return padrao_do_bot(agente)
    return AUTOMATICA


async def escolha_da_execucao(
    usuario_id: UUID, conversa_id: UUID | None, agente_id: UUID | None
) -> EscolhaModelo:
    """``escolha_efetiva`` com sessão própria (worker e ferramentas). Falha = automático."""
    from app.ferramentas.infra import abrir_sessao

    try:
        async with abrir_sessao() as sessao:
            return await escolha_efetiva(
                sessao, usuario_id, conversa_id=conversa_id, agente_id=agente_id
            )
    except Exception:
        return AUTOMATICA


# ---------- validação e gravação ----------


async def _conferir_modelo(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID, modelo: str
) -> None:
    provedor = await sessao.scalar(
        select(Provedor).where(
            Provedor.id == provedor_id,
            Provedor.usuario_id == usuario_id,
            Provedor.apagado_em.is_(None),
        )
    )
    if provedor is None:
        raise ErroPreferencia("Provedor não encontrado. Confira em Configurações → Modelos de IA.")
    if provedor.validado_em is None:
        raise ErroPreferencia(
            "Esse provedor ainda não foi validado. "
            "Confira a chave em Configurações → Modelos de IA."
        )
    linha = await sessao.scalar(
        select(ModeloDisponivel).where(
            ModeloDisponivel.provedor_id == provedor_id, ModeloDisponivel.modelo == modelo
        )
    )
    if linha is None:
        raise ErroPreferencia(f"O modelo {modelo} não existe nesse provedor.")
    if not linha.ativo:
        raise ErroPreferencia(
            f"O modelo {modelo} está desligado. Ligue-o em Configurações → Modelos de IA."
        )


def _texto_dos_niveis(modelo: str) -> str:
    aceitos = niveis_de_raciocinio(modelo)
    if not aceitos:
        return f"O modelo {modelo} não tem nível de raciocínio ajustável. Use Automático."
    return (
        f"O modelo {modelo} aceita os níveis: "
        + ", ".join(ROTULO_DO_NIVEL[n] for n in aceitos)
        + " (ou Automático)."
    )


async def aplicar_mudancas(
    sessao: AsyncSession,
    usuario_id: UUID,
    atual: EscolhaModelo,
    dados: PreferenciaAtualizacao,
) -> EscolhaModelo:
    """Valida o PATCH sobre a escolha atual e devolve a nova. ``ErroPreferencia`` = 422.

    - provedor e modelo andam juntos (os dois ou nenhum); o provedor é do usuário, não apagado e
      validado; o modelo existe nele e está ligado;
    - o nível de raciocínio precisa ser aceito pelo modelo escolhido (no automático vale qualquer
      nível: o worker usa o aceito mais próximo do modelo que o seletor achar). Trocar de modelo
      sem mandar o nível volta o nível para ``auto`` quando o novo modelo não o aceita;
    - mudar para ``total`` exige ``confirmar_total: true``.
    """
    campos = dados.model_fields_set
    provedor_id = atual.provedor_id if atual.modelo_fixo else None
    modelo = atual.modelo if atual.modelo_fixo else None
    if "provedor_id" in campos:
        provedor_id = dados.provedor_id
    if "modelo" in campos:
        modelo = (dados.modelo or "").strip() or None
        if modelo is not None and modelo.lower() == AUTO:
            modelo = None
    if modelo is None and "modelo" in campos and "provedor_id" not in campos:
        provedor_id = None  # ``{"modelo": null}`` sozinho volta para o automático
    if (provedor_id is None) != (modelo is None):
        raise ErroPreferencia(
            "Escolha o provedor do modelo."
            if provedor_id is None
            else "Escolha um modelo desse provedor ou volte para Automático."
        )
    if modelo is not None and provedor_id is not None:
        await _conferir_modelo(sessao, usuario_id, provedor_id, modelo)

    raciocinio = atual.raciocinio
    if "raciocinio" in campos:
        raciocinio = dados.raciocinio or AUTO
        if raciocinio not in RACIOCINIOS:
            raise ErroPreferencia(
                "Nível de raciocínio inválido. Use auto, baixo, medio, alto, extra_alto ou maximo."
            )
        if (
            raciocinio != AUTO
            and modelo is not None
            and raciocinio not in niveis_de_raciocinio(modelo)
        ):
            raise ErroPreferencia(_texto_dos_niveis(modelo))
    elif raciocinio != AUTO and modelo is not None:
        if raciocinio not in niveis_de_raciocinio(modelo):
            raciocinio = AUTO

    permissao = atual.permissao
    if "permissao" in campos:
        permissao = dados.permissao or PERGUNTAR
        if permissao not in PERMISSOES:
            raise ErroPreferencia("Modo de permissão inválido. Use perguntar, automatico ou total.")
        if permissao == TOTAL and atual.permissao != TOTAL and not dados.confirmar_total:
            raise ErroPreferencia(
                "O modo total deixa os bots agirem sem pedir aprovação. Para ligar, confirme "
                "(confirmar_total: true)."
            )
    return EscolhaModelo(
        provedor_id=provedor_id,
        modelo=modelo,
        raciocinio=raciocinio,
        permissao=permissao,
        origem=atual.origem,
    )


async def gravar_da_conversa(
    sessao: AsyncSession,
    usuario_id: UUID,
    alvo_id: UUID,
    tipo: TipoAlvo,
    escolha: EscolhaModelo,
) -> EscolhaModelo:
    from datetime import UTC, datetime

    linha = await sessao.get(PreferenciaConversa, alvo_id, with_for_update=True)
    if linha is None:
        linha = PreferenciaConversa(alvo_id=alvo_id, usuario_id=usuario_id, tipo=tipo)
        sessao.add(linha)
    linha.provedor_id = escolha.provedor_id
    linha.modelo = escolha.modelo
    linha.raciocinio = escolha.raciocinio
    linha.permissao = escolha.permissao
    linha.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return replace(escolha, origem="conversa")


def gravar_no_bot(agente: Agente, escolha: EscolhaModelo) -> None:
    agente.provedor_padrao_id = escolha.provedor_id
    agente.modelo_padrao = escolha.modelo
    agente.raciocinio_padrao = escolha.raciocinio
    agente.permissao_padrao = escolha.permissao


def campos_enviados(dados: BaseModel) -> bool:
    return any(c in dados.model_fields_set for c in CAMPOS_DA_PREFERENCIA)


def so_preferencia(dados: BaseModel) -> PreferenciaAtualizacao:
    """Copia os campos do seletor de outro corpo (bot, novo bot) mantendo o que foi enviado."""
    enviados = {
        c: getattr(dados, c)
        for c in (*CAMPOS_DA_PREFERENCIA, "confirmar_total")
        if c in dados.model_fields_set
    }
    return PreferenciaAtualizacao(**enviados)


# ---------- uso no worker ----------


def marcar_escolhido(chat: Any, modelo: str, capacidades: Sequence[str]) -> None:
    """Marca o modelo escolhido pelo usuário (o worker não troca sozinho se ele falhar)."""
    chat.metadata = {
        **(getattr(chat, "metadata", None) or {}),
        CHAVE_ESCOLHA: {"modelo": modelo, "capacidades": sorted(capacidades)},
    }


def modelo_escolhido(modelos: Sequence[Any]) -> str | None:
    """Nome do modelo escolhido pelo usuário, se a lista é a de um modelo fixo."""
    if not modelos:
        return None
    dados = (getattr(modelos[0], "metadata", None) or {}).get(CHAVE_ESCOLHA)
    return str(dados["modelo"]) if isinstance(dados, dict) and dados.get("modelo") else None


def escolhido_enxerga(modelos: Sequence[Any]) -> bool:
    dados = (getattr(modelos[0], "metadata", None) or {}).get(CHAVE_ESCOLHA) if modelos else None
    return isinstance(dados, dict) and "visao" in (dados.get("capacidades") or [])


SUGESTAO_DE_TROCA = (
    "Não troquei de modelo sozinho: escolha outro no seletor do campo de mensagem ou volte para "
    "Automático."
)


def texto_da_falha_do_escolhido(modelo: str, erro: BaseException) -> str:
    """Aviso em PT-BR de que o modelo escolhido falhou, com o motivo e a sugestão de trocar."""
    if isinstance(erro, ModeloEscolhidoIndisponivel):
        return str(erro)
    from app.llm.limite import chave_recusada, cota_diaria, mensagem_de_limite
    from app.llm.troca import MotivoTroca, classificar_erro

    if mensagem_de_limite(erro) is not None:
        motivo = (
            "atingiu a cota do dia no provedor"
            if cota_diaria(erro)
            else "atingiu o limite de uso do provedor"
        )
    elif chave_recusada(erro):
        motivo = "teve a chave de API recusada pelo provedor"
    elif classificar_erro(erro) in {MotivoTroca.ERRO_DO_SERVIDOR, MotivoTroca.PRAZO}:
        motivo = "está fora do ar ou demorou demais para responder"
    else:
        motivo = "não conseguiu responder"
    return f"O modelo {modelo}, escolhido para esta conversa, {motivo}. {SUGESTAO_DE_TROCA}"


def falha_de_provedor(erro: BaseException) -> bool:
    """Limite, cota, chave recusada, 5xx ou prazo: falha do provedor, não da resposta."""
    from app.llm.limite import chave_recusada, mensagem_de_limite
    from app.llm.troca import classificar_erro

    return (
        classificar_erro(erro) is not None
        or mensagem_de_limite(erro) is not None
        or chave_recusada(erro)
    )


def texto_da_falha(modelos: Sequence[Any], erro: BaseException) -> str | None:
    """O aviso do modelo escolhido, ou ``None`` no automático (vale o texto de sempre)."""
    if isinstance(erro, ModeloEscolhidoIndisponivel):
        return str(erro)
    nome = modelo_escolhido(modelos)
    return None if nome is None else texto_da_falha_do_escolhido(nome, erro)
