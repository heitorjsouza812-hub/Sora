"""Jobs da cadeia (especificação §6, tabela "Os jobs", e §6.1, "Como uma etapa roda").

Todo job recebe o ``ctx`` do ARQ como primeiro argumento. Todo job começa
pegando o trabalho com ``UPDATE ... WHERE status = ... RETURNING`` (sem
trabalho em dobro) e termina chamando ``avancar_cadeia`` quando muda o
estado da cadeia.
"""

from __future__ import annotations

from typing import Any


async def planejar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Chama o planejador (N3), grava o plano, cria as etapas e um especialista
    por papel; emite ``agente.criado`` e ``cadeia.criada``. Quem põe na fila: a API."""
    raise NotImplementedError


async def avancar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Enfileira as etapas que já podem rodar (até 3 em paralelo) ou manda para
    verificação. Quem põe na fila: todo job que termina."""
    raise NotImplementedError


async def executar_etapa(ctx: dict[str, Any], etapa_id: str, resposta: Any | None = None) -> None:
    """Roda o especialista até ``entregar`` (ou retoma depois de uma pergunta ou
    aprovação, com ``resposta``). Prazo de 5 minutos. Quem põe na fila:
    ``avancar_cadeia`` e a API (retomada)."""
    raise NotImplementedError


async def verificar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Roda o Verificador sobre o resultado e aplica a regra de reprovação.
    Quem põe na fila: ``avancar_cadeia``, quando todas as etapas terminam."""
    raise NotImplementedError


async def entregar_resultado(ctx: dict[str, Any], cadeia_id: str) -> None:
    """A Sora escreve a resposta final com a voz dela; a cadeia fica ``concluida``.
    Quem põe na fila: ``verificar_cadeia``, quando aprova."""
    raise NotImplementedError


async def ajustar(
    ctx: dict[str, Any], conversa_id: str, texto: str, agente_id: str | None = None
) -> None:
    """Cria a cadeia ``versao + 1`` só com o especialista certo e o Verificador.
    Quem põe na fila: a API, em ``POST /ajuste``."""
    raise NotImplementedError
