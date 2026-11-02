"""Ferramenta ``perguntar`` (especificação §4; pausa por interrupção do LangGraph
em §6.1). Vira um cartão de pergunta no app (evento ``pergunta``).

Ao retomar, o LangGraph executa a função desde o início, então o id da pergunta é
determinístico (mesma conversa, etapa, texto e opções = mesma linha) e nada é gravado
nem emitido duas vezes.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.core.banco import fabrica_sessoes
from app.eventos.tipos import OpcaoPergunta, PerguntaEvento
from app.ferramentas.ambiente import emitir
from app.ferramentas.base import ContextoFerramenta
from app.modelos.tabelas import Etapa, Pergunta


class Opcao(BaseModel):
    rotulo: str = Field(max_length=40)
    valor: str = Field(description="O que volta para a Sora, escrito como o usuário responderia")


class Perguntar(BaseModel):
    """Pergunta ao usuário com opções clicáveis.
    Use só para ação irreversível ou ambiguidade real."""

    texto: str = Field(max_length=200)
    opcoes: list[Opcao] = Field(min_length=2, max_length=4)
    resposta_livre: bool = False


def id_da_pergunta(args: Perguntar, contexto: ContextoFerramenta) -> UUID:
    base = "|".join(
        [
            str(contexto.conversa_id),
            str(contexto.etapa_id or ""),
            args.texto,
            *(f"{o.rotulo}={o.valor}" for o in args.opcoes),
        ]
    )
    return uuid5(NAMESPACE_URL, f"sora:pergunta:{base}")


async def perguntar(args: Perguntar, contexto: ContextoFerramenta) -> str:
    """Grava a pergunta, emite ``pergunta`` e interrompe até a resposta do usuário."""
    pergunta_id = id_da_pergunta(args, contexto)
    opcoes = [o.model_dump() for o in args.opcoes]
    criada = False
    async with fabrica_sessoes()() as sessao:
        if await sessao.get(Pergunta, pergunta_id) is None:
            sessao.add(
                Pergunta(
                    id=pergunta_id,
                    conversa_id=contexto.conversa_id,
                    cadeia_id=contexto.cadeia_id,
                    texto=args.texto,
                    opcoes=opcoes,
                    resposta_livre=args.resposta_livre,
                )
            )
            criada = True
        if contexto.etapa_id is not None:
            etapa = await sessao.get(Etapa, contexto.etapa_id)
            if etapa is not None and etapa.cadeia_id == contexto.cadeia_id:
                # Grave o vinculo antes de publicar o cartao, mas preserve `executando`: o
                # worker ainda precisa receber o interrupt e persistir a pausa.
                etapa.saida = {**(etapa.saida or {}), "pergunta_id": str(pergunta_id)}
        await sessao.commit()
    if criada:
        await emitir(
            contexto,
            PerguntaEvento(
                pergunta_id=pergunta_id,
                texto=args.texto,
                opcoes=[OpcaoPergunta(**o) for o in opcoes],
                resposta_livre=args.resposta_livre,
            ),
        )
    resposta = interrupt({"tipo": "pergunta", "pergunta_id": str(pergunta_id)})
    return str(resposta)
