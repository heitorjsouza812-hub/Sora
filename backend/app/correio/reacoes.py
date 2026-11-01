"""Reações em mensagens (👍 ✅ 👀 …), do usuário e dos agentes.

Regras da Sora:

- só emojis de uma lista curta: reação é sinal rápido, não texto livre (e não dá para esconder
  instrução para o modelo num "emoji");
- cada autor tem no máximo uma reação de cada tipo por mensagem; reagir de novo **tira**;
- no máximo ``MAX_REACOES_POR_AUTOR`` reações diferentes do mesmo autor numa mensagem;
- reação de agente **não** inicia turno de ninguém e não conta salto: assim dois agentes não
  ficam reagindo um ao outro para sempre. Ela só aparece na interface e no histórico;
- a reação do usuário numa mensagem de agente vira uma linha curta no próximo turno daquele
  agente (``"O usuário reagiu com 👍 à sua mensagem de 14:02"``), como retorno leve.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta

EMOJIS_PERMITIDOS: dict[str, str] = {
    "👍": "concordo",
    "👎": "discordo",
    "✅": "feito",
    "👀": "vendo",
    "❤️": "adorei",
    "🎉": "comemorando",
    "🤔": "pensando",
    "❗": "importante",
    "🙏": "obrigado",
    "😂": "engraçado",
}
MAX_REACOES_POR_AUTOR = 3

TipoAutor = Literal["usuario", "agente"]


@dataclass(frozen=True, slots=True)
class Reacao:
    mensagem_id: UUID
    autor: TipoAutor
    agente_id: UUID | None
    emoji: str
    criada_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def chave(self) -> tuple[UUID, str, UUID | None, str]:
        return (self.mensagem_id, self.autor, self.agente_id, self.emoji)


def normalizar_emoji(emoji: str) -> str:
    bruto = emoji.strip()
    if bruto in EMOJIS_PERMITIDOS:
        return bruto
    # "❤" sem o seletor de variação vira "❤️"
    com_variacao = bruto + "️"
    if com_variacao in EMOJIS_PERMITIDOS:
        return com_variacao
    raise ErroFerramenta(
        "Essa reação não está disponível. Use uma destas: " + " ".join(EMOJIS_PERMITIDOS)
    )


class ReagirMensagem(BaseModel):
    """Reage a uma mensagem com um emoji. Reagir de novo com o mesmo emoji tira a reação."""

    mensagem_id: UUID = Field(description="Id da mensagem.")
    emoji: str = Field(description="Um dos emojis permitidos: " + " ".join(EMOJIS_PERMITIDOS))

    @field_validator("emoji")
    @classmethod
    def _emoji_valido(cls, valor: str) -> str:
        try:
            return normalizar_emoji(valor)
        except ErroFerramenta as erro:
            raise ValueError(str(erro)) from erro


class ArmazemReacoes(Protocol):
    async def da_mensagem(self, mensagem_id: UUID) -> list[Reacao]: ...
    async def adicionar(self, reacao: Reacao) -> None: ...
    async def remover(self, reacao: Reacao) -> None: ...


class ArmazemReacoesEmMemoria:
    def __init__(self) -> None:
        self._reacoes: dict[tuple[UUID, str, UUID | None, str], Reacao] = {}

    async def da_mensagem(self, mensagem_id: UUID) -> list[Reacao]:
        return sorted(
            (r for r in self._reacoes.values() if r.mensagem_id == mensagem_id),
            key=lambda r: r.criada_em,
        )

    async def adicionar(self, reacao: Reacao) -> None:
        self._reacoes[reacao.chave] = reacao

    async def remover(self, reacao: Reacao) -> None:
        self._reacoes.pop(reacao.chave, None)


@dataclass(frozen=True, slots=True)
class ResultadoReacao:
    reacao: Reacao
    ligada: bool
    """``True`` = acabou de entrar; ``False`` = foi tirada."""


async def alternar(
    armazem: ArmazemReacoes,
    *,
    mensagem_id: UUID,
    emoji: str,
    autor: TipoAutor,
    agente_id: UUID | None = None,
) -> ResultadoReacao:
    if (autor == "agente") != (agente_id is not None):
        raise ErroFerramenta("Reação de agente precisa do agente; a do usuário, não.")
    emoji = normalizar_emoji(emoji)
    nova = Reacao(mensagem_id, autor, agente_id, emoji)
    existentes = await armazem.da_mensagem(mensagem_id)
    for atual in existentes:
        if atual.chave == nova.chave:
            await armazem.remover(atual)
            return ResultadoReacao(atual, ligada=False)
    do_mesmo_autor = [r for r in existentes if (r.autor, r.agente_id) == (autor, agente_id)]
    if len(do_mesmo_autor) >= MAX_REACOES_POR_AUTOR:
        raise ErroFerramenta(
            f"Cada um pode deixar no máximo {MAX_REACOES_POR_AUTOR} reações na mesma mensagem."
        )
    await armazem.adicionar(nova)
    return ResultadoReacao(nova, ligada=True)


async def reagir_como_agente(
    armazem: ArmazemReacoes,
    args: ReagirMensagem,
    contexto: ContextoFerramenta,
    *,
    mensagens_visiveis: set[UUID],
) -> str:
    """A ferramenta ``reagir``: o agente só reage a mensagens que ele pode ver."""
    if args.mensagem_id not in mensagens_visiveis:
        raise ErroFerramenta("Você não pode reagir a essa mensagem.")
    resultado = await alternar(
        armazem,
        mensagem_id=args.mensagem_id,
        emoji=args.emoji,
        autor="agente",
        agente_id=contexto.agente_id,
    )
    acao = "Reação adicionada" if resultado.ligada else "Reação removida"
    return f"{acao}: {resultado.reacao.emoji}. Isso não avisa ninguém nem pede resposta."


def resumo(reacoes: Iterable[Reacao]) -> list[tuple[str, int]]:
    """``[(emoji, quantidade)]`` na ordem da primeira vez que cada emoji apareceu."""
    contagem: Counter[str] = Counter()
    ordem: list[str] = []
    for reacao in reacoes:
        if reacao.emoji not in contagem:
            ordem.append(reacao.emoji)
        contagem[reacao.emoji] += 1
    return [(emoji, contagem[emoji]) for emoji in ordem]


def aviso_para_o_agente(reacoes_do_usuario: Iterable[tuple[Reacao, str]]) -> str:
    """Linha curta com as reações novas do usuário às mensagens do agente.

    Recebe ``(reacao, rotulo_da_mensagem)``; o rótulo é algo como ``"de 14:02"``.
    """
    linhas = [
        f"- O usuário reagiu com {r.emoji} ({EMOJIS_PERMITIDOS[r.emoji]}) à sua mensagem {rotulo}."
        for r, rotulo in reacoes_do_usuario
        if r.autor == "usuario"
    ]
    return "\n".join(linhas)
