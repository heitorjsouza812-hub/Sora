"""Autorizações por bot e preferências (retenção, análise) dos canais da empresa."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.canais_empresa.comum import (
    Sessao,
    Usuario,
    roteador,
)
from app.api.canais_empresa.esquemas import (
    AutorizacaoEntrada,
    AutorizacaoSaida,
    PreferenciasEntrada,
    PreferenciasSaida,
)
from app.canais_empresa import acesso, lgpd
from app.canais_empresa.tabelas import (
    PreferenciasCanaisEmpresa,
)


@roteador.get("/autorizacoes")
async def listar_autorizacoes(usuario_id: Usuario, sessao: Sessao) -> list[AutorizacaoSaida]:
    agrupadas: dict[tuple[str, UUID], list[str]] = {}
    for a in await acesso.listar(sessao, usuario_id):
        agrupadas.setdefault((a.alvo_tipo, a.alvo_id), []).append(a.escopo)
    return [AutorizacaoSaida(alvo_tipo=t, alvo_id=i, escopos=e) for (t, i), e in agrupadas.items()]


@roteador.put("/autorizacoes")
async def definir_autorizacao(
    dados: AutorizacaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> AutorizacaoSaida:
    """Define exatamente quais escopos (``clientes``, ``conhecimento``) o bot ou grupo tem."""
    try:
        escopos = await acesso.definir(
            sessao, usuario_id, dados.alvo_tipo, dados.alvo_id, list(dados.escopos)
        )
    except acesso.ErroAcesso as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    return AutorizacaoSaida(alvo_tipo=dados.alvo_tipo, alvo_id=dados.alvo_id, escopos=escopos)


async def _preferencias(sessao: AsyncSession, usuario_id: UUID) -> PreferenciasCanaisEmpresa:
    prefs = await sessao.get(PreferenciasCanaisEmpresa, usuario_id)
    if prefs is None:
        prefs = PreferenciasCanaisEmpresa(
            usuario_id=usuario_id,
            retencao_dias=lgpd.RETENCAO_PADRAO_DIAS,
            retencao_fatos_dias=lgpd.RETENCAO_FATOS_PADRAO_DIAS,
            sugestoes_intervalo_dias=7,
        )
        sessao.add(prefs)
        await sessao.flush()
    return prefs


def _saida_prefs(p: PreferenciasCanaisEmpresa) -> PreferenciasSaida:
    return PreferenciasSaida(
        retencao_dias=p.retencao_dias,
        retencao_fatos_dias=p.retencao_fatos_dias,
        sugestoes_intervalo_dias=p.sugestoes_intervalo_dias,
        ultima_analise_em=p.ultima_analise_em,
    )


@roteador.get("/preferencias")
async def ver_preferencias(usuario_id: Usuario, sessao: Sessao) -> PreferenciasSaida:
    return _saida_prefs(await _preferencias(sessao, usuario_id))


@roteador.put("/preferencias")
async def salvar_preferencias(
    dados: PreferenciasEntrada, usuario_id: Usuario, sessao: Sessao
) -> PreferenciasSaida:
    prefs = await _preferencias(sessao, usuario_id)
    if dados.retencao_dias is not None:
        prefs.retencao_dias = dados.retencao_dias
    if dados.retencao_fatos_dias is not None:
        prefs.retencao_fatos_dias = dados.retencao_fatos_dias
    if dados.sugestoes_intervalo_dias is not None:
        prefs.sugestoes_intervalo_dias = dados.sugestoes_intervalo_dias
    prefs.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_prefs(prefs)
