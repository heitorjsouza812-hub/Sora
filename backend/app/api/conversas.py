"""Rotas de conversas e mensagens; especificação §2."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.contas import tem_provedor_validado
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.streams import publicar_evento
from app.eventos.tipos import (
    ConversaAtualizada,
    MensagemDelta,
    MensagemFim,
    MensagemInicio,
    RoteamentoEvento,
)
from app.llm.custo import gravar_chamada
from app.llm.provedores import ConfigProvedor
from app.modelos.enumeracoes import (
    AutorMensagem,
    Nivel,
    TipoAgente,
    TipoConversa,
    TipoProvedor,
)
from app.modelos.esquemas import (
    AjusteEntrada,
    AprovacaoVersaoEntrada,
    ConversaCriacao,
    ConversaSaida,
    MensagemAceita,
    MensagemCriacao,
    MensagemSaida,
    RenomearConversaEntrada,
)
from app.modelos.tabelas import Agente, Cadeia, Conector, Conversa, Entrega, Mensagem, Roteamento
from app.repositorios import conversas as repositorio
from app.seletor.repositorio import config_do_provedor, contexto_do_usuario
from app.seletor.tipos import Capacidade, ModeloCandidato, ProvedorSeletor
from app.sistema1.esquemas import ModoTriagem
from app.sistema1.triagem import AgenteIndividualResumo, ContextoTriagem, triar

PROVEDOR_FALSO_ID = UUID(int=0)

roteador = APIRouter(prefix="/conversas", tags=["conversas"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]


async def usuario_com_modelo(usuario_id: Usuario, sessao: Sessao) -> UUID:
    """No desenvolvimento, o modelo falso substitui uma API conectada sem criar segredo fake."""
    if obter_configuracao().sora_modelo_falso:
        return usuario_id
    if not await tem_provedor_validado(sessao, usuario_id):
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "Conecte uma API de modelos antes de fazer pedidos.",
        )
    return usuario_id


UsuarioComProvedor = Annotated[UUID, Depends(usuario_com_modelo)]


def obter_fila(redis: RedisDep) -> ArqRedis:
    """Adapta o pool Redis da API ao cliente ARQ, sem abrir outra conexão."""
    return ArqRedis(redis.connection_pool)


Fila = Annotated[ArqRedis, Depends(obter_fila)]


def _nao_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")


async def _conferir_entrada(
    sessao: AsyncSession, usuario_id: UUID, texto: str, anexos: list[UUID]
) -> None:
    if not texto.strip() and not anexos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escreva uma mensagem.")
    if not await repositorio.conferir_anexos(sessao, usuario_id, anexos):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.")


async def _contexto_triagem(
    sessao: AsyncSession, usuario_id: UUID, conversa_id: UUID
) -> ContextoTriagem:
    agentes = list(
        (
            await sessao.scalars(
                select(Agente).where(
                    Agente.usuario_id == usuario_id,
                    Agente.tipo == TipoAgente.INDIVIDUAL,
                    Agente.apagado_em.is_(None),
                )
            )
        ).all()
    )
    conectores = list(
        (
            await sessao.scalars(
                select(Conector.nome).where(
                    Conector.usuario_id == usuario_id,
                    Conector.ativo.is_(True),
                )
            )
        ).all()
    )
    ultimas = list(
        (
            await sessao.scalars(
                select(Mensagem.conteudo)
                .where(Mensagem.conversa_id == conversa_id, Mensagem.visivel.is_(True))
                .order_by(Mensagem.criada_em.desc())
                .limit(10)
            )
        ).all()
    )
    return ContextoTriagem(
        agentes_individuais=[
            AgenteIndividualResumo(id=str(a.id), nome=a.nome, funcao=a.funcao) for a in agentes
        ],
        conectores=conectores,
        ultimas_mensagens=list(reversed(ultimas)),
    )


registro = logging.getLogger(__name__)

MENSAGEM_FALHA_DO_PROVEDOR = (
    "Não consegui falar com o seu modelo de IA agora. Veja a chave e o limite do provedor em "
    "Configurações → Modelos de IA e envie o pedido de novo. Sua mensagem foi guardada."
)


async def _publicar_primeira_resposta(
    redis: Redis,
    sessao: AsyncSession,
    *,
    usuario_id: UUID,
    conversa_id: UUID,
    texto: str,
    agente_id: UUID,
) -> None:
    conversa = await repositorio.obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        return
    mensagem = await repositorio.criar_mensagem(
        sessao,
        conversa=conversa,
        texto=texto,
        anexos=[],
        agente_id=agente_id,
        autor=AutorMensagem.SORA,
    )
    await sessao.commit()
    await publicar_evento(
        redis,
        MensagemInicio(mensagem_id=mensagem.id, autor=AutorMensagem.SORA, agente_id=agente_id),
        conversa_id,
        usuario_id,
    )
    if texto:
        await publicar_evento(
            redis,
            MensagemDelta(mensagem_id=mensagem.id, texto=texto),
            conversa_id,
            usuario_id,
        )
    await publicar_evento(
        redis,
        MensagemFim(mensagem_id=mensagem.id),
        conversa_id,
        usuario_id,
    )


async def _encaminhar(
    sessao: AsyncSession,
    redis: Redis,
    fila: ArqRedis,
    *,
    usuario_id: UUID,
    conversa: Conversa,
    mensagem: Mensagem,
    agente: Agente,
) -> None:
    """Faz a triagem na requisição, confirma o banco e só então enfileira."""
    if agente.tipo == TipoAgente.INDIVIDUAL:
        await sessao.commit()
        await fila.enqueue_job(
            "responder_direto", str(mensagem.id), _job_id=f"responder:{mensagem.id}"
        )
        return

    seletor = await contexto_do_usuario(sessao, usuario_id, conversa_privada=conversa.privada)
    configs: dict[str, ConfigProvedor]
    if obter_configuracao().sora_modelo_falso and not seletor.modelos:
        provedor_falso = ProvedorSeletor(id=PROVEDOR_FALSO_ID, tipo=TipoProvedor.OLLAMA)
        seletor.modelos.append(
            ModeloCandidato(
                modelo="sora/falso",
                provedor=provedor_falso,
                nivel=Nivel.N1,
                capacidades=frozenset(
                    {
                        Capacidade.JSON,
                        Capacidade.FERRAMENTAS,
                        Capacidade.VISAO,
                        Capacidade.IMAGEM,
                    }
                ),
                contexto=1_000_000,
                preco_entrada=0,
                preco_saida=0,
            )
        )
        configs = {
            str(provedor_falso.id): ConfigProvedor(
                provedor_id=provedor_falso.id, tipo=provedor_falso.tipo
            )
        }
    else:
        configs = {
            str(provedor_id): await config_do_provedor(sessao, usuario_id, provedor_id)
            for provedor_id in {m.provedor.id for m in seletor.modelos}
        }
    contexto = await _contexto_triagem(sessao, usuario_id, conversa.id)
    contexto.tem_modelo_de_imagem = any("imagem" in m.capacidades for m in seletor.modelos)
    try:
        resultado = await triar(mensagem.conteudo, contexto, seletor, configs)
    except Exception as erro:
        # Provedor fora do ar, chave inválida, limite estourado ou resposta ilegível: o texto
        # do usuário não se perde. A conversa é criada e a Sora explica o que houve.
        registro.warning("triagem falhou (%s): %s", type(erro).__name__, str(erro)[:200])
        await sessao.commit()
        await _publicar_primeira_resposta(
            redis,
            sessao,
            usuario_id=usuario_id,
            conversa_id=conversa.id,
            texto=MENSAGEM_FALHA_DO_PROVEDOR,
            agente_id=agente.id,
        )
        return
    sessao.add(
        Roteamento(
            mensagem_id=mensagem.id,
            saida=resultado.saida.model_dump(mode="json"),
            modelo=resultado.modelo,
            confianca=resultado.saida.confianca,
            escalou=resultado.escalou,
            latencia_ms=resultado.latencia_ms,
        )
    )
    for chamada in resultado.chamadas:
        if chamada.provedor_id == PROVEDOR_FALSO_ID:
            continue  # o modelo falso não tem linha em `provedores` nem custa nada
        await gravar_chamada(sessao, usuario_id, chamada)

    candidato = next((m for m in seletor.modelos if m.provedor.id == resultado.provedor_id), None)
    if candidato is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Modelo de triagem indisponível.")
    await sessao.flush()
    await sessao.commit()
    await publicar_evento(
        redis,
        RoteamentoEvento(
            modo="cadeia" if resultado.saida.modo == ModoTriagem.CADEIA else "direto",
            dificuldade=resultado.saida.dificuldade,
            especialistas=[e.value for e in resultado.saida.especialistas],
            nivel=Nivel(f"N{resultado.saida.dificuldade}"),
            provedor=candidato.provedor.tipo,
            modelo=resultado.modelo,
        ),
        conversa.id,
        usuario_id,
    )
    await _publicar_primeira_resposta(
        redis,
        sessao,
        usuario_id=usuario_id,
        conversa_id=conversa.id,
        texto=resultado.saida.primeira_resposta,
        agente_id=agente.id,
    )

    if resultado.saida.modo == ModoTriagem.CADEIA:
        versao = (
            await sessao.scalar(
                select(func.coalesce(func.max(Cadeia.versao), 0)).where(
                    Cadeia.conversa_id == conversa.id
                )
            )
        ) + 1
        cadeia = Cadeia(
            usuario_id=usuario_id,
            conversa_id=conversa.id,
            pedido_id=mensagem.id,
            orcamento_tokens=200_000,
            versao=versao,
        )
        conversa.tipo = TipoConversa.PROJETO
        sessao.add(cadeia)
        await sessao.flush()
        await sessao.commit()
        await fila.enqueue_job("planejar_cadeia", str(cadeia.id), _job_id=f"planejar:{cadeia.id}")
    else:
        await fila.enqueue_job(
            "responder_direto", str(mensagem.id), _job_id=f"responder:{mensagem.id}"
        )


@roteador.get("")
async def listar_conversas(usuario_id: Usuario, sessao: Sessao) -> list[ConversaSaida]:
    return [ConversaSaida.model_validate(c) for c in await repositorio.listar(sessao, usuario_id)]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_conversa(
    dados: ConversaCriacao,
    usuario_id: UsuarioComProvedor,
    sessao: Sessao,
    redis: RedisDep,
    fila: Fila,
) -> ConversaSaida:
    await _conferir_entrada(sessao, usuario_id, dados.texto, dados.anexos)
    agente = await repositorio.obter_agente(sessao, usuario_id, dados.agente_id)
    if agente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")
    conversa, mensagem = await repositorio.criar(
        sessao,
        usuario_id=usuario_id,
        agente=agente,
        texto=dados.texto,
        anexos=dados.anexos,
    )
    conversa.titulo = dados.texto.strip()[:120] or None
    await _encaminhar(
        sessao,
        redis,
        fila,
        usuario_id=usuario_id,
        conversa=conversa,
        mensagem=mensagem,
        agente=agente,
    )
    return ConversaSaida.model_validate(conversa)


@roteador.patch("/{conversa_id}")
async def renomear_conversa(
    conversa_id: UUID, dados: RenomearConversaEntrada, usuario_id: Usuario, sessao: Sessao
) -> ConversaSaida:
    conversa = await repositorio.renomear(sessao, usuario_id, conversa_id, dados.titulo)
    if conversa is None:
        raise _nao_encontrada()
    return ConversaSaida.model_validate(conversa)


@roteador.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conversa(
    conversa_id: UUID, usuario_id: Usuario, sessao: Sessao, manter_agentes: bool = False
) -> None:
    if not await repositorio.apagar(sessao, usuario_id, conversa_id, manter_agentes=manter_agentes):
        raise _nao_encontrada()


@roteador.get("/{conversa_id}/mensagens")
async def listar_mensagens(
    conversa_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    antes: datetime | None = None,
    limite: int = 50,
) -> list[MensagemSaida]:
    if not 1 <= limite <= 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Limite deve ficar entre 1 e 100."
        )
    mensagens = await repositorio.listar_mensagens(
        sessao, usuario_id, conversa_id, antes=antes, limite=limite
    )
    if mensagens is None:
        raise _nao_encontrada()
    return [MensagemSaida.model_validate(m) for m in mensagens]


@roteador.post("/{conversa_id}/mensagens", status_code=status.HTTP_202_ACCEPTED)
async def enviar_mensagem(
    conversa_id: UUID,
    dados: MensagemCriacao,
    usuario_id: UsuarioComProvedor,
    sessao: Sessao,
    redis: RedisDep,
    fila: Fila,
) -> MensagemAceita:
    await _conferir_entrada(sessao, usuario_id, dados.texto, dados.anexos)
    conversa = await repositorio.obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        raise _nao_encontrada()
    agente = await repositorio.obter_agente(sessao, usuario_id, conversa.agente_id)
    if agente is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "O agente desta conversa não está disponível."
        )
    if dados.para_agente_id is not None:
        especialista = await repositorio.obter_agente(sessao, usuario_id, dados.para_agente_id)
        if especialista is None or especialista.tipo != TipoAgente.ESPECIALISTA:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Especialista não encontrado.")
        etapa = await repositorio.etapa_ativa_do_agente(
            sessao, usuario_id, conversa_id, dados.para_agente_id
        )
        if etapa is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Esse especialista não tem uma etapa ativa nesta conversa.",
            )
    mensagem = await repositorio.criar_mensagem(
        sessao,
        conversa=conversa,
        texto=dados.texto,
        anexos=dados.anexos,
        agente_id=dados.para_agente_id,
    )
    if dados.para_agente_id is not None:
        await sessao.commit()
        await fila.enqueue_job(
            "executar_etapa",
            str(etapa.id),
            {
                "tipo": "mensagem_usuario",
                "texto": dados.texto,
                "anexos": [str(anexo) for anexo in dados.anexos],
            },
            _job_id=f"retomar:{mensagem.id}",
        )
        return MensagemAceita(mensagem_id=mensagem.id)
    await _encaminhar(
        sessao,
        redis,
        fila,
        usuario_id=usuario_id,
        conversa=conversa,
        mensagem=mensagem,
        agente=agente,
    )
    return MensagemAceita(mensagem_id=mensagem.id)


@roteador.post("/{conversa_id}/aprovar", status_code=status.HTTP_204_NO_CONTENT)
async def aprovar_versao(
    conversa_id: UUID,
    dados: AprovacaoVersaoEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> None:
    conversa = await repositorio.obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        raise _nao_encontrada()
    existe = await sessao.scalar(
        select(Entrega.id).where(
            Entrega.usuario_id == usuario_id,
            Entrega.conversa_id == conversa_id,
            Entrega.versao == dados.versao,
        )
    )
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versão não encontrada.")
    conversa.aprovada_versao = dados.versao
    await sessao.commit()
    await publicar_evento(
        redis,
        ConversaAtualizada(
            conversa_id=conversa.id,
            titulo=conversa.titulo,
            tipo=conversa.tipo,
            aprovada_versao=conversa.aprovada_versao,
        ),
        conversa.id,
        usuario_id,
    )


@roteador.post("/{conversa_id}/ajuste", status_code=status.HTTP_202_ACCEPTED)
async def pedir_ajuste(
    conversa_id: UUID,
    dados: AjusteEntrada,
    usuario_id: UsuarioComProvedor,
    sessao: Sessao,
    fila: Fila,
) -> None:
    conversa = await repositorio.obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        raise _nao_encontrada()
    if not dados.texto.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Descreva o ajuste.")
    if dados.agente_id is not None:
        agente = await repositorio.obter_agente(sessao, usuario_id, dados.agente_id)
        if agente is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")
    await sessao.commit()
    await fila.enqueue_job(
        "ajustar",
        str(conversa_id),
        dados.texto,
        str(dados.agente_id) if dados.agente_id else None,
        _job_id=f"ajustar:{conversa_id}:{uuid4().hex}",
    )
