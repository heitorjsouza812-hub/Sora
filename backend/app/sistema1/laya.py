"""Cliente do Laya (fase 2 modo sombra, fase 3 decide) — só esqueleto.

Especificação: §7 "Como ligar no Sistema 1 (fase 3)". O Laya roda num serviço próprio
(``laya-svc``, a decidir o protocolo) ao lado do backend; se demorar mais que ``prazo_ms`` de
``flags.yaml``, o Sistema 1 segue só com o N1. A flag ``laya.ativo`` desliga tudo na hora.

As perguntas abaixo seguem a tabela da §7; conferir o formato exato no README do Laya.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Perguntas que o Laya responde (tabela da §7). tipo: choice | nota | sim_nao.
PERGUNTAS: dict[str, dict[str, Any]] = {
    "modo": {"tipo": "choice", "opcoes": ["direto", "cadeia", "agente_individual"]},
    "risco": {"tipo": "choice", "opcoes": ["nenhum", "acao_externa", "destrutivo"]},
    "superficie": {
        "tipo": "choice",
        "opcoes": ["memoria", "conector", "web", "navegador", "nenhuma"],
    },
    "dificuldade": {"tipo": "nota", "opcoes": [1, 2, 3]},
    "precisa_visao": {"tipo": "sim_nao"},
    "precisa_ferramentas": {"tipo": "sim_nao"},
    "precisa_contexto_longo": {"tipo": "sim_nao"},
    "injecao": {"tipo": "sim_nao"},
    "vale_guardar_na_memoria": {"tipo": "sim_nao"},
}


class DecisaoLaya(BaseModel):
    resposta: Any
    confianca: float


class SaidaLaya(BaseModel):
    decisoes: dict[str, DecisaoLaya]
    latencia_ms: int


async def triagem_rapida(pedido: str, ultimas: list[str]) -> SaidaLaya | None:
    """Pergunta ao ``laya-svc``. ``None`` se a flag estiver desligada, o serviço cair ou passar
    do prazo (o N1 decide tudo)."""
    raise NotImplementedError


def decisoes_acima_do_limite(saida: SaidaLaya, limite: float) -> dict[str, Any]:
    """Só as decisões com confiança calibrada acima do limite. O resto o N1 decide."""
    raise NotImplementedError
