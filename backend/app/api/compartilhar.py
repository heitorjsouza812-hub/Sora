"""Compartilhar bot por link, exportar e importar (Onda 3, item 16). Regras em
``app/bots_compartilhados.py``.

Com login:

- ``GET/POST/DELETE /v1/bots/{id}/compartilhamento``: o link ativo do bot (um por bot). Criar de
  novo troca o código e o retrato; apagar desliga o link na hora;
- ``POST /v1/bots/{id}/exportar``: o mesmo retrato num ``.zip``;
- ``POST /v1/bots/importar`` (arquivo ``.zip``) e ``POST /v1/bots/importar-link`` (código): cria
  uma cópia na conta, com as rotinas pausadas.

Sem login (o código de 96 bits no endereço é o segredo; limite por IP):

- ``GET /v1/publico/bots/{codigo}`` e ``…/imagem.png``;
- ``GET /b/{codigo}`` (fora do ``/v1``, ver ``roteador_pagina``): a página com a prévia para
  redes sociais, que leva para ``/compartilhado/{codigo}`` no app.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import bots_compartilhados as bc
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite
from app.ferramentas.base import ErroFerramenta
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, BotCompartilhado, Habilidade, Rotina

roteador = APIRouter(prefix="/bots", tags=["bots"])
roteador_publico = APIRouter(prefix="/publico/bots", tags=["bots"])
roteador_pagina = APIRouter(tags=["bots"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_PUBLICO = (120, 60)
LIMITE_IMPORTAR = (20, 60 * 60)


class OpcoesRetrato(BaseModel):
    habilidades: list[UUID] = Field(default_factory=list, max_length=bc.MAX_HABILIDADES)
    com_rotinas: bool = True


class CompartilhamentoSaida(BaseModel):
    codigo: str
    url: str
    usos: int
    criado_em: datetime
    bot: bc.BotRetrato


class PublicoSaida(BaseModel):
    codigo: str
    criado_em: datetime
    bot: bc.BotRetrato


class ImportarLink(BaseModel):
    codigo: str = Field(min_length=8, max_length=40)


class ImportadoSaida(BaseModel):
    agente_id: UUID
    nome: str
    rotinas: int
    habilidades: int
    avisos: list[str]


def _base_url(requisicao: Request) -> str:
    """Endereço público do site (o app e a API ficam no mesmo domínio em produção)."""
    configuracao = obter_configuracao()
    if configuracao.ambiente == "producao":
        return configuracao.app_url.rstrip("/")
    return str(requisicao.base_url).rstrip("/")


def _url_do_link(codigo: str) -> str:
    return f"{obter_configuracao().app_url.rstrip('/')}/b/{codigo}"


async def _bot_do_usuario(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> Agente:
    agente = await sessao.scalar(
        select(Agente).where(
            Agente.id == agente_id,
            Agente.usuario_id == usuario_id,
            Agente.apagado_em.is_(None),
        )
    )
    if agente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot não encontrado.")
    if agente.tipo != TipoAgente.INDIVIDUAL:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Só bots criados por você podem ser compartilhados.",
        )
    return agente


async def montar_retrato(
    sessao: AsyncSession, usuario_id: UUID, agente: Agente, opcoes: OpcoesRetrato
) -> bc.BotRetrato:
    from app.habilidades import ler_skill_md

    rotinas: list[bc.RotinaCompartilhada] = []
    if opcoes.com_rotinas:
        linhas = await sessao.scalars(
            select(Rotina)
            .where(Rotina.usuario_id == usuario_id, Rotina.agente_id == agente.id)
            .order_by(Rotina.criada_em)
        )
        for rotina in linhas:
            if rotina.tipo not in ("cron", "intervalo") or not rotina.expressao:
                continue  # rotina de uma vez só não faz sentido em outra conta
            rotinas.append(
                bc.RotinaCompartilhada(
                    titulo=rotina.titulo[:120],
                    pedido=rotina.pedido,
                    tipo=rotina.tipo,  # type: ignore[arg-type]
                    expressao=rotina.expressao,
                    fuso=rotina.fuso,
                    silencioso=rotina.silencioso,
                )
            )
            if len(rotinas) >= bc.MAX_ROTINAS:
                break
    habilidades: list[bc.HabilidadeCompartilhada] = []
    if opcoes.habilidades:
        escolhidas = await sessao.scalars(
            select(Habilidade).where(
                Habilidade.usuario_id == usuario_id, Habilidade.id.in_(opcoes.habilidades)
            )
        )
        for habilidade in escolhidas:
            try:
                skill = ler_skill_md(habilidade.conteudo)
                corpo = skill.corpo.strip() or habilidade.descricao
            except ErroFerramenta:
                corpo = habilidade.conteudo
            habilidades.append(
                bc.HabilidadeCompartilhada(
                    nome=habilidade.nome, descricao=habilidade.descricao, corpo=corpo
                )
            )
    return bc.BotRetrato(
        nome=agente.nome[: bc.MAX_NOME_BOT],
        funcao=(agente.funcao or "")[: bc.MAX_FUNCAO],
        papel=agente.papel or "",
        cor=agente.cor if len(agente.cor) == 7 else "#46E8A8",
        movimento=getattr(agente.movimento, "value", agente.movimento),  # type: ignore[arg-type]
        instrucoes=(agente.instrucoes or "")[: bc.MAX_INSTRUCOES],
        ferramentas=[f for f in agente.ferramentas if f in ferramentas_importaveis()],
        rotinas=rotinas,
        habilidades=habilidades,
    )


def ferramentas_importaveis() -> frozenset[str]:
    """Ferramentas que viajam com o bot: as do bot comum e do navegador. Computador e dados de
    clientes ficam de fora (o usuário liga à parte, em Configurações)."""
    from app.api.agentes import FERRAMENTAS_CONHECIDAS
    from app.computador.ferramentas import NOMES as FERRAMENTAS_DO_COMPUTADOR

    return (
        FERRAMENTAS_CONHECIDAS
        - frozenset(FERRAMENTAS_DO_COMPUTADOR)
        - {"consultar_cliente", "consultar_conhecimento"}
    )


async def _ativo(sessao: AsyncSession, agente_id: UUID) -> BotCompartilhado | None:
    return await sessao.scalar(
        select(BotCompartilhado).where(
            BotCompartilhado.agente_id == agente_id, BotCompartilhado.revogado_em.is_(None)
        )
    )


def _saida(linha: BotCompartilhado) -> CompartilhamentoSaida:
    return CompartilhamentoSaida(
        codigo=linha.codigo,
        url=_url_do_link(linha.codigo),
        usos=linha.usos,
        criado_em=linha.criado_em,
        bot=bc.BotRetrato.model_validate(linha.retrato),
    )


@roteador.get("/{agente_id}/compartilhamento")
async def ver_compartilhamento(
    agente_id: UUID, usuario_id: UsuarioId, sessao: Sessao
) -> CompartilhamentoSaida | None:
    await _bot_do_usuario(sessao, usuario_id, agente_id)
    linha = await _ativo(sessao, agente_id)
    return _saida(linha) if linha is not None else None


@roteador.post("/{agente_id}/compartilhamento", status_code=status.HTTP_201_CREATED)
async def compartilhar(
    agente_id: UUID, opcoes: OpcoesRetrato, usuario_id: UsuarioId, sessao: Sessao
) -> CompartilhamentoSaida:
    """Cria o link (ou troca o código e o retrato do link que já existia)."""
    agente = await _bot_do_usuario(sessao, usuario_id, agente_id)
    retrato = await montar_retrato(sessao, usuario_id, agente, opcoes)
    await sessao.execute(
        update(BotCompartilhado)
        .where(BotCompartilhado.agente_id == agente_id, BotCompartilhado.revogado_em.is_(None))
        .values(revogado_em=datetime.now(UTC))
    )
    linha = BotCompartilhado(
        usuario_id=usuario_id,
        agente_id=agente_id,
        codigo=bc.gerar_codigo(),
        retrato=retrato.model_dump(mode="json"),
        imagem=bc.imagem_de_previa(retrato),
        criado_em=datetime.now(UTC),
    )
    sessao.add(linha)
    await sessao.flush()
    return _saida(linha)


@roteador.delete("/{agente_id}/compartilhamento", status_code=status.HTTP_204_NO_CONTENT)
async def parar_de_compartilhar(agente_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    await _bot_do_usuario(sessao, usuario_id, agente_id)
    await sessao.execute(
        update(BotCompartilhado)
        .where(BotCompartilhado.agente_id == agente_id, BotCompartilhado.revogado_em.is_(None))
        .values(revogado_em=datetime.now(UTC))
    )


@roteador.post("/{agente_id}/exportar", response_class=Response)
async def exportar(
    agente_id: UUID, opcoes: OpcoesRetrato, usuario_id: UsuarioId, sessao: Sessao
) -> Response:
    agente = await _bot_do_usuario(sessao, usuario_id, agente_id)
    retrato = await montar_retrato(sessao, usuario_id, agente, opcoes)
    return Response(
        bc.escrever_zip(retrato),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{bc.nome_do_arquivo(retrato.nome)}"',
            "Cache-Control": "no-store",
        },
    )


async def importar_retrato(
    sessao: AsyncSession, usuario_id: UUID, retrato: bc.BotRetrato
) -> ImportadoSaida:
    """Cria a cópia do bot na conta. Rotinas pausadas; ferramentas fora da lista caem."""
    from app.agentes.aparencia import COR_SORA, escolher_cor
    from app.api.agentes import _em_uso, _garantir_vaga
    from app.api.habilidades import MAX_HABILIDADES
    from app.habilidades import montar_skill_md

    await _garantir_vaga(sessao, usuario_id)
    nomes, cores = await _em_uso(sessao, usuario_id)
    avisos: list[str] = []
    nome = " ".join(retrato.nome.split())[: bc.MAX_NOME_BOT] or "Bot"
    if nome.casefold() == "sora":
        nome = "Bot da Sora"
    usados = {n.casefold() for n in nomes}
    if nome.casefold() in usados:
        base = nome[: bc.MAX_NOME_BOT - 4]
        nome = next(f"{base} {i}" for i in range(2, 1000) if f"{base} {i}".casefold() not in usados)
    cor = retrato.cor.upper()
    valida = len(cor) == 7 and cor.startswith("#") and all(c in "0123456789ABCDEF" for c in cor[1:])
    if not valida or cor == COR_SORA:
        cor = escolher_cor(cores)
    permitidas = ferramentas_importaveis()
    ferramentas = [f for f in dict.fromkeys(retrato.ferramentas) if f in permitidas]
    if len(ferramentas) < len(set(retrato.ferramentas)):
        avisos.append("Algumas ferramentas do bot original não vieram e podem ser ligadas depois.")
    agente = Agente(
        usuario_id=usuario_id,
        tipo=TipoAgente.INDIVIDUAL,
        nome=nome,
        funcao=retrato.funcao.strip(),
        papel=retrato.papel.strip(),
        cor=cor,
        movimento=retrato.movimento,
        instrucoes=retrato.instrucoes.strip(),
        ferramentas=ferramentas or _ferramentas_padrao(),
    )
    sessao.add(agente)
    await sessao.flush()

    rotinas = 0
    for rotina in retrato.rotinas:
        try:
            conferida = bc.validar_agenda(rotina)
        except ErroFerramenta:
            avisos.append(f"A rotina “{rotina.titulo}” tinha uma agenda inválida e ficou de fora.")
            continue
        sessao.add(
            Rotina(
                usuario_id=usuario_id,
                agente_id=agente.id,
                titulo=conferida.titulo,
                pedido=conferida.pedido,
                tipo=conferida.tipo,
                expressao=conferida.expressao,
                fuso=conferida.fuso,
                silencioso=conferida.silencioso,
                ativa=False,  # o usuário liga quando quiser
                proxima_execucao=None,
            )
        )
        rotinas += 1

    habilidades = 0
    if retrato.habilidades:
        existentes = {
            n.casefold()
            for n in (
                await sessao.scalars(
                    select(Habilidade.nome).where(Habilidade.usuario_id == usuario_id)
                )
            ).all()
        }
        vagas = MAX_HABILIDADES - len(existentes)
        for habilidade in retrato.habilidades:
            if vagas <= 0:
                avisos.append("A conta já tem o máximo de habilidades; algumas ficaram de fora.")
                break
            nome_h = habilidade.nome.strip()
            if nome_h.casefold() in existentes:
                nome_h = f"{nome_h[: 80 - 13]} (importada)"
                if nome_h.casefold() in existentes:
                    continue
            try:
                conteudo = montar_skill_md(nome_h, habilidade.descricao, habilidade.corpo)
            except ErroFerramenta:
                avisos.append(f"A habilidade “{habilidade.nome}” era inválida e ficou de fora.")
                continue
            sessao.add(
                Habilidade(
                    usuario_id=usuario_id,
                    nome=nome_h,
                    descricao=habilidade.descricao.strip(),
                    conteudo=conteudo,
                    origem="importada",
                )
            )
            existentes.add(nome_h.casefold())
            habilidades += 1
            vagas -= 1
    if rotinas:
        avisos.append("As rotinas chegaram pausadas: ligue as que quiser.")
    await sessao.flush()
    return ImportadoSaida(
        agente_id=agente.id, nome=nome, rotinas=rotinas, habilidades=habilidades, avisos=avisos
    )


def _ferramentas_padrao() -> list[str]:
    from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL

    return list(FERRAMENTAS_POR_PAPEL["individual"])


async def _limite_importar(redis: Redis, usuario_id: UUID) -> None:
    espera = await verificar_limite(redis, f"bots:importar:{usuario_id}", *LIMITE_IMPORTAR)
    if espera:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas importações seguidas. Tente mais tarde.",
            headers={"Retry-After": str(espera)},
        )


@roteador.post("/importar", status_code=status.HTTP_201_CREATED)
async def importar_arquivo(
    usuario_id: UsuarioId,
    sessao: Sessao,
    redis: RedisDep,
    arquivo: Annotated[UploadFile, File()],
) -> ImportadoSaida:
    await _limite_importar(redis, usuario_id)
    dados = await arquivo.read(bc.MAX_ZIP + 1)
    try:
        retrato = bc.ler_zip(dados)
    except ErroFerramenta as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from erro
    return await importar_retrato(sessao, usuario_id, retrato)


@roteador.post("/importar-link", status_code=status.HTTP_201_CREATED)
async def importar_link(
    dados: ImportarLink, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> ImportadoSaida:
    await _limite_importar(redis, usuario_id)
    linha = await _por_codigo(sessao, dados.codigo)
    saida = await importar_retrato(sessao, usuario_id, bc.BotRetrato.model_validate(linha.retrato))
    await sessao.execute(
        update(BotCompartilhado)
        .where(BotCompartilhado.id == linha.id)
        .values(usos=BotCompartilhado.usos + 1)
    )
    return saida


# ---------------------------------------------------------------- sem login


async def _por_codigo(sessao: AsyncSession, codigo: str) -> BotCompartilhado:
    linha = (
        await sessao.scalar(
            select(BotCompartilhado)
            .join(Agente, Agente.id == BotCompartilhado.agente_id)
            .where(
                BotCompartilhado.codigo == codigo,
                BotCompartilhado.revogado_em.is_(None),
                Agente.apagado_em.is_(None),
            )
        )
        if bc.codigo_valido(codigo)
        else None
    )
    if linha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este link não existe mais.")
    return linha


async def _limite_publico(requisicao: Request, redis: Redis) -> None:
    ip = requisicao.client.host if requisicao.client else "sem-ip"
    espera = await verificar_limite(redis, f"bots:publico:{ip}", *LIMITE_PUBLICO)
    if espera:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitos pedidos. Tente de novo em instantes.",
            headers={"Retry-After": str(espera)},
        )


@roteador_publico.get("/{codigo}")
async def ver_publico(
    codigo: str, requisicao: Request, sessao: Sessao, redis: RedisDep
) -> PublicoSaida:
    await _limite_publico(requisicao, redis)
    linha = await _por_codigo(sessao, codigo)
    return PublicoSaida(
        codigo=linha.codigo,
        criado_em=linha.criado_em,
        bot=bc.BotRetrato.model_validate(linha.retrato),
    )


@roteador_publico.get("/{codigo}/imagem.png", response_class=Response)
async def imagem_publica(
    codigo: str, requisicao: Request, sessao: Sessao, redis: RedisDep
) -> Response:
    await _limite_publico(requisicao, redis)
    linha = await _por_codigo(sessao, codigo)
    imagem = linha.imagem or bc.imagem_de_previa(bc.BotRetrato.model_validate(linha.retrato))
    return Response(
        imagem, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"}
    )


@roteador_pagina.get("/b/{codigo}", response_class=HTMLResponse, include_in_schema=False)
async def pagina_publica(
    codigo: str, requisicao: Request, sessao: Sessao, redis: RedisDep
) -> HTMLResponse:
    await _limite_publico(requisicao, redis)
    linha = await _por_codigo(sessao, codigo)
    corpo = bc.pagina_de_previa(
        bc.BotRetrato.model_validate(linha.retrato), linha.codigo, _base_url(requisicao)
    )
    return HTMLResponse(corpo, headers={"Cache-Control": "public, max-age=300"})
