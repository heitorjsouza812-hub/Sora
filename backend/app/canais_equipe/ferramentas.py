"""Ferramentas dos agentes dentro de uma tarefa de canal.

O worker preenche o canal, a tarefa e a revisão; o modelo só escolhe o colega e escreve o
texto. Assim um agente não consegue mexer em tarefa de outro canal nem numa revisão velha.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.canais_equipe.modelos import MAX_TEXTO_MENSAGEM


class CanalHistorico(BaseModel):
    """Lê mensagens mais antigas do canal (o pacote só traz as recentes)."""

    antes_de_seq: int | None = Field(
        default=None, ge=1, description="Lê as mensagens anteriores a esta posição."
    )
    limite: int = Field(default=20, ge=1, le=50)


class CanalDelegar(BaseModel):
    """Passa uma parte da sua tarefa para outro membro. Você recebe o resultado depois."""

    agente_id: UUID = Field(description="Id do membro (da lista de membros do canal).")
    instrucao: str = Field(min_length=1, max_length=4_000)


class CanalTransferir(BaseModel):
    """Passa a tarefa inteira para outro membro mais indicado. Seu turno acaba aqui."""

    agente_id: UUID
    nota: str = Field(default="", max_length=1_000)


class CanalResultado(BaseModel):
    """Entrega o resultado da sua tarefa no canal. Use quando terminar."""

    texto: str = Field(min_length=1, max_length=MAX_TEXTO_MENSAGEM)


FERRAMENTAS_DO_CANAL: dict[str, type[BaseModel]] = {
    "canal_historico": CanalHistorico,
    "canal_delegar": CanalDelegar,
    "canal_transferir": CanalTransferir,
    "canal_resultado": CanalResultado,
}

INSTRUCOES_DO_CANAL = (
    "Você está trabalhando num canal com outros agentes e o usuário. Todos veem o que você "
    "escreve. Responda só sobre a sua tarefa; não narre preparação. Se uma parte é da área de "
    "outro membro, delegue com canal_delegar em vez de fazer mal. Nunca devolva a tarefa para "
    "quem te passou. Se estiver bloqueado, diga o que tentou e a única ação que desbloqueia."
)
