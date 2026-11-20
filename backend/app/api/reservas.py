"""Modelos reserva da conta: ``GET``/``PUT /v1/modelos-reserva`` (migração 0019).

Só valem quando há um modelo fixo escolhido no campo de mensagem e ele falha (limite, fora do
ar); a troca aparece na conversa. Regras em ``app/core/reservas.py``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import reservas
from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual

roteador = APIRouter(
    prefix="/modelos-reserva", tags=["modelos"], dependencies=[Depends(usuario_atual)]
)

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]


class ReservasEntrada(BaseModel):
    itens: list[reservas.ItemReserva] = Field(max_length=reservas.MAX_RESERVAS)


@roteador.get("")
async def obter_reservas(usuario_id: Usuario, sessao: Sessao) -> list[reservas.ItemReserva]:
    """A lista em ordem (a 1ª é tentada primeiro)."""
    return [
        reservas.ItemReserva(provedor_id=r.provedor_id, modelo=r.modelo)
        for r in await reservas.listar_reservas(sessao, usuario_id)
    ]


@roteador.put("")
async def definir_reservas(
    dados: ReservasEntrada, usuario_id: Usuario, sessao: Sessao
) -> list[reservas.ItemReserva]:
    """Troca a lista inteira (``[]`` desliga as reservas)."""
    linhas = await reservas.definir_reservas(sessao, usuario_id, dados.itens)
    return [reservas.ItemReserva(provedor_id=r.provedor_id, modelo=r.modelo) for r in linhas]
