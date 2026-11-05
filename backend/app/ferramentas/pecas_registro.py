"""Liga no catálogo as ferramentas das peças do Rakazo (Âncora, etapa 4)."""

from __future__ import annotations

from pydantic import BaseModel

MODULO = "app.ferramentas.pecas"

NOMES = (
    "lembrar",
    "buscar_memoria",
    "esquecer_memoria",
    "buscar_historico",
    "ler_historico",
    "catalogo_tarefas",
    "propor_instrucoes",
    "adicionar_pendencia",
    "listar_pendencias",
    "atualizar_pendencia",
    "concluir_pendencia",
    "remover_pendencia",
    "ler_habilidade",
    "criar_habilidade",
    "atualizar_habilidade",
    "apagar_habilidade",
    "enviar_para_agente",
)


def registrar(esquemas: dict[str, type[BaseModel]], modulos: dict[str, str]) -> None:
    from app.ferramentas.catalogo_tarefas import CatalogoTarefas
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.historico import BuscarHistorico, LerHistorico
    from app.ferramentas.propor_instrucoes import ProporInstrucoes
    from app.habilidades import (
        ApagarHabilidade,
        AtualizarHabilidade,
        CriarHabilidade,
        LerHabilidade,
    )
    from app.memoria.servico import BuscarMemoria, EsquecerMemoria, Lembrar
    from app.pendencias import (
        AdicionarPendencia,
        AtualizarPendencia,
        ConcluirPendencia,
        ListarPendencias,
        RemoverPendencia,
    )

    mapa: dict[str, type[BaseModel]] = {
        "lembrar": Lembrar,
        "buscar_memoria": BuscarMemoria,
        "esquecer_memoria": EsquecerMemoria,
        "buscar_historico": BuscarHistorico,
        "ler_historico": LerHistorico,
        "catalogo_tarefas": CatalogoTarefas,
        "propor_instrucoes": ProporInstrucoes,
        "adicionar_pendencia": AdicionarPendencia,
        "listar_pendencias": ListarPendencias,
        "atualizar_pendencia": AtualizarPendencia,
        "concluir_pendencia": ConcluirPendencia,
        "remover_pendencia": RemoverPendencia,
        "ler_habilidade": LerHabilidade,
        "criar_habilidade": CriarHabilidade,
        "atualizar_habilidade": AtualizarHabilidade,
        "apagar_habilidade": ApagarHabilidade,
        "enviar_para_agente": EnviarParaAgente,
    }
    for nome in NOMES:
        esquemas[nome] = mapa[nome]
        modulos[nome] = MODULO
