"""Busca nas mensagens do próprio usuário (etapa 6, item 17): conversas da Sora, dos bots e dos
grupos.

``GET /v1/busca?q=termo`` devolve as mensagens mais novas em que **todas** as palavras do termo
aparecem (sem diferença de maiúscula nem de acento), cada uma com um trecho e as posições a
destacar. Só entram conversas e grupos da própria conta; bot apagado fica de fora. Mensagem de
outro usuário nunca aparece: a consulta filtra por ``conversas.usuario_id`` e
``canais_equipe.usuario_id``.

A comparação sem acento e sem caixa usa expressão regular com as variantes acentuadas de cada
vogal (``_regex``), sem extensão do PostgreSQL. O trecho e o destaque são calculados aqui com
``dobrar``, que troca um caractere por outro e por isso mantém as posições.
Com 5.000 mensagens a busca leva cerca de 25 ms no banco (``tests/integracao/test_etapa6_ancora4``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.enumeracoes import AutorMensagem, TipoAgente
from app.modelos.tabelas import (
    Agente,
    CanalEquipe,
    Conversa,
    Mensagem,
    MensagemCanalTabela,
)

roteador = APIRouter(prefix="/busca", tags=["busca"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]

MAX_PALAVRAS = 6
TAMANHO_MINIMO = 2
LIMITE_PADRAO = 20
LIMITE_MAXIMO = 50
ANTES_DO_TRECHO = 60
TAMANHO_DO_TRECHO = 180

_COM_ACENTO = "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ"
_SEM_ACENTO = "aaaaaeeeeiiiiooooouuuucnaaaaaeeeeiiiiooooouuuucn"
_TABELA = str.maketrans(_COM_ACENTO, _SEM_ACENTO)


def dobrar(texto: str) -> str:
    """Minúsculas e sem acento, mantendo o tamanho: ``Ação`` -> ``acao``."""
    trocado = texto.translate(_TABELA)
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in trocado)


_VARIANTES = {
    "a": "aàáâãäAÀÁÂÃÄ",
    "e": "eèéêëEÈÉÊË",
    "i": "iìíîïIÌÍÎÏ",
    "o": "oòóôõöOÒÓÔÕÖ",
    "u": "uùúûüUÙÚÛÜ",
    "c": "cçCÇ",
    "n": "nñNÑ",
}


def _regex(palavra: str) -> str:
    """Expressão regular (``~*``, sem diferença de caixa) que casa a palavra com qualquer
    acentuação: ``acao`` vira ``[aàá…]c[cç][aàá…]o``. É várias vezes mais rápida que
    ``translate`` + ``lower`` em cada linha (≈25 ms contra ≈350 ms em 5.000 mensagens)."""
    partes = []
    for letra in palavra:
        if letra in _VARIANTES:
            partes.append(f"[{_VARIANTES[letra]}]")
        elif letra.isalnum() or letra == " ":
            partes.append(letra)
        else:
            partes.append("\\" + letra)
    return "".join(partes)


def _condicao(coluna: ColumnElement[str], palavras: list[str]) -> ColumnElement[bool]:
    return and_(*(coluna.op("~*")(_regex(p)) for p in palavras))


class ResultadoBusca(BaseModel):
    tipo: Literal["conversa", "grupo"]
    mensagem_id: UUID
    conversa_id: UUID | None = None
    """Chat 1:1 (Sora ou bot) onde a mensagem está."""
    grupo_id: UUID | None = None
    """Grupo onde a mensagem está."""
    seq: int | None = None
    """Posição da mensagem no grupo (para abrir a conversa naquele ponto)."""
    agente_id: UUID | None = None
    """Dono do chat 1:1 ou, no grupo, quem escreveu (se foi um bot)."""
    titulo: str
    """"Sora", o nome do bot ou o nome do grupo."""
    arquivado: bool = False
    autor: Literal["usuario", "sora", "agente", "sistema"]
    autor_nome: str
    trecho: str
    destaques: list[tuple[int, int]]
    """Pares [início, fim) dentro de ``trecho`` para realçar."""
    criada_em: datetime


class BuscaSaida(BaseModel):
    consulta: str
    resultados: list[ResultadoBusca]


def palavras_da_busca(consulta: str) -> list[str]:
    vistas: dict[str, None] = {}
    for palavra in dobrar(consulta).split():
        vistas.setdefault(palavra, None)
    return list(vistas)[:MAX_PALAVRAS]


def trecho_destacado(texto: str, palavras: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Janela do texto em volta da primeira palavra achada, com as posições a realçar."""
    plano = " ".join(texto.split()) if "\n" in texto or "  " in texto else texto
    dobrado = dobrar(plano)
    achados = [(dobrado.find(p), p) for p in palavras if dobrado.find(p) >= 0]
    inicio_janela = max(0, min((i for i, _ in achados), default=0) - ANTES_DO_TRECHO)
    fim_janela = min(len(plano), inicio_janela + TAMANHO_DO_TRECHO)
    corte = plano[inicio_janela:fim_janela]
    prefixo = "…" if inicio_janela > 0 else ""
    sufixo = "…" if fim_janela < len(plano) else ""
    destaques: list[tuple[int, int]] = []
    janela = dobrado[inicio_janela:fim_janela]
    for palavra in palavras:
        posicao = janela.find(palavra)
        while posicao >= 0:
            destaques.append((len(prefixo) + posicao, len(prefixo) + posicao + len(palavra)))
            posicao = janela.find(palavra, posicao + len(palavra))
    destaques.sort()
    unidos: list[tuple[int, int]] = []
    for inicio, fim in destaques:
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], fim))
        else:
            unidos.append((inicio, fim))
    return f"{prefixo}{corte}{sufixo}", unidos


def _autor_da_conversa(autor: AutorMensagem, nome_do_bot: str) -> tuple[str, str]:
    if autor is AutorMensagem.USUARIO:
        return "usuario", "Você"
    if autor is AutorMensagem.SORA:
        return "sora", "Sora"
    return "agente", nome_do_bot


@roteador.get("")
async def buscar_mensagens(
    usuario_id: Usuario,
    sessao: Sessao,
    q: Annotated[str, Query(max_length=200)],
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_PADRAO,
) -> BuscaSaida:
    """Mensagens do usuário que contêm todas as palavras de ``q``, das mais novas às mais
    antigas. Termo com menos de 2 letras devolve lista vazia."""
    palavras = palavras_da_busca(q)
    if not palavras or all(len(p) < TAMANHO_MINIMO for p in palavras):
        return BuscaSaida(consulta=q, resultados=[])

    resultados: list[ResultadoBusca] = []

    em_conversas = await sessao.execute(
        select(
            Mensagem.id,
            Mensagem.conversa_id,
            Mensagem.autor,
            Mensagem.conteudo,
            Mensagem.criada_em,
            Agente.id,
            Agente.nome,
            Agente.tipo,
        )
        .join(Conversa, Conversa.id == Mensagem.conversa_id)
        .join(Agente, Agente.id == Conversa.agente_id)
        .where(
            Conversa.usuario_id == usuario_id,
            Agente.usuario_id == usuario_id,
            Agente.apagado_em.is_(None),
            Mensagem.visivel.is_(True),
            Mensagem.autor.in_([AutorMensagem.USUARIO, AutorMensagem.SORA, AutorMensagem.AGENTE]),
            _condicao(Mensagem.conteudo, palavras),
        )
        .order_by(Mensagem.criada_em.desc())
        .limit(limite)
    )
    for (
        mensagem_id,
        conversa_id,
        autor,
        conteudo,
        criada_em,
        dono_id,
        dono_nome,
        dono_tipo,
    ) in em_conversas.all():
        autor_valor, autor_nome = _autor_da_conversa(autor, dono_nome)
        trecho, destaques = trecho_destacado(conteudo, palavras)
        resultados.append(
            ResultadoBusca(
                tipo="conversa",
                mensagem_id=mensagem_id,
                conversa_id=conversa_id,
                agente_id=dono_id,
                titulo="Sora" if dono_tipo is TipoAgente.SORA else dono_nome,
                autor=autor_valor,  # type: ignore[arg-type]
                autor_nome=autor_nome,
                trecho=trecho,
                destaques=destaques,
                criada_em=criada_em,
            )
        )

    em_grupos = await sessao.execute(
        select(
            MensagemCanalTabela.id,
            MensagemCanalTabela.canal_id,
            MensagemCanalTabela.seq,
            MensagemCanalTabela.autor,
            MensagemCanalTabela.agente_id,
            MensagemCanalTabela.texto,
            MensagemCanalTabela.criada_em,
            CanalEquipe.nome,
            CanalEquipe.arquivado_em,
            Agente.nome,
            Agente.tipo,
        )
        .join(CanalEquipe, CanalEquipe.id == MensagemCanalTabela.canal_id)
        .outerjoin(Agente, Agente.id == MensagemCanalTabela.agente_id)
        .where(
            CanalEquipe.usuario_id == usuario_id,
            MensagemCanalTabela.tipo != "atividade",
            MensagemCanalTabela.autor.in_(["usuario", "agente"]),
            _condicao(MensagemCanalTabela.texto, palavras),
        )
        .order_by(MensagemCanalTabela.criada_em.desc())
        .limit(limite)
    )
    for (
        mensagem_id,
        grupo_id,
        seq,
        autor,
        agente_id,
        texto,
        criada_em,
        grupo_nome,
        arquivado_em,
        autor_agente_nome,
        autor_agente_tipo,
    ) in em_grupos.all():
        if autor == "usuario":
            autor_valor, autor_nome = "usuario", "Você"
        elif autor_agente_tipo is TipoAgente.SORA:
            autor_valor, autor_nome = "sora", "Sora"
        else:
            autor_valor, autor_nome = "agente", autor_agente_nome or "Bot"
        trecho, destaques = trecho_destacado(texto, palavras)
        resultados.append(
            ResultadoBusca(
                tipo="grupo",
                mensagem_id=mensagem_id,
                grupo_id=grupo_id,
                seq=seq,
                agente_id=agente_id,
                titulo=grupo_nome,
                arquivado=arquivado_em is not None,
                autor=autor_valor,  # type: ignore[arg-type]
                autor_nome=autor_nome,
                trecho=trecho,
                destaques=destaques,
                criada_em=criada_em,
            )
        )

    resultados.sort(key=lambda r: r.criada_em, reverse=True)
    return BuscaSaida(consulta=q, resultados=resultados[:limite])
