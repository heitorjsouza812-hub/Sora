"""Jobs das rotinas (Relógio, etapa 4).

- ``disparar_rotinas``: cron do ARQ (a cada 10 s). Pega as rotinas vencidas com
  ``SKIP LOCKED``, avança a próxima execução e enfileira ``executar_rotina`` com o id da
  ocorrência (a fila não duplica). Também marca como falhas as execuções que ficaram
  ``executando`` por causa de um worker que caiu.
- ``executar_rotina``: roda o pedido **sempre sem supervisão** (só ferramentas seguras, navegador
  efêmero, sem ``falar``/``perguntar``) numa thread só da execução. A resposta ``SEM_RESPOSTA``
  não manda mensagem; qualquer outro texto é falado na conversa da rotina.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.eventos.rotinas import RotinaExecutada
from app.eventos.streams import publicar_evento
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.modelos.enumeracoes import AutorMensagem, TipoAgente, TipoConversa
from app.modelos.tabelas import Agente, Conversa, Mensagem, Rotina, RotinaExecucao
from app.rotinas import servico
from app.rotinas.silencio import INSTRUCAO_ROTINA_SILENCIOSA, limpar_resposta
from workers.fila import enfileirar

registro = logging.getLogger(__name__)

PRAZO_EXECUCAO_S = 300
ORFA_APOS = timedelta(minutes=10)
MENSAGEM_LIMITE_DE_PASSOS_ROTINA = (
    "A rotina usou o máximo de passos permitido sem terminar. "
    "Simplifique o pedido da rotina e rode de novo."
)
MENSAGEM_LIMITE_DO_PROVEDOR_ROTINA = (
    "O provedor recusou: limite por minuto do plano. Tente de novo em alguns instantes "
    "ou use um modelo com limite maior."
)
MENSAGEM_FALHA = "A rotina não terminou: o modelo de IA não respondeu. Confira em Configurações."


async def disparar_rotinas(ctx: dict[str, Any]) -> int:
    """Devolve quantas ocorrências foram enfileiradas."""
    agora = datetime.now(UTC)
    async with ctx["sessoes"]() as sessao:
        vencidas = await servico.pegar_vencidas(sessao, agora)
        # Enfileira ANTES de confirmar: se o processo cair no meio, o próximo tick enfileira de
        # novo com o mesmo id (a fila ignora a repetição) e só então avança a agenda.
        for rotina_id, ocorrencia in vencidas:
            await enfileirar(
                "executar_rotina",
                id_job=f"rotina:{rotina_id}:{int(ocorrencia.timestamp())}",
                rotina_id=str(rotina_id),
                ocorrencia=ocorrencia.isoformat(),
            )
        await sessao.commit()
        await sessao.execute(
            update(RotinaExecucao)
            .where(
                RotinaExecucao.status == "executando",
                RotinaExecucao.iniciada_em < agora - ORFA_APOS,
            )
            .values(
                status="falhou",
                erro="O worker parou durante esta execução.",
                concluida_em=agora,
            )
        )
        await sessao.commit()
    return len(vencidas)


def _texto_final(resultado: dict[str, Any]) -> str:
    for mensagem in reversed(resultado.get("messages", [])):
        if isinstance(mensagem, AIMessage) and isinstance(mensagem.content, str):
            if mensagem.content.strip():
                return mensagem.content.strip()
    return ""


async def _garantir_conversa(sessao: Any, rotina: Rotina) -> UUID:
    if rotina.conversa_id is not None:
        existe = await sessao.scalar(
            select(Conversa.id).where(
                Conversa.id == rotina.conversa_id, Conversa.usuario_id == rotina.usuario_id
            )
        )
        if existe is not None:
            return existe
    conversa = Conversa(
        usuario_id=rotina.usuario_id,
        agente_id=rotina.agente_id,
        tipo=TipoConversa.CHAT,
        titulo=f"Rotina: {rotina.titulo}"[:120],
    )
    sessao.add(conversa)
    await sessao.flush()
    rotina.conversa_id = conversa.id
    return conversa.id


async def executar_rotina(
    ctx: dict[str, Any],
    rotina_id: str,
    ocorrencia: str | None = None,
    execucao_id: str | None = None,
    manual: bool = False,
) -> str | None:
    """Roda uma ocorrência. Nunca levanta: o resultado fica em ``rotina_execucoes``."""
    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar
    from app.orquestrador.modelos import modelos_do_papel
    from workers.cadeia import dependencias_da_etapa

    inicio = datetime.now(UTC)
    async with ctx["sessoes"]() as sessao:
        rotina = await sessao.get(Rotina, UUID(rotina_id))
        if rotina is None:
            return None
        if not manual and not rotina.ativa and rotina.proxima_execucao is not None:
            return None  # pausada depois de enfileirar
        agente = await sessao.get(Agente, rotina.agente_id)
        if agente is None or agente.apagado_em is not None:
            return None
        execucao = await sessao.get(RotinaExecucao, UUID(execucao_id)) if execucao_id else None
        if execucao is None:
            # Idempotente por ocorrência: o id da execução sai da rotina + ocorrência, então a
            # reentrega do mesmo job (ou um segundo worker) bate na chave primária e desiste.
            nova_id = (
                uuid5(
                    NAMESPACE_URL,
                    f"rotina:{rotina.id}:{int(datetime.fromisoformat(ocorrencia).timestamp())}",
                )
                if ocorrencia and not manual
                else uuid4()
            )
            if await sessao.get(RotinaExecucao, nova_id) is not None:
                return None
            execucao = RotinaExecucao(
                id=nova_id, rotina_id=rotina.id, usuario_id=rotina.usuario_id, iniciada_em=inicio
            )
            sessao.add(execucao)
            try:
                await sessao.flush()
            except IntegrityError:
                return None
        elif execucao.status != "executando" or execucao.concluida_em is not None:
            return None  # reentrega do mesmo job
        rotina.ultima_execucao = inicio
        conversa_id = await _garantir_conversa(sessao, rotina)
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        usuario_id, agente_id = rotina.usuario_id, agente.id
        titulo, pedido, silencioso = rotina.titulo, rotina.pedido, rotina.silencioso
        exec_id, rid = execucao.id, rotina.id
        modelos = (
            [criar_modelo_falso("rotina")]
            if modelo_falso_ativo()
            else await modelos_do_papel(sessao, usuario_id, papel, dificuldade=1)
        )
        await sessao.commit()

    status, erro, texto, mensagem_id = "enviada", None, "", None
    try:
        contexto = ContextoAgente(
            usuario_id=usuario_id,
            agente_id=agente_id,
            conversa_id=conversa_id,
            papel=papel,
            dependencias=dependencias_da_etapa(ctx, usuario_id=usuario_id, conversa_id=conversa_id),
            sem_supervisao=True,
            thread_proprio=f"rotina:{exec_id}",
        )
        instrucao = f"\n\n{INSTRUCAO_ROTINA_SILENCIOSA}" if silencioso else ""
        entrada = HumanMessage(
            f"[Rotina agendada: {titulo}. Ninguém está olhando agora: use só as ferramentas "
            f"seguras e responda com o resultado final.]\n\n{pedido}{instrucao}"
        )
        resultado = await asyncio.wait_for(
            montar_e_rodar_agente(
                contexto=contexto,
                modelos=modelos,
                checkpointer=ctx["checkpointer"],
                entrada={"messages": [entrada]},
            ),
            PRAZO_EXECUCAO_S,
        )
        texto = _texto_final(resultado)
        limpo = limpar_resposta(texto) if texto else None
        if not limpo:
            status = "silenciosa"
        else:
            texto = limpo
            await falar(
                Falar(texto=f"**{titulo}**\n\n{texto}"),
                ContextoFerramenta(
                    usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id
                ),
            )
            async with ctx["sessoes"]() as sessao:
                mensagem_id = await sessao.scalar(
                    select(Mensagem.id)
                    .where(
                        Mensagem.conversa_id == conversa_id,
                        Mensagem.autor != AutorMensagem.USUARIO,
                        Mensagem.criada_em >= inicio,
                    )
                    .order_by(Mensagem.criada_em.desc())
                    .limit(1)
                )
    except Exception as falha:
        from app.agentes.middleware.limites import estourou_limite_de_passos
        from app.llm.limite import limite_do_provedor

        registro.exception("a rotina %s falhou", rid)
        status = "falhou"
        if estourou_limite_de_passos(falha):
            erro = MENSAGEM_LIMITE_DE_PASSOS_ROTINA
        elif limite_do_provedor(falha):
            erro = MENSAGEM_LIMITE_DO_PROVEDOR_ROTINA
        else:
            erro = MENSAGEM_FALHA
    async with ctx["sessoes"]() as sessao:
        await sessao.execute(
            update(RotinaExecucao)
            .where(RotinaExecucao.id == exec_id)
            .values(
                status=status,
                erro=erro,
                resumo=(texto[:300] or None),
                concluida_em=datetime.now(UTC),
                mensagem_id=mensagem_id,
            )
        )
        await sessao.commit()
    await publicar_evento(
        ctx["redis_eventos"],
        RotinaExecutada(rotina_id=rid, execucao_id=exec_id, status=status, mensagem_id=mensagem_id),  # type: ignore[arg-type]
        conversa_id,
        usuario_id,
    )
    return status
