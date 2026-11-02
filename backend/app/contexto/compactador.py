"""Compactação do histórico do agente sobre as mensagens do próprio turno (Âncora, etapa 4).

Junta duas peças já escritas: o monitor de ``app/contexto`` (quando e quantas mensagens
liberar) e o resumo cumulativo de ``app/memoria/compactacao.py`` (prompt, limites, escape).
Aqui elas agem nas mensagens do LangGraph (o histórico que o modelo realmente recebe):

- as mensagens mais antigas viram **um** resumo, marcado como dado e não como instrução;
- o corte nunca separa uma chamada de ferramenta do resultado dela;
- o resumo anterior (se houver) entra no prompt e é substituído pelo novo, então ele é
  cumulativo e o histórico nunca ganha buraco.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately

from app.contexto import MIN_MENSAGENS_NA_JANELA, mensagens_para_liberar
from app.memoria.compactacao import (
    MensagemHistorico,
    formatar_resumo,
    resumir_lote,
)

MARCA_DO_RESUMO = "sora_resumo"
MAX_CARACTERES_RESULTADO = 600

Resumir = Callable[[str, float], Awaitable[str]]


def eh_resumo(mensagem: BaseMessage) -> bool:
    return bool(mensagem.additional_kwargs.get(MARCA_DO_RESUMO))


def _texto(mensagem: BaseMessage) -> str:
    conteudo = mensagem.content
    if isinstance(conteudo, list):
        conteudo = " ".join(
            str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in conteudo
        )
    return str(conteudo or "")


def tokens_da_mensagem(mensagem: BaseMessage) -> int:
    return count_tokens_approximately([mensagem])


def tokens_do_historico(mensagens: Sequence[BaseMessage]) -> int:
    return count_tokens_approximately(list(mensagens))


def _para_historico(mensagens: Sequence[BaseMessage]) -> list[MensagemHistorico]:
    saida: list[MensagemHistorico] = []
    for posicao, mensagem in enumerate(mensagens):
        texto = _texto(mensagem)
        if isinstance(mensagem, HumanMessage):
            autor = "usuario"
        elif isinstance(mensagem, ToolMessage):
            autor = "sistema"
            texto = (
                f"[resultado de {mensagem.name or 'ferramenta'}] {texto[:MAX_CARACTERES_RESULTADO]}"
            )
        elif isinstance(mensagem, AIMessage):
            autor = "sora"
            for chamada in mensagem.tool_calls:
                texto += f"\n[chamou {chamada.get('name')}]"
        else:
            autor = "sistema"
        if texto.strip():
            saida.append(MensagemHistorico(seq=posicao, autor=autor, conteudo=texto))  # type: ignore[arg-type]
    return saida


@dataclass(frozen=True, slots=True)
class PlanoDeCompactacao:
    remover: list[BaseMessage]
    resumo: HumanMessage
    tokens_depois: int


def onde_cortar(mensagens: Sequence[BaseMessage], janela: int) -> int:
    """Quantas mensagens do começo resumir para o uso cair até a meta (0 = nada a fazer).

    Avança o corte até uma mensagem que não seja resultado de ferramenta, para o resultado
    ficar sempre junto da chamada que o pediu.
    """
    if len(mensagens) <= MIN_MENSAGENS_NA_JANELA:
        return 0
    n = mensagens_para_liberar([tokens_da_mensagem(m) for m in mensagens], janela)
    n = max(n, 1) if len(mensagens) > MIN_MENSAGENS_NA_JANELA else n
    while 0 < n < len(mensagens) and isinstance(mensagens[n], ToolMessage):
        n += 1
    return n if n < len(mensagens) else 0


async def planejar(
    mensagens: Sequence[BaseMessage], janela: int, resumir: Resumir
) -> PlanoDeCompactacao | None:
    """Resume o começo do histórico. ``None`` quando não há o que compactar."""
    n = onde_cortar(mensagens, janela)
    if n <= 0:
        return None
    antigas = list(mensagens[:n])
    anterior = None
    if antigas and eh_resumo(antigas[0]):
        anterior = _texto(antigas[0])
        anterior = anterior.split("<resumo_da_conversa>\n", 1)[-1].rsplit(
            "\n</resumo_da_conversa>", 1
        )[0]
        antigas = antigas[1:]
    lote = _para_historico(antigas)
    if not lote:
        return None
    texto, cursor = await resumir_lote(resumir, anterior, lote)
    resumo = HumanMessage(
        content=formatar_resumo(texto, cursor), additional_kwargs={MARCA_DO_RESUMO: True}
    )
    restantes = list(mensagens[n:])
    return PlanoDeCompactacao(
        remover=list(mensagens[:n]),
        resumo=resumo,
        tokens_depois=tokens_do_historico([resumo, *restantes]),
    )


def atualizacao_do_estado(plano: PlanoDeCompactacao) -> list[BaseMessage]:
    """Valor de ``messages`` para devolver ao grafo: remove as antigas e põe o resumo no topo.

    ``add_messages`` junta no fim; por isso o resumo recebe o id da primeira mensagem removida
    (substituição no lugar) e as outras antigas são removidas por id.
    """
    primeira = plano.remover[0]
    resumo = plano.resumo.model_copy(update={"id": primeira.id})
    outras = [RemoveMessage(id=m.id) for m in plano.remover[1:] if m.id]
    return [resumo, *outras]
