"""Rotas dos cartões de aprovação; especificação §§2 e 6.1."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.atencao import publicar_estado_atencao
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.streams import publicar_evento
from app.eventos.tipos import AprovacaoResolvida
from app.modelos.enumeracoes import DecisaoAprovacao, StatusAprovacao
from app.modelos.esquemas import DecisaoAprovacaoEntrada
from app.modelos.tabelas import Aprovacao, Cadeia, Conversa, Etapa, RegraPermissao
from app.revisor.decisoes import SO_UMA_VEZ, aceita_sempre, condicao_da_regra

roteador = APIRouter(
    prefix="/aprovacoes", tags=["aprovacoes"], dependencies=[Depends(usuario_atual)]
)

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]


def obter_fila(redis: RedisDep) -> ArqRedis:
    """Mesmo adaptador de ``api/conversas``: reaproveita o pool Redis da API."""
    return ArqRedis(redis.connection_pool)


Fila = Annotated[ArqRedis, Depends(obter_fila)]

SOB_CONTROLE = (
    "Um bot está usando o seu computador agora. "
    "Pause ou pare o controle antes de decidir este pedido."
)


async def _conferir_quem_decide(redis: Redis, usuario_id: UUID) -> None:
    """Com a vez ativa, nenhuma sessão da conta decide cartões (Cerca A2)."""
    from app.computador.pc_usuario_canal import CanalPc

    if await CanalPc(redis).bot_no_controle(usuario_id):
        raise HTTPException(status.HTTP_409_CONFLICT, SOB_CONTROLE)


@roteador.post("/{aprovacao_id}/decidir", status_code=status.HTTP_204_NO_CONTENT)
async def decidir_aprovacao(
    aprovacao_id: UUID,
    dados: DecisaoAprovacaoEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    fila: Fila,
) -> None:
    """Registra a decisão e retoma a etapa interrompida.

    ``sempre_permitir`` também grava uma ``regras_permissao`` para o agente e a condição de
    ``revisor/decisoes.py``; fora dela, 422 e o cartão segue pendente. Enquanto um bot desta
    conta controla o PC do usuário, nenhuma sessão decide: primeiro pause ou pare o controle.
    """
    aprovacao = await sessao.scalar(
        select(Aprovacao)
        .where(Aprovacao.id == aprovacao_id, Aprovacao.usuario_id == usuario_id)
        .with_for_update()
    )
    if aprovacao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aprovação não encontrada.")
    agora = datetime.now(UTC)
    if aprovacao.status != StatusAprovacao.PENDENTE or aprovacao.expira_em <= agora:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido não está mais pendente.")

    await _conferir_quem_decide(redis, usuario_id)
    # Regra única (``revisor/decisoes.py``): instruções, envio externo, domínio novo, retomar o
    # PC e o PC do usuário sem programa só aceitam "uma vez"; ferramenta genérica sem condição
    # também. Recusar antes de mudar qualquer coisa: o cartão continua pendente.
    condicao = condicao_da_regra(aprovacao.acao)
    decisao = dados.decisao
    if decisao == DecisaoAprovacao.SEMPRE_PERMITIR and not aceita_sempre(
        aprovacao.acao, aprovacao.agente_id
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, SO_UMA_VEZ)
    sempre = decisao == DecisaoAprovacao.SEMPRE_PERMITIR

    negada = decisao == DecisaoAprovacao.NEGAR
    aprovacao.status = StatusAprovacao.NEGADA if negada else StatusAprovacao.PERMITIDA
    aprovacao.decidida_em = agora
    sugestao_de_melhoria = (
        isinstance(aprovacao.acao, dict) and aprovacao.acao.get("tipo") == "sugestao_melhoria"
    )
    if sempre and condicao is not None:
        sessao.add(
            RegraPermissao(
                usuario_id=usuario_id,
                agente_id=aprovacao.agente_id,
                ferramenta=str(aprovacao.acao["ferramenta"]),
                condicao=condicao,
            )
        )
    if (
        not negada
        and isinstance(aprovacao.acao, dict)
        and aprovacao.acao.get("tipo") == "aprovar_dominio"
    ):
        from app.navegador.repositorio import aprovar_dominio_no_perfil

        try:
            await aprovar_dominio_no_perfil(
                sessao,
                particao=str(aprovacao.acao["particao"]),
                usuario_id=usuario_id,
                dominio=str(aprovacao.acao["dominio"]),
            )
        except (KeyError, TypeError, ValueError) as erro:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "O perfil desta aprovação não está mais disponível.",
            ) from erro
    if sugestao_de_melhoria:
        # Ponte: Aplicar muda o bot, Descartar não; tudo na mesma transação do cartão.
        from app.canais_empresa.sugestoes import ErroSugestao, resolver_pela_aprovacao

        try:
            await resolver_pela_aprovacao(sessao, usuario_id, aprovacao, aplicar=not negada)
        except ErroSugestao as erro:
            raise HTTPException(erro.status, erro.mensagem) from erro
    conversa_id = None
    if aprovacao.etapa_id is not None:
        conversa_id = await sessao.scalar(
            select(Cadeia.conversa_id)
            .join(Etapa, Etapa.cadeia_id == Cadeia.id)
            .where(Etapa.id == aprovacao.etapa_id, Cadeia.usuario_id == usuario_id)
        )
    conversa_fora_de_cadeia: UUID | None = None
    if aprovacao.etapa_id is None and isinstance(aprovacao.acao, dict):
        # Aprovação pedida pela Sora ou por um agente individual, fora de cadeia: a conversa
        # vem no próprio cartão (``acao.conversa_id``) e precisa ser do usuário.
        try:
            candidata = UUID(str(aprovacao.acao.get("conversa_id")))
        except ValueError:
            candidata = None
        if candidata is not None:
            conversa_fora_de_cadeia = await sessao.scalar(
                select(Conversa.id).where(
                    Conversa.id == candidata, Conversa.usuario_id == usuario_id
                )
            )
            conversa_id = conversa_fora_de_cadeia
    novo_status = aprovacao.status
    etapa_id = aprovacao.etapa_id
    grupo_id = aprovacao.grupo_id
    await sessao.commit()
    await publicar_estado_atencao(
        redis,
        sessao,
        usuario_id,
        agente_id=aprovacao.agente_id,
        grupo_id=aprovacao.grupo_id,
    )
    # Evento e job só depois do commit; o worker relê a decisão no banco.
    if conversa_id is not None:
        await publicar_evento(
            redis,
            AprovacaoResolvida(aprovacao_id=aprovacao_id, status=novo_status),
            conversa_id,
            usuario_id,
        )
    if etapa_id is not None:
        await fila.enqueue_job(
            "executar_etapa",
            str(etapa_id),
            {"aprovacao_id": str(aprovacao_id), "decisao": decisao.value},
            _job_id=f"aprovacao:{aprovacao_id}",
        )
    elif conversa_fora_de_cadeia is not None:
        await fila.enqueue_job(
            "retomar_conversa",
            str(conversa_fora_de_cadeia),
            {"aprovacao_id": str(aprovacao_id), "decisao": decisao.value},
            _job_id=f"aprovacao:{aprovacao_id}",
        )
    elif grupo_id is not None:
        # Cartão aberto no turno de um bot dentro do grupo: o worker retoma aquele turno.
        await fila.enqueue_job(
            "retomar_tarefa_canal",
            cartao_id=str(aprovacao_id),
            resposta={"aprovacao_id": str(aprovacao_id), "decisao": decisao.value},
            _job_id=f"aprovacao:{aprovacao_id}",
        )
