"""Esquemas (entrada e saída) das rotas dos canais da empresa."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.canais_empresa import lgpd, sugestoes


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
    retencao_fatos_dias: int
    sugestoes_intervalo_dias: int
    ultima_analise_em: datetime | None


class PreferenciasEntrada(BaseModel):
    retencao_dias: int | None = Field(
        default=None, ge=lgpd.RETENCAO_MIN_DIAS, le=lgpd.RETENCAO_MAX_DIAS
    )
    retencao_fatos_dias: int | None = Field(
        default=None, ge=lgpd.RETENCAO_MIN_DIAS, le=lgpd.RETENCAO_MAX_DIAS
    )
    """Prazo dos fatos da ficha (padrão 365), contado da criação do fato."""
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
    estado: Literal["pendente", "aprovado"]
    aprovado_em: datetime | None
    no_prompt: bool
    """Os bots só leem o item aprovado, sem contradição e com conteúdo."""
    sem_resposta: bool
    """Item que nasceu da pergunta de um cliente e ainda não tem resposta de funcionário."""
    em_disputa: list[dict[str, Any]]
    """Versões novas que contradizem ``conteudo`` (``{conteudo, em, papel}``)."""
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


def _erro(erro: Exception, codigo: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(codigo, str(erro))
