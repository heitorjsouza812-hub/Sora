"""Medidor de contexto e compactação automática antes de cada chamada do modelo (Âncora).

- depois de cada resposta do modelo, mede pelo uso que o provedor informou (ou estima) e emite
  ``contexto.atualizado``;
- antes da chamada seguinte, se o histórico passou de 80% da janela, resume as mensagens mais
  antigas (``app/contexto/compactador.py``) e troca por um resumo no estado do agente.

Falha de resumo nunca derruba o turno: o medidor marca ``falhou`` e o agente segue com o
histórico inteiro (o provedor decide se aceita).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from app.contexto import (
    SituacaoCompactacao,
    decidir_antes_do_turno,
    medir,
)
from app.contexto.compactador import (
    atualizacao_do_estado,
    planejar,
    tokens_do_historico,
)
from app.contexto.porta import PortaContexto, janela_do_modelo

registro = logging.getLogger(__name__)


def _modelo_da_resposta(mensagem: AIMessage) -> str | None:
    meta = mensagem.response_metadata or {}
    nome = meta.get("model_name") or meta.get("model")
    return str(nome) if nome else None


class MiddlewareContexto(AgentMiddleware):
    def __init__(self, porta: PortaContexto) -> None:
        self.porta = porta
        self._modelo: str | None = None

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        mensagens = state["messages"]
        ultima = mensagens[-1] if mensagens else None
        informado = None
        if isinstance(ultima, AIMessage):
            self._modelo = _modelo_da_resposta(ultima) or self._modelo
            uso = ultima.usage_metadata or {}
            informado = uso.get("input_tokens") if uso.get("input_tokens") else None
        try:
            if informado is not None:
                await self.porta.registrar(
                    modelo=self._modelo, tokens_informados=informado, textos=[]
                )
            else:
                # Sem uso informado pelo provedor: estima pelos caracteres (1 token ≈ 4).
                texto = "x" * (tokens_do_historico(mensagens) * 4)
                await self.porta.registrar(
                    modelo=self._modelo, tokens_informados=None, textos=[texto]
                )
        except Exception:
            registro.warning("não consegui registrar o medidor de contexto", exc_info=True)
        return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        mensagens = list(state["messages"])
        janela = janela_do_modelo(self._modelo)
        estado = medir(
            self.porta.agente_id,
            self.porta.fio,
            janela=janela,
            tokens_informados=tokens_do_historico(mensagens),
        )
        if decidir_antes_do_turno(estado).decisao != "compactar_antes":
            return None
        try:
            plano = await planejar(mensagens, estado.janela, self.porta.resumir)
        except Exception:
            registro.warning("a compactação do contexto falhou", exc_info=True)
            await self._publicar(replace(estado, compactacao=SituacaoCompactacao.FALHOU), True)
            return None
        if plano is None:
            return None
        await self._publicar(replace(estado, compactacao=SituacaoCompactacao.COMPACTANDO), False)
        depois = medir(
            self.porta.agente_id,
            self.porta.fio,
            janela=estado.janela,
            tokens_informados=plano.tokens_depois,
        )
        await self._publicar(depois, True)
        return {"messages": atualizacao_do_estado(plano)}

    async def _publicar(self, estado: Any, fim: bool) -> None:
        from app.contexto.estado import registrar_e_publicar

        await registrar_e_publicar(
            self.porta.redis,
            estado,
            usuario_id=self.porta.usuario_id,
            conversa_id=self.porta.conversa_id,
            fim_da_compactacao=fim,
        )
