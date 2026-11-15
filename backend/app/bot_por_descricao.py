"""Sugestao sem historico; falhas do modelo usam regras locais."""

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL
from app.llm.fabrica import criar_chat_model
from app.seletor.repositorio import config_do_provedor, contexto_do_usuario
from app.seletor.seletor import escolher_modelos
from app.seletor.tipos import PapelModelo

NAVEGADOR = [
    "navegador_abrir",
    "navegador_observar",
    "navegador_acao",
    "navegador_procurar",
    "navegador_esperar",
    "navegador_tecla",
    "navegador_elemento",
    "navegador_lote",
]


class SugestaoBot(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    funcao: str = Field(min_length=1, max_length=80)
    instrucoes: str = Field(min_length=1, max_length=8000)
    ferramentas: list[str] = Field(min_length=1, max_length=50)

    @field_validator("nome", "funcao", "instrucoes")
    @classmethod
    def texto_valido(cls, valor):
        if not valor.strip() or valor.strip().casefold() == "sora":
            raise ValueError("Texto invalido")
        return valor.strip()


async def sugerir_bot(sessao, usuario_id, descricao):
    from app.api.agentes import FERRAMENTAS_CONHECIDAS, _validar_ferramentas

    base = list(FERRAMENTAS_POR_PAPEL["individual"])
    web = any(t in descricao.casefold() for t in ("http", "site", "naveg", "página", "pagina"))
    obrigatorias = [*NAVEGADOR, "ler_pagina"] if web else []
    fallback = {"ferramentas": list(dict.fromkeys(base + obrigatorias))}
    try:
        contexto = await contexto_do_usuario(sessao, usuario_id)
        selecao = escolher_modelos(contexto, PapelModelo.SORA, 1, set(), 1000)
        candidato = selecao.modelos[0]
        provedor = await config_do_provedor(sessao, usuario_id, candidato.provedor.id)
        modelo = criar_chat_model(candidato.modelo, provedor, timeout_s=25, max_tokens=1800)
        resposta = await asyncio.wait_for(
            modelo.ainvoke(
                [
                    SystemMessage(
                        content="Crie um bot especializado em PT-BR. Retorne somente JSON "
                        "com nome curto e legivel, funcao curta, instrucoes e ferramentas (lista). "
                        "Nao execute o pedido. Ferramentas permitidas: "
                        + ", ".join(sorted(FERRAMENTAS_CONHECIDAS))
                    ),
                    HumanMessage(content=descricao),
                ]
            ),
            timeout=30,
        )
        sugestao = SugestaoBot.model_validate_json(resposta.content).model_dump()
        sugestao["ferramentas"] = _validar_ferramentas(
            list(dict.fromkeys(sugestao["ferramentas"] + obrigatorias))
        )
        return sugestao
    except Exception:
        # Nunca registrar prompts ou excecoes do provedor.
        return fallback
