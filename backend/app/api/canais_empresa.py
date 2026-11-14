"""Rotas dos canais da empresa (Ponte): conexões com Slack e WhatsApp Business (só leitura),
webhooks, clientes e fichas, autorizações, base de conhecimento e sugestões de melhoria.

A Sora nunca envia nada por esses canais. Os webhooks não usam login: a origem é conferida pela
assinatura (``X-Slack-Signature``; ``X-Hub-Signature-256`` e o handshake do GET na Meta). Detalhes
e campos em ``docs/canais-da-empresa.md``.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa import acesso, clientes, conexoes, ingestao, lgpd, sugestoes
from app.canais_empresa import conhecimento as base
from app.canais_empresa.assinaturas import handshake_meta_valido, meta_autentico, slack_autentico
from app.canais_empresa.eventos import ClienteAtualizado, ConhecimentoAtualizado, publicar
from app.canais_empresa.extracao import CATEGORIAS
from app.canais_empresa.pii import anonimizar_para_conhecimento, mascarar_pii
from app.canais_empresa.tabelas import (
    ConexaoCanalEmpresa,
    ConhecimentoEmpresa,
    ContatoEmpresa,
    FatoCliente,
    PreferenciasCanaisEmpresa,
    SugestaoMelhoria,
)
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual

registro = logging.getLogger(__name__)

roteador = APIRouter(prefix="/canais-empresa", tags=["canais-empresa"])
roteador_webhooks = APIRouter(prefix="/canais-empresa/webhooks", tags=["canais-empresa"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_CORPO_WEBHOOK = 1_000_000
ATRASO_DO_RESUMO_SEGUNDOS = 60


# ----------------------------------------------------------------------------- esquemas


class ConexaoSaida(BaseModel):
    canal: str
    configurada: bool
    id: UUID | None = None
    rotulo: str = ""
    ativa: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    segredos_definidos: dict[str, bool] = Field(default_factory=dict)
    canais_escolhidos: list[str] = Field(default_factory=list)
    webhook_caminho: str | None = None
    ultimo_teste_em: datetime | None = None
    ultimo_teste_ok: bool | None = None
    ultimo_teste_detalhe: str | None = None
    escopos_slack: list[str] = Field(default_factory=list)
    """Escopos que o app do Slack deve pedir (só leitura). Vazio no WhatsApp."""


class ConexaoEntrada(BaseModel):
    rotulo: str | None = Field(default=None, max_length=80)
    segredos: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    ativa: bool | None = None


class CanaisEscolhidosEntrada(BaseModel):
    canais: list[str] = Field(max_length=200)


class TesteSaida(BaseModel):
    ok: bool
    detalhe: str
    avisos: list[str] = Field(default_factory=list)


class FatoSaida(BaseModel):
    id: UUID
    tipo: str
    texto: str
    data_referencia: date | None
    origem_canal: str
    origem_link: str | None
    origem_externo_id: str | None
    editado: bool
    criado_em: datetime


class ClienteResumo(BaseModel):
    id: UUID
    canal: str
    nome: str
    id_externo: str
    papel: str
    ultima_mensagem_em: datetime | None
    total_fatos: int


class FichaSaida(ClienteResumo):
    fatos: list[FatoSaida]


class ClienteEntrada(BaseModel):
    nome: str | None = Field(default=None, max_length=120)
    papel: Literal["cliente", "funcionario"] | None = None


class FatoEntrada(BaseModel):
    texto: str | None = Field(default=None, min_length=1, max_length=300)
    tipo: (
        Literal["preferencia", "pedido", "promessa", "prazo", "reclamacao", "dado_de_contato"]
        | None
    ) = None
    data_referencia: date | None = None
    limpar_data: bool = False


class AutorizacaoSaida(BaseModel):
    alvo_tipo: str
    alvo_id: UUID
    escopos: list[str]


class AutorizacaoEntrada(BaseModel):
    alvo_tipo: Literal["agente", "grupo"]
    alvo_id: UUID
    escopos: list[Literal["clientes", "conhecimento"]]


class PreferenciasSaida(BaseModel):
    retencao_dias: int
    sugestoes_intervalo_dias: int
    ultima_analise_em: datetime | None


class PreferenciasEntrada(BaseModel):
    retencao_dias: int | None = Field(
        default=None, ge=lgpd.RETENCAO_MIN_DIAS, le=lgpd.RETENCAO_MAX_DIAS
    )
    sugestoes_intervalo_dias: int | None = Field(default=None, ge=0, le=90)
    """0 desliga a análise periódica."""


class ConhecimentoSaida(BaseModel):
    id: UUID
    categoria: str
    titulo: str
    conteudo: str
    ocorrencias: int
    contraditorio: bool
    editado: bool
    anteriores: list[dict[str, Any]]
    origens: list[dict[str, Any]]
    primeira_em: datetime
    ultima_em: datetime


class ConhecimentoEntrada(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    conteudo: str | None = Field(default=None, min_length=1, max_length=800)
    categoria: Literal["faq", "produto", "politica", "processo", "tom_de_voz", "objecao"] | None = (
        None
    )


class SugestaoSaida(BaseModel):
    id: UUID
    agente_id: UUID
    tipo: str
    titulo: str
    motivo: str
    texto: str
    habilidade_nome: str | None
    conhecimento_ids: list[str]
    status: str
    aprovacao_id: UUID | None
    criada_em: datetime
    decidida_em: datetime | None
    desfeita_em: datetime | None


class SugestaoEntrada(BaseModel):
    texto: str = Field(min_length=1, max_length=sugestoes.MAX_TEXTO)


def _erro(erro: Exception, codigo: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(codigo, str(erro))


# ----------------------------------------------------------------------------- conexões


def _saida_conexao(canal: str, c: ConexaoCanalEmpresa | None) -> ConexaoSaida:
    escopos = list(clientes.ESCOPOS_DE_LEITURA) if canal == "slack" else []
    if c is None:
        return ConexaoSaida(canal=canal, configurada=False, escopos_slack=escopos)
    try:
        definidos = set(conexoes.decifrar_segredos(c))
    except Exception:
        definidos = set()
    return ConexaoSaida(
        canal=canal,
        configurada=True,
        id=c.id,
        rotulo=c.rotulo,
        ativa=c.ativa,
        config=c.config,
        segredos_definidos={k: k in definidos for k in conexoes.SEGREDOS_DO_CANAL[canal]},
        canais_escolhidos=c.canais_escolhidos,
        webhook_caminho=conexoes.caminho_do_webhook(c),
        ultimo_teste_em=c.ultimo_teste_em,
        ultimo_teste_ok=c.ultimo_teste_ok,
        ultimo_teste_detalhe=c.ultimo_teste_detalhe,
        escopos_slack=escopos,
    )


@roteador.get("/conexoes")
async def listar_conexoes(usuario_id: Usuario, sessao: Sessao) -> list[ConexaoSaida]:
    return [
        _saida_conexao(canal, await conexoes.obter(sessao, usuario_id, canal))
        for canal in conexoes.CANAIS
    ]


@roteador.put("/conexoes/{canal}")
async def salvar_conexao(
    canal: str, dados: ConexaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> ConexaoSaida:
    """Cria ou atualiza a conexão. Na atualização, segredo omitido é mantido."""
    try:
        conexoes.validar_canal(canal)
        existente = await conexoes.obter(sessao, usuario_id, canal)
        novos = conexoes.limpar_segredos(canal, dados.segredos, completo=existente is None)
        config = (
            conexoes.limpar_config(canal, dados.config, completo=True)
            if existente is None
            else {**existente.config, **conexoes.limpar_config(canal, dados.config, completo=False)}
        )
    except conexoes.ErroConexao as erro:
        raise _erro(erro) from erro
    if existente is None:
        existente = ConexaoCanalEmpresa(
            usuario_id=usuario_id,
            canal=canal,
            rotulo=(dados.rotulo or "").strip(),
            config=config,
            segredos=conexoes.cifrar_segredos(novos, usuario_id=usuario_id, canal=canal),
            canais_escolhidos=[],
            ativa=True if dados.ativa is None else dados.ativa,
        )
        sessao.add(existente)
    else:
        if novos:
            atuais = conexoes.decifrar_segredos(existente)
            existente.segredos = conexoes.cifrar_segredos(
                {**atuais, **novos}, usuario_id=usuario_id, canal=canal
            )
            existente.ultimo_teste_ok = None
        existente.config = config
        if dados.rotulo is not None:
            existente.rotulo = dados.rotulo.strip()
        if dados.ativa is not None:
            existente.ativa = dados.ativa
        existente.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_conexao(canal, existente)


@roteador.delete("/conexoes/{canal}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conexao(canal: str, usuario_id: Usuario, sessao: Sessao) -> None:
    """Remove a conexão **e tudo que veio dela** (contatos, mensagens e fichas)."""
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    await sessao.delete(c)


@roteador.put("/conexoes/{canal}/canais")
async def escolher_canais(
    canal: str, dados: CanaisEscolhidosEntrada, usuario_id: Usuario, sessao: Sessao
) -> ConexaoSaida:
    """Os canais do Slack (ids) ou o número do WhatsApp (phone_number_id) que a Sora lê.
    Só o que estiver aqui entra; o resto do workspace é ignorado."""
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    try:
        c.canais_escolhidos = conexoes.validar_canais_escolhidos(canal, dados.canais)
    except conexoes.ErroConexao as erro:
        raise _erro(erro) from erro
    c.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_conexao(canal, c)


@roteador.post("/conexoes/{canal}/testar")
async def testar_conexao(canal: str, usuario_id: Usuario, sessao: Sessao) -> TesteSaida:
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    segredos = conexoes.decifrar_segredos(c)
    avisos: list[str] = []
    try:
        http = clientes.fabrica_http()
        if canal == "slack":
            info = await clientes.ClienteSlackLeitura(segredos["bot_token"], cliente=http).testar()
            escrita = clientes.escopos_de_escrita(info["escopos"])
            if escrita:
                resultado = TesteSaida(
                    ok=False,
                    detalhe=(
                        "Este token pode enviar mensagens (" + ", ".join(escrita) + "). A Sora só "
                        "lê: reinstale o app do Slack só com "
                        + ", ".join(clientes.ESCOPOS_DE_LEITURA)
                        + "."
                    ),
                )
            else:
                faltam = sorted(set(clientes.ESCOPOS_DE_LEITURA) - set(info["escopos"]))
                if info["escopos"] and faltam:
                    avisos.append("Faltam escopos de leitura: " + ", ".join(faltam) + ".")
                c.config = {
                    **c.config,
                    "team_id": info["team_id"],
                    "bot_user_id": info["user_id"],
                    **({"workspace": info["team"]} if info["team"] else {}),
                }
                resultado = TesteSaida(
                    ok=True, detalhe=f"Conectado ao workspace {info['team'] or info['team_id']}."
                )
        else:
            info = await clientes.ClienteWhatsAppLeitura(
                segredos["access_token"], cliente=http
            ).testar(str(c.config.get("phone_number_id", "")))
            c.config = {
                **c.config,
                "numero_exibicao": info["numero"] or c.config.get("numero_exibicao", ""),
            }
            resultado = TesteSaida(
                ok=True,
                detalhe=(
                    f"Número {info['numero'] or c.config.get('phone_number_id')} ({info['nome']})."
                ),
            )
    except clientes.ErroCanalEmpresa as erro:
        resultado = TesteSaida(ok=False, detalhe=str(erro))
    resultado.avisos = avisos
    c.ultimo_teste_em = datetime.now(UTC)
    c.ultimo_teste_ok = resultado.ok
    c.ultimo_teste_detalhe = resultado.detalhe
    await sessao.flush()
    return resultado


class CanalDoSlack(BaseModel):
    id: str
    nome: str
    privado: bool


@roteador.get("/conexoes/slack/canais-disponiveis")
async def canais_disponiveis(usuario_id: Usuario, sessao: Sessao) -> list[CanalDoSlack]:
    """Canais que o bot do Slack enxerga, para o usuário marcar quais a Sora lê."""
    c = await conexoes.obter(sessao, usuario_id, "slack")
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    try:
        lista = await clientes.ClienteSlackLeitura(
            conexoes.decifrar_segredos(c)["bot_token"], cliente=clientes.fabrica_http()
        ).listar_canais()
    except clientes.ErroCanalEmpresa as erro:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(erro)) from erro
    return [CanalDoSlack(**item) for item in lista]


# ----------------------------------------------------------------------------- webhooks


async def _corpo_limitado(requisicao: Request) -> bytes:
    declarado = requisicao.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > LIMITE_CORPO_WEBHOOK:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    corpo = await requisicao.body()
    if len(corpo) > LIMITE_CORPO_WEBHOOK:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    return corpo


async def _conexao_do_webhook(
    sessao: AsyncSession, conexao_id: UUID, canal: str
) -> ConexaoCanalEmpresa:
    c = await sessao.get(ConexaoCanalEmpresa, conexao_id)
    if c is None or c.canal != canal or not c.ativa:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return c


async def _enfileirar_resumo(usuario_id: UUID) -> None:
    """Põe o resumo na fila (adiado, para juntar as mensagens de uma mesma conversa). Se a fila
    falhar nada se perde: as mensagens já estão no banco e a rotina do worker as pega."""
    try:
        from workers.fila import enfileirar

        agora = datetime.now(UTC)
        await enfileirar(
            "processar_canais_empresa",
            id_job=f"ce:{usuario_id}:{int(time.time() // 60)}",
            agendar_para=agora + timedelta(seconds=ATRASO_DO_RESUMO_SEGUNDOS),
            usuario_id=str(usuario_id),
        )
    except Exception:
        registro.warning("não consegui enfileirar o resumo dos canais da empresa", exc_info=True)


async def _guardar(
    sessao: AsyncSession, c: ConexaoCanalEmpresa, mensagens: list[ingestao.MensagemNormalizada]
) -> int:
    novas = await ingestao.registrar_mensagens(sessao, c, mensagens)
    if novas:
        await sessao.commit()
        await _enfileirar_resumo(c.usuario_id)
    return len(novas)


@roteador_webhooks.post("/slack/{conexao_id}", include_in_schema=False)
async def webhook_slack(
    conexao_id: UUID,
    requisicao: Request,
    sessao: Sessao,
    timestamp: Annotated[str | None, Header(alias="X-Slack-Request-Timestamp")] = None,
    assinatura: Annotated[str | None, Header(alias="X-Slack-Signature")] = None,
) -> Response:
    corpo = await _corpo_limitado(requisicao)
    c = await _conexao_do_webhook(sessao, conexao_id, "slack")
    segredos = conexoes.decifrar_segredos(c)
    if not slack_autentico(segredos.get("signing_secret", ""), corpo, timestamp, assinatura):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Assinatura inválida.")
    try:
        carga = json.loads(corpo)
    except ValueError as erro:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.") from erro
    if not isinstance(carga, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.")
    if carga.get("type") == "url_verification" and isinstance(carga.get("challenge"), str):
        return Response(
            json.dumps({"challenge": carga["challenge"]}), media_type="application/json"
        )
    await _guardar(sessao, c, ingestao.normalizar_slack(carga, c.config, c.canais_escolhidos))
    return Response(json.dumps({"ok": True}), media_type="application/json")


@roteador_webhooks.get("/whatsapp/{conexao_id}", include_in_schema=False)
async def verificar_whatsapp(
    conexao_id: UUID,
    sessao: Sessao,
    modo: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    desafio: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Handshake da Meta ao cadastrar o webhook: devolve ``hub.challenge`` em texto puro."""
    c = await _conexao_do_webhook(sessao, conexao_id, "whatsapp")
    segredos = conexoes.decifrar_segredos(c)
    if not handshake_meta_valido(segredos.get("verify_token", ""), modo, token) or desafio is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return Response(desafio, media_type="text/plain")


@roteador_webhooks.post("/whatsapp/{conexao_id}", include_in_schema=False)
async def webhook_whatsapp(
    conexao_id: UUID,
    requisicao: Request,
    sessao: Sessao,
    assinatura: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> Response:
    corpo = await _corpo_limitado(requisicao)
    c = await _conexao_do_webhook(sessao, conexao_id, "whatsapp")
    segredos = conexoes.decifrar_segredos(c)
    if not meta_autentico(segredos.get("app_secret", ""), corpo, assinatura):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Assinatura inválida.")
    try:
        carga = json.loads(corpo)
    except ValueError as erro:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.") from erro
    if isinstance(carga, dict):
        await _guardar(sessao, c, ingestao.normalizar_whatsapp(carga, c.canais_escolhidos))
    return Response(json.dumps({"ok": True}), media_type="application/json")


# ----------------------------------------------------------------------------- clientes e fichas


def _fato_saida(f: FatoCliente) -> FatoSaida:
    return FatoSaida(
        id=f.id,
        tipo=f.tipo,
        texto=f.texto,
        data_referencia=f.data_referencia,
        origem_canal=f.origem_canal,
        origem_link=f.origem_link,
        origem_externo_id=f.origem_externo_id,
        editado=f.editado,
        criado_em=f.criado_em,
    )


@roteador.get("/clientes")
async def listar_clientes(
    usuario_id: Usuario,
    sessao: Sessao,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    canal: Annotated[Literal["slack", "whatsapp"] | None, Query()] = None,
    papel: Annotated[Literal["cliente", "funcionario"], Query()] = "cliente",
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[ClienteResumo]:
    total = (
        select(FatoCliente.contato_id, func.count().label("n"))
        .where(FatoCliente.usuario_id == usuario_id)
        .group_by(FatoCliente.contato_id)
        .subquery()
    )
    consulta = (
        select(ContatoEmpresa, func.coalesce(total.c.n, 0))
        .outerjoin(total, total.c.contato_id == ContatoEmpresa.id)
        .where(ContatoEmpresa.usuario_id == usuario_id, ContatoEmpresa.papel == papel)
    )
    if canal:
        consulta = consulta.where(ContatoEmpresa.canal == canal)
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            ContatoEmpresa.nome.ilike(termo) | ContatoEmpresa.id_externo.ilike(termo)
        )
    linhas = await sessao.execute(
        consulta.order_by(ContatoEmpresa.ultima_mensagem_em.desc().nulls_last(), ContatoEmpresa.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return [
        ClienteResumo(
            id=c.id,
            canal=c.canal,
            nome=c.nome,
            id_externo=c.id_externo,
            papel=c.papel,
            ultima_mensagem_em=c.ultima_mensagem_em,
            total_fatos=n,
        )
        for c, n in linhas.all()
    ]


async def _contato(sessao: AsyncSession, usuario_id: UUID, contato_id: UUID) -> ContatoEmpresa:
    c = await sessao.scalar(
        select(ContatoEmpresa).where(
            ContatoEmpresa.id == contato_id, ContatoEmpresa.usuario_id == usuario_id
        )
    )
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return c


async def _ficha(sessao: AsyncSession, c: ContatoEmpresa) -> FichaSaida:
    fatos = (
        await sessao.scalars(
            select(FatoCliente)
            .where(FatoCliente.contato_id == c.id, FatoCliente.usuario_id == c.usuario_id)
            .order_by(FatoCliente.tipo, FatoCliente.criado_em)
        )
    ).all()
    return FichaSaida(
        id=c.id,
        canal=c.canal,
        nome=c.nome,
        id_externo=c.id_externo,
        papel=c.papel,
        ultima_mensagem_em=c.ultima_mensagem_em,
        total_fatos=len(fatos),
        fatos=[_fato_saida(f) for f in fatos],
    )


@roteador.get("/clientes/{contato_id}")
async def ver_cliente(contato_id: UUID, usuario_id: Usuario, sessao: Sessao) -> FichaSaida:
    return await _ficha(sessao, await _contato(sessao, usuario_id, contato_id))


@roteador.patch("/clientes/{contato_id}")
async def editar_cliente(
    contato_id: UUID, dados: ClienteEntrada, usuario_id: Usuario, sessao: Sessao
) -> FichaSaida:
    c = await _contato(sessao, usuario_id, contato_id)
    if dados.nome is not None:
        c.nome = mascarar_pii(dados.nome.strip())
    if dados.papel is not None:
        c.papel = dados.papel
    await sessao.flush()
    return await _ficha(sessao, c)


@roteador.delete("/clientes/{contato_id}")
async def apagar_cliente(
    contato_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> dict[str, int]:
    """LGPD: apaga a ficha, as mensagens e o que a Sora aprendeu a partir deste cliente."""
    contato = await _contato(sessao, usuario_id, contato_id)
    canal = contato.canal
    contagem = await lgpd.apagar_cliente(sessao, usuario_id, contato_id)
    if contagem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    await sessao.commit()
    await publicar(
        redis,
        ClienteAtualizado(contato_id=contato_id, canal=canal, motivo="apagado"),
        usuario_id,
    )
    if contagem["conhecimento_limpo"] or contagem["conhecimento_removido"]:
        await publicar(redis, ConhecimentoAtualizado(motivo="remocao"), usuario_id)
    return contagem


async def _fato(sessao: AsyncSession, usuario_id: UUID, fato_id: UUID) -> FatoCliente:
    f = await sessao.scalar(
        select(FatoCliente).where(FatoCliente.id == fato_id, FatoCliente.usuario_id == usuario_id)
    )
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fato não encontrado.")
    return f


async def _total_fatos(sessao: AsyncSession, contato_id: UUID) -> int:
    return (
        await sessao.scalar(
            select(func.count())
            .select_from(FatoCliente)
            .where(FatoCliente.contato_id == contato_id)
        )
        or 0
    )


@roteador.patch("/fatos/{fato_id}")
async def editar_fato(
    fato_id: UUID, dados: FatoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> FatoSaida:
    f = await _fato(sessao, usuario_id, fato_id)
    if dados.texto is not None:
        f.texto = mascarar_pii(" ".join(dados.texto.split()))[:300]
    if dados.tipo is not None:
        f.tipo = dados.tipo
    if dados.limpar_data:
        f.data_referencia = None
    elif dados.data_referencia is not None:
        f.data_referencia = dados.data_referencia
    f.editado = True
    f.atualizado_em = datetime.now(UTC)
    await sessao.commit()
    contato = await sessao.get(ContatoEmpresa, f.contato_id)
    await publicar(
        redis,
        ClienteAtualizado(
            contato_id=f.contato_id,
            canal=contato.canal if contato else "",
            total_fatos=await _total_fatos(sessao, f.contato_id),
            motivo="edicao",
        ),
        usuario_id,
    )
    return _fato_saida(f)


@roteador.delete("/fatos/{fato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_fato(fato_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep) -> None:
    f = await _fato(sessao, usuario_id, fato_id)
    contato_id = f.contato_id
    contato = await sessao.get(ContatoEmpresa, contato_id)
    await sessao.delete(f)
    await sessao.commit()
    await publicar(
        redis,
        ClienteAtualizado(
            contato_id=contato_id,
            canal=contato.canal if contato else "",
            total_fatos=await _total_fatos(sessao, contato_id),
            motivo="remocao",
        ),
        usuario_id,
    )


# ---------------------------------------------------------------- autorizações e preferências


@roteador.get("/autorizacoes")
async def listar_autorizacoes(usuario_id: Usuario, sessao: Sessao) -> list[AutorizacaoSaida]:
    agrupadas: dict[tuple[str, UUID], list[str]] = {}
    for a in await acesso.listar(sessao, usuario_id):
        agrupadas.setdefault((a.alvo_tipo, a.alvo_id), []).append(a.escopo)
    return [AutorizacaoSaida(alvo_tipo=t, alvo_id=i, escopos=e) for (t, i), e in agrupadas.items()]


@roteador.put("/autorizacoes")
async def definir_autorizacao(
    dados: AutorizacaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> AutorizacaoSaida:
    """Define exatamente quais escopos (``clientes``, ``conhecimento``) o bot ou grupo tem."""
    try:
        escopos = await acesso.definir(
            sessao, usuario_id, dados.alvo_tipo, dados.alvo_id, list(dados.escopos)
        )
    except acesso.ErroAcesso as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    return AutorizacaoSaida(alvo_tipo=dados.alvo_tipo, alvo_id=dados.alvo_id, escopos=escopos)


async def _preferencias(sessao: AsyncSession, usuario_id: UUID) -> PreferenciasCanaisEmpresa:
    prefs = await sessao.get(PreferenciasCanaisEmpresa, usuario_id)
    if prefs is None:
        prefs = PreferenciasCanaisEmpresa(
            usuario_id=usuario_id,
            retencao_dias=lgpd.RETENCAO_PADRAO_DIAS,
            sugestoes_intervalo_dias=7,
        )
        sessao.add(prefs)
        await sessao.flush()
    return prefs


def _saida_prefs(p: PreferenciasCanaisEmpresa) -> PreferenciasSaida:
    return PreferenciasSaida(
        retencao_dias=p.retencao_dias,
        sugestoes_intervalo_dias=p.sugestoes_intervalo_dias,
        ultima_analise_em=p.ultima_analise_em,
    )


@roteador.get("/preferencias")
async def ver_preferencias(usuario_id: Usuario, sessao: Sessao) -> PreferenciasSaida:
    return _saida_prefs(await _preferencias(sessao, usuario_id))


@roteador.put("/preferencias")
async def salvar_preferencias(
    dados: PreferenciasEntrada, usuario_id: Usuario, sessao: Sessao
) -> PreferenciasSaida:
    prefs = await _preferencias(sessao, usuario_id)
    if dados.retencao_dias is not None:
        prefs.retencao_dias = dados.retencao_dias
    if dados.sugestoes_intervalo_dias is not None:
        prefs.sugestoes_intervalo_dias = dados.sugestoes_intervalo_dias
    prefs.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_prefs(prefs)


# ----------------------------------------------------------------------------- conhecimento


def _saida_conhecimento(i: ConhecimentoEmpresa) -> ConhecimentoSaida:
    return ConhecimentoSaida(
        id=i.id,
        categoria=i.categoria,
        titulo=i.titulo,
        conteudo=i.conteudo,
        ocorrencias=i.ocorrencias,
        contraditorio=i.contraditorio,
        editado=i.travado,
        anteriores=i.anteriores,
        origens=i.origens,
        primeira_em=i.primeira_em,
        ultima_em=i.ultima_em,
    )


@roteador.get("/conhecimento")
async def listar_conhecimento(
    usuario_id: Usuario,
    sessao: Sessao,
    busca: Annotated[str | None, Query(max_length=300)] = None,
    categoria: Annotated[str | None, Query()] = None,
    contraditorio: Annotated[bool | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[ConhecimentoSaida]:
    if categoria is not None and categoria not in CATEGORIAS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Categoria inválida.")
    if busca and busca.strip():
        itens = await base.buscar(
            sessao, usuario_id, busca, categoria=categoria, limite=limite + deslocamento
        )
        if contraditorio is not None:
            itens = [i for i in itens if i.contraditorio == contraditorio]
        return [_saida_conhecimento(i) for i in itens[deslocamento : deslocamento + limite]]
    consulta = select(ConhecimentoEmpresa).where(
        ConhecimentoEmpresa.usuario_id == usuario_id, ConhecimentoEmpresa.apagado_em.is_(None)
    )
    if categoria:
        consulta = consulta.where(ConhecimentoEmpresa.categoria == categoria)
    if contraditorio is not None:
        consulta = consulta.where(ConhecimentoEmpresa.contraditorio == contraditorio)
    itens = await sessao.scalars(
        consulta.order_by(
            ConhecimentoEmpresa.ocorrencias.desc(), ConhecimentoEmpresa.ultima_em.desc()
        )
        .limit(limite)
        .offset(deslocamento)
    )
    return [_saida_conhecimento(i) for i in itens.all()]


async def _item(sessao: AsyncSession, usuario_id: UUID, item_id: UUID) -> ConhecimentoEmpresa:
    i = await sessao.scalar(
        select(ConhecimentoEmpresa).where(
            ConhecimentoEmpresa.id == item_id,
            ConhecimentoEmpresa.usuario_id == usuario_id,
            ConhecimentoEmpresa.apagado_em.is_(None),
        )
    )
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item não encontrado.")
    return i


@roteador.patch("/conhecimento/{item_id}")
async def editar_conhecimento(
    item_id: UUID, dados: ConhecimentoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> ConhecimentoSaida:
    """Editar trava o item: o aprendizado automático passa a só contar, sem sobrescrever."""
    i = await _item(sessao, usuario_id, item_id)
    if dados.titulo is not None:
        i.titulo = anonimizar_para_conhecimento(" ".join(dados.titulo.split()))[:200]
    if dados.conteudo is not None:
        i.conteudo = anonimizar_para_conhecimento(" ".join(dados.conteudo.split()))[:800]
    if dados.categoria is not None:
        i.categoria = dados.categoria
    i.chave = f"editado:{i.id}"
    i.travado = True
    i.contraditorio = False
    i.atualizado_em = datetime.now(UTC)
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="edicao"), usuario_id)
    return _saida_conhecimento(i)


@roteador.delete("/conhecimento/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conhecimento(
    item_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    """Esconde o item e impede que o aprendizado automático o traga de volta."""
    i = await _item(sessao, usuario_id, item_id)
    i.apagado_em = datetime.now(UTC)
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="remocao"), usuario_id)


# ----------------------------------------------------------------------------- sugestões


def _saida_sugestao(s: SugestaoMelhoria) -> SugestaoSaida:
    return SugestaoSaida(
        id=s.id,
        agente_id=s.agente_id,
        tipo=s.tipo,
        titulo=s.titulo,
        motivo=s.motivo,
        texto=s.texto,
        habilidade_nome=s.habilidade_nome,
        conhecimento_ids=s.conhecimento_ids,
        status=s.status,
        aprovacao_id=s.aprovacao_id,
        criada_em=s.criada_em,
        decidida_em=s.decidida_em,
        desfeita_em=s.desfeita_em,
    )


@roteador.get("/sugestoes")
async def listar_sugestoes(
    usuario_id: Usuario,
    sessao: Sessao,
    situacao: Annotated[
        Literal["pendente", "aplicada", "descartada", "desfeita"] | None, Query(alias="status")
    ] = None,
    agente_id: Annotated[UUID | None, Query()] = None,
) -> list[SugestaoSaida]:
    consulta = select(SugestaoMelhoria).where(SugestaoMelhoria.usuario_id == usuario_id)
    if situacao:
        consulta = consulta.where(SugestaoMelhoria.status == situacao)
    if agente_id:
        consulta = consulta.where(SugestaoMelhoria.agente_id == agente_id)
    linhas = await sessao.scalars(
        consulta.order_by(SugestaoMelhoria.criada_em.desc(), SugestaoMelhoria.id).limit(200)
    )
    return [_saida_sugestao(s) for s in linhas.all()]


async def _publicar_sugestao(
    redis: Redis, sessao: AsyncSession, usuario_id: UUID, s: SugestaoMelhoria, motivo: str
) -> None:
    from app.atencao import publicar_estado_atencao

    pendentes = (
        await sessao.scalar(
            select(func.count())
            .select_from(SugestaoMelhoria)
            .where(SugestaoMelhoria.usuario_id == usuario_id, SugestaoMelhoria.status == "pendente")
        )
        or 0
    )
    await publicar_estado_atencao(redis, sessao, usuario_id, agente_id=s.agente_id, grupo_id=None)
    await publicar(
        redis,
        ConhecimentoAtualizado(
            motivo=motivo,  # type: ignore[arg-type]
            sugestao_id=s.id,
            agente_id=s.agente_id,
            sugestoes_pendentes=pendentes,
        ),
        usuario_id,
    )


async def _executar(chamada: Any) -> SugestaoMelhoria:
    try:
        return await chamada
    except sugestoes.ErroSugestao as erro:
        raise HTTPException(erro.status, erro.mensagem) from erro


@roteador.patch("/sugestoes/{sugestao_id}")
async def editar_sugestao(
    sugestao_id: UUID, dados: SugestaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> SugestaoSaida:
    """Editar o texto antes de aplicar (o botão Editar do cartão)."""
    return _saida_sugestao(
        await _executar(sugestoes.editar_texto(sessao, usuario_id, sugestao_id, dados.texto))
    )


@roteador.post("/sugestoes/{sugestao_id}/aplicar")
async def aplicar_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    s = await _executar(sugestoes.decidir(sessao, usuario_id, sugestao_id, aplicar=True))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "aplicacao")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/{sugestao_id}/descartar")
async def descartar_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    s = await _executar(sugestoes.decidir(sessao, usuario_id, sugestao_id, aplicar=False))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "sugestoes")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/{sugestao_id}/desfazer")
async def desfazer_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    """Volta o bot (ou a habilidade) à versão de antes do Aplicar."""
    s = await _executar(sugestoes.desfazer(sessao, usuario_id, sugestao_id))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "desfeita")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/analisar", status_code=status.HTTP_202_ACCEPTED)
async def analisar_agora(usuario_id: Usuario) -> dict[str, bool]:
    """Pede uma rodada de análise já (a rotina semanal continua valendo)."""
    from workers.fila import enfileirar

    await enfileirar(
        "analisar_aprendizado_empresa",
        id_job=f"ce-analise:{usuario_id}:{int(time.time() // 60)}",
        usuario_id=str(usuario_id),
    )
    return {"enfileirada": True}
