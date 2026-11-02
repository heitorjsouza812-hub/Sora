"""Ferramenta ``falar`` (especificação §4): a única forma de a Sora e dos agentes
individuais mandarem texto ao usuário. Gera ``mensagem.inicio/delta/fim``.

Grava a mensagem (visível) e só depois publica os eventos: quando o app recebe o SSE, o
estado já está no banco.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.eventos.streams import publicar_evento
from app.eventos.tipos import MensagemDelta, MensagemFim, MensagemInicio
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao, obter_redis
from app.modelos.enumeracoes import AutorMensagem, TipoAgente
from app.modelos.tabelas import Agente, Anexo, Mensagem

TAMANHO_DELTA = 400
"""Caracteres por ``mensagem.delta``: o app mostra o texto aparecendo, sem uma chamada por letra."""
MAX_ANEXOS = 10


class Falar(BaseModel):
    """Manda uma mensagem ao usuário. Só o que passa por aqui chega a ele."""

    texto: str = Field(min_length=1)
    anexos: list[UUID] | None = None
    responde_a: UUID | None = None


async def falar(args: Falar, contexto: ContextoFerramenta) -> str:
    """Grava a mensagem visível e emite os eventos de mensagem."""
    texto = args.texto.strip()
    if not texto:
        raise ErroFerramenta("A mensagem está vazia.")
    anexos = list(dict.fromkeys(args.anexos or []))
    if len(anexos) > MAX_ANEXOS:
        raise ErroFerramenta(f"No máximo {MAX_ANEXOS} anexos por mensagem.")

    mensagem_id = uuid4()
    async with abrir_sessao() as sessao:
        tipo = await sessao.scalar(
            select(Agente.tipo).where(
                Agente.id == contexto.agente_id, Agente.usuario_id == contexto.usuario_id
            )
        )
        if tipo is None:
            raise ErroFerramenta("Agente não encontrado.")
        if anexos:
            achados = set(
                (
                    await sessao.scalars(
                        select(Anexo.id).where(
                            Anexo.id.in_(anexos), Anexo.usuario_id == contexto.usuario_id
                        )
                    )
                ).all()
            )
            if achados != set(anexos):
                raise ErroFerramenta("Algum anexo não foi encontrado.")
        if args.responde_a is not None:
            existe = await sessao.scalar(
                select(Mensagem.id).where(
                    Mensagem.id == args.responde_a, Mensagem.conversa_id == contexto.conversa_id
                )
            )
            if existe is None:
                raise ErroFerramenta("A mensagem a que você responde não existe nesta conversa.")
        autor = AutorMensagem.SORA if tipo is TipoAgente.SORA else AutorMensagem.AGENTE
        sessao.add(
            Mensagem(
                id=mensagem_id,
                conversa_id=contexto.conversa_id,
                autor=autor,
                agente_id=contexto.agente_id,
                conteudo=texto,
                anexos=[str(a) for a in anexos],
                visivel=True,
                responde_a=args.responde_a,
            )
        )

    redis = obter_redis()
    cabecalho = (contexto.conversa_id, contexto.usuario_id)
    await publicar_evento(
        redis,
        MensagemInicio(mensagem_id=mensagem_id, autor=autor, agente_id=contexto.agente_id),
        *cabecalho,
    )
    for inicio in range(0, len(texto), TAMANHO_DELTA):
        await publicar_evento(
            redis,
            MensagemDelta(mensagem_id=mensagem_id, texto=texto[inicio : inicio + TAMANHO_DELTA]),
            *cabecalho,
        )
    await publicar_evento(redis, MensagemFim(mensagem_id=mensagem_id, anexos=anexos), *cabecalho)
    return "Mensagem enviada ao usuário."
