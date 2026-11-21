"""Agrega os grupos de rotas FastAPI da especificação §§2 e 8.2."""

from fastapi import APIRouter

from app.api import (
    agenda,
    agentes,
    anexos,
    aprovacoes,
    atencao,
    auth,
    biblioteca,
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
    ganchos,
    grupos,
    habilidades,
    modelos,
    navegador,
    navegador_ao_vivo,
    navegador_senha,
    pecas,
    perguntas,
    preferencias,
    provedores,
    push,
    relatos,
    reservas,
    rotinas,
    uso,
    voz,
)

roteador_v1 = APIRouter()
for roteador in (
    auth.roteador,
    conta.roteador,
    relatos.roteador,
    reservas.roteador,
    push.roteador,
    navegador_senha.roteador,
    ganchos.roteador,
    ganchos.roteador_publico,  # webhook das rotinas: sem login, vale a assinatura
    agenda.roteador,  # agenda das rotinas e feed .ics (o feed é sem login: segredo no endereço)
    agentes.roteador,
    bots.roteador,
    atencao.roteador,
    conversas.roteador,
    eventos.roteador,
    cadeias.roteador,
    entregas.roteador,
    anexos.roteador,
    biblioteca.roteador,
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
