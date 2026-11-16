"""O bot só diz que fez no PC do usuário o que viu feito (C3, Vela-12).

Teste real do Heitor (2026-11-15): o bot respondia "Pronto!" sem ter conseguido mexer no
computador. A regra fica do lado do worker, sem depender do modelo:

- uma ação no PC do usuário (``computador_agir`` ou ``computador_abrir_programa`` com
  ``alvo: "pc_usuario"``) só conta como **conferida** quando deu certo e a tela nova veio junto
  (``Conferência: a tela mudou`` ou o programa aberto na frente);
- se o turno termina com uma mensagem que afirma ter feito algo no computador e nenhuma ação
  do turno foi conferida, a mensagem vira um aviso claro em PT-BR em vez da afirmação.

Funções puras, sobre a lista de mensagens do LangGraph (testes em ``test_vela12_pc.py``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

FERRAMENTAS_DE_ACAO = frozenset({"computador_agir", "computador_abrir_programa"})
MARCAS_DE_CONFERIDO = ("Conferência: a tela mudou", "Programa aberto e na frente")

AVISO = (
    "Não consegui confirmar que fiz isso no seu computador: nenhuma ação minha teve o resultado "
    "conferido na tela."
)

_AFIRMA = re.compile(
    r"\b(pronto|pronta|conclui|concluido|concluida|terminei|finalizei|feito|feita|criei|"
    r"preenchi|montei|abri|digitei|fiz|consegui|esta criada|esta criado|esta pronta|"
    r"esta pronto|tabela criada|planilha criada)\b"
)
_NEGA = re.compile(
    r"\b(nao (consegui|deu|foi possivel|abri|fiz|criei|preenchi|terminei|pude|tenho como)|"
    r"preciso que voce|peca ao|pedi permissao|aguardando|esperando)\b"
)
_FALA_DO_PC = re.compile(
    r"\b(excel|planilha|bloco de notas|word|powerpoint|paint|libreoffice|celula|celulas|"
    r"no seu computador|na sua tela|no seu pc)\b"
)


def _simples(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _tipo(mensagem: Any) -> str:
    return str(getattr(mensagem, "type", "") or "")


@dataclass(frozen=True, slots=True)
class AcoesDoTurno:
    tentativas: int = 0
    conferidas: int = 0
    ultimo_erro: str | None = None


def acoes_do_turno(mensagens: list[Any]) -> AcoesDoTurno:
    """Ações no PC do usuário desde a última mensagem do usuário, e quantas foram conferidas."""
    inicio = 0
    for i in range(len(mensagens) - 1, -1, -1):
        if _tipo(mensagens[i]) == "human":
            inicio = i + 1
            break
    chamadas: dict[str, str] = {}
    for mensagem in mensagens[inicio:]:
        if _tipo(mensagem) != "ai":
            continue
        for chamada in getattr(mensagem, "tool_calls", None) or []:
            nome = chamada.get("name")
            args = chamada.get("args") or {}
            padrao = "pc_usuario" if nome == "computador_abrir_programa" else "virtual"
            if nome in FERRAMENTAS_DE_ACAO and (args.get("alvo") or padrao) == "pc_usuario":
                chamadas[str(chamada.get("id"))] = nome
    tentativas = conferidas = 0
    ultimo_erro: str | None = None
    for mensagem in mensagens[inicio:]:
        if _tipo(mensagem) != "tool" or str(getattr(mensagem, "tool_call_id", "")) not in chamadas:
            continue
        tentativas += 1
        conteudo = str(getattr(mensagem, "content", "") or "")
        if conteudo.startswith("Erro") or getattr(mensagem, "status", None) == "error":
            ultimo_erro = conteudo.removeprefix("Erro:").strip()
            continue
        if any(marca in conteudo for marca in MARCAS_DE_CONFERIDO):
            conferidas += 1
    return AcoesDoTurno(tentativas, conferidas, ultimo_erro)


def afirma_que_fez(texto: str) -> bool:
    """A mensagem diz que algo foi feito (e não que não deu)?"""
    simples = _simples(texto)
    return bool(_AFIRMA.search(simples)) and not _NEGA.search(simples)


def precisa_de_aviso(texto: str, acoes: AcoesDoTurno) -> bool:
    if acoes.conferidas or not afirma_que_fez(texto):
        return False
    if acoes.tentativas:
        return True
    # nenhuma ação no PC neste turno, mas a mensagem diz que fez algo nele
    return bool(_FALA_DO_PC.search(_simples(texto)))


def texto_com_aviso(texto: str, acoes: AcoesDoTurno) -> str:
    """Troca a afirmação pelo aviso, com o último erro (curto) quando houver."""
    partes = [AVISO]
    if acoes.ultimo_erro:
        primeira = re.split(r"(?<=[.!?])\s", acoes.ultimo_erro.strip(), maxsplit=1)[0]
        partes.append(f"O que aconteceu: {primeira[:240]}")
    elif not acoes.tentativas:
        partes.append("Não cheguei a usar o computador nesta resposta.")
    partes.append("Se quiser, peça de novo que eu tento outra vez e confiro na tela.")
    return "\n\n".join(partes)
