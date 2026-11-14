"""Grupos da etapa 5 sobre a persistência e execução de ``canais_equipe``."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agentes import _saida as _saida_agente
from app.api.agentes import _sora_persistente
from app.api.bots import _aplicar_ajustes, _materializar_rascunho
from app.canais_equipe.modelos import (
    EM_ANDAMENTO,
    MAX_INSTRUCOES,
    MAX_NOME_CANAL,
    MAX_PROPOSITO,
    ErroCanal,
)
from app.canais_equipe.roteamento import Membro
from app.canais_equipe.servico import Mudancas, ServicoCanais
from app.canais_equipe.sql import ArmazemCanaisSQL
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.estado_interface import EstadoInterface, estados_dos_grupos
from app.eventos.equipe import (
    CanalAtualizado,
    GrupoPropostaResolvida,
    GrupoPropostoEvento,
    TarefaCanalAtualizada,
    publicar_evento_equipe,
)
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import AgenteSaida
from app.modelos.tabelas import Agente, CanalEquipe, PropostaGrupo, RascunhoBot
from app.modelos.tabelas import Usuario as UsuarioTabela
from app.rascunhos_bot import (
    RascunhoBotAjuste,
    RascunhoBotSaida,
    criar_rascunho,
    obter_rascunho_para_atualizar,
    saida_do_rascunho,
)

roteador = APIRouter(prefix="/grupos", tags=["grupos"], dependencies=[Depends(usuario_atual)])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]

MIN_BOTS = 2
MAX_BOTS = 5


class GrupoCriacao(BaseModel):
    nome: str = Field(min_length=1, max_length=MAX_NOME_CANAL)
    membros: list[UUID]
    proposito: str = Field(default="", max_length=MAX_PROPOSITO)
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES)


class GrupoAtualizacao(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=MAX_NOME_CANAL)
    membros: list[UUID] | None = None
    proposito: str | None = Field(default=None, max_length=MAX_PROPOSITO)
    instrucoes: str | None = Field(default=None, max_length=MAX_INSTRUCOES)


class GrupoSaida(BaseModel):
    id: UUID
    nome: str
    membros: list[UUID]
    lider_id: UUID
    proposito: str
    instrucoes: str
    arquivado: bool
    estado: EstadoInterface
    precisa_de_bots: bool


class PropostaGrupoCriacao(BaseModel):
    pedido: str = Field(min_length=1, max_length=20_000)


class PropostaGrupoAtualizacao(BaseModel):
    nome: str | None = None
    bots_reaproveitados: list[UUID] | None = Field(default=None, max_length=MAX_BOTS)
    bots_novos: list[RascunhoBotAjuste] | None = Field(default=None, max_length=MAX_BOTS)


class PropostaGrupoSaida(BaseModel):
    id: UUID
    nome: str
    pedido: str
    bots_reaproveitados: list[AgenteSaida]
    bots_novos: list[RascunhoBotSaida]
    status: Literal["proposta"] = "proposta"


async def _bots_validos(
    sessao: AsyncSession, usuario_id: UUID, membros: list[UUID], sora_id: UUID
) -> list[UUID]:
    membros = list(dict.fromkeys(membros))
    if not MIN_BOTS <= len(membros) <= MAX_BOTS:
        raise HTTPException(422, f"Escolha de {MIN_BOTS} a {MAX_BOTS} bots.")
    if sora_id in membros:
        raise HTTPException(422, "A Sora entra automaticamente como chefe do grupo.")
    encontrados = set(
        (
            await sessao.scalars(
                select(Agente.id).where(
                    Agente.id.in_(membros),
                    Agente.usuario_id == usuario_id,
                    Agente.tipo == TipoAgente.INDIVIDUAL,
                    Agente.apagado_em.is_(None),
                )
            )
        ).all()
    )
    if encontrados != set(membros):
        raise HTTPException(422, "Use somente bots ativos da sua conta.")
    return membros


def _saida(canal, estado: EstadoInterface) -> GrupoSaida:
    assert canal.lider_id is not None
    return GrupoSaida(
        id=canal.id,
        nome=canal.nome,
        membros=list(canal.membros),
        lider_id=canal.lider_id,
        proposito=canal.proposito,
        instrucoes=canal.instrucoes,
        arquivado=canal.arquivado,
        estado=estado,
        precisa_de_bots=len(set(canal.membros) - {canal.lider_id}) < MIN_BOTS,
    )


def _evento(canal, estado: EstadoInterface) -> CanalAtualizado:
    return CanalAtualizado(
        canal_id=canal.id,
        nome=canal.nome,
        membros=list(canal.membros),
        lider_id=canal.lider_id,
        arquivado=canal.arquivado,
        proposito=canal.proposito,
        instrucoes=canal.instrucoes,
        estado=estado,
    )


async def _grupo_do_usuario(
    armazem: ArmazemCanaisSQL, sessao: AsyncSession, usuario_id: UUID, grupo_id: UUID
):
    dono = await sessao.scalar(select(CanalEquipe.usuario_id).where(CanalEquipe.id == grupo_id))
    if dono != usuario_id:
        raise HTTPException(404, "Grupo não encontrado.")
    canal = await armazem.canal(grupo_id)
    if canal is None:
        raise HTTPException(404, "Grupo não encontrado.")
    return canal


async def _proposta_do_usuario(
    sessao: AsyncSession, usuario_id: UUID, proposta_id: UUID, *, travar: bool = False
) -> PropostaGrupo:
    consulta = select(PropostaGrupo).where(
        PropostaGrupo.id == proposta_id, PropostaGrupo.usuario_id == usuario_id
    )
    if travar:
        consulta = consulta.with_for_update()
    proposta = await sessao.scalar(consulta)
    if proposta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta não encontrada.")
    return proposta


async def _saida_da_proposta(sessao: AsyncSession, proposta: PropostaGrupo) -> PropostaGrupoSaida:
    agentes = list(
        await sessao.scalars(select(Agente).where(Agente.id.in_(proposta.bots_reaproveitados)))
    )
    por_id = {agente.id: agente for agente in agentes}
    reaproveitados = [
        _saida_agente(por_id[agente_id])
        for agente_id in proposta.bots_reaproveitados
        if agente_id in por_id
    ]
    ids_novos = [UUID(str(item["id"])) for item in proposta.bots_novos]
    rascunhos = list(await sessao.scalars(select(RascunhoBot).where(RascunhoBot.id.in_(ids_novos))))
    rascunhos_por_id = {rascunho.id: rascunho for rascunho in rascunhos}
    novos = [
        saida_do_rascunho(rascunhos_por_id[rascunho_id])
        for rascunho_id in ids_novos
        if rascunho_id in rascunhos_por_id
    ]
    return PropostaGrupoSaida(
        id=proposta.id,
        nome=proposta.nome,
        pedido=proposta.pedido,
        bots_reaproveitados=reaproveitados,
        bots_novos=novos,
    )


def _evento_proposta(saida: PropostaGrupoSaida) -> GrupoPropostoEvento:
    return GrupoPropostoEvento(**saida.model_dump())


LIMITE_NOME_GRUPO = 60


def nome_do_pedido(pedido: str) -> str:
    """Nome curto para a proposta: primeira linha, cortada em 60 no limite de palavra."""
    linhas = pedido.strip().splitlines()
    primeira = " ".join(linhas[0].split()) if linhas else ""
    if len(primeira) > LIMITE_NOME_GRUPO:
        corte = primeira[: LIMITE_NOME_GRUPO + 1].rsplit(" ", 1)[0]
        primeira = (corte if len(corte) >= 20 else primeira[:LIMITE_NOME_GRUPO]).rstrip(" ,;:-")
    return primeira[:LIMITE_NOME_GRUPO] or "Novo grupo"


@roteador.get("/propostas")
async def listar_propostas(usuario_id: Usuario, sessao: Sessao) -> list[PropostaGrupoSaida]:
    """Propostas ainda sem decisão, em ordem de criação (o cartão sobrevive à recarga)."""
    propostas = await sessao.scalars(
        select(PropostaGrupo)
        .where(PropostaGrupo.usuario_id == usuario_id, PropostaGrupo.status == "proposta")
        .order_by(PropostaGrupo.criado_em, PropostaGrupo.id)
    )
    return [await _saida_da_proposta(sessao, proposta) for proposta in propostas]


@roteador.post("/propostas", status_code=status.HTTP_201_CREATED)
async def criar_proposta(
    dados: PropostaGrupoCriacao, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> PropostaGrupoSaida:
    bots = list(
        await sessao.scalars(
            select(Agente)
            .where(
                Agente.usuario_id == usuario_id,
                Agente.tipo == TipoAgente.INDIVIDUAL,
                Agente.apagado_em.is_(None),
            )
            .order_by(Agente.criado_em, Agente.id)
            .limit(2)
        )
    )
    rascunhos: list[RascunhoBot] = []
    funcoes = ("Pesquisa e organização", "Produção e revisão")
    for indice in range(2 - len(bots)):
        rascunho = await criar_rascunho(
            sessao,
            usuario_id,
            descricao=dados.pedido,
            funcao=funcoes[len(bots) + indice],
        )
        rascunhos.append(rascunho)
    proposta = PropostaGrupo(
        usuario_id=usuario_id,
        nome=nome_do_pedido(dados.pedido),
        pedido=dados.pedido.strip(),
        bots_reaproveitados=[bot.id for bot in bots],
        bots_novos=[saida_do_rascunho(rascunho).model_dump(mode="json") for rascunho in rascunhos],
    )
    sessao.add(proposta)
    await sessao.flush()
    saida = await _saida_da_proposta(sessao, proposta)
    await sessao.commit()
    await publicar_evento_equipe(redis, _evento_proposta(saida), usuario_id)
    return saida


@roteador.patch("/propostas/{proposta_id}")
async def ajustar_proposta(
    proposta_id: UUID,
    dados: PropostaGrupoAtualizacao,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> PropostaGrupoSaida:
    proposta = await _proposta_do_usuario(sessao, usuario_id, proposta_id, travar=True)
    if proposta.status != "proposta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa proposta já foi resolvida.")
    if dados.nome is not None:
        nome = dados.nome.strip()
        if not 1 <= len(nome) <= MAX_NOME_CANAL:
            raise HTTPException(422, "O nome do grupo precisa ter de 1 a 60 caracteres.")
        proposta.nome = nome
    if dados.bots_reaproveitados is not None:
        ids = list(dict.fromkeys(dados.bots_reaproveitados))
        validos = set(
            await sessao.scalars(
                select(Agente.id).where(
                    Agente.id.in_(ids),
                    Agente.usuario_id == usuario_id,
                    Agente.tipo == TipoAgente.INDIVIDUAL,
                    Agente.apagado_em.is_(None),
                )
            )
        )
        if validos != set(ids):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Use bots ativos da sua conta."
            )
        proposta.bots_reaproveitados = ids
    if dados.bots_novos is not None:
        novos: list[dict] = []
        for ajuste in dados.bots_novos:
            if ajuste.id is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe o id do rascunho."
                )
            rascunho = await obter_rascunho_para_atualizar(sessao, usuario_id, ajuste.id)
            if rascunho is None or rascunho.status != "rascunho":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Rascunho de bot inválido."
                )
            _aplicar_ajustes(rascunho, ajuste)
            novos.append(saida_do_rascunho(rascunho).model_dump(mode="json"))
        mantidos = {item["id"] for item in novos}
        from app.rascunhos_bot import resolver

        for item in proposta.bots_novos:
            if item["id"] not in mantidos:
                removido = await obter_rascunho_para_atualizar(sessao, usuario_id, UUID(item["id"]))
                if removido is not None and removido.status == "rascunho":
                    resolver(removido, "descartado")
        proposta.bots_novos = novos
    total = len(proposta.bots_reaproveitados) + len(proposta.bots_novos)
    if not MIN_BOTS <= total <= MAX_BOTS:
        raise HTTPException(422, f"Escolha de {MIN_BOTS} a {MAX_BOTS} bots.")
    saida = await _saida_da_proposta(sessao, proposta)
    await sessao.commit()
    await publicar_evento_equipe(redis, _evento_proposta(saida), usuario_id)
    return saida


@roteador.post("/propostas/{proposta_id}/aceitar", status_code=status.HTTP_201_CREATED)
async def aceitar_proposta(
    proposta_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> GrupoSaida:
    proposta = await _proposta_do_usuario(sessao, usuario_id, proposta_id, travar=True)
    if proposta.status != "proposta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa proposta já foi resolvida.")
    await sessao.scalar(
        select(UsuarioTabela.id).where(UsuarioTabela.id == usuario_id).with_for_update()
    )
    reaproveitados = list(
        await sessao.scalars(
            select(Agente).where(
                Agente.id.in_(proposta.bots_reaproveitados),
                Agente.usuario_id == usuario_id,
                Agente.tipo == TipoAgente.INDIVIDUAL,
                Agente.apagado_em.is_(None),
            )
        )
    )
    if len(reaproveitados) != len(proposta.bots_reaproveitados):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Um bot reaproveitado não está mais disponível."
        )
    por_id = {bot.id: bot for bot in reaproveitados}
    bots = [por_id[bot_id] for bot_id in proposta.bots_reaproveitados]
    for item in proposta.bots_novos:
        rascunho = await obter_rascunho_para_atualizar(sessao, usuario_id, UUID(str(item["id"])))
        if rascunho is None or rascunho.status != "rascunho":
            raise HTTPException(status.HTTP_409_CONFLICT, "Um rascunho não está mais disponível.")
        bots.append(await _materializar_rascunho(sessao, usuario_id, rascunho))
    if not MIN_BOTS <= len(bots) <= MAX_BOTS:
        raise HTTPException(422, f"Escolha de {MIN_BOTS} a {MAX_BOTS} bots.")

    sora = await _sora_persistente(sessao, usuario_id)
    armazem = ArmazemCanaisSQL(sessao)
    servico = ServicoCanais(armazem)
    try:
        canal = await servico.criar(
            usuario_id=usuario_id,
            nome=proposta.nome,
            membros=[sora.id, *[bot.id for bot in bots]],
            lider_id=sora.id,
            proposito=proposta.pedido,
            agentes_do_usuario={sora.id, *[bot.id for bot in bots]},
        )
        mudancas = await servico.mensagem_do_usuario(
            canal.id,
            usuario_id,
            texto=proposta.pedido,
            membros=[
                Membro(sora.id, sora.nome, sora.funcao),
                *[Membro(bot.id, bot.nome, bot.funcao) for bot in bots],
            ],
        )
    except ErroCanal as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    proposta.status = "aceita"
    proposta.grupo_id = canal.id
    await sessao.commit()
    from app.api.equipe import _despachar, _publicar_mudancas

    await publicar_evento_equipe(redis, _evento(canal, "trabalhando"), usuario_id)
    await _publicar_mudancas(redis, usuario_id, mudancas)
    await publicar_evento_equipe(
        redis,
        GrupoPropostaResolvida(proposta_id=proposta.id, status="aceita", grupo_id=canal.id),
        usuario_id,
    )
    await _despachar(canal_id=canal.id)
    return _saida(canal, "trabalhando")


@roteador.post("/propostas/{proposta_id}/recusar", status_code=status.HTTP_204_NO_CONTENT)
async def recusar_proposta(
    proposta_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    proposta = await _proposta_do_usuario(sessao, usuario_id, proposta_id, travar=True)
    if proposta.status != "proposta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa proposta já foi resolvida.")
    proposta.status = "recusada"
    for item in proposta.bots_novos:
        rascunho = await obter_rascunho_para_atualizar(sessao, usuario_id, UUID(str(item["id"])))
        if rascunho is not None and rascunho.status == "rascunho":
            from app.rascunhos_bot import resolver

            resolver(rascunho, "descartado")
    await sessao.commit()
    await publicar_evento_equipe(
        redis,
        GrupoPropostaResolvida(proposta_id=proposta.id, status="recusada"),
        usuario_id,
    )


@roteador.get("")
async def listar_grupos(
    usuario_id: Usuario, sessao: Sessao, arquivados: bool = False
) -> list[GrupoSaida]:
    canais = [
        canal
        for canal in await ArmazemCanaisSQL(sessao).canais_do_usuario(usuario_id)
        if canal.arquivado == arquivados
    ]
    estados = await estados_dos_grupos(sessao, usuario_id, [canal.id for canal in canais])
    # Grupo antigo pode guardar bot apagado antes da limpeza no DELETE: não aparece na lista.
    apagados = set(
        await sessao.scalars(
            select(Agente.id).where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_not(None))
        )
    )
    saidas = [_saida(canal, estados[canal.id]) for canal in canais]
    for saida in saidas:
        saida.membros = [membro for membro in saida.membros if membro not in apagados]
        saida.precisa_de_bots = len(set(saida.membros) - {saida.lider_id}) < MIN_BOTS
    return saidas


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_grupo(
    dados: GrupoCriacao, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> GrupoSaida:
    sora = await _sora_persistente(sessao, usuario_id)
    bots = await _bots_validos(sessao, usuario_id, dados.membros, sora.id)
    try:
        canal = await ServicoCanais(ArmazemCanaisSQL(sessao)).criar(
            usuario_id=usuario_id,
            nome=dados.nome,
            membros=[sora.id, *bots],
            lider_id=sora.id,
            proposito=dados.proposito,
            instrucoes=dados.instrucoes,
            agentes_do_usuario={sora.id, *bots},
        )
    except ErroCanal as erro:
        raise HTTPException(409, str(erro)) from erro
    await sessao.commit()
    saida = _saida(canal, "livre")
    await publicar_evento_equipe(redis, _evento(canal, "livre"), usuario_id)
    return saida


@roteador.patch("/{grupo_id}")
async def atualizar_grupo(
    grupo_id: UUID,
    dados: GrupoAtualizacao,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> GrupoSaida:
    armazem = ArmazemCanaisSQL(sessao)
    atual = await _grupo_do_usuario(armazem, sessao, usuario_id, grupo_id)
    sora = await _sora_persistente(sessao, usuario_id)
    bots_atuais = [membro for membro in atual.membros if membro != sora.id]
    bots = await _bots_validos(
        sessao, usuario_id, dados.membros if dados.membros is not None else bots_atuais, sora.id
    )
    try:
        await ServicoCanais(armazem).configurar(
            grupo_id,
            usuario_id,
            nome=dados.nome if dados.nome is not None else atual.nome,
            membros=[sora.id, *bots],
            lider_id=sora.id,
            proposito=dados.proposito if dados.proposito is not None else atual.proposito,
            instrucoes=dados.instrucoes if dados.instrucoes is not None else atual.instrucoes,
            agentes_do_usuario={sora.id, *bots},
        )
        canal = await armazem.canal(grupo_id)
        assert canal is not None
    except ErroCanal as erro:
        raise HTTPException(409, str(erro)) from erro
    await sessao.commit()
    estado = (await estados_dos_grupos(sessao, usuario_id, [grupo_id]))[grupo_id]
    await publicar_evento_equipe(redis, _evento(canal, estado), usuario_id)
    return _saida(canal, estado)


@roteador.post("/{grupo_id}/membros/{bot_id}/parar")
async def parar_bot_no_grupo(
    grupo_id: UUID,
    bot_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> list[TarefaCanalAtualizada]:
    """Para todo o trabalho aberto de um bot no grupo; vazio é uma resposta idempotente."""
    from app.api.equipe import _despachar, _publicar_mudancas, _tarefa

    armazem = ArmazemCanaisSQL(sessao)
    canal = await _grupo_do_usuario(armazem, sessao, usuario_id, grupo_id)
    if bot_id == canal.lider_id:
        raise HTTPException(409, "A Sora coordena o grupo e não pode ser parada como um bot.")
    if bot_id not in canal.membros:
        raise HTTPException(404, "Bot não encontrado neste grupo.")
    servico = ServicoCanais(armazem)
    abertas = [
        tarefa
        for tarefa in await servico.tarefas(grupo_id)
        if tarefa.dono_id == bot_id and tarefa.status in EM_ANDAMENTO
    ]
    acumuladas = Mudancas()
    try:
        for tarefa in abertas:
            async with armazem.transacao_tarefa(tarefa.id):
                mudancas = await servico.parar(tarefa.id, usuario_id)
            acumuladas.mensagens.extend(mudancas.mensagens)
            acumuladas.tarefas.extend(mudancas.tarefas)
            acumuladas.interromper.extend(mudancas.interromper)
    except ErroCanal as erro:
        raise HTTPException(409, str(erro)) from erro
    await sessao.commit()
    await _publicar_mudancas(redis, usuario_id, acumuladas)
    if acumuladas.tarefas:
        await _despachar(canal_id=grupo_id)
    unicas = {tarefa.id: tarefa for tarefa in acumuladas.tarefas}
    return [_tarefa(tarefa) for tarefa in unicas.values()]
