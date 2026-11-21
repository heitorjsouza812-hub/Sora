"""Ensinar uma tarefa (Onda 3, item 14; ideia vista no OpenBot, escrita do zero).

Com a aba do bot **assumida**, o usuário toca em "Ensinar" e faz a tarefa como sempre faz
(clicar, digitar, Enter). Enquanto a marca ``navegador:ensinando:<aba>`` existe, o worker que
executa os pedidos do usuário (``app/navegador/ao_vivo.py``) anota cada passo numa lista no Redis:
o que foi clicado (papel e nome do elemento, não a coordenada), em que campo se digitou e o que,
qual tecla, e para que página foi. Ao concluir, os passos viram um **rascunho** de habilidade no
formato de playbook (``app/habilidades``), que o usuário revisa e salva; nada é salvo sozinho.

Cuidados:

- texto digitado em campo de senha **nunca** é anotado (vira ``[senha]``); texto com cara de dado
  pessoal ou credencial vira ``[dado pessoal]``; o resto é cortado em ``MAX_TEXTO``;
- a gravação vive no Redis por ``VALIDADE_S`` (30 min) e some ao concluir ou cancelar;
- nomes de elementos vêm da página (podem ter sido escritos por qualquer um): são cortados e
  aparecem entre aspas no rascunho, que o usuário lê antes de salvar;
- no máximo ``MAX_PASSOS`` passos.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.redacao import url_sem_segredos

CHAVE_ENSINANDO = "navegador:ensinando:{aba_id}"
CHAVE_GRAVACAO = "navegador:gravacao:{aba_id}"
VALIDADE_S = 30 * 60
MAX_PASSOS = 200
MAX_TEXTO = 80
MAX_NOME_ALVO = 60

_SENSIVEL = re.compile(r"\b(senhas?|password|token|cart[aã]o|cpf|cnpj|cvv|pin)\b", re.IGNORECASE)

DESCREVER_PONTO_JS = """
([x, y]) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return null;
  const seletor = 'a,button,input,select,textarea,label,summary,[role],[onclick],[tabindex]';
  const alvo = el.closest(seletor) || el;
  const tag = alvo.tagName.toLowerCase();
  const tipo = (alvo.getAttribute('type') || '').toLowerCase();
  const rotulo = alvo.labels && alvo.labels[0] ? alvo.labels[0].innerText : '';
  const nome = alvo.getAttribute('aria-label') || rotulo || alvo.getAttribute('placeholder')
    || alvo.getAttribute('title') || alvo.getAttribute('alt')
    || (tag === 'input' ? alvo.value : '') || alvo.innerText || alvo.textContent || '';
  return {tag, tipo, papel: alvo.getAttribute('role') || '',
    nome: String(nome).trim().slice(0, 120),
    senha: tipo === 'password' || /password/i.test(alvo.getAttribute('autocomplete') || '')};
}
"""

DESCREVER_FOCO_JS = """
() => {
  const alvo = document.activeElement;
  if (!alvo || alvo === document.body) return null;
  const tag = alvo.tagName.toLowerCase();
  const tipo = (alvo.getAttribute('type') || '').toLowerCase();
  const rotulo = alvo.labels && alvo.labels[0] ? alvo.labels[0].innerText : '';
  const nome = alvo.getAttribute('aria-label') || rotulo || alvo.getAttribute('placeholder')
    || alvo.getAttribute('name') || alvo.getAttribute('title') || '';
  return {tag, tipo, papel: alvo.getAttribute('role') || '',
    nome: String(nome).trim().slice(0, 120),
    senha: tipo === 'password' || /password/i.test(alvo.getAttribute('autocomplete') || '')};
}
"""


class Passo(BaseModel):
    tipo: Literal["abrir", "pagina", "clicar", "digitar", "tecla"]
    """``abrir``: onde a tarefa começa; ``pagina``: para onde um passo levou."""
    alvo: str | None = Field(default=None, max_length=200)
    texto: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    em: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Rascunho(BaseModel):
    nome: str
    descricao: str
    corpo: str
    passos: int


# ---------------------------------------------------------------- descrever


_PAPEL = {
    "button": "botão",
    "a": "link",
    "link": "link",
    "select": "lista",
    "textarea": "campo",
    "input": "campo",
    "checkbox": "caixa de marcar",
    "radio": "opção",
    "tab": "aba",
    "menuitem": "item do menu",
    "summary": "seção",
    "label": "rótulo",
}


def _limpar_nome(nome: str) -> str:
    texto = " ".join(str(nome or "").split())
    texto = texto.replace("“", "").replace("”", "").replace('"', "")
    return texto[:MAX_NOME_ALVO] + ("…" if len(texto) > MAX_NOME_ALVO else "")


def descrever_alvo(info: dict[str, Any] | None) -> str:
    """``{"tag": "button", "nome": "Entrar"}`` → ``botão “Entrar”``."""
    if not info:
        return "um ponto da página"
    tag = str(info.get("tag") or "")
    tipo = str(info.get("tipo") or "")
    papel = str(info.get("papel") or "")
    if tag == "input" and tipo in ("checkbox", "radio"):
        rotulo = _PAPEL[tipo]
    elif tag == "input" and tipo in ("submit", "button"):
        rotulo = "botão"
    else:
        rotulo = _PAPEL.get(papel) or _PAPEL.get(tag) or "elemento"
    nome = _limpar_nome(str(info.get("nome") or ""))
    return f"{rotulo} “{nome}”" if nome else rotulo


def texto_seguro(texto: str, *, senha: bool) -> str:
    """O que entra na gravação do que foi digitado: nunca senha nem dado pessoal."""
    if senha:
        return "[senha]"
    from app.canais_empresa.pii import mascarar_pii

    limpo = " ".join(texto.split())
    if _SENSIVEL.search(limpo) or mascarar_pii(limpo) != limpo:
        return "[dado pessoal]"
    return limpo[:MAX_TEXTO] + ("…" if len(limpo) > MAX_TEXTO else "")


# ---------------------------------------------------------------- Redis


async def iniciar(
    redis: Any, aba_id: UUID, usuario_id: UUID, agente_id: UUID, url_inicial: str | None
) -> None:
    marca = json.dumps({"usuario_id": str(usuario_id), "agente_id": str(agente_id)})
    await redis.set(CHAVE_ENSINANDO.format(aba_id=aba_id), marca, ex=VALIDADE_S)
    chave = CHAVE_GRAVACAO.format(aba_id=aba_id)
    await redis.delete(chave)
    if url_inicial:
        await gravar(redis, aba_id, Passo(tipo="abrir", url=url_sem_segredos(url_inicial)[:500]))


async def ensinando(redis: Any, aba_id: UUID) -> dict[str, str] | None:
    bruto = await redis.get(CHAVE_ENSINANDO.format(aba_id=aba_id))
    if not bruto:
        return None
    try:
        return json.loads(bruto)
    except ValueError:
        return None


async def gravar(redis: Any, aba_id: UUID, passo: Passo) -> None:
    chave = CHAVE_GRAVACAO.format(aba_id=aba_id)
    if await redis.llen(chave) >= MAX_PASSOS:
        return
    await redis.rpush(chave, passo.model_dump_json())
    await redis.expire(chave, VALIDADE_S)


async def ler(redis: Any, aba_id: UUID) -> list[Passo]:
    brutos = await redis.lrange(CHAVE_GRAVACAO.format(aba_id=aba_id), 0, MAX_PASSOS - 1)
    passos: list[Passo] = []
    for bruto in brutos:
        try:
            passos.append(Passo.model_validate_json(bruto))
        except ValueError:
            continue
    return passos


async def encerrar(redis: Any, aba_id: UUID) -> None:
    await redis.delete(CHAVE_ENSINANDO.format(aba_id=aba_id), CHAVE_GRAVACAO.format(aba_id=aba_id))


# ---------------------------------------------------------------- rascunho


def frase_do_passo(passo: Passo) -> str:
    if passo.tipo == "abrir":
        return f"Abra {passo.url}" if passo.url else "Abra a página inicial da tarefa"
    if passo.tipo == "pagina":
        return f"Confira que abriu {passo.url}" if passo.url else "Confira que a página mudou"
    if passo.tipo == "clicar":
        return f"Clique em {passo.alvo or 'um ponto da página'}"
    if passo.tipo == "digitar":
        campo = passo.alvo or "o campo em foco"
        if passo.texto == "[senha]":
            return f"Em {campo}, peça a senha ao usuário com navegador_pedir_senha (nunca digite)"
        if passo.texto == "[dado pessoal]":
            return f"Em {campo}, digite o dado que o usuário informar (pergunte se não souber)"
        return f"Em {campo}, digite “{passo.texto}” (troque pelo valor do pedido, se for outro)"
    return f"Aperte {passo.texto or 'Enter'}"


def juntar_passos(passos: list[Passo]) -> list[Passo]:
    """Junta digitações seguidas no mesmo campo e tira aberturas repetidas da mesma página."""
    juntos: list[Passo] = []
    for passo in passos:
        anterior = juntos[-1] if juntos else None
        if (
            anterior is not None
            and passo.tipo == "digitar"
            and anterior.tipo == "digitar"
            and anterior.alvo == passo.alvo
            and anterior.texto not in ("[senha]", "[dado pessoal]")
            and passo.texto not in ("[senha]", "[dado pessoal]")
        ):
            texto = f"{anterior.texto or ''}{passo.texto or ''}"[:MAX_TEXTO]
            juntos[-1] = anterior.model_copy(update={"texto": texto})
            continue
        if (
            anterior is not None
            and passo.tipo in ("abrir", "pagina")
            and anterior.tipo in ("abrir", "pagina")
            and anterior.url == passo.url
        ):
            continue
        juntos.append(passo)
    return juntos


def rascunho(passos: list[Passo], objetivo: str, dominio: str | None) -> Rascunho:
    """Monta o playbook. ``objetivo`` é o que o usuário disse que a tarefa faz."""
    from app.habilidades import Playbook, playbook_para_markdown

    limpos = juntar_passos(passos)
    if not any(p.tipo in ("clicar", "digitar", "tecla") for p in limpos):
        raise ValueError("Nenhum passo gravado: faça a tarefa na aba antes de concluir.")
    objetivo = " ".join(objetivo.split())[:300] or "Repetir a tarefa que o usuário mostrou"
    entradas = sorted(
        {p.alvo for p in limpos if p.tipo == "digitar" and p.alvo},
    )[:20]
    playbook = Playbook(
        quando_usar=f"Quando o usuário pedir: {objetivo}."
        + (f" Site: {dominio}." if dominio else ""),
        entradas=[f"valor para {campo}" for campo in entradas],
        passos=[frase_do_passo(p) for p in limpos][:60]
        + [
            "Use navegador_observar antes de cada clique para achar o elemento pelo nome "
            "(a página pode ter mudado de lugar).",
        ][: max(0, 60 - len(limpos))],
        como_conferir="Depois do último passo, observe a página e confira se o resultado esperado "
        "apareceu.",
        o_que_devolver="Conte ao usuário o que foi feito e o resultado que apareceu na página.",
    )
    nome = _limpar_nome(objetivo)[:60].rstrip("…").strip() or "Tarefa ensinada"
    return Rascunho(
        nome=nome,
        descricao=f"Tarefa ensinada pelo usuário no navegador: {objetivo}"[:300],
        corpo=playbook_para_markdown(playbook),
        passos=len(limpos),
    )
