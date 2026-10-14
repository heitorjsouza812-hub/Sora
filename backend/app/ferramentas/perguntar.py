"""Ferramenta ``perguntar`` (especificação §4; pausa por interrupção do LangGraph
em §6.1). Vira um cartão de pergunta no app (evento ``pergunta``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class Opcao(BaseModel):
    rotulo: str = Field(max_length=40)
    valor: str = Field(description="O que volta para a Sora, escrito como o usuário responderia")


class Perguntar(BaseModel):
    """Pergunta ao usuário com opções clicáveis.
    Use só para ação irreversível ou ambiguidade real."""

    texto: str = Field(max_length=200)
    opcoes: list[Opcao] = Field(min_length=2, max_length=4)
    resposta_livre: bool = False


async def perguntar(args: Perguntar, contexto: ContextoFerramenta) -> str:
    """Grava a pergunta, emite ``pergunta`` e interrompe até a resposta do usuário."""
    raise NotImplementedError
