"""Agrega os grupos de rotas FastAPI da especificação §§2 e 8.2."""

from fastapi import APIRouter

from app.api import (
    agentes,
    anexos,
    aprovacoes,
    auth,
    cadeias,
    canais,
    conta,
    conversas,
    entregas,
    eventos,
    modelos,
    perguntas,
    preferencias,
    provedores,
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
):
    roteador_v1.include_router(roteador)

__all__ = ["roteador_v1"]
