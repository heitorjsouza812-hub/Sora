"""Rotas das filas, canais de equipe e reacoes persistidos no PostgreSQL."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_equipe.interrupcao import pedir_interrupcao
from app.canais_equipe.modelos import (
    MAX_INSTRUCOES,
    MAX_MEMBROS,
    MAX_NOME_CANAL,
    MAX_PROPOSITO,
    MAX_TEXTO_MENSAGEM,
    ErroCanal,
    MensagemCanal,
    TarefaCanal,
)
from app.canais_equipe.roteamento import Membro
from app.canais_equipe.servico import Mudancas, ServicoCanais
from app.canais_equipe.sql import ArmazemCanaisSQL
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.correio.reacoes import alternar, resumo
from app.correio.sql import ArmazemReacoesSQL
from app.eventos.equipe import (
    AbaNavegadorEvento,
    CanalAtualizado,
    FilaAtualizada,
    ItemFilaResumo,
    MensagemCanalEvento,
    ReacaoEvento,
    TarefaCanalAtualizada,
    acoes_da_tarefa,
    publicar_evento_equipe,
)
from app.ferramentas.base import ErroFerramenta
from app.filas import LIMITE_TAREFAS_MAXIMO, ErroFila, FilaAgente
from app.filas.sql import ArmazemFilaSQL
from app.modelos.tabelas import (
    AbaNavegador,
    Agente,
    Anexo,
    CanalEquipe,
    Mensagem,
    MensagemCanalTabela,
)
from workers.fila import enfileirar

roteador = APIRouter(tags=["equipe"], dependencies=[Depends(usuario_atual)])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]


class CanalEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=MAX_NOME_CANAL)
    membros: list[UUID] = Field(min_length=1, max_length=MAX_MEMBROS)
    lider_id: UUID | None = None
    proposito: str = Field(default="", max_length=MAX_PROPOSITO)
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES)


class MensagemCanalEntrada(BaseModel):
    texto: str = Field(default="", max_length=MAX_TEXTO_MENSAGEM)
    destinatario: UUID | None = None
    responde_a: UUID | None = None
    anexos: list[UUID] = Field(default_factory=list, max_length=10)


class ReatribuirEntrada(BaseModel):
    novo_dono: UUID


class LimiteEntrada(BaseModel):
    limite_tarefas: int = Field(ge=1, le=LIMITE_TAREFAS_MAXIMO)


class MoverEntrada(BaseModel):
    antes_de: UUID | None = None


class EdicaoEntrada(BaseModel):
    editor: str = Field(min_length=8, max_length=64)
    texto: str | None = Field(default=None, max_length=MAX_TEXTO_MENSAGEM)


class ReacaoEntrada(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)


class PerfilEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=60)


class PerfilDoAgenteEntrada(BaseModel):
    tipo: Literal["compartilhado", "agente", "nomeado"]
    perfil_id: UUID | None = None


def _http(erro: Exception) -> HTTPException:
    codigo = 404 if "encontrad" in str(erro).casefold() else 409
    return HTTPException(codigo, str(erro))


def _canal(canal) -> CanalAtualizado:
    return CanalAtualizado(
        canal_id=canal.id,
        nome=canal.nome,
        membros=canal.membros,
        lider_id=canal.lider_id,
        arquivado=canal.arquivado,
    )


def _mensagem(mensagem: MensagemCanal) -> MensagemCanalEvento:
    return MensagemCanalEvento(
        canal_id=mensagem.canal_id,
        mensagem_id=mensagem.id,
        seq=mensagem.seq,
        autor=mensagem.autor.value,
        agente_id=mensagem.agente_id,
        tipo=mensagem.tipo.value,
        texto=mensagem.texto,
        responde_a=mensagem.responde_a,
        tarefa_id=mensagem.tarefa_id,
        anexos=list(mensagem.anexos),
        criada_em=mensagem.criada_em,
    )


def _tarefa(tarefa: TarefaCanal) -> TarefaCanalAtualizada:
    return TarefaCanalAtualizada(
        canal_id=tarefa.canal_id,
        tarefa_id=tarefa.id,
        dono_id=tarefa.dono_id,
        pai_id=tarefa.pai_id,
        status=tarefa.status.value,
        motivo=tarefa.motivo.value if tarefa.motivo else None,
        revisao=tarefa.revisao,
        acoes=acoes_da_tarefa(tarefa.status.value),
    )


async def _agentes(sessao: AsyncSession, usuario_id: UUID) -> list[Agente]:
    consulta = (
        select(Agente)
        .where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None))
        .order_by(Agente.criado_em, Agente.id)
    )
    return list((await sessao.scalars(consulta)).all())


async def _membros(sessao: AsyncSession, usuario_id: UUID) -> list[Membro]:
    return [
        Membro(agente.id, agente.nome, agente.funcao, not agente.fila_pausada)
        for agente in await _agentes(sessao, usuario_id)
    ]


async def _exigir_agente(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> None:
    existe = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id,
            Agente.usuario_id == usuario_id,
            Agente.apagado_em.is_(None),
        )
    )
    if existe is None:
        raise HTTPException(404, "Agente nao encontrado.")


async def _publicar_mudancas(redis: Redis, usuario_id: UUID, mudancas: Mudancas) -> None:
    await pedir_interrupcao(redis, mudancas.interromper)  # o worker dono do turno para
    for mensagem in mudancas.mensagens:
        await publicar_evento_equipe(redis, _mensagem(mensagem), usuario_id)
    for tarefa in mudancas.tarefas:
        await publicar_evento_equipe(redis, _tarefa(tarefa), usuario_id)


async def _despachar(*, canal_id: UUID | None = None, agente_id: UUID | None = None) -> None:
    await enfileirar(
        "despachar_equipe",
        canal_id=str(canal_id) if canal_id else None,
        agente_id=str(agente_id) if agente_id else None,
    )


@roteador.get("/canais-equipe")
async def listar_canais(
    usuario_id: Usuario, sessao: Sessao, arquivados: bool = False
) -> list[CanalAtualizado]:
    canais = await ArmazemCanaisSQL(sessao).canais_do_usuario(usuario_id)
    return [_canal(canal) for canal in canais if canal.arquivado == arquivados]


@roteador.post("/canais-equipe", status_code=status.HTTP_201_CREATED)
async def criar_canal(
    dados: CanalEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> CanalAtualizado:
    try:
        canal = await ServicoCanais(ArmazemCanaisSQL(sessao)).criar(
            usuario_id=usuario_id,
            **dados.model_dump(),
            agentes_do_usuario={agente.id for agente in await _agentes(sessao, usuario_id)},
        )
    except ErroCanal as erro:
        raise _http(erro) from erro
    await sessao.commit()
    evento = _canal(canal)
    await publicar_evento_equipe(redis, evento, usuario_id)
    return evento


@roteador.put("/canais-equipe/{canal_id}")
async def configurar_canal(
    canal_id: UUID,
    dados: CanalEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> CanalAtualizado:
    servico = ServicoCanais(ArmazemCanaisSQL(sessao))
    try:
        mudancas = await servico.configurar(
            canal_id,
            usuario_id,
            **dados.model_dump(),
            agentes_do_usuario={agente.id for agente in await _agentes(sessao, usuario_id)},
        )
        canal = await servico.canal(canal_id)
    except ErroCanal as erro:
        raise _http(erro) from erro
    await sessao.commit()
    await _publicar_mudancas(redis, usuario_id, mudancas)
    evento = _canal(canal)
    await publicar_evento_equipe(redis, evento, usuario_id)
    await _despachar(canal_id=canal_id)
    return evento


async def _arquivo(
    canal_id: UUID,
    usuario_id: UUID,
    sessao: AsyncSession,
    redis: Redis,
    restaurar: bool,
) -> None:
    servico = ServicoCanais(ArmazemCanaisSQL(sessao))
    try:
        operacao = servico.restaurar if restaurar else servico.arquivar
        mudancas = await operacao(canal_id, usuario_id)
        canal = await servico.canal(canal_id)
    except ErroCanal as erro:
        raise _http(erro) from erro
    await sessao.commit()
    await _publicar_mudancas(redis, usuario_id, mudancas)
    await publicar_evento_equipe(redis, _canal(canal), usuario_id)


@roteador.post("/canais-equipe/{canal_id}/arquivar", status_code=204)
async def arquivar_canal(
    canal_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    await _arquivo(canal_id, usuario_id, sessao, redis, False)


@roteador.post("/canais-equipe/{canal_id}/restaurar", status_code=204)
async def restaurar_canal(
    canal_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    await _arquivo(canal_id, usuario_id, sessao, redis, True)


@roteador.get("/canais-equipe/{canal_id}/mensagens")
async def mensagens_do_canal(
    canal_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    depois_de_seq: int = 0,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[MensagemCanalEvento]:
    try:
        itens = await ServicoCanais(ArmazemCanaisSQL(sessao)).historico(
            canal_id, usuario_id, depois_de_seq=depois_de_seq, limite=limite
        )
    except ErroCanal as erro:
        raise _http(erro) from erro
    return [_mensagem(item) for item in itens]


@roteador.post("/canais-equipe/{canal_id}/mensagens", status_code=202)
async def enviar_ao_canal(
    canal_id: UUID,
    dados: MensagemCanalEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> MensagemCanalEvento:
    if dados.anexos:
        encontrados = set(
            (
                await sessao.scalars(
                    select(Anexo.id).where(
                        Anexo.usuario_id == usuario_id, Anexo.id.in_(dados.anexos)
                    )
                )
            ).all()
        )
        if encontrados != set(dados.anexos):
            raise HTTPException(404, "Anexo nao encontrado.")
    try:
        mudancas = await ServicoCanais(ArmazemCanaisSQL(sessao)).mensagem_do_usuario(
            canal_id,
            usuario_id,
            **dados.model_dump(),
            membros=await _membros(sessao, usuario_id),
        )
    except ErroCanal as erro:
        raise _http(erro) from erro
    await sessao.commit()
    await _publicar_mudancas(redis, usuario_id, mudancas)
    await _despachar(canal_id=canal_id)
    return _mensagem(mudancas.mensagens[0])


@roteador.get("/canais-equipe/{canal_id}/tarefas")
async def tarefas_do_canal(
    canal_id: UUID, usuario_id: Usuario, sessao: Sessao
) -> list[TarefaCanalAtualizada]:
    servico = ServicoCanais(ArmazemCanaisSQL(sessao))
    try:
        canal = await servico.canal(canal_id)
        if canal.usuario_id != usuario_id:
            raise ErroCanal("Canal nao encontrado.")
        tarefas = await servico.tarefas(canal_id)
    except ErroCanal as erro:
        raise _http(erro) from erro
    return [_tarefa(tarefa) for tarefa in tarefas]


async def _controlar_tarefa(
    acao: str,
    tarefa_id: UUID,
    usuario_id: UUID,
    sessao: AsyncSession,
    redis: Redis,
    novo_dono: UUID | None = None,
) -> list[TarefaCanalAtualizada]:
    armazem = ArmazemCanaisSQL(sessao)
    servico = ServicoCanais(armazem)
    disponiveis = {m.id for m in await _membros(sessao, usuario_id) if m.disponivel}
    try:
        async with armazem.transacao_tarefa(tarefa_id):
            if acao == "parar":
                mudancas = await servico.parar(tarefa_id, usuario_id)
            elif acao == "retomar":
                mudancas = await servico.retomar(tarefa_id, usuario_id, disponiveis=disponiveis)
            elif acao == "reatribuir" and novo_dono is not None:
                mudancas = await servico.reatribuir(
                    tarefa_id,
                    usuario_id,
                    novo_dono=novo_dono,
                    disponiveis=disponiveis,
                )
            else:
                mudancas = await servico.cancelar(tarefa_id, usuario_id)
    except ErroCanal as erro:
        raise _http(erro) from erro
    await sessao.commit()
    await _publicar_mudancas(redis, usuario_id, mudancas)
    if mudancas.tarefas:
        await _despachar(canal_id=mudancas.tarefas[0].canal_id)
    return [_tarefa(tarefa) for tarefa in mudancas.tarefas]


@roteador.post("/tarefas-canal/{tarefa_id}/parar")
async def parar_tarefa(
    tarefa_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> list[TarefaCanalAtualizada]:
    return await _controlar_tarefa("parar", tarefa_id, usuario_id, sessao, redis)


@roteador.post("/tarefas-canal/{tarefa_id}/retomar")
async def retomar_tarefa(
    tarefa_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> list[TarefaCanalAtualizada]:
    return await _controlar_tarefa("retomar", tarefa_id, usuario_id, sessao, redis)


@roteador.post("/tarefas-canal/{tarefa_id}/reatribuir")
async def reatribuir_tarefa(
    tarefa_id: UUID,
    dados: ReatribuirEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> TarefaCanalAtualizada:
    tarefas = await _controlar_tarefa(
        "reatribuir", tarefa_id, usuario_id, sessao, redis, dados.novo_dono
    )
    return next(tarefa for tarefa in tarefas if tarefa.tarefa_id == tarefa_id)


@roteador.post("/tarefas-canal/{tarefa_id}/cancelar")
async def cancelar_tarefa(
    tarefa_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> list[TarefaCanalAtualizada]:
    return await _controlar_tarefa("cancelar", tarefa_id, usuario_id, sessao, redis)


async def _evento_fila(fila: FilaAgente, agente_id: UUID) -> FilaAtualizada:
    estado, itens = await fila.visao(agente_id)
    liberacao = await fila.proximos(agente_id)
    return FilaAtualizada(
        agente_id=agente_id,
        pausada=estado.pausada,
        limite_tarefas=estado.limite_tarefas,
        itens=[
            ItemFilaResumo(
                item_id=item.id,
                seq=item.seq,
                pista=item.pista,
                origem=item.origem.value,
                previa=item.texto[:200],
                status=item.status.value,
                esperando_por=(
                    liberacao.esperando[item.id].value if item.id in liberacao.esperando else None
                ),
                em_edicao=bool(item.em_edicao_por),
            )
            for item in itens
        ],
    )


async def _operar_fila(
    agente_id: UUID,
    usuario_id: UUID,
    sessao: AsyncSession,
    redis: Redis,
    acao: str,
    item_id: UUID | None = None,
    dados: Any = None,
) -> FilaAtualizada:
    await _exigir_agente(sessao, usuario_id, agente_id)
    fila = FilaAgente(ArmazemFilaSQL(sessao))
    try:
        if acao == "pausar":
            await fila.pausar(agente_id)
        elif acao == "retomar":
            await fila.retomar(agente_id)
        elif acao == "limite":
            await fila.definir_limite(agente_id, dados.limite_tarefas)
        elif acao == "cancelar":
            await fila.cancelar(item_id, agente_id)
        elif acao == "mover":
            await fila.mover(item_id, agente_id, antes_de=dados.antes_de)
        elif acao == "repetir":
            await fila.repetir(item_id, agente_id)
        elif acao == "comecar":
            await fila.comecar_edicao(item_id, agente_id, dados.editor)
        elif acao == "salvar":
            await fila.salvar_edicao(item_id, agente_id, dados.editor, dados.texto or "")
        elif acao == "descartar":
            await fila.descartar_edicao(item_id, agente_id, dados.editor)
    except ErroFila as erro:
        raise _http(erro) from erro
    await sessao.commit()
    evento = await _evento_fila(fila, agente_id)
    await publicar_evento_equipe(redis, evento, usuario_id)
    if acao in {"retomar", "limite", "mover", "repetir", "salvar", "descartar"}:
        await _despachar(agente_id=agente_id)
    return evento


@roteador.get("/agentes/{agente_id}/fila")
async def fila_do_agente(agente_id: UUID, usuario_id: Usuario, sessao: Sessao) -> FilaAtualizada:
    await _exigir_agente(sessao, usuario_id, agente_id)
    return await _evento_fila(FilaAgente(ArmazemFilaSQL(sessao)), agente_id)


@roteador.post("/agentes/{agente_id}/fila/pausar")
async def pausar_fila(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> FilaAtualizada:
    return await _operar_fila(agente_id, usuario_id, sessao, redis, "pausar")


@roteador.post("/agentes/{agente_id}/fila/retomar")
async def retomar_fila(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> FilaAtualizada:
    return await _operar_fila(agente_id, usuario_id, sessao, redis, "retomar")


@roteador.put("/agentes/{agente_id}/fila/limite")
async def limite_da_fila(
    agente_id: UUID,
    dados: LimiteEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> FilaAtualizada:
    return await _operar_fila(agente_id, usuario_id, sessao, redis, "limite", dados=dados)


@roteador.post("/agentes/{agente_id}/fila/{item_id}/cancelar")
async def cancelar_item(
    agente_id: UUID,
    item_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> FilaAtualizada:
    return await _operar_fila(agente_id, usuario_id, sessao, redis, "cancelar", item_id=item_id)


@roteador.post("/agentes/{agente_id}/fila/{item_id}/mover")
async def mover_item(
    agente_id: UUID,
    item_id: UUID,
    dados: MoverEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> FilaAtualizada:
    return await _operar_fila(
        agente_id, usuario_id, sessao, redis, "mover", item_id=item_id, dados=dados
    )


@roteador.post("/agentes/{agente_id}/fila/{item_id}/repetir")
async def repetir_item(
    agente_id: UUID,
    item_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> FilaAtualizada:
    return await _operar_fila(agente_id, usuario_id, sessao, redis, "repetir", item_id=item_id)


@roteador.post("/agentes/{agente_id}/fila/{item_id}/edicao/{acao}")
async def editar_item(
    agente_id: UUID,
    item_id: UUID,
    acao: Literal["comecar", "salvar", "descartar"],
    dados: EdicaoEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> FilaAtualizada:
    return await _operar_fila(
        agente_id, usuario_id, sessao, redis, acao, item_id=item_id, dados=dados
    )


async def _mensagem_da_conta(sessao: AsyncSession, usuario_id: UUID, mensagem_id: UUID) -> bool:
    conversa = await sessao.scalar(
        select(Mensagem.id)
        .join(Agente, Mensagem.agente_id == Agente.id, isouter=True)
        .where(Mensagem.id == mensagem_id, Agente.usuario_id == usuario_id)
    )
    if conversa is not None:
        return True
    canal = await sessao.scalar(
        select(MensagemCanalTabela.id)
        .join(CanalEquipe, CanalEquipe.id == MensagemCanalTabela.canal_id)
        .where(
            MensagemCanalTabela.id == mensagem_id,
            CanalEquipe.usuario_id == usuario_id,
        )
    )
    return canal is not None


@roteador.post("/mensagens/{mensagem_id}/reacoes")
async def reagir(
    mensagem_id: UUID,
    dados: ReacaoEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> dict[str, int]:
    if not await _mensagem_da_conta(sessao, usuario_id, mensagem_id):
        raise HTTPException(404, "Mensagem nao encontrada.")
    armazem = ArmazemReacoesSQL(sessao, usuario_id)
    try:
        resultado = await alternar(
            armazem, mensagem_id=mensagem_id, emoji=dados.emoji, autor="usuario"
        )
    except ErroFerramenta as erro:
        raise _http(erro) from erro
    await sessao.commit()
    await publicar_evento_equipe(
        redis,
        ReacaoEvento(
            mensagem_id=mensagem_id,
            emoji=resultado.reacao.emoji,
            autor="usuario",
            ligada=resultado.ligada,
        ),
        usuario_id,
    )
    return dict(resumo(await armazem.da_mensagem(mensagem_id)))


def _fora_do_escopo() -> None:
    raise HTTPException(501, "Esta peca sera ligada pelo dono do escopo nesta etapa.")


@roteador.get("/navegador/abas")
async def abas_abertas(
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    agente_id: UUID | None = None,
) -> list[AbaNavegadorEvento]:
    consulta = select(AbaNavegador).where(AbaNavegador.usuario_id == usuario_id)
    if agente_id is not None:
        consulta = consulta.where(AbaNavegador.agente_id == agente_id)
    abas = list((await sessao.scalars(consulta.order_by(AbaNavegador.usada_em.desc()))).all())
    return [await _evento_aba(redis, aba) for aba in abas]


@roteador.post("/navegador/abas/{aba_id}/assumir")
async def assumir_aba(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> AbaNavegadorEvento:
    aba = await _aba_da_conta(sessao, usuario_id, aba_id)
    await redis.set(f"navegador:assumida:{aba.id}", "1")
    evento = await _evento_aba(redis, aba)
    await publicar_evento_equipe(redis, evento, usuario_id)
    return evento


@roteador.post("/navegador/abas/{aba_id}/devolver")
async def devolver_aba(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> AbaNavegadorEvento:
    aba = await _aba_da_conta(sessao, usuario_id, aba_id)
    await redis.delete(f"navegador:assumida:{aba.id}")
    evento = await _evento_aba(redis, aba)
    await publicar_evento_equipe(redis, evento, usuario_id)
    return evento


@roteador.delete("/navegador/abas/{aba_id}", status_code=204)
async def fechar_aba(aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep) -> None:
    aba = await _aba_da_conta(sessao, usuario_id, aba_id)
    await sessao.delete(aba)
    await sessao.commit()
    await redis.delete(f"navegador:assumida:{aba.id}")
    await redis.set(f"navegador:fechada:{aba.id}", "1", ex=24 * 60 * 60)
    await publicar_evento_equipe(
        redis,
        AbaNavegadorEvento(
            aba_id=aba.id,
            agente_id=aba.agente_id,
            url=aba.url,
            titulo=aba.titulo,
            carregada=False,
            assumida_pelo_usuario=False,
            fechada=True,
        ),
        usuario_id,
    )


async def _aba_da_conta(sessao: AsyncSession, usuario_id: UUID, aba_id: UUID) -> AbaNavegador:
    aba = await sessao.scalar(
        select(AbaNavegador).where(AbaNavegador.id == aba_id, AbaNavegador.usuario_id == usuario_id)
    )
    if aba is None:
        raise HTTPException(404, "Aba não encontrada.")
    return aba


async def _evento_aba(redis: Redis, aba: AbaNavegador) -> AbaNavegadorEvento:
    assumida = bool(await redis.exists(f"navegador:assumida:{aba.id}"))
    return AbaNavegadorEvento(
        aba_id=aba.id,
        agente_id=aba.agente_id,
        url=aba.url,
        titulo=aba.titulo,
        carregada=False,
        assumida_pelo_usuario=assumida,
    )


@roteador.get("/navegador/perfis")
async def perfis_do_navegador() -> list[dict[str, str]]:
    _fora_do_escopo()


@roteador.post("/navegador/perfis", status_code=201)
async def criar_perfil(dados: PerfilEntrada) -> dict[str, str]:
    _fora_do_escopo()


@roteador.delete("/navegador/perfis/{perfil_id}", status_code=204)
async def apagar_perfil(perfil_id: UUID) -> None:
    _fora_do_escopo()


@roteador.put("/agentes/{agente_id}/navegador")
async def perfil_do_agente(agente_id: UUID, dados: PerfilDoAgenteEntrada) -> None:
    _fora_do_escopo()
