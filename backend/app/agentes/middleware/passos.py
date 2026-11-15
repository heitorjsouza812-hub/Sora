"""Porta do middleware para registrar os passos do painel Trabalho."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langgraph.errors import GraphBubbleUp

registro = logging.getLogger(__name__)

PAUSADO_PARA_APROVACAO = "Aguardando a sua resposta."


def desembrulhar_catalogo(chamada: dict[str, Any]) -> dict[str, Any]:
    """``navegador_executar_ferramenta(id="navegador_capturar", argumentos={...})`` vira, no
    painel Trabalho, o passo ``navegador_capturar`` com os argumentos de verdade. Assim o painel
    e o Verificador veem o que foi feito, não a meta-ferramenta do catálogo sob demanda."""
    nome = str(chamada.get("name") or "")
    args = chamada.get("args")
    if nome.endswith("_executar_ferramenta") and isinstance(args, dict) and args.get("id"):
        interno = args.get("argumentos")
        return {
            **chamada,
            "name": str(args["id"]),
            "args": interno if isinstance(interno, dict) else {},
        }
    return chamada


IniciarPasso = Callable[[UUID, UUID, dict[str, Any]], Awaitable[Any]]
FinalizarPasso = Callable[[Any, Any | None, BaseException | None], Awaitable[None]]
AnunciarPrompt = Callable[[UUID, UUID, str], Awaitable[None]]

PASSOS_DA_CONVERSA_IGNORADOS = frozenset(
    {"falar", "perguntar", "conectores_buscar_ferramentas", "conectores_carregar_ferramenta"}
)
"""Na conversa direta o painel mostra o trabalho, não a fala: responder, perguntar e folhear o
catálogo de ferramentas não são passos."""


def id_do_turno(contexto: Any) -> UUID:
    """Id sintético do turno na conversa direta: o mesmo na retomada do mesmo pedido (a thread do
    pedido), outro a cada turno novo. O app aceita qualquer ``etapa_id`` e agrupa por ele."""
    from uuid import NAMESPACE_URL, uuid4, uuid5

    if getattr(contexto, "thread_proprio", None):
        return uuid5(NAMESPACE_URL, f"sora:turno:{contexto.thread_proprio}")
    return uuid4()


def _texto_da_mensagem(mensagem: Any) -> str:
    conteudo = getattr(mensagem, "content", "")
    if isinstance(conteudo, list):
        return " ".join(
            str(parte.get("text", "")) for parte in conteudo if isinstance(parte, dict)
        ).strip()
    return str(conteudo).strip()


class MiddlewarePassos(AgentMiddleware):
    def __init__(
        self,
        etapa_id: UUID,
        agente_id: UUID,
        *,
        iniciar: IniciarPasso,
        finalizar: FinalizarPasso,
        anunciar_prompt: AnunciarPrompt | None = None,
        ignorar: frozenset[str] = frozenset(),
    ) -> None:
        self.etapa_id = etapa_id
        self.agente_id = agente_id
        self._iniciar = iniciar
        self._finalizar = finalizar
        self._anunciar_prompt = anunciar_prompt
        self._ignorar = ignorar

    async def abefore_agent(self, state: Any, runtime: Any) -> None:
        """Conversa direta: o pedido que o agente acabou de receber vira o passo ``prompt``."""
        if self._anunciar_prompt is None:
            return None
        from langchain_core.messages import HumanMessage

        pedido = next(
            (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None
        )
        texto = _texto_da_mensagem(pedido) if pedido is not None else ""
        if texto:
            try:
                await self._anunciar_prompt(self.etapa_id, self.agente_id, texto[:2000])
            except Exception:  # o painel é só de leitura: nunca derruba o turno
                registro.warning("não consegui publicar o prompt no painel", exc_info=True)
        return None

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        chamada = desembrulhar_catalogo(dict(request.tool_call))
        if str(chamada.get("name") or "") in self._ignorar:
            return await handler(request)
        passo = await self._iniciar(self.etapa_id, self.agente_id, chamada)
        try:
            resultado = await handler(request)
        except GraphBubbleUp:
            # Pausa legítima (cartão de aprovação, pergunta): não é falha da ferramenta. O passo
            # fecha como "aguardando a aprovação" e, na retomada, a ferramenta ganha outro passo.
            await self._finalizar(passo, PAUSADO_PARA_APROVACAO, None)
            raise
        except BaseException as erro:
            await self._finalizar(passo, None, erro)
            raise
        await self._finalizar(passo, resultado, None)
        return resultado
