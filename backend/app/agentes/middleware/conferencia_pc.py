"""Bot com o computador do usuário: não diz que fez sem conferir e solta o PC no fim (Vela-12).

- ``falar`` e a resposta final em texto passam por ``app/computador/conferencia.py``: se a
  mensagem afirma ter feito algo no computador e nenhuma ação do turno foi conferida na tela,
  ela vira o aviso "Não consegui confirmar que fiz isso…".
- No fim do turno (resposta final, sem ferramenta pendente), o bot que usou o PC do usuário
  devolve a vez e manda a ponte apagar a borda. Antes a borda ficava acesa até 90 s depois do
  turno e qualquer movimento do mouse abria um cartão "Retomar?" de um bot que já tinha
  terminado: o "Permitir" não tinha o que retomar.

Só entra para bots com ``computador_agir`` (``montagem.py``).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from app.computador.conferencia import acoes_do_turno, precisa_de_aviso, texto_com_aviso

registro = logging.getLogger(__name__)


def _texto(mensagem: AIMessage) -> str:
    conteudo = mensagem.content
    if isinstance(conteudo, str):
        return conteudo
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in conteudo or [])


class MiddlewareConferenciaPc(AgentMiddleware):
    def __init__(self, usuario_id: UUID, agente_id: UUID) -> None:
        super().__init__()
        self.usuario_id = usuario_id
        self.agente_id = agente_id

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        if request.tool_call.get("name") == "falar":
            args = dict(request.tool_call.get("args") or {})
            texto = str(args.get("texto") or "")
            mensagens = list((getattr(request, "state", None) or {}).get("messages") or [])
            acoes = acoes_do_turno(mensagens)
            if texto and precisa_de_aviso(texto, acoes):
                args["texto"] = texto_com_aviso(texto, acoes)
                request.tool_call["args"] = args
        return await handler(request)

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        mensagens = list(state.get("messages") or [])
        if not mensagens or not isinstance(mensagens[-1], AIMessage):
            return None
        final = mensagens[-1]
        if final.tool_calls:
            return None
        texto = _texto(final)
        acoes = acoes_do_turno(mensagens)
        if texto and precisa_de_aviso(texto, acoes):
            return {"messages": [AIMessage(content=texto_com_aviso(texto, acoes), id=final.id)]}
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        if acoes_do_turno(list(state.get("messages") or [])).tentativas or _usou_o_pc(state):
            await soltar_o_pc(self.usuario_id, self.agente_id)
        return None


def _usou_o_pc(state: Any) -> bool:
    for mensagem in reversed(list(state.get("messages") or [])):
        if getattr(mensagem, "type", "") == "human":
            return False
        for chamada in getattr(mensagem, "tool_calls", None) or []:
            if (chamada.get("args") or {}).get("alvo") == "pc_usuario":
                return True
    return False


async def soltar_o_pc(usuario_id: UUID, agente_id: UUID) -> None:
    """Fim do turno: devolve a vez (se for deste bot) e apaga a borda na ponte. Melhor esforço."""
    from app.computador.pc_usuario_canal import AgentePc, CanalPc
    from app.ferramentas.ambiente import redis_dos_eventos

    try:
        canal = CanalPc(redis_dos_eventos())
        dono = await canal.quem_tem_a_vez(usuario_id)
        if dono and dono.get("agente_id") != str(agente_id):
            return  # outro bot está usando: não mexer
        await canal.soltar_vez(usuario_id, agente_id)
        sessao = await canal.sessao(usuario_id)
        if sessao is not None:
            await canal.enviar(
                usuario_id,
                str(sessao["sessao_id"]),
                AgentePc(id=agente_id, nome="", cor=""),
                "encerrar",
                {},
                15.0,
                esperar=False,
            )
    except Exception:  # nunca derruba a resposta do bot
        registro.warning("não consegui soltar o PC no fim do turno", exc_info=True)
