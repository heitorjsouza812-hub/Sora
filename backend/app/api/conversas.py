"""Rotas de conversas, mensagens, aprovação e ajuste; especificação §2."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import (
    AjusteEntrada,
    AprovacaoVersaoEntrada,
    ConversaCriacao,
    ConversaSaida,
    MensagemAceita,
    MensagemCriacao,
    MensagemSaida,
    RenomearConversaEntrada,
)

roteador = APIRouter(prefix="/conversas", tags=["conversas"], dependencies=[Depends(usuario_atual)])


@roteador.get("")
async def listar_conversas() -> list[ConversaSaida]:
    """Lista chats, projetos e conversas de agentes do usuário."""
    raise NotImplementedError


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_conversa(dados: ConversaCriacao) -> ConversaSaida:
    """Cria uma conversa já com a primeira mensagem."""
    raise NotImplementedError


@roteador.patch("/{conversa_id}")
async def renomear_conversa(conversa_id: UUID, dados: RenomearConversaEntrada) -> ConversaSaida:
    """Renomeia uma conversa do usuário."""
    raise NotImplementedError


@roteador.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conversa(conversa_id: UUID, manter_agentes: bool = False) -> None:
    """Apaga uma conversa e opcionalmente preserva seus especialistas."""
    raise NotImplementedError


@roteador.get("/{conversa_id}/mensagens")
async def listar_mensagens(
    conversa_id: UUID, antes: datetime | None = None, limite: int = 50
) -> list[MensagemSaida]:
    """Pagina mensagens visíveis de uma conversa."""
    raise NotImplementedError


@roteador.post("/{conversa_id}/mensagens", status_code=status.HTTP_202_ACCEPTED)
async def enviar_mensagem(conversa_id: UUID, dados: MensagemCriacao) -> MensagemAceita:
    """Grava uma mensagem e inicia seu processamento assíncrono."""
    raise NotImplementedError


@roteador.post("/{conversa_id}/aprovar", status_code=status.HTTP_204_NO_CONTENT)
async def aprovar_versao(conversa_id: UUID, dados: AprovacaoVersaoEntrada) -> None:
    """Registra a versão aprovada na revisão."""
    raise NotImplementedError


@roteador.post("/{conversa_id}/ajuste", status_code=status.HTTP_202_ACCEPTED)
async def pedir_ajuste(conversa_id: UUID, dados: AjusteEntrada) -> None:
    """Solicita uma nova versão com o especialista apropriado."""
    raise NotImplementedError
