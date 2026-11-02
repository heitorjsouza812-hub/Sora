"""Ciclo de vida do navegador persistente dentro do worker ARQ."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from uuid import UUID

from app.eventos.equipe import AbaNavegadorEvento, publicar_evento_equipe
from app.ferramentas.navegador_worker import AmbienteNavegador, configurar
from app.navegador.abas import GerenteAbas
from app.navegador.arvore import ServicoArvore
from app.navegador.perfis import EscolhaPerfil, TipoPerfil, particao
from app.navegador.persistente import MotorPlaywright
from app.navegador.repositorio import RepositorioNavegador, aprovar_dominio_no_perfil
from app.revisor.politica import dominio_registravel

registro = logging.getLogger(__name__)
INTERVALO_SALVAR_S = 15


async def iniciar_navegador(ctx: dict[str, Any]) -> AmbienteNavegador:
    repositorio = RepositorioNavegador(ctx["sessoes"])
    gerente_ref: dict[str, GerenteAbas] = {}
    motor = MotorPlaywright(
        ler_estado=repositorio.ler_estado,
        gravar_estado=repositorio.gravar_estado,
        ao_console=lambda aba_id, nivel, texto: gerente_ref["gerente"].anotar_console(
            aba_id, nivel, texto
        ),
    )
    gerente = GerenteAbas(motor)
    gerente_ref["gerente"] = gerente
    abas, perfis = await repositorio.carregar_abas()
    await gerente.restaurar(abas, perfis_por_usuario=perfis)
    ambiente = AmbienteNavegador(
        gerente=gerente,
        motor=motor,
        arvore=ServicoArvore(gerente, motor.pagina),
        repositorio=repositorio,
        sessoes=ctx["sessoes"],
        redis=ctx["redis_eventos"],
    )
    ctx["navegador"] = ambiente
    ctx["navegador_salvador"] = asyncio.create_task(_salvar_logins(motor))
    configurar(ambiente)
    return ambiente


async def _salvar_logins(motor: MotorPlaywright) -> None:
    """O usuário loga numa aba assumida sem nenhum agente rodando: grava o login aos poucos."""
    while True:
        await asyncio.sleep(INTERVALO_SALVAR_S)
        try:
            await motor.salvar_estados()
        except Exception:
            registro.warning("não consegui salvar o login dos perfis", exc_info=True)


async def abrir_aba_de_perfil(
    ctx: dict[str, Any], usuario_id: str, agente_id: str, perfil_id: str, url: str
) -> dict[str, Any]:
    """Abre uma aba no perfil nomeado e a entrega ao usuário (assumida), para ele logar.

    Quem abre é o próprio usuário: o domínio do endereço já nasce aprovado no perfil.
    """
    ambiente: AmbienteNavegador = ctx["navegador"]
    usuario, agente, perfil = UUID(usuario_id), UUID(agente_id), UUID(perfil_id)
    escolha = EscolhaPerfil(tipo=TipoPerfil.NOMEADO, perfil_id=perfil)
    nome_particao = particao(usuario, agente, escolha)
    async with ctx["sessoes"]() as sessao:
        await aprovar_dominio_no_perfil(
            sessao, particao=nome_particao, usuario_id=usuario, dominio=dominio_registravel(url)
        )
        await sessao.commit()
    await ambiente.motor.recarregar_estado_da_particao(nome_particao)
    aba = await ambiente.gerente.abrir(
        usuario_id=usuario, agente_id=agente, escolha=escolha, url=url
    )
    aba = ambiente.gerente.assumir(aba.id, usuario)
    await ambiente.redis.set(f"navegador:assumida:{aba.id}", "1")
    await ambiente.repositorio.salvar_aba(aba)
    evento = AbaNavegadorEvento(
        aba_id=aba.id,
        agente_id=aba.agente_id,
        url=aba.url,
        titulo=aba.titulo,
        carregada=aba.carregada,
        assumida_pelo_usuario=True,
    )
    await publicar_evento_equipe(ambiente.redis, evento, usuario)
    return evento.model_dump(mode="json")


async def fechar_navegador(ctx: dict[str, Any]) -> None:
    configurar(None)
    salvador = ctx.pop("navegador_salvador", None)
    if salvador is not None:
        salvador.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await salvador
    ambiente = ctx.pop("navegador", None)
    if ambiente is None:
        return
    for aba in ambiente.gerente.para_salvar():
        await ambiente.repositorio.salvar_aba(aba)
    await ambiente.motor.encerrar()
