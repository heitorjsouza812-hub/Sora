"""Semeia um perfil nomeado do navegador com login salvo e domínios aprovados, para o QA.

Os domínios só nascem de um cartão de aprovação de um agente com Chromium real; o QA não tem como
provocar isso. Então este script grava, com as MESMAS funções do backend (cifra incluída), o que o
fluxo real gravaria. Roda no `backend/` (`uv run python ../app/qa/semear_perfil.py ...`).

Uso: semear_perfil.py <email> <nome do perfil> <dominio> [<dominio> ...]
Imprime o perfil_id (id da linha do perfil nomeado).
"""

from __future__ import annotations

import asyncio
import sys
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.banco import fabrica_sessoes
from app.modelos.tabelas import EstadoNavegador, PerfilNavegador, Usuario
from app.navegador.perfis import cifrar_estado, com_dominio_aprovado, particao, EscolhaPerfil, TipoPerfil


async def semear(email: str, nome: str, dominios: list[str]) -> str:
    async with fabrica_sessoes()() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        if usuario_id is None:
            raise SystemExit(f"Usuário {email} não existe.")
        antigo = await sessao.scalar(select(PerfilNavegador).where(PerfilNavegador.usuario_id == usuario_id, PerfilNavegador.nome == nome))
        if antigo is not None:
            await sessao.execute(delete(EstadoNavegador).where(EstadoNavegador.particao == particao(usuario_id, uuid4(), EscolhaPerfil(TipoPerfil.NOMEADO, antigo.id))))
            await sessao.delete(antigo)
            await sessao.flush()
        perfil = PerfilNavegador(id=uuid4(), usuario_id=usuario_id, nome=nome, cor="#56A8FF")
        sessao.add(perfil)
        await sessao.flush()
        # login salvo (um cookie de teste) + os domínios que o usuário "aprovou"
        estado: dict = {"cookies": [{"name": "sessao", "value": "x", "domain": dominios[0], "path": "/"}], "origins": []}
        for dominio in dominios:
            estado = com_dominio_aprovado(estado, dominio)
        chave = particao(usuario_id, uuid4(), EscolhaPerfil(TipoPerfil.NOMEADO, perfil.id))
        sessao.add(EstadoNavegador(particao=chave, usuario_id=usuario_id, estado_cifrado=cifrar_estado(estado, usuario_id=usuario_id, particao_=chave)))
        await sessao.commit()
        return str(perfil.id)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    print(asyncio.run(semear(sys.argv[1], sys.argv[2], sys.argv[3:])))
