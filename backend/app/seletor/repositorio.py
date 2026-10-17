"""Ponte banco → seletor: monta o ``ContextoSeletor`` e a ``ConfigProvedor`` a partir das linhas.

Especificação: §1 (``provedores`` e ``modelos_disponiveis``) e §5 (seletor). O seletor em si é
puro (``app.seletor.seletor``); só este módulo fala com o banco.
"""

from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguranca import decifrar_segredo, precisa_recifrar, recifrar_segredo
from app.llm.custo import gasto_do_mes_por_provedor
from app.llm.provedores import ConfigProvedor
from app.modelos.enumeracoes import Prioridade
from app.modelos.tabelas import ModeloDisponivel, Provedor, Usuario
from app.seletor.catalogo import obter_catalogo
from app.seletor.tipos import Capacidade, ContextoSeletor, ModeloCandidato, ProvedorSeletor

_CAPACIDADES = frozenset(c.value for c in Capacidade)


async def contexto_do_usuario(
    sessao: AsyncSession, usuario_id: UUID, *, conversa_privada: bool = False
) -> ContextoSeletor:
    """Candidatos do usuário: modelos de provedores validados e não apagados, com pausa, teto e
    gasto do mês de cada provedor, mais a prioridade escolhida.

    Modelos inativos também vêm (``ativo=False``): quem filtra é ``modelos_ativos()``.
    """
    prioridade = await sessao.scalar(select(Usuario.prioridade).where(Usuario.id == usuario_id))
    linhas = (
        await sessao.execute(
            select(ModeloDisponivel, Provedor)
            .join(Provedor, Provedor.id == ModeloDisponivel.provedor_id)
            .where(
                Provedor.usuario_id == usuario_id,
                Provedor.apagado_em.is_(None),
                Provedor.validado_em.is_not(None),
            )
            .order_by(Provedor.criado_em, Provedor.id, ModeloDisponivel.modelo)
        )
    ).all()
    gastos = await gasto_do_mes_por_provedor(sessao, usuario_id) if linhas else {}
    catalogo = obter_catalogo()

    provedores: dict[UUID, ProvedorSeletor] = {}
    candidatos: list[ModeloCandidato] = []
    for modelo, provedor in linhas:
        if provedor.id not in provedores:
            provedores[provedor.id] = ProvedorSeletor(
                id=provedor.id,
                tipo=provedor.tipo,
                pausado_ate=provedor.pausado_ate,
                teto_mensal_usd=provedor.teto_mensal_usd,
                gasto_mes_usd=gastos.get(provedor.id, 0),
            )
        entrada = catalogo.buscar(modelo.modelo)
        candidatos.append(
            ModeloCandidato(
                modelo=modelo.modelo,
                provedor=provedores[provedor.id],
                nivel=modelo.nivel,
                # Valor estranho no banco não derruba a seleção: só some aquela capacidade.
                capacidades=frozenset(c for c in modelo.capacidades if c in _CAPACIDADES),
                contexto=modelo.contexto,
                preco_entrada=modelo.preco_entrada,
                preco_saida=modelo.preco_saida,
                velocidade_tps=modelo.velocidade_tps,
                ativo=modelo.ativo,
                somente_se_escolhido=entrada.somente_se_escolhido if entrada else False,
            )
        )
    return ContextoSeletor(
        modelos=candidatos,
        prioridade=prioridade or Prioridade.CUSTO,
        conversa_privada=conversa_privada,
    )


async def config_do_provedor(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID
) -> ConfigProvedor:
    """Decifra a chave do provedor (AAD = id da linha) para uma chamada ao modelo.

    Se a chave foi cifrada com uma chave mestra antiga, regrava com a atual (rotação, §8.1).
    Provedor de outro usuário, apagado ou inexistente → ``LookupError`` (sem dizer qual).
    """
    provedor = await sessao.scalar(
        select(Provedor).where(
            Provedor.id == provedor_id,
            Provedor.usuario_id == usuario_id,
            Provedor.apagado_em.is_(None),
        )
    )
    if provedor is None:
        raise LookupError("Provedor não encontrado.")
    chave: SecretStr | None = None
    if provedor.chave_cifrada:
        aad = {"usuario_id": usuario_id, "provedor": str(provedor.id)}
        if precisa_recifrar(provedor.chave_cifrada):
            provedor.chave_cifrada = recifrar_segredo(provedor.chave_cifrada, **aad)
            await sessao.flush()
        chave = SecretStr(decifrar_segredo(provedor.chave_cifrada, **aad))
    return ConfigProvedor(
        provedor_id=provedor.id, tipo=provedor.tipo, api_key=chave, base_url=provedor.base_url
    )
