"""Carrega as ferramentas dos servidores MCP do usuário para o turno de um agente.

Nunca derruba o turno: sem conectores, com servidor fora do ar ou com prazo estourado, o agente
só fica sem essas ferramentas. Sem supervisão (rotina) só entram as de leitura.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

registro = logging.getLogger(__name__)
PRAZO_CARGA_SEGUNDOS = 20


async def ferramentas_dos_conectores(
    usuario_id: UUID, *, sem_supervisao: bool = False
) -> list[BaseTool]:
    from app.conectores.ferramenta import ambiente_local, servidores_do_usuario
    from app.conectores.servidores import carregar_ferramentas
    from app.ferramentas.infra import abrir_sessao
    from app.revisor.politica import pode_sem_supervisao

    try:
        async with abrir_sessao() as sessao:
            servidores = await servidores_do_usuario(sessao, usuario_id)
        if not servidores:
            return []
        ferramentas = await asyncio.wait_for(
            carregar_ferramentas(servidores, ambiente_local=ambiente_local()),
            PRAZO_CARGA_SEGUNDOS,
        )
    except Exception:
        registro.warning("conectores MCP indisponíveis para %s", usuario_id, exc_info=True)
        return []
    if sem_supervisao:
        ferramentas = [f for f in ferramentas if pode_sem_supervisao(f.name)]
    return ferramentas
