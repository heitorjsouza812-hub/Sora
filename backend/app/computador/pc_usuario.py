"""Alvo ``pc_usuario`` (C3): o PC do próprio usuário, só pelo app de desktop.

Ainda não existe: este arquivo fixa a interface para o C3 e recusa tudo. Como o C3 deve se
encaixar está em ``docs/computador-por-bot.md`` ("C3: controle do PC do usuário"):

- a execução mora numa **ponte local no Tauri** (Rust, UI Automation do Windows), nunca no
  servidor; o servidor só pede ações e recebe observações pela conexão do app;
- **um bot por vez** (vez/fila), desligado por padrão e ligado por bot em Configurações;
- borda acesa enquanto controla, **Parar** sempre visível, mexer no mouse pausa;
- primeira ação em cada programa vira cartão "Precisa de você";
- nunca digita em campo de senha (``IsPassword`` da UI Automation) nem mostra senha na árvore.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.computador.interface import (
    AcaoResolvida,
    Alvo,
    ArquivoArea,
    Observacao,
)
from app.ferramentas.base import ErroFerramenta

RECUSA = (
    "O controle do seu computador ainda não está disponível. Use o computador virtual do bot "
    "(alvo virtual)."
)


@dataclass(slots=True)
class ComputadorPcUsuario:
    """Stub do C3: mesma interface do virtual, sempre recusa."""

    usuario_id: UUID
    agente_id: UUID
    alvo: Alvo = Alvo.PC_USUARIO

    async def observar(self) -> Observacao:
        raise ErroFerramenta(RECUSA)

    async def agir(self, acao: AcaoResolvida) -> None:
        raise ErroFerramenta(RECUSA)

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        raise ErroFerramenta(RECUSA)

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        raise ErroFerramenta(RECUSA)

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        raise ErroFerramenta(RECUSA)


@dataclass(slots=True)
class ProvedorPcUsuario:
    """O C3 troca isto por um provedor que fala com a ponte do app de desktop conectado."""

    async def obter(self, usuario_id: UUID, agente_id: UUID) -> ComputadorPcUsuario:
        raise ErroFerramenta(RECUSA)

    async def desligar(self, agente_id: UUID) -> bool:
        return False
