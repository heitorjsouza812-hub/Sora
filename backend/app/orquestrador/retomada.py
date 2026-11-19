"""Retomada e motivos de parada de uma etapa da cadeia (funções puras, sem banco).

Saíram de ``workers/cadeia.py``; lá os nomes continuam importáveis."""

from __future__ import annotations

from typing import Any

from app.modelos.enumeracoes import StatusEtapa


def valor_da_retomada(resposta: Any) -> Any:
    """A API manda ``{"pergunta_id", "valor"}`` ou ``{"aprovacao_id", "decisao"}``; as
    ferramentas ``perguntar`` e ``criar_agente`` esperam so o valor/decisao no ``resume``."""
    if isinstance(resposta, dict):
        if "valor" in resposta:
            return resposta["valor"]
        if "decisao" in resposta:
            return resposta["decisao"]
    return resposta


def _estado_da_pausa(valor: Any) -> StatusEtapa:
    tipo = valor.get("tipo") if isinstance(valor, dict) else None
    if tipo == "pergunta":
        return StatusEtapa.AGUARDANDO_USUARIO
    if tipo == "aprovacao":
        return StatusEtapa.AGUARDANDO_APROVACAO
    raise RuntimeError(f"interrupcao desconhecida: {valor!r}")


def _foi_cancelamento(erro: BaseException | None) -> bool:
    from app.agentes.middleware.cancelamento import CadeiaCancelada

    visto: set[int] = set()
    while erro is not None and id(erro) not in visto:
        if isinstance(erro, CadeiaCancelada):
            return True
        visto.add(id(erro))
        erro = erro.__cause__ or erro.__context__
    return False


def _estourou_orcamento(erro: BaseException | None) -> bool:
    from app.agentes.middleware.orcamento import OrcamentoEstourado

    visto: set[int] = set()
    while erro is not None and id(erro) not in visto:
        if isinstance(erro, OrcamentoEstourado):
            return True
        visto.add(id(erro))
        erro = erro.__cause__ or erro.__context__
    return False
