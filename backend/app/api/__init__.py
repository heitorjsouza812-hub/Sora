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
    eventos,
    habilidades,
    modelos,
    navegador,
    pecas,
    perguntas,
    preferencias,
    provedores,
    rotinas,
    uso,
    voz,
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
    navegador.roteador,  # perfis do navegador (Leme): antes da equipe
    pecas.roteador,  # antes da equipe: as rotas de contexto são da Âncora
    equipe.roteador,
    rotinas.roteador,
    conectores.roteador,
    habilidades.roteador,
    voz.roteador,
):
    roteador_v1.include_router(roteador)

__all__ = ["roteador_v1"]
