"""Modelos de um papel para o worker: seletor (§5) + chave do usuário (§8.1) + ``ChatLiteLLM``.

Com ``SORA_MODELO_FALSO=1`` (só desenvolvimento; barrado em produção) devolve o modelo falso do
papel. Sem ele, escolhe entre os modelos que o usuário conectou, na ordem do seletor (o 1º é o
principal, os demais são fallback). Sem nenhum modelo que sirva, ``SemModeloDisponivel``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.seletor.tipos import Capacidade, PapelModelo

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

# Nome do papel do agente (montagem) -> chave da política do seletor.
_PAPEL_DO_SELETOR = {"individual": "agente_individual"}


class SemModeloDisponivel(RuntimeError):
    """Nenhum modelo conectado serve para o papel (sem API, sem teto, sem capacidade)."""


async def modelos_do_papel(
    sessao: AsyncSession,
    usuario_id: UUID,
    papel: str,
    *,
    dificuldade: int = 2,
    precisa: Iterable[Capacidade] = (Capacidade.FERRAMENTAS,),
    tokens_prompt: int = 4_000,
    conversa_privada: bool = False,
    preferido: str | None = None,
    streaming: bool = False,
) -> list[BaseChatModel]:
    """Lista de ``BaseChatModel`` na ordem do seletor para o papel."""
    if modelo_falso_ativo():
        return [criar_modelo_falso(_PAPEL_DO_SELETOR.get(papel, papel))]

    from app.llm.fabrica import criar_modelos_na_ordem
    from app.seletor.repositorio import config_do_provedor, contexto_do_usuario
    from app.seletor.seletor import escolher_modelos

    nome = _PAPEL_DO_SELETOR.get(papel, papel)
    contexto = await contexto_do_usuario(sessao, usuario_id, conversa_privada=conversa_privada)
    resultado = escolher_modelos(
        contexto,
        PapelModelo(nome),
        dificuldade,
        set(precisa),
        tokens_prompt,
        preferido=preferido,
    )
    if not resultado.modelos:
        raise SemModeloDisponivel(f"Nenhum modelo conectado serve para o papel {nome}.")
    configs = {
        m.provedor.id: await config_do_provedor(sessao, usuario_id, m.provedor.id)
        for m in resultado.modelos
    }
    return criar_modelos_na_ordem(
        [(m.modelo, configs[m.provedor.id]) for m in resultado.modelos],
        papel=nome,
        streaming=streaming,
    )
