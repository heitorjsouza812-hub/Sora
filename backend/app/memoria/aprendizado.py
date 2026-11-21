"""Aprender com correções (Onda 3, item 15; ideia vista no OpenBot, escrita do zero).

A cada ``usuarios.aprender_a_cada`` mensagens do usuário numa conversa (10, 20 ou 40; 0 =
desligado), o worker relê o trecho novo com o modelo barato do usuário (papel
``memoria_sintese``) e guarda até ``MAX_MEMORIAS`` correções e preferências duradouras como
memória do bot (ou geral). Cada uma aparece na conversa com o chip "Guardei isto" e Desfazer.

Regras:

- **só o que o usuário escreveu** vira memória: cada proposta precisa citar o id de uma mensagem
  do usuário do trecho (``evidencia``); proposta sem isso é descartada. Texto do bot e de páginas
  entra no prompt só como contexto, cercado como dado;
- conversa **privada** e mensagem escondida ficam de fora;
- a marca ``conversas.aprendizado_ate`` anda antes de chamar o modelo: uma falha (limite da
  conta, por exemplo) não faz o mesmo trecho ser relido em laço;
- memórias daqui são ``origem = sintese`` e **não travadas** (o usuário edita ou apaga em
  Configurações → Memória).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas.base import ErroFerramenta
from app.memoria.servico import validar_conteudo
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import Conversa, Mensagem, Usuario

OPCOES = (0, 10, 20, 40)
PADRAO = 20
MAX_MEMORIAS = 3
MAX_CONTEUDO = 300
MAX_MENSAGENS = 80
MAX_TEXTO_MENSAGEM = 1_500
MAX_MEMORIAS_NO_PROMPT = 40

_SENSIVEL = re.compile(
    r"(senhas?|password|token|chaves? de api|api key|cart[aã]o|cpf|cnpj|cvv|pin|"
    r"conta banc[aá]ria|ag[eê]ncia)",
    re.IGNORECASE,
)
"""Memória automática (sem o usuário confirmar antes) não fala de credencial nem documento."""


def _sensivel(texto: str) -> bool:
    from app.canais_empresa.pii import mascarar_pii

    return bool(_SENSIVEL.search(texto)) or mascarar_pii(texto) != texto


class PropostaMemoria(BaseModel):
    conteudo: str
    evidencia: str
    escopo: Literal["bot", "geral"]


class PropostasMemoria(BaseModel):
    memorias: list[PropostaMemoria]


@dataclass(frozen=True, slots=True)
class LinhaConversa:
    id: UUID
    autor: str
    texto: str


@dataclass(frozen=True, slots=True)
class Aprendida:
    conteudo: str
    evidencia: UUID
    geral: bool


async def mensagens_novas_do_usuario(
    sessao: AsyncSession, conversa_id: UUID, desde: datetime | None
) -> int:
    consulta = select(func.count()).where(
        Mensagem.conversa_id == conversa_id,
        Mensagem.autor == AutorMensagem.USUARIO,
        Mensagem.visivel.is_(True),
    )
    if desde is not None:
        consulta = consulta.where(Mensagem.criada_em > desde)
    return int(await sessao.scalar(consulta) or 0)


async def precisa_reler(sessao: AsyncSession, usuario_id: UUID, conversa_id: UUID) -> UUID | None:
    """Id da última mensagem do usuário quando já há mensagens novas suficientes; senão ``None``.

    Barato: uma leitura da conta, uma da conversa e uma contagem."""
    a_cada = await sessao.scalar(select(Usuario.aprender_a_cada).where(Usuario.id == usuario_id))
    if not a_cada:
        return None
    conversa = await sessao.get(Conversa, conversa_id)
    if conversa is None or conversa.usuario_id != usuario_id or conversa.privada:
        return None
    if await mensagens_novas_do_usuario(sessao, conversa_id, conversa.aprendizado_ate) < a_cada:
        return None
    return await sessao.scalar(
        select(Mensagem.id)
        .where(Mensagem.conversa_id == conversa_id, Mensagem.autor == AutorMensagem.USUARIO)
        .order_by(Mensagem.criada_em.desc())
        .limit(1)
    )


async def trecho_para_reler(
    sessao: AsyncSession, conversa: Conversa
) -> tuple[list[LinhaConversa], datetime | None]:
    """Mensagens visíveis depois da marca (as ``MAX_MENSAGENS`` mais novas) e a data da última."""
    consulta = select(Mensagem).where(
        Mensagem.conversa_id == conversa.id, Mensagem.visivel.is_(True)
    )
    if conversa.aprendizado_ate is not None:
        consulta = consulta.where(Mensagem.criada_em > conversa.aprendizado_ate)
    linhas = list(
        (
            await sessao.scalars(consulta.order_by(Mensagem.criada_em.desc()).limit(MAX_MENSAGENS))
        ).all()
    )
    linhas.reverse()
    trecho = [
        LinhaConversa(
            id=m.id,
            autor="usuario" if m.autor == AutorMensagem.USUARIO else "bot",
            texto=(m.conteudo or "")[:MAX_TEXTO_MENSAGEM],
        )
        for m in linhas
        if (m.conteudo or "").strip()
    ]
    return trecho, (linhas[-1].criada_em if linhas else None)


def montar_prompt(
    nome_do_bot: str, trecho: Sequence[LinhaConversa], memorias: Sequence[str]
) -> str:
    from app.agentes.prompts import carregar_prompt, cercar, preencher

    conversa = "\n".join(f"[{linha.id}] {linha.autor}: {linha.texto}" for linha in trecho)
    atuais = "\n".join(f"- {m}" for m in memorias[:MAX_MEMORIAS_NO_PROMPT]) or "(vazia)"
    return preencher(
        carregar_prompt("aprender_correcoes"),
        nome_do_bot=nome_do_bot,
        maximo=str(MAX_MEMORIAS),
        memorias=cercar(atuais, "memória atual"),
        conversa=cercar(conversa, "conversa"),
    )


def conferir_propostas(
    bruto: Any, trecho: Sequence[LinhaConversa], memorias: Sequence[str]
) -> list[Aprendida]:
    """Só passa o que cita uma mensagem do usuário do trecho, é texto válido e ainda não existe."""
    from app.memoria.servico import normalizar

    try:
        propostas = PropostasMemoria.model_validate(bruto).memorias
    except Exception:
        return []
    do_usuario = {str(linha.id): linha.id for linha in trecho if linha.autor == "usuario"}
    vistas = {normalizar(m) for m in memorias}
    aceitas: list[Aprendida] = []
    for proposta in propostas:
        evidencia = do_usuario.get(proposta.evidencia.strip().strip("[]"))
        if evidencia is None:
            continue
        texto = " ".join(proposta.conteudo.split())
        if not texto or len(texto) > MAX_CONTEUDO:
            continue
        try:
            texto = validar_conteudo(texto)
        except ErroFerramenta:
            continue
        if _sensivel(texto):
            continue
        if normalizar(texto) in vistas:
            continue
        vistas.add(normalizar(texto))
        aceitas.append(
            Aprendida(conteudo=texto, evidencia=evidencia, geral=proposta.escopo == "geral")
        )
        if len(aceitas) >= MAX_MEMORIAS:
            break
    return aceitas


def propostas_do_modelo_falso(trecho: Sequence[LinhaConversa]) -> dict[str, Any]:
    """Com ``SORA_MODELO_FALSO=1`` (testes): cada mensagem do usuário com "da próxima vez" vira
    uma proposta. Também propõe uma tirada de uma fala do bot, que a conferência tem de barrar."""
    memorias: list[dict[str, str]] = []
    for linha in trecho:
        if "próxima vez" in linha.texto.lower():
            memorias.append(
                {
                    "conteudo": linha.texto.strip()[:MAX_CONTEUDO],
                    "evidencia": str(linha.id),
                    "escopo": "bot" if linha.autor == "usuario" else "geral",
                }
            )
    return {"memorias": memorias}
