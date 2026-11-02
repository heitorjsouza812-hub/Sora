"""Vetorizador da memória: embeddings de 768 dimensões com o provedor do próprio usuário.

Sem provedor que sirva (ou com ``SORA_MODELO_FALSO``), devolve ``None`` e a memória busca por
palavras. A chave nunca sai do processo: é a mesma decifrada para as chamadas de modelo.
Provedores aceitos, na ordem: OpenAI (``text-embedding-3-small`` com ``dimensions=768``),
Gemini (``text-embedding-004``) e Ollama (``nomic-embed-text``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.memoria.servico import DIMENSOES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PRAZO_S = 15.0
MODELOS: dict[str, tuple[str, dict[str, Any]]] = {
    "openai": ("text-embedding-3-small", {"dimensions": DIMENSOES}),
    "gemini": ("gemini/text-embedding-004", {}),
    "ollama": ("ollama/nomic-embed-text", {}),
}


class VetorizadorLiteLLM:
    def __init__(self, modelo: str, parametros: dict[str, Any], extra: dict[str, Any]) -> None:
        self.modelo, self.parametros, self.extra = modelo, parametros, extra

    async def vetorizar(self, texto: str) -> list[float]:
        import litellm

        resposta = await litellm.aembedding(
            model=self.modelo,
            input=[texto[:8000]],
            timeout=PRAZO_S,
            **self.parametros,
            **self.extra,
        )
        vetor = [float(v) for v in resposta["data"][0]["embedding"]]
        if len(vetor) != DIMENSOES:
            raise ValueError(f"O embedding veio com {len(vetor)} dimensões, esperava {DIMENSOES}.")
        return vetor


async def vetorizador_do_usuario(
    sessao: AsyncSession, usuario_id: UUID
) -> VetorizadorLiteLLM | None:
    from sqlalchemy import select

    from app.llm.falso import modelo_falso_ativo
    from app.llm.provedores import parametros_litellm, politica_de_rede
    from app.modelos.tabelas import Provedor
    from app.seletor.repositorio import config_do_provedor

    if modelo_falso_ativo():
        return None
    provedores = (
        await sessao.scalars(
            select(Provedor).where(
                Provedor.usuario_id == usuario_id,
                Provedor.apagado_em.is_(None),
                Provedor.validado_em.is_not(None),
            )
        )
    ).all()
    por_tipo = {str(getattr(p.tipo, "value", p.tipo)): p for p in provedores}
    for tipo, (modelo, extra) in MODELOS.items():
        provedor = por_tipo.get(tipo)
        if provedor is None:
            continue
        try:
            config = await config_do_provedor(sessao, usuario_id, provedor.id)
            parametros = parametros_litellm(config, politica_de_rede())
        except Exception:
            continue
        return VetorizadorLiteLLM(modelo, parametros, extra)
    return None
