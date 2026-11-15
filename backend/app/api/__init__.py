"""Agrega os grupos de rotas FastAPI da especificação §§2 e 8.2."""

from fastapi import APIRouter

from app.api import (
    agentes,
    anexos,
    aprovacoes,
    atencao,
    auth,
    bots,
    busca,
    cadeias,
    canais,
    canais_empresa,
    computador,
    computador_pc,
    conectores,
    conta,
    conversas,
    entregas,
    equipe,
    eventos,
    grupos,
    habilidades,
    modelos,
    navegador,
    navegador_ao_vivo,
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
    bots.roteador,
    atencao.roteador,
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
    canais_empresa.roteador,  # Ponte: Slack e WhatsApp Business só de leitura
    canais_empresa.roteador_webhooks,
    navegador.roteador_agente,
    navegador.roteador,  # perfis do navegador (Leme): antes da equipe
    navegador_ao_vivo.roteador,  # Farol-2 (item 18): quadros, captura e pedidos do usuário
    pecas.roteador,  # antes da equipe: as rotas de contexto são da Âncora
    equipe.roteador,
    grupos.roteador,
    rotinas.roteador,
    busca.roteador,
    conectores.roteador,
    habilidades.roteador,
    voz.roteador,
    computador.roteador,  # Farol (C2): computador virtual do bot
    computador_pc.roteador,  # Vela-3 (C3): canal do app de desktop para o PC do usuário
):
    roteador_v1.include_router(roteador)

__all__ = ["roteador_v1"]
