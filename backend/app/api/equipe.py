"""Rotas das peças inspiradas no OpenBot (``docs/referencias/openbot.md``).

Contrato com o app: canais de equipe, fila de cada agente, medidor de contexto, reações e o
navegador persistente. As regras já existem e têm testes (``app/canais_equipe``, ``app/filas``,
``app/contexto``, ``app/correio``, ``app/navegador``); falta o repositório no banco e ligar no
worker, como as outras rotas que ainda respondem ``NotImplementedError``.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.canais_equipe.modelos import (
    MAX_INSTRUCOES,
    MAX_MEMBROS,
    MAX_NOME_CANAL,
    MAX_PROPOSITO,
    MAX_TEXTO_MENSAGEM,
)
from app.core.dependencias import usuario_atual
from app.eventos.equipe import (
    AbaNavegadorEvento,
    CanalAtualizado,
    ContextoAtualizado,
    FilaAtualizada,
    MensagemCanalEvento,
    TarefaCanalAtualizada,
)
from app.filas import LIMITE_TAREFAS_MAXIMO

roteador = APIRouter(tags=["equipe"], dependencies=[Depends(usuario_atual)])


# ---------- canais de equipe ----------


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


@roteador.get("/canais-equipe")
async def listar_canais(arquivados: bool = False) -> list[CanalAtualizado]:
    """Canais do usuário; com ``arquivados=true``, os que estão em "Apagados"."""
    raise NotImplementedError


@roteador.post("/canais-equipe", status_code=status.HTTP_201_CREATED)
async def criar_canal(dados: CanalEntrada) -> CanalAtualizado:
    raise NotImplementedError


@roteador.put("/canais-equipe/{canal_id}")
async def configurar_canal(canal_id: UUID, dados: CanalEntrada) -> CanalAtualizado:
    """Troca nome, membros, líder, propósito e instruções. Tirar o responsável para a tarefa."""
    raise NotImplementedError


@roteador.post("/canais-equipe/{canal_id}/arquivar", status_code=status.HTTP_204_NO_CONTENT)
async def arquivar_canal(canal_id: UUID) -> None:
    raise NotImplementedError


@roteador.post("/canais-equipe/{canal_id}/restaurar", status_code=status.HTTP_204_NO_CONTENT)
async def restaurar_canal(canal_id: UUID) -> None:
    raise NotImplementedError


@roteador.get("/canais-equipe/{canal_id}/mensagens")
async def mensagens_do_canal(
    canal_id: UUID, depois_de_seq: int = 0, limite: int = 50
) -> list[MensagemCanalEvento]:
    raise NotImplementedError


@roteador.post("/canais-equipe/{canal_id}/mensagens", status_code=status.HTTP_202_ACCEPTED)
async def enviar_ao_canal(canal_id: UUID, dados: MensagemCanalEntrada) -> MensagemCanalEvento:
    raise NotImplementedError


@roteador.get("/canais-equipe/{canal_id}/tarefas")
async def tarefas_do_canal(canal_id: UUID) -> list[TarefaCanalAtualizada]:
    raise NotImplementedError


@roteador.post("/tarefas-canal/{tarefa_id}/parar")
async def parar_tarefa(tarefa_id: UUID) -> list[TarefaCanalAtualizada]:
    raise NotImplementedError


@roteador.post("/tarefas-canal/{tarefa_id}/retomar")
async def retomar_tarefa(tarefa_id: UUID) -> list[TarefaCanalAtualizada]:
    raise NotImplementedError


@roteador.post("/tarefas-canal/{tarefa_id}/reatribuir")
async def reatribuir_tarefa(tarefa_id: UUID, dados: ReatribuirEntrada) -> TarefaCanalAtualizada:
    raise NotImplementedError


@roteador.post("/tarefas-canal/{tarefa_id}/cancelar")
async def cancelar_tarefa(tarefa_id: UUID) -> list[TarefaCanalAtualizada]:
    raise NotImplementedError


# ---------- fila de cada agente ----------


class LimiteEntrada(BaseModel):
    limite_tarefas: int = Field(ge=1, le=LIMITE_TAREFAS_MAXIMO)


class MoverEntrada(BaseModel):
    antes_de: UUID | None = None


class EdicaoEntrada(BaseModel):
    editor: str = Field(min_length=8, max_length=64)
    """Id gerado pela tela que está editando (para só ela salvar)."""
    texto: str | None = Field(default=None, max_length=MAX_TEXTO_MENSAGEM)


@roteador.get("/agentes/{agente_id}/fila")
async def fila_do_agente(agente_id: UUID) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/pausar")
async def pausar_fila(agente_id: UUID) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/retomar")
async def retomar_fila(agente_id: UUID) -> FilaAtualizada:
    raise NotImplementedError


@roteador.put("/agentes/{agente_id}/fila/limite")
async def limite_da_fila(agente_id: UUID, dados: LimiteEntrada) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/{item_id}/cancelar")
async def cancelar_item(agente_id: UUID, item_id: UUID) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/{item_id}/mover")
async def mover_item(agente_id: UUID, item_id: UUID, dados: MoverEntrada) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/{item_id}/repetir")
async def repetir_item(agente_id: UUID, item_id: UUID) -> FilaAtualizada:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/fila/{item_id}/edicao/{acao}")
async def editar_item(
    agente_id: UUID,
    item_id: UUID,
    acao: Literal["comecar", "salvar", "descartar"],
    dados: EdicaoEntrada,
) -> FilaAtualizada:
    raise NotImplementedError


# ---------- medidor de contexto ----------


@roteador.get("/agentes/{agente_id}/contexto")
async def contexto_do_agente(agente_id: UUID) -> list[ContextoAtualizado]:
    raise NotImplementedError


@roteador.post("/agentes/{agente_id}/contexto/compactar", status_code=status.HTTP_202_ACCEPTED)
async def compactar_agora(agente_id: UUID, fio: str = "principal") -> ContextoAtualizado:
    """Botão "Compactar agora". 409 com o motivo se o agente estiver trabalhando."""
    raise NotImplementedError


# ---------- reações ----------


class ReacaoEntrada(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)


@roteador.post("/mensagens/{mensagem_id}/reacoes")
async def reagir(mensagem_id: UUID, dados: ReacaoEntrada) -> dict[str, int]:
    """Alterna a reação do usuário; devolve o resumo ``{emoji: quantidade}``."""
    raise NotImplementedError


# ---------- navegador persistente ----------


class PerfilEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=60)


class PerfilDoAgenteEntrada(BaseModel):
    tipo: Literal["compartilhado", "agente", "nomeado"]
    perfil_id: UUID | None = None


@roteador.get("/navegador/abas")
async def abas_abertas(agente_id: UUID | None = None) -> list[AbaNavegadorEvento]:
    raise NotImplementedError


@roteador.post("/navegador/abas/{aba_id}/assumir")
async def assumir_aba(aba_id: UUID) -> AbaNavegadorEvento:
    """O usuário pega a aba (login, captcha). Os agentes não mexem nela até devolver."""
    raise NotImplementedError


@roteador.post("/navegador/abas/{aba_id}/devolver")
async def devolver_aba(aba_id: UUID) -> AbaNavegadorEvento:
    raise NotImplementedError


@roteador.delete("/navegador/abas/{aba_id}", status_code=status.HTTP_204_NO_CONTENT)
async def fechar_aba(aba_id: UUID) -> None:
    raise NotImplementedError


@roteador.get("/navegador/perfis")
async def perfis_do_navegador() -> list[dict[str, str]]:
    raise NotImplementedError


@roteador.post("/navegador/perfis", status_code=status.HTTP_201_CREATED)
async def criar_perfil(dados: PerfilEntrada) -> dict[str, str]:
    raise NotImplementedError


@roteador.delete("/navegador/perfis/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_perfil(perfil_id: UUID) -> None:
    """Fecha as abas do perfil, apaga os logins e devolve os agentes ao compartilhado."""
    raise NotImplementedError


@roteador.put("/agentes/{agente_id}/navegador")
async def perfil_do_agente(agente_id: UUID, dados: PerfilDoAgenteEntrada) -> None:
    """Troca o perfil do agente; as abas dele fecham e as novas abrem no perfil escolhido."""
    raise NotImplementedError
