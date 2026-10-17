"""Rotas do catálogo de modelos disponíveis; especificação §§2 e 5."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.esquemas import ModeloAtualizacao, ModeloSaida
from app.modelos.tabelas import ModeloDisponivel, Provedor

roteador = APIRouter(prefix="/modelos", tags=["modelos"], dependencies=[Depends(usuario_atual)])

NIVEIS_VALIDOS = frozenset({"N1", "N2", "N3", "especial"})


def consulta_modelos_do_usuario(usuario_id: UUID) -> Select[tuple[ModeloDisponivel]]:
    """Modelos cujos provedores são do usuário e não foram apagados (regras 9 e 10)."""
    return (
        select(ModeloDisponivel)
        .join(Provedor, Provedor.id == ModeloDisponivel.provedor_id)
        .where(Provedor.usuario_id == usuario_id, Provedor.apagado_em.is_(None))
    )


@roteador.get("")
async def listar_modelos(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
) -> list[ModeloSaida]:
    """Lista modelos com nível, capacidades e preço, por provedor (ordem de conexão) e nome."""
    consulta = consulta_modelos_do_usuario(usuario_id).order_by(
        Provedor.criado_em, Provedor.id, ModeloDisponivel.modelo
    )
    return [ModeloSaida.model_validate(m) for m in (await sessao.scalars(consulta)).all()]


@roteador.patch("/{modelo_id}")
async def atualizar_modelo(
    modelo_id: UUID,
    dados: ModeloAtualizacao,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
) -> ModeloSaida:
    """Atualiza nível ou ativação definida pelo usuário.

    Mudar o nível grava ``origem="usuario"``: a sincronização do provedor não desfaz a escolha.
    Modelo de outro usuário ou de provedor apagado responde 404, igual a inexistente.
    """
    enviados = dados.model_fields_set
    if "nivel" in enviados and dados.nivel not in NIVEIS_VALIDOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Nível inválido. Use N1, N2, N3 ou especial."
        )
    if "ativo" in enviados and dados.ativo is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe se o modelo fica ativo (true ou false)."
        )
    modelo = await sessao.scalar(
        consulta_modelos_do_usuario(usuario_id)
        .where(ModeloDisponivel.id == modelo_id)
        .with_for_update(of=ModeloDisponivel)
    )
    if modelo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo não encontrado.")
    if dados.nivel is not None and dados.nivel != modelo.nivel:
        modelo.nivel = dados.nivel
        modelo.origem = "usuario"
    if dados.ativo is not None:
        modelo.ativo = dados.ativo
    await sessao.flush()
    return ModeloSaida.model_validate(modelo)
