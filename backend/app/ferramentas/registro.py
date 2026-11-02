"""Registro das ferramentas e montagem como ``@tool`` do LangChain (especificação
§4 e §6.1: ``@tool`` com ``args_schema`` = a classe Pydantic).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.buscar_web import BuscarWeb
from app.ferramentas.criar_agente import CriarAgente
from app.ferramentas.disparar_especialista import DispararEspecialista
from app.ferramentas.entregar import Entregar
from app.ferramentas.escrever_arquivo import EscreverArquivo
from app.ferramentas.falar import Falar
from app.ferramentas.gerar_imagem import GerarImagem
from app.ferramentas.ler_anexo import LerAnexo
from app.ferramentas.ler_pagina import LerPagina
from app.ferramentas.mensagem_especialista import MensagemEspecialista
from app.ferramentas.parar_especialista import PararEspecialista
from app.ferramentas.perguntar import Perguntar
from app.ferramentas.ver_especialista import VerEspecialista
from app.ferramentas.veredito import Veredito

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

ESQUEMAS: dict[str, type[BaseModel]] = {
    "falar": Falar,
    "perguntar": Perguntar,
    "disparar_especialista": DispararEspecialista,
    "ver_especialista": VerEspecialista,
    "mensagem_especialista": MensagemEspecialista,
    "parar_especialista": PararEspecialista,
    "buscar_web": BuscarWeb,
    "ler_pagina": LerPagina,
    "ler_anexo": LerAnexo,
    "escrever_arquivo": EscreverArquivo,
    "gerar_imagem": GerarImagem,
    "entregar": Entregar,
    "veredito": Veredito,
    "criar_agente": CriarAgente,
}
"""Ferramentas da fase 1: nome → esquema dos argumentos."""


def esquemas_das_proximas_fases() -> dict[str, type[BaseModel]]:
    """Fases 2 e 3, adaptadas do Rakazo (``docs/referencias/rakazo.md``).

    Ficam fora de ``ESQUEMAS`` até cada uma ser ligada no worker; a política de aprovação
    de cada nome está em ``app/revisor/politica.py``.
    """
    # Peças inspiradas no OpenBot, escritas pela Sora (``docs/referencias/openbot.md``).
    from app.canais_equipe.ferramentas import FERRAMENTAS_DO_CANAL
    from app.computador import ExecutarComando
    from app.conectores.servidores import AdicionarServidorMCP
    from app.correio.reacoes import ReagirMensagem
    from app.ferramentas.catalogo_tarefas import CatalogoTarefas
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.gerar_grafico import GerarGrafico
    from app.ferramentas.historico import BuscarHistorico, LerHistorico
    from app.ferramentas.propor_instrucoes import ProporInstrucoes
    from app.habilidades import (
        ApagarHabilidade,
        AtualizarHabilidade,
        CriarHabilidade,
        LerHabilidade,
    )
    from app.memoria.servico import BuscarMemoria, EsquecerMemoria, Lembrar
    from app.navegador import NavegadorAbrir, NavegadorAgir, NavegadorLer
    from app.navegador.abas import (
        NavegadorAbas,
        NavegadorCapturar,
        NavegadorConsole,
        NavegadorFecharAba,
        NavegadorPedirAjuda,
    )
    from app.navegador.arvore.ferramentas import ESQUEMAS as FERRAMENTAS_DA_ARVORE
    from app.pendencias import (
        AdicionarPendencia,
        AtualizarPendencia,
        ConcluirPendencia,
        ListarPendencias,
        RemoverPendencia,
    )
    from app.rotinas.agenda import Agendar, CancelarAgendamento, ListarAgendamentos

    return {
        "buscar_memoria": BuscarMemoria,
        "lembrar": Lembrar,
        "esquecer_memoria": EsquecerMemoria,
        "enviar_para_agente": EnviarParaAgente,
        "buscar_historico": BuscarHistorico,
        "ler_historico": LerHistorico,
        "catalogo_tarefas": CatalogoTarefas,
        "propor_instrucoes": ProporInstrucoes,
        "agendar": Agendar,
        "listar_agendamentos": ListarAgendamentos,
        "cancelar_agendamento": CancelarAgendamento,
        "adicionar_pendencia": AdicionarPendencia,
        "listar_pendencias": ListarPendencias,
        "atualizar_pendencia": AtualizarPendencia,
        "concluir_pendencia": ConcluirPendencia,
        "remover_pendencia": RemoverPendencia,
        "ler_habilidade": LerHabilidade,
        "criar_habilidade": CriarHabilidade,
        "atualizar_habilidade": AtualizarHabilidade,
        "apagar_habilidade": ApagarHabilidade,
        "gerar_grafico": GerarGrafico,
        "adicionar_servidor_mcp": AdicionarServidorMCP,
        "executar_comando": ExecutarComando,
        "navegador_abrir": NavegadorAbrir,
        "navegador_ler": NavegadorLer,
        "navegador_agir": NavegadorAgir,
        "navegador_abas": NavegadorAbas,
        "navegador_fechar_aba": NavegadorFecharAba,
        "navegador_capturar": NavegadorCapturar,
        "navegador_console": NavegadorConsole,
        "navegador_pedir_ajuda": NavegadorPedirAjuda,
        "reagir": ReagirMensagem,
        **FERRAMENTAS_DO_CANAL,
        # navegador por árvore, adaptado do agent-desktop (docs/referencias/agent-desktop.md)
        **FERRAMENTAS_DA_ARVORE,
    }


def criar_ferramentas(nomes: list[str], contexto: ContextoFerramenta) -> list[BaseTool]:
    """Monta as ferramentas pedidas como ``@tool`` do LangChain, presas ao contexto.

    Cada ferramenta vira uma ``StructuredTool`` assíncrona com ``args_schema`` = a classe
    Pydantic. ``ErroFerramenta`` volta ao modelo como texto ("Erro: …"); a interrupção do
    LangGraph (``perguntar``, ``criar_agente``) passa direto. ``entregar`` e ``veredito``
    usam ``return_direct``: depois delas o laço do agente termina.
    """
    from importlib import import_module

    from langchain_core.tools import StructuredTool

    from app.ferramentas.base import ErroFerramenta

    def montar(nome: str) -> BaseTool:
        esquema = ESQUEMAS.get(nome)
        if esquema is None:
            raise ValueError(f"Ferramenta desconhecida: {nome}")
        funcao = getattr(import_module(f"app.ferramentas.{nome}"), nome)

        async def executar(**argumentos):
            try:
                return await funcao(esquema(**argumentos), contexto)
            except ErroFerramenta as erro:
                return f"Erro: {erro}"

        return StructuredTool.from_function(
            coroutine=executar,
            name=nome,
            description=(esquema.__doc__ or nome).strip(),
            args_schema=esquema,
            return_direct=nome in FERRAMENTAS_QUE_ENCERRAM,
        )

    return [montar(nome) for nome in dict.fromkeys(nomes)]


FERRAMENTAS_QUE_ENCERRAM: frozenset[str] = frozenset({"entregar", "veredito"})
