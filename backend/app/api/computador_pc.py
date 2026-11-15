"""Canal do app de desktop para o controle do PC do usuário (C3, ``docs/computador-por-bot.md``).

Só o app de desktop usa estas rotas (cabeçalho ``X-Sora-Cliente: desktop``, o mesmo do login do
desktop); quem executa no PC é a ponte Rust do app. O servidor nunca age no PC: ele só entrega
comandos e recebe resultados.

- ``POST   /v1/computador-pc/sessao``: o app se apresenta (bots que o usuário ligou nele);
- ``PUT    /v1/computador-pc/sessao/{id}``: troca a lista de bots ligados;
- ``DELETE /v1/computador-pc/sessao/{id}``: o app saiu (logout, fechou);
- ``GET    /v1/computador-pc/comandos?sessao_id=…&espera=20``: long-poll do próximo comando
  (200 com o comando, 204 sem comando, 409 se outra sessão assumiu);
- ``POST   /v1/computador-pc/comandos/{id}/resultado``: resultado, uma única vez, no prazo;
- ``POST   /v1/computador-pc/parar``: o usuário clicou em Parar na borda;
- ``GET    /v1/computador-pc/estado``: para a tela de Configurações (vale também no navegador).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.computador.pc_usuario_canal import (
    MAX_AUTORIZADOS,
    MAX_ESPERA_LONG_POLL_S,
    VALIDADE_SESSAO_S,
    CanalPc,
)
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.modelos.tabelas import Agente

roteador = APIRouter(
    prefix="/computador-pc", tags=["computador-pc"], dependencies=[Depends(usuario_atual)]
)
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]

SO_DESKTOP = "Só o app de desktop da Sora controla o computador."
SESSAO_TROCADA = "Outra sessão do app de desktop assumiu o controle do computador nesta conta."


def exigir_desktop(x_sora_cliente: Annotated[str | None, Header()] = None) -> None:
    if (x_sora_cliente or "").strip().lower() != "desktop":
        raise HTTPException(status.HTTP_403_FORBIDDEN, SO_DESKTOP)


Desktop = Depends(exigir_desktop)


class SessaoEntrada(BaseModel):
    dispositivo: str = Field(default="", max_length=80)
    autorizados: list[UUID] = Field(default_factory=list, max_length=MAX_AUTORIZADOS)


class SessaoSaida(BaseModel):
    sessao_id: str
    usuario_id: UUID
    autorizados: list[UUID]
    validade_s: int = VALIDADE_SESSAO_S


class AutorizadosEntrada(BaseModel):
    autorizados: list[UUID] = Field(default_factory=list, max_length=MAX_AUTORIZADOS)


class AutorizadosSaida(BaseModel):
    autorizados: list[UUID]


class ErroComando(BaseModel):
    codigo: str = Field(max_length=40)
    mensagem: str | None = Field(default=None, max_length=500)
    programa: str | None = Field(default=None, max_length=260)
    titulo: str | None = Field(default=None, max_length=300)
    por: str | None = Field(default=None, max_length=80)


class ResultadoEntrada(BaseModel):
    sessao_id: str = Field(max_length=64)
    ok: bool
    resultado: dict[str, Any] | None = None
    erro: ErroComando | None = None


class PararEntrada(BaseModel):
    sessao_id: str = Field(max_length=64)
    agente_id: UUID | None = None


class VezSaida(BaseModel):
    agente_id: UUID
    nome: str


class EstadoSaida(BaseModel):
    conectado: bool
    dispositivo: str | None = None
    autorizados: list[UUID] = Field(default_factory=list)
    vez: VezSaida | None = None


class ComandoSaida(BaseModel):
    id: str
    agente: dict[str, str]
    operacao: Literal["observar", "agir", "retomar", "encerrar"]
    dados: dict[str, Any]
    prazo_ms: int
    prazo_em_ms: int


async def _bots_do_usuario(sessao: AsyncSession, usuario_id: UUID, ids: list[UUID]) -> list[UUID]:
    """Só bots do próprio usuário e não apagados (o resto some da lista em silêncio)."""
    if not ids:
        return []
    validos = set(
        await sessao.scalars(
            select(Agente.id).where(
                Agente.id.in_(ids), Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
            )
        )
    )
    return [i for i in dict.fromkeys(ids) if i in validos]


@roteador.post("/sessao", dependencies=[Desktop])
async def registrar_sessao(
    dados: SessaoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SessaoSaida:
    autorizados = await _bots_do_usuario(sessao, usuario_id, dados.autorizados)
    sessao_id = await CanalPc(redis).registrar_sessao(usuario_id, autorizados, dados.dispositivo)
    return SessaoSaida(sessao_id=sessao_id, usuario_id=usuario_id, autorizados=autorizados)


@roteador.put("/sessao/{sessao_id}", dependencies=[Desktop])
async def atualizar_sessao(
    sessao_id: str, dados: AutorizadosEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> AutorizadosSaida:
    autorizados = await _bots_do_usuario(sessao, usuario_id, dados.autorizados)
    if not await CanalPc(redis).atualizar_autorizados(usuario_id, sessao_id[:64], autorizados):
        raise HTTPException(status.HTTP_409_CONFLICT, SESSAO_TROCADA)
    return AutorizadosSaida(autorizados=autorizados)


@roteador.delete(
    "/sessao/{sessao_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Desktop]
)
async def encerrar_sessao(sessao_id: str, usuario_id: Usuario, redis: RedisDep) -> None:
    canal = CanalPc(redis)
    if await canal.encerrar_sessao(usuario_id, sessao_id[:64]):
        await canal.soltar_vez(usuario_id)


@roteador.get(
    "/comandos",
    response_model=ComandoSaida,
    responses={204: {"description": "Sem comando no prazo do long-poll."}},
    dependencies=[Desktop],
)
async def proximo_comando(
    usuario_id: Usuario,
    redis: RedisDep,
    sessao_id: Annotated[str, Query(max_length=64)],
    espera: Annotated[float, Query(ge=0, le=MAX_ESPERA_LONG_POLL_S)] = 20,
) -> Any:
    canal = CanalPc(redis)
    if not await canal.tocar(usuario_id, sessao_id):
        raise HTTPException(status.HTTP_409_CONFLICT, SESSAO_TROCADA)
    comando = await canal.proximo_comando(usuario_id, sessao_id, espera)
    if comando is None:
        await canal.tocar(usuario_id, sessao_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return comando


@roteador.post(
    "/comandos/{comando_id}/resultado",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Desktop],
)
async def responder_comando(
    comando_id: str, dados: ResultadoEntrada, usuario_id: Usuario, redis: RedisDep
) -> None:
    resposta: dict[str, Any] = {"ok": dados.ok}
    if dados.ok:
        resposta["resultado"] = dados.resultado or {}
    else:
        resposta["erro"] = (dados.erro or ErroComando(codigo="falha")).model_dump()
    situacao = await CanalPc(redis).responder(usuario_id, dados.sessao_id, comando_id, resposta)
    if situacao == "nao_encontrado":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comando não encontrado.")
    if situacao == "usado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este comando já foi respondido.")
    if situacao == "vencido":
        raise HTTPException(status.HTTP_409_CONFLICT, "O prazo deste comando acabou.")


@roteador.post("/parar", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Desktop])
async def parar(dados: PararEntrada, usuario_id: Usuario, redis: RedisDep) -> None:
    """Parar na borda da tela: o bot perde a vez e não pega o PC de novo por um tempo."""
    canal = CanalPc(redis)
    if await canal.sessao_atual(usuario_id, dados.sessao_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, SESSAO_TROCADA)
    agente_id = dados.agente_id
    if agente_id is None:
        dono = await canal.quem_tem_a_vez(usuario_id)
        try:
            agente_id = UUID(str((dono or {}).get("agente_id")))
        except ValueError:
            agente_id = None
    if agente_id is not None:
        await canal.marcar_parado(usuario_id, agente_id)
    else:
        await canal.soltar_vez(usuario_id)


@roteador.post("/pausar", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Desktop])
async def pausar(dados: PararEntrada, usuario_id: Usuario, redis: RedisDep) -> None:
    """Entrada física abre atenção imediatamente, mesmo entre comandos do bot."""
    from app.computador.pc_usuario_cartoes import CartoesBanco

    canal = CanalPc(redis)
    if await canal.sessao_atual(usuario_id, dados.sessao_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, SESSAO_TROCADA)
    dono = await canal.quem_tem_a_vez(usuario_id)
    if dados.agente_id is None or not dono or dono.get("agente_id") != str(dados.agente_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este bot não está usando o computador.")
    await canal.marcar_pausado(usuario_id, dados.agente_id)
    guardado = await canal.cartao(usuario_id, dados.agente_id, "retomar")
    if guardado:
        return
    cartoes = CartoesBanco()
    cartao = await cartoes.abrir(
        usuario_id,
        dados.agente_id,
        {
            "tipo": "pc_retomar",
            "titulo": "Retomar o controle do computador?",
            "resumo": (
                "Você mexeu no computador e o bot pausou. Permitir uma vez retoma; Recusar para."
            ),
        },
        "Pausado porque você usou o computador.",
    )
    await canal.guardar_cartao(usuario_id, dados.agente_id, "retomar", cartao, 600)


@roteador.get("/estado")
async def estado(usuario_id: Usuario, redis: RedisDep) -> EstadoSaida:
    canal = CanalPc(redis)
    sessao = await canal.sessao(usuario_id)
    if sessao is None:
        return EstadoSaida(conectado=False)
    dono = await canal.quem_tem_a_vez(usuario_id)
    vez = None
    if dono:
        try:
            vez = VezSaida(agente_id=UUID(str(dono.get("agente_id"))), nome=str(dono.get("nome")))
        except ValueError:
            vez = None
    return EstadoSaida(
        conectado=True,
        dispositivo=str(sessao.get("dispositivo") or "") or None,
        autorizados=[UUID(a) for a in sessao.get("autorizados") or []],
        vez=vez,
    )
