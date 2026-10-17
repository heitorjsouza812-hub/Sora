"""Regras das APIs de modelos conectadas pelo usuário."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.contas import ErroConta, _limitar
from app.llm.custo import gasto_do_mes_por_provedor
from app.llm.provedores import (
    ChaveInvalida,
    ConfigProvedor,
    DestinoBloqueado,
    ErroProvedor,
    politica_de_rede,
    validar_base_url,
)
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.esquemas import ProvedorAtualizacao, ProvedorCriacao
from app.modelos.tabelas import ModeloDisponivel, Provedor, Usuario
from app.seletor.catalogo import ClassificacaoModelo, obter_catalogo

ListadorModelos = Callable[[ConfigProvedor], Awaitable[list[str]]]

LIMITE_PROVEDORES = 10
LIMITE_TESTES = (10, 60 * 60)
MAX_MODELOS = 500
TIPOS_COM_CHAVE_OBRIGATORIA = frozenset(
    {
        TipoProvedor.GROQ,
        TipoProvedor.OPENAI,
        TipoProvedor.ANTHROPIC,
        TipoProvedor.GOOGLE,
        TipoProvedor.OPENROUTER,
    }
)


class ErroConexao(ErroConta):
    """Erro de negócio das conexões, convertido pelo handler comum da API."""


class ErroDadosProvedor(ErroConexao):
    status_code = 422


class ErroProvedorDuplicado(ErroConexao):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Essa API já está conectada.")


class ErroLimiteProvedores(ErroConexao):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Você pode conectar no máximo 10 APIs.")


class ErroProvedorNaoEncontrado(ErroConexao):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Provedor não encontrado.")


def _limpar_chave(chave: SecretStr | None) -> str | None:
    limpa = chave.get_secret_value().strip() if chave is not None else None
    return limpa or None


def _validar_chave(tipo: TipoProvedor, chave: SecretStr | None) -> str | None:
    limpa = _limpar_chave(chave)
    if tipo in TIPOS_COM_CHAVE_OBRIGATORIA and limpa is None:
        raise ErroDadosProvedor("Informe a chave da API.")
    return limpa


def _chave_final(chave: str | None) -> str | None:
    return chave[-4:] if chave is not None and len(chave) >= 12 else None


async def _testar(
    redis: Redis,
    usuario_id: UUID,
    config: ConfigProvedor,
    listador: ListadorModelos,
) -> list[str]:
    await _limitar(redis, f"provedor:teste:{usuario_id}", LIMITE_TESTES)
    try:
        nomes = await listador(config)
    except (DestinoBloqueado, ChaveInvalida, ErroProvedor) as erro:
        raise ErroDadosProvedor(str(erro)) from erro
    nomes = sorted(set(nomes))[:MAX_MODELOS]
    if not nomes:
        raise ErroDadosProvedor("O provedor não devolveu nenhum modelo.")
    return nomes


def _novo_modelo(provedor_id: UUID, classificacao: ClassificacaoModelo) -> ModeloDisponivel:
    return ModeloDisponivel(
        id=uuid4(),
        provedor_id=provedor_id,
        modelo=classificacao.modelo,
        nivel=classificacao.nivel,
        capacidades=list(classificacao.capacidades),
        contexto=classificacao.contexto,
        preco_entrada=classificacao.preco_entrada,
        preco_saida=classificacao.preco_saida,
        velocidade_tps=classificacao.velocidade_tps,
        origem=classificacao.origem,
        ativo=not classificacao.somente_se_escolhido,
    )


async def _provedor_do_usuario(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID
) -> Provedor:
    provedor = await sessao.scalar(
        select(Provedor).where(
            Provedor.id == provedor_id,
            Provedor.usuario_id == usuario_id,
            Provedor.apagado_em.is_(None),
        )
    )
    if provedor is None:
        raise ErroProvedorNaoEncontrado()
    return provedor


async def conectar(
    sessao: AsyncSession,
    redis: Redis,
    usuario_id: UUID,
    dados: ProvedorCriacao,
    listador: ListadorModelos,
) -> tuple[Provedor, list[ModeloDisponivel]]:
    """Testa e grava um provedor e até 500 modelos classificados."""
    chave = _validar_chave(dados.tipo, dados.chave)
    try:
        base_url = validar_base_url(dados.tipo, dados.base_url, politica_de_rede())
    except DestinoBloqueado as erro:
        raise ErroDadosProvedor(str(erro)) from erro

    await sessao.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
    duplicado = await sessao.scalar(
        select(Provedor.id).where(
            Provedor.usuario_id == usuario_id,
            Provedor.tipo == dados.tipo,
            Provedor.base_url.is_not_distinct_from(base_url),
            Provedor.apagado_em.is_(None),
        )
    )
    if duplicado is not None:
        raise ErroProvedorDuplicado()
    total = await sessao.scalar(
        select(func.count(Provedor.id)).where(
            Provedor.usuario_id == usuario_id, Provedor.apagado_em.is_(None)
        )
    )
    if (total or 0) >= LIMITE_PROVEDORES:
        raise ErroLimiteProvedores()

    config = ConfigProvedor(tipo=dados.tipo, api_key=chave, base_url=base_url)
    nomes = await _testar(redis, usuario_id, config, listador)
    provedor_id = uuid4()
    provedor = Provedor(
        id=provedor_id,
        usuario_id=usuario_id,
        tipo=dados.tipo,
        base_url=base_url,
        chave_cifrada=(
            seguranca.cifrar_segredo(chave, usuario_id=usuario_id, provedor=str(provedor_id))
            if chave is not None
            else None
        ),
        chave_final=_chave_final(chave),
        validado_em=datetime.now(UTC),
    )
    sessao.add(provedor)
    # Não há relacionamento ORM entre as tabelas; materializa o pai antes dos FKs dos modelos.
    await sessao.flush()
    modelos = [_novo_modelo(provedor_id, obter_catalogo().classificar(nome)) for nome in nomes]
    sessao.add_all(modelos)
    await sessao.flush()
    return provedor, modelos


async def listar(sessao: AsyncSession, usuario_id: UUID) -> list[tuple[Provedor, Decimal]]:
    """Lista provedores ativos do usuário com o gasto do mês."""
    provedores = list(
        (
            await sessao.scalars(
                select(Provedor)
                .where(Provedor.usuario_id == usuario_id, Provedor.apagado_em.is_(None))
                .order_by(Provedor.criado_em)
            )
        ).all()
    )
    gastos = await gasto_do_mes_por_provedor(sessao, usuario_id)
    return [(provedor, gastos.get(provedor.id, Decimal("0"))) for provedor in provedores]


async def atualizar(
    sessao: AsyncSession,
    redis: Redis,
    usuario_id: UUID,
    provedor_id: UUID,
    dados: ProvedorAtualizacao,
    listador: ListadorModelos,
) -> Provedor:
    """Atualiza o teto e, quando enviada, testa a chave e sincroniza os modelos."""
    provedor = await _provedor_do_usuario(sessao, usuario_id, provedor_id)
    if "teto_mensal_usd" in dados.model_fields_set:
        teto = dados.teto_mensal_usd
        if teto is not None and not Decimal("0") <= teto <= Decimal("100000"):
            raise ErroDadosProvedor("O teto mensal deve ficar entre 0 e 100000 dólares.")

    if "chave" in dados.model_fields_set:
        chave = _validar_chave(provedor.tipo, dados.chave)
        config = ConfigProvedor(tipo=provedor.tipo, api_key=chave, base_url=provedor.base_url)
        nomes = await _testar(redis, usuario_id, config, listador)
        existentes = {
            modelo.modelo: modelo
            for modelo in (
                await sessao.scalars(
                    select(ModeloDisponivel).where(ModeloDisponivel.provedor_id == provedor.id)
                )
            ).all()
        }
        catalogo = obter_catalogo()
        for nome in nomes:
            classificacao = catalogo.classificar(nome)
            modelo = existentes.pop(nome, None)
            if modelo is None:
                sessao.add(_novo_modelo(provedor.id, classificacao))
                continue
            modelo.capacidades = list(classificacao.capacidades)
            modelo.contexto = classificacao.contexto
            modelo.preco_entrada = classificacao.preco_entrada
            modelo.preco_saida = classificacao.preco_saida
            modelo.velocidade_tps = classificacao.velocidade_tps
        for modelo in existentes.values():
            modelo.ativo = False

        provedor.chave_cifrada = (
            seguranca.cifrar_segredo(chave, usuario_id=usuario_id, provedor=str(provedor.id))
            if chave is not None
            else None
        )
        provedor.chave_final = _chave_final(chave)
        provedor.validado_em = datetime.now(UTC)
        provedor.falhas_seguidas = 0
        provedor.pausado_ate = None

    if "teto_mensal_usd" in dados.model_fields_set:
        provedor.teto_mensal_usd = dados.teto_mensal_usd
    await sessao.flush()
    return provedor


async def apagar(sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID) -> None:
    """Apaga logicamente o provedor, elimina a chave e desativa seus modelos."""
    provedor = await _provedor_do_usuario(sessao, usuario_id, provedor_id)
    provedor.apagado_em = datetime.now(UTC)
    provedor.chave_cifrada = None
    provedor.chave_final = None
    modelos = await sessao.scalars(
        select(ModeloDisponivel).where(ModeloDisponivel.provedor_id == provedor.id)
    )
    for modelo in modelos.all():
        modelo.ativo = False
    await sessao.flush()
