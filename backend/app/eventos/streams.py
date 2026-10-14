"""Persistência e leitura dos Redis Streams de eventos; especificação §2."""

from collections.abc import AsyncIterator
from uuid import UUID

from app.eventos.tipos import TIPOS_EVENTOS_ESTADO, Evento, EventoEstado


def canal_conversa(conversa_id: UUID) -> str:
    """Calcula o nome do stream durável de uma conversa."""
    return f"eventos:{conversa_id}"


def canal_usuario(usuario_id: UUID) -> str:
    """Calcula o nome do stream agregado de estado do usuário."""
    return f"eventos:usuario:{usuario_id}"


async def publicar_evento(evento: Evento, conversa_id: UUID, usuario_id: UUID) -> str:
    """Grava o evento e usa a lista central para decidir o canal do usuário."""
    raise NotImplementedError


def eh_evento_de_estado(evento: Evento) -> bool:
    """Informa, pela lista central, se o evento também pertence ao canal do usuário."""
    return evento.evento in TIPOS_EVENTOS_ESTADO


def enriquecer_evento_do_usuario(evento: EventoEstado, conversa_id: UUID) -> dict[str, object]:
    """Representa o payload achatado do canal do usuário com sua conversa."""
    return {"conversa_id": conversa_id, **evento.model_dump(mode="json")}


async def ler_eventos(canal: str, depois_de: str | None) -> AsyncIterator[tuple[str, Evento]]:
    """Lê continuamente um stream a partir do identificador informado."""
    raise NotImplementedError
    yield  # pragma: no cover
