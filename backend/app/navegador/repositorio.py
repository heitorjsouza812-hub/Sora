"""Persistência PostgreSQL do navegador usado pelo worker.

O estado de login fica cifrado em ``estados_navegador``; as abas ficam em
``abas_navegador`` e são restauradas descarregadas depois de reiniciar o worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.modelos.tabelas import AbaNavegador, Agente, EstadoNavegador, PerfilNavegador
from app.navegador.abas import Aba
from app.navegador.perfis import (
    EscolhaPerfil,
    TipoPerfil,
    cifrar_estado,
    com_dominio_aprovado,
    decifrar_estado,
    ler_particao,
)


class RepositorioNavegador:
    def __init__(self, fabrica_sessoes: Any) -> None:
        self._sessoes = fabrica_sessoes

    async def ler_estado(self, particao: str) -> dict[str, Any] | None:
        lida = ler_particao(particao)
        if lida is None:
            return None
        async with self._sessoes() as sessao:
            registro = await sessao.get(EstadoNavegador, particao)
            if registro is None or registro.usuario_id != lida.usuario_id:
                return None
            return decifrar_estado(
                registro.estado_cifrado, usuario_id=lida.usuario_id, particao_=particao
            )

    async def gravar_estado(self, particao: str, estado: dict[str, Any]) -> None:
        lida = ler_particao(particao)
        if lida is None:  # perfis efêmeros nunca são persistidos
            return
        cifrado = cifrar_estado(estado, usuario_id=lida.usuario_id, particao_=particao)
        async with self._sessoes() as sessao:
            registro = await sessao.get(EstadoNavegador, particao, with_for_update=True)
            if registro is None:
                sessao.add(
                    EstadoNavegador(
                        particao=particao,
                        usuario_id=lida.usuario_id,
                        estado_cifrado=cifrado,
                    )
                )
            else:
                registro.estado_cifrado = cifrado
                registro.atualizado_em = datetime.now(UTC)
            await sessao.commit()

    async def carregar_abas(self) -> tuple[list[Aba], dict[UUID, set[UUID]]]:
        async with self._sessoes() as sessao:
            registros = list((await sessao.scalars(select(AbaNavegador))).all())
            perfis = list((await sessao.scalars(select(PerfilNavegador))).all())
        por_usuario: dict[UUID, set[UUID]] = {}
        for perfil in perfis:
            por_usuario.setdefault(perfil.usuario_id, set()).add(perfil.id)
        return (
            [
                Aba(
                    id=item.id,
                    usuario_id=item.usuario_id,
                    agente_id=item.agente_id,
                    particao=item.particao,
                    url=item.url,
                    titulo=item.titulo,
                    aberta_em=item.aberta_em,
                    usada_em=item.usada_em,
                    carregada=False,
                )
                for item in registros
            ],
            por_usuario,
        )

    async def salvar_aba(self, aba: Aba) -> None:
        if aba.perfil_efemero:
            return
        async with self._sessoes() as sessao:
            item = await sessao.get(AbaNavegador, aba.id, with_for_update=True)
            if item is None:
                item = AbaNavegador(id=aba.id, usuario_id=aba.usuario_id, agente_id=aba.agente_id)
                sessao.add(item)
            item.particao = aba.particao
            item.url = aba.url
            item.titulo = aba.titulo
            item.aberta_em = aba.aberta_em
            item.usada_em = aba.usada_em
            await sessao.commit()

    async def remover_aba(self, aba_id: UUID) -> None:
        async with self._sessoes() as sessao:
            await sessao.execute(delete(AbaNavegador).where(AbaNavegador.id == aba_id))
            await sessao.commit()

    async def escolha_do_agente(self, agente_id: UUID, usuario_id: UUID) -> EscolhaPerfil:
        async with self._sessoes() as sessao:
            agente = await sessao.scalar(
                select(Agente).where(Agente.id == agente_id, Agente.usuario_id == usuario_id)
            )
        if agente is None:
            raise ValueError("Agente não encontrado.")
        tipo = TipoPerfil(agente.perfil_navegador)
        return EscolhaPerfil(tipo=tipo, perfil_id=agente.perfil_navegador_id)


async def aprovar_dominio_no_perfil(
    sessao: Any, *, particao: str, usuario_id: UUID, dominio: str
) -> str:
    """Grava a permissão no estado cifrado, na mesma transação da aprovação."""
    lida = ler_particao(particao)
    if lida is None or lida.usuario_id != usuario_id:
        raise ValueError("Perfil do navegador inválido.")
    registro = await sessao.get(EstadoNavegador, particao, with_for_update=True)
    estado = (
        decifrar_estado(registro.estado_cifrado, usuario_id=usuario_id, particao_=particao)
        if registro is not None
        else {"cookies": [], "origins": []}
    )
    cifrado = cifrar_estado(
        com_dominio_aprovado(estado, dominio), usuario_id=usuario_id, particao_=particao
    )
    if registro is None:
        sessao.add(
            EstadoNavegador(particao=particao, usuario_id=usuario_id, estado_cifrado=cifrado)
        )
    else:
        registro.estado_cifrado = cifrado
        registro.atualizado_em = datetime.now(UTC)
    return particao
