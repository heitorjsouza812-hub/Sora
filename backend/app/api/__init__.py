"""Agrega os grupos de rotas FastAPI da especificação §§2 e 8.2."""

from fastapi import APIRouter

from app.api import (
    agentes,
    anexos,
    aprovacoes,
    auth,
    cadeias,
    canais,
    conectores,
    conta,
    conversas,
    entregas,
    equipe,
    pecas,
    eventos,
    habilidades,
    modelos,
    perguntas,
    preferencias,
    provedores,
    rotinas,
    uso,
)

roteador_v1 = APIRouter()
for roteador in (
    auth.roteador,
    conta.roteador,
    agentes.roteador,
    conversas.roteador,
    eventos.roteador,
    cadeias.roteador,
    entregas.roteador,
    anexos.roteador,
    perguntas.roteador,
    aprovacoes.roteador,
    provedores.roteador,
    modelos.roteador,
    preferencias.roteador,
    uso.roteador,
    canais.roteador,
    pecas.roteador,  # antes da equipe: as rotas de contexto são da Âncora
    equipe.roteador,
    rotinas.roteador,
    conectores.roteador,
    habilidades.roteador,
):
    roteador_v1.include_router(roteador)

__all__ = ["roteador_v1"]
