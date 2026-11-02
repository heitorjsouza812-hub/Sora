"""Ferramenta ``entregar`` (especificação §4): fim da etapa de um especialista.
Vira uma linha em ``entregas`` e o evento ``entrega``. Idempotente por etapa: repetir a
chamada (retomada após queda) atualiza a mesma linha e não emite o evento de novo.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.banco import fabrica_sessoes
from app.eventos.tipos import EntregaEvento
from app.ferramentas.ambiente import emitir
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.tabelas import Cadeia, Entrega, Etapa


class Entregar(BaseModel):
    """Entrega o resultado da etapa para a Sora e para a Revisão."""

    tipo: Literal["texto", "links", "imagem", "calendario", "arquivo"]
    titulo: str = Field(max_length=40, description='Uma palavra: "Pesquisa", "Peças", "Calendário"')
    resumo: str = Field(max_length=80, description='Curto: "4 referências", "3 peças", "12 posts"')
    conteudo: dict[str, Any] | list[Any] | str
    fontes: list[str] = Field(default_factory=list)
    pendencias: list[str] = Field(default_factory=list)


async def entregar(args: Entregar, contexto: ContextoFerramenta) -> str:
    """Grava a entrega e encerra o laço do agente."""
    if contexto.cadeia_id is None:
        raise ErroFerramenta("Só um especialista de uma cadeia pode entregar.")
    conteudo = {"dados": args.conteudo, "fontes": args.fontes, "pendencias": args.pendencias}
    async with fabrica_sessoes()() as sessao:
        cadeia = await sessao.get(Cadeia, contexto.cadeia_id)
        if cadeia is None or cadeia.usuario_id != contexto.usuario_id:
            raise ErroFerramenta("Cadeia não encontrada.")
        etapa = await sessao.get(Etapa, contexto.etapa_id) if contexto.etapa_id else None
        linha = None
        if etapa is not None:
            linha = await sessao.scalar(select(Entrega).where(Entrega.etapa_id == etapa.id))
        novo = linha is None
        if linha is None:
            linha = Entrega(
                usuario_id=contexto.usuario_id,
                conversa_id=contexto.conversa_id,
                cadeia_id=cadeia.id,
                etapa_id=contexto.etapa_id,
                agente_id=contexto.agente_id,
                versao=cadeia.versao,
                tipo=args.tipo,
                titulo=args.titulo,
                resumo=args.resumo,
                conteudo=conteudo,
            )
            sessao.add(linha)
        else:
            linha.tipo, linha.titulo = args.tipo, args.titulo
            linha.resumo, linha.conteudo = args.resumo, conteudo
        await sessao.commit()
        entrega_id, versao = linha.id, linha.versao
    if novo:
        await emitir(
            contexto,
            EntregaEvento(
                entrega_id=entrega_id,
                agente_id=contexto.agente_id,
                versao=versao,
                tipo=args.tipo,
                titulo=args.titulo,
                resumo=args.resumo,
            ),
        )
    return f"Entrega registrada: {args.titulo} ({args.resumo})."
