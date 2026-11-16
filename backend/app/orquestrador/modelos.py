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

    from app.preferencias_conversa import EscolhaModelo
    from app.seletor.tipos import ContextoSeletor, ModeloCandidato

# Nome do papel do agente (montagem) -> chave da política do seletor.
_PAPEL_DO_SELETOR = {"individual": "agente_individual"}


class SemModeloDisponivel(RuntimeError):
    """Nenhum modelo conectado serve para o papel (sem API, sem teto, sem capacidade)."""


def _candidato_escolhido(
    contexto: ContextoSeletor, escolha: EscolhaModelo, conversa_privada: bool
) -> ModeloCandidato:
    """O modelo que o usuário fixou no seletor do campo de mensagem. Sem troca automática: se ele
    sumiu ou passou do teto, ``ModeloEscolhidoIndisponivel`` com o aviso em PT-BR."""
    from app.modelos.enumeracoes import TipoProvedor
    from app.preferencias_conversa import SUGESTAO_DE_TROCA, ModeloEscolhidoIndisponivel

    candidato = next(
        (
            m
            for m in contexto.modelos
            if m.provedor.id == escolha.provedor_id and m.modelo == escolha.modelo
        ),
        None,
    )
    motivo = None
    if candidato is None:
        motivo = "o provedor ou o modelo não está mais conectado"
    elif not candidato.ativo:
        motivo = "o modelo foi desligado em Configurações → Modelos de IA"
    elif candidato.provedor.passou_do_teto():
        motivo = "o provedor chegou ao teto de gasto do mês"
    elif conversa_privada and candidato.provedor.tipo is not TipoProvedor.OLLAMA:
        motivo = "conversa privada só usa modelo local (Ollama)"
    if motivo is not None or candidato is None:
        raise ModeloEscolhidoIndisponivel(
            f"O modelo {escolha.modelo}, escolhido para esta conversa, não está disponível: "
            f"{motivo}. {SUGESTAO_DE_TROCA}"
        )
    return candidato


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
    escolha: EscolhaModelo | None = None,
) -> list[BaseChatModel]:
    """Lista de ``BaseChatModel`` na ordem do seletor para o papel.

    ``escolha`` é o seletor do campo de mensagem (``app/preferencias_conversa.py``): com modelo
    fixo, a lista tem só ele (sem reservas: o worker não troca sozinho) e vem marcada para o aviso
    de falha; no automático vale o seletor de sempre. O nível de raciocínio entra nos dois casos
    (no automático, o nível aceito mais próximo de cada modelo).
    """
    if modelo_falso_ativo():
        return [criar_modelo_falso(_PAPEL_DO_SELETOR.get(papel, papel))]

    from app.llm.fabrica import criar_modelos_na_ordem
    from app.llm.raciocinio import nivel_mais_proximo
    from app.seletor.repositorio import config_do_provedor, contexto_do_usuario
    from app.seletor.seletor import escolher_modelos

    nome = _PAPEL_DO_SELETOR.get(papel, papel)
    contexto = await contexto_do_usuario(sessao, usuario_id, conversa_privada=conversa_privada)
    fixo = escolha is not None and escolha.modelo_fixo
    if fixo:
        assert escolha is not None
        selecionados = [_candidato_escolhido(contexto, escolha, conversa_privada)]
    else:
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
        selecionados = resultado.modelos
    configs = {
        m.provedor.id: await config_do_provedor(sessao, usuario_id, m.provedor.id)
        for m in selecionados
    }
    nivel = escolha.raciocinio if escolha is not None else None
    chats = criar_modelos_na_ordem(
        [(m.modelo, configs[m.provedor.id]) for m in selecionados],
        papel=nome,
        streaming=streaming,
        raciocinios=[nivel_mais_proximo(m.modelo, nivel) if nivel else None for m in selecionados],
    )
    from app.agentes.middleware.custo import marcar_custo

    for chat, candidato in zip(chats, selecionados, strict=True):
        marcar_custo(
            chat,
            modelo=candidato.modelo,
            provedor_id=candidato.provedor.id,
            nivel=str(candidato.nivel),
            papel=nome,
            preco_entrada=candidato.preco_entrada,
            preco_saida=candidato.preco_saida,
        )
    if fixo:
        from app.preferencias_conversa import marcar_escolhido

        escolhido = selecionados[0]
        marcar_escolhido(chats[0], escolhido.modelo, [str(c) for c in escolhido.capacidades])
    return chats
