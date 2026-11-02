"""Ciclo de vida do navegador persistente dentro do worker ARQ."""

from __future__ import annotations

from typing import Any

from app.ferramentas.navegador_worker import AmbienteNavegador, configurar
from app.navegador.abas import GerenteAbas
from app.navegador.arvore import ServicoArvore
from app.navegador.persistente import MotorPlaywright
from app.navegador.repositorio import RepositorioNavegador


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
    configurar(ambiente)
    return ambiente


async def fechar_navegador(ctx: dict[str, Any]) -> None:
    configurar(None)
    ambiente = ctx.pop("navegador", None)
    if ambiente is None:
        return
    for aba in ambiente.gerente.para_salvar():
        await ambiente.repositorio.salvar_aba(aba)
    await ambiente.motor.encerrar()
