"""Porta do medidor de contexto para o middleware do agente (Âncora, etapa 4).

O middleware não conhece Redis nem modelos: ele chama esta porta, que o worker monta com
``fabricar_porta`` (uma linha em ``workers/portas.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.contexto import EstadoContexto, medir

registro = logging.getLogger(__name__)

PRAZO_PADRAO_S = 120.0


def janela_do_modelo(nome: str | None) -> int | None:
    """Tamanho da janela pelo catálogo do seletor (``None`` = desconhecido)."""
    if not nome:
        return None
    try:
        from app.seletor.catalogo import obter_catalogo

        entrada = obter_catalogo().buscar(nome)
    except Exception:
        return None
    if entrada is None:
        return None
    valor = getattr(entrada, "contexto", None)
    return valor if isinstance(valor, int) and valor > 0 else None


@dataclass(slots=True)
class PortaContexto:
    redis: Any
    usuario_id: UUID
    conversa_id: UUID
    agente_id: UUID
    fio: str = "principal"
    papel_do_resumo: str = "memoria_sintese"

    async def registrar(
        self,
        *,
        modelo: str | None,
        tokens_informados: int | None,
        textos: list[str],
        fim_da_compactacao: bool = False,
    ) -> EstadoContexto:
        from app.contexto.estado import registrar_e_publicar

        estado = medir(
            self.agente_id,
            self.fio,
            janela=janela_do_modelo(modelo),
            tokens_informados=tokens_informados,
            textos_do_historico=textos,
        )
        return await registrar_e_publicar(
            self.redis,
            estado,
            usuario_id=self.usuario_id,
            conversa_id=self.conversa_id,
            fim_da_compactacao=fim_da_compactacao,
        )

    async def resumir(self, prompt: str, prazo_s: float) -> str:
        """Resumo no modelo barato do usuário (papel ``memoria_sintese``)."""
        import asyncio

        from langchain_core.messages import HumanMessage

        from app.ferramentas.infra import abrir_sessao
        from app.orquestrador.modelos import modelos_do_papel

        async with abrir_sessao() as sessao:
            modelos = await modelos_do_papel(
                sessao, self.usuario_id, self.papel_do_resumo, dificuldade=1
            )
        resposta = await asyncio.wait_for(modelos[0].ainvoke([HumanMessage(prompt)]), prazo_s)
        conteudo = resposta.content
        return conteudo if isinstance(conteudo, str) else str(conteudo)
