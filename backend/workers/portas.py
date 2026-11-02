"""Portas de infraestrutura que o worker entrega aos middlewares do agente (§4 e §6.1).

Sem elas os middlewares de cancelamento, orçamento de tokens, passos do painel Trabalho e
saída grande ficam desligados (``montar_middleware`` só os liga quando a porta existe).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update

from app.core.banco import fabrica_sessoes
from app.eventos.streams import publicar_evento
from app.eventos.tipos import PassoEvento
from app.ferramentas.rotulos import (
    parametros_sem_segredos,
    resumir_resultado,
    rotulo_do_passo,
)
from app.modelos.enumeracoes import StatusCadeia, StatusPasso, TipoPasso
from app.modelos.tabelas import Cadeia, Passo
from app.orquestrador.cadeia import chave_de_cancelamento

PRAZO_CONTADOR_S = 2 * 24 * 60 * 60


def _chave_tokens(cadeia_id: UUID) -> str:
    return f"tokens:{cadeia_id}"


def construir_dependencias(
    ctx: dict[str, Any],
    *,
    usuario_id: UUID,
    conversa_id: UUID,
    cadeia_id: UUID | None = None,
    orcamento_tokens: int | None = None,
    etapa_id: UUID | None = None,
    agente_id: UUID | None = None,
) -> Any:
    """``DependenciasAgente`` completa para uma etapa (ou conversa direta, sem cadeia)."""
    from app.agentes.montagem import DependenciasAgente
    from app.ferramentas import ambiente

    redis = ctx["redis_eventos"]

    async def esta_cancelada(cadeia: UUID) -> bool:
        if await redis.exists(chave_de_cancelamento(cadeia)):
            return True
        async with fabrica_sessoes()() as sessao:
            status = await sessao.get(Cadeia, cadeia)
            return status is not None and status.status == StatusCadeia.CANCELADA

    async def reservar_tokens(cadeia: UUID, estimativa: int, teto: int) -> bool:
        chave = _chave_tokens(cadeia)
        total = await redis.incrby(chave, estimativa)
        await redis.expire(chave, PRAZO_CONTADOR_S)
        if total > teto:
            await redis.decrby(chave, estimativa)
            return False
        return True

    async def corrigir_tokens(cadeia: UUID, estimativa: int, real: int) -> None:
        if real != estimativa:
            await redis.incrby(_chave_tokens(cadeia), real - estimativa)
        if real > 0:
            async with fabrica_sessoes()() as sessao:
                await sessao.execute(
                    update(Cadeia)
                    .where(Cadeia.id == cadeia)
                    .values(tokens_usados=Cadeia.tokens_usados + real)
                )
                await sessao.commit()

    async def iniciar_passo(etapa_id: UUID, agente_id: UUID, chamada: dict[str, Any]) -> dict:
        nome = str(chamada.get("name", "ferramenta"))
        argumentos = chamada.get("args") if isinstance(chamada.get("args"), dict) else {}
        passo = Passo(
            id=uuid4(),
            etapa_id=etapa_id,
            agente_id=agente_id,
            tipo=TipoPasso.FERRAMENTA,
            texto=rotulo_do_passo(nome, argumentos),
            ferramenta=nome,
            acao=nome,
            parametros=parametros_sem_segredos(argumentos),
            status=StatusPasso.EXECUTANDO.value,
            iniciado_em=datetime.now(UTC),
        )
        async with fabrica_sessoes()() as sessao:
            sessao.add(passo)
            await sessao.commit()
        estado = {
            "id": passo.id,
            "etapa_id": etapa_id,
            "agente_id": agente_id,
            "tipo": TipoPasso.FERRAMENTA,
            "texto": passo.texto,
            "ferramenta": nome,
            "acao": nome,
            "parametros": passo.parametros,
        }
        await _emitir(redis, estado, StatusPasso.EXECUTANDO, None, usuario_id, conversa_id)
        return estado

    async def finalizar_passo(
        passo: dict, resultado: Any | None, erro: BaseException | None
    ) -> None:
        status = StatusPasso.ERRO if erro is not None else StatusPasso.CONCLUIDO
        conteudo = getattr(resultado, "content", resultado)
        resumo = (
            {"erro": str(erro)[:300]}
            if erro is not None
            else resumir_resultado(passo["acao"], conteudo)
        )
        async with fabrica_sessoes()() as sessao:
            await sessao.execute(
                update(Passo)
                .where(Passo.id == passo["id"])
                .values(status=status.value, resultado=resumo, concluido_em=datetime.now(UTC))
            )
            await sessao.commit()
        await _emitir(redis, passo, status, resumo, usuario_id, conversa_id)

    async def salvar_saida(cadeia: UUID | None, texto: str) -> str:
        from app.ferramentas.arquivos import gravar_na_cadeia
        from app.ferramentas.infra import raiz_dos_arquivos

        caminho = await asyncio.to_thread(
            gravar_na_cadeia,
            raiz_dos_arquivos(),
            usuario_id,
            cadeia or conversa_id,
            f"saida-{uuid4().hex[:8]}.txt",
            texto,
        )
        return caminho.name

    async def ao_trocar_modelo(troca: Any) -> None:
        """§6 "Falha de provedor": a troca aparece na linha do tempo (passo de pensamento)."""
        destino = troca.para_modelo or "nenhum modelo disponível"
        texto = f"Troquei de modelo: {troca.de_modelo} → {destino}"
        passo = Passo(
            id=uuid4(),
            etapa_id=etapa_id,
            agente_id=agente_id,
            tipo=TipoPasso.PENSAMENTO,
            texto=texto,
            status=StatusPasso.CONCLUIDO.value,
            resultado={"motivo": str(getattr(troca.motivo, "value", troca.motivo))},
            iniciado_em=datetime.now(UTC),
            concluido_em=datetime.now(UTC),
        )
        async with fabrica_sessoes()() as sessao:
            sessao.add(passo)
            await sessao.commit()
        estado = {
            "id": passo.id,
            "etapa_id": etapa_id,
            "agente_id": agente_id,
            "tipo": TipoPasso.PENSAMENTO,
            "texto": texto,
            "ferramenta": None,
            "acao": None,
            "parametros": None,
        }
        await _emitir(
            redis, estado, StatusPasso.CONCLUIDO, passo.resultado, usuario_id, conversa_id
        )

    com_cadeia = cadeia_id is not None
    com_passo = etapa_id is not None and agente_id is not None
    return DependenciasAgente(
        esta_cancelada=esta_cancelada if com_cadeia else None,
        orcamento_tokens=orcamento_tokens if com_cadeia else None,
        reservar_tokens=reservar_tokens if com_cadeia and orcamento_tokens else None,
        corrigir_tokens=corrigir_tokens if com_cadeia and orcamento_tokens else None,
        iniciar_passo=iniciar_passo,
        finalizar_passo=finalizar_passo,
        salvar_saida=salvar_saida,
        ler_mensagens_pendentes=ambiente.ler_mensagens_pendentes,
        ao_trocar_modelo=ao_trocar_modelo if com_passo else None,
    )


async def _emitir(
    redis: Any,
    passo: dict[str, Any],
    status: StatusPasso,
    resultado: dict[str, Any] | None,
    usuario_id: UUID,
    conversa_id: UUID,
) -> None:
    await publicar_evento(
        redis,
        PassoEvento(
            passo_id=passo["id"],
            etapa_id=passo["etapa_id"],
            agente_id=passo["agente_id"],
            tipo=passo["tipo"],
            texto=passo["texto"],
            ferramenta=passo["ferramenta"],
            acao=passo["acao"],
            parametros=passo["parametros"],
            resultado=resultado,
            status=status,
        ),
        conversa_id,
        usuario_id,
    )
