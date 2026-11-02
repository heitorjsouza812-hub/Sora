"""Quem responde a uma mensagem do usuário no canal.

A ordem foi pensada para gastar modelo só quando não há outro jeito:

1. o usuário escolheu um destinatário na interface → ele;
2. a mensagem começa com menções (``@Atlas @Luna …`` ou ``@todos``) → cada um mencionado;
3. a mensagem é só "continua"/"pode seguir"/"retoma" → retoma as tarefas paradas do último
   pedido que tem alguma;
4. a mensagem responde a outra que tem tarefa aberta → vira seguimento daquela tarefa;
5. o canal tem um membro só → ele;
6. senão, o **líder** decide (um turno curto, sem ferramentas, com resposta em esquema). Sem
   líder, a tarefa fica parada com ``lider_necessario`` até alguém escolher um.

A resposta do líder é conferida: agente que não é membro some; se não sobra ninguém, a tarefa
para com ``roteamento_ilegivel`` (nunca vira "manda para todo mundo").
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.canais_equipe.modelos import MAX_MEMBROS, MensagemCanal, StatusTarefa, TarefaCanal

TODOS = frozenset({"todos", "equipe", "everyone", "all"})
PALAVRAS_CONTINUAR = frozenset(
    {
        "continua",
        "continue",
        "continuar",
        "pode continuar",
        "segue",
        "siga",
        "pode seguir",
        "retoma",
        "retome",
        "retomar",
        "vai",
        "manda ver",
    }
)


@dataclass(frozen=True, slots=True)
class Membro:
    id: UUID
    nome: str
    funcao: str = ""
    disponivel: bool = True
    """``False`` quando o agente foi pausado ou escondido: não recebe trabalho novo."""


TipoRota = Literal["donos", "seguimento", "retomar", "lider", "sem_lider"]


@dataclass(frozen=True, slots=True)
class Rota:
    tipo: TipoRota
    agentes: tuple[UUID, ...] = ()
    tarefas: tuple[UUID, ...] = ()
    texto: str = ""
    """O texto sem as menções do começo (o que vira a instrução da tarefa)."""
    determinista: bool = True
    nota: str = field(default="", compare=False)


def _simplificar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def _apelidos(membros: Sequence[Membro]) -> list[tuple[str, Membro]]:
    """Nome completo de cada membro e, quando não repete no canal, o primeiro nome.

    Assim ``@Luna`` acha "Luna Designer". O mais longo vem primeiro, para ``@Luna Designer``
    consumir o nome inteiro.
    """
    primeiros: dict[str, list[Membro]] = {}
    for membro in membros:
        primeiro = membro.nome.split()[0] if membro.nome.split() else ""
        if primeiro and primeiro != membro.nome:
            primeiros.setdefault(_simplificar(primeiro), []).append(membro)
    completos = {_simplificar(m.nome) for m in membros}
    apelidos = [(m.nome, m) for m in membros]
    for chave, donos in primeiros.items():
        if len(donos) == 1 and chave not in completos:
            apelidos.append((donos[0].nome.split()[0], donos[0]))
    return sorted(apelidos, key=lambda par: len(par[0]), reverse=True)


def ler_mencoes(texto: str, membros: Sequence[Membro]) -> tuple[list[UUID], bool, str]:
    """Lê as menções **do começo** da mensagem.

    Devolve ``(agentes, todos, resto)``. Nome com espaço funciona (``@Luna Designer``), e o
    primeiro nome também quando só um membro o usa. Menção no meio do texto não conta
    ("pergunte à @Luna depois").
    """
    resto = texto.lstrip()
    agentes: list[UUID] = []
    todos = False
    apelidos = _apelidos(membros)
    while resto.startswith("@"):
        candidato = resto[1:]
        palavra = re.match(r"[\w-]+", candidato)
        if palavra and _simplificar(palavra.group(0)) in TODOS:
            todos = True
            resto = candidato[palavra.end() :].lstrip(" ,:").lstrip()
            continue
        achado: tuple[str, Membro] | None = None
        for apelido, membro in apelidos:
            tamanho = len(apelido)
            trecho = candidato[:tamanho]
            depois = candidato[tamanho : tamanho + 1]
            if _simplificar(trecho) == _simplificar(apelido) and (
                not depois or not (depois.isalnum() or depois == "_")
            ):
                achado = (apelido, membro)
                break
        if achado is None:
            break
        if achado[1].id not in agentes:
            agentes.append(achado[1].id)
        resto = candidato[len(achado[0]) :].lstrip(" ,:").lstrip()
    return agentes, todos, resto


def e_pedido_para_continuar(texto: str) -> bool:
    limpo = _simplificar(texto).strip(" .!?")
    return limpo in PALAVRAS_CONTINUAR


def rotear(
    *,
    texto: str,
    membros: Sequence[Membro],
    lider_id: UUID | None,
    tarefas: Sequence[TarefaCanal],
    mensagens: dict[UUID, MensagemCanal],
    destinatario: UUID | None = None,
    responde_a: UUID | None = None,
) -> Rota:
    disponiveis = [m for m in membros if m.disponivel]
    ids_disponiveis = {m.id for m in disponiveis}

    if destinatario is not None:
        if destinatario not in ids_disponiveis:
            return Rota("sem_lider", nota="Esse agente não pode receber trabalho neste canal.")
        return Rota("donos", (destinatario,), texto=texto.strip())

    mencionados, todos, resto = ler_mencoes(texto, membros)
    if todos:
        return Rota("donos", tuple(m.id for m in disponiveis), texto=resto)
    mencionados = [a for a in mencionados if a in ids_disponiveis]
    if mencionados:
        return Rota("donos", tuple(mencionados), texto=resto)

    if e_pedido_para_continuar(texto):
        paradas = _paradas_do_ultimo_pedido(tarefas)
        if paradas:
            return Rota("retomar", tarefas=tuple(t.id for t in paradas), texto=texto.strip())

    if responde_a is not None:
        respondida = mensagens.get(responde_a)
        if respondida is not None and respondida.tarefa_id is not None:
            tarefa = next((t for t in tarefas if t.id == respondida.tarefa_id), None)
            if tarefa is not None and tarefa.status not in (
                StatusTarefa.CONCLUIDA,
                StatusTarefa.CANCELADA,
            ):
                return Rota("seguimento", (tarefa.dono_id,), (tarefa.id,), texto=texto.strip())

    if len(disponiveis) == 1:
        return Rota("donos", (disponiveis[0].id,), texto=texto.strip())

    if lider_id is None or lider_id not in {m.id for m in membros}:
        return Rota("sem_lider", texto=texto.strip(), nota="O canal precisa de um líder.")
    return Rota("lider", (lider_id,), texto=texto.strip(), determinista=False)


def _paradas_do_ultimo_pedido(tarefas: Sequence[TarefaCanal]) -> list[TarefaCanal]:
    """Tarefas raiz paradas do pedido mais recente que tem alguma; senão as que falharam."""
    for status in (StatusTarefa.PARADA, StatusTarefa.FALHOU):
        raizes = [t for t in tarefas if t.raiz and t.status is status]
        if raizes:
            ultimo = max(raizes, key=lambda t: t.criada_em).pedido_id
            return [t for t in raizes if t.pedido_id == ultimo]
    return []


# ---------- decisão do líder ----------


MAX_PERGUNTA_LIDER = 500


class DecisaoLider(BaseModel):
    """Esquema que o líder preenche num turno curto, sem ferramentas.

    Compatível com a saída estruturada estrita (Groq, OpenAI): toda chave é obrigatória e as
    que não se aplicam vêm ``null``; sem ``default``, limites nem ``format`` no esquema. Ids
    chegam como texto e os limites são conferidos em ``conferir_decisao``.
    """

    model_config = ConfigDict(extra="forbid")

    acao: Literal["atribuir", "tarefa_existente", "perguntar", "sem_resposta"] = Field(
        description="O que fazer com o pedido."
    )
    agentes: list[str] | None = Field(
        description="Ids dos membros escolhidos (só em 'atribuir'); null nos outros casos."
    )
    tarefa_id: str | None = Field(
        description="Id da tarefa aberta que o pedido continua (só em 'tarefa_existente')."
    )
    pergunta: str | None = Field(
        description="Pergunta curta ao usuário (só em 'perguntar'); null nos outros casos."
    )


INSTRUCOES_LIDER = (
    "Você coordena este canal. Leia o pedido e escolha quem responde. Escolha só os membros "
    "cuja função o pedido toca; pedido da área de um só (ou de ninguém) vai para o mais capaz; "
    "pedido de opinião sobre trabalho de todos vai para quem tem visão diferente; pedido para o "
    "grupo inteiro vai para todos. Se o pedido continua uma tarefa aberta, use "
    "'tarefa_existente'. Se não dá para saber, use 'perguntar'. Mensagem que não pede nada "
    "('obrigado', 'ok') é 'sem_resposta'. Responda só com o JSON do esquema."
)


@dataclass(frozen=True, slots=True)
class DecisaoConferida:
    rota: Rota | None
    pergunta: str | None = None
    ilegivel: bool = False
    sem_resposta: bool = False


def conferir_decisao(
    bruto: str | dict[str, object],
    *,
    membros: Sequence[Membro],
    tarefas: Sequence[TarefaCanal],
    texto: str,
) -> DecisaoConferida:
    """Valida a resposta do líder. Qualquer coisa estranha vira ``ilegivel`` (a tarefa para)."""
    try:
        dados = json.loads(bruto) if isinstance(bruto, str) else dict(bruto)
        if not isinstance(dados, dict):
            raise ValueError("decisão não é objeto")
        # fora do modo estrito (modelo falso, queda json_object) as nulas podem faltar e
        # pode sobrar chave: fica só o que o esquema conhece
        decisao = DecisaoLider.model_validate({c: dados.get(c) for c in DecisaoLider.model_fields})
        agentes = [UUID(str(a)) for a in decisao.agentes or []]
        tarefa_id = UUID(decisao.tarefa_id) if decisao.tarefa_id else None
    except (ValueError, TypeError):  # inclui ValidationError e JSON quebrado
        return DecisaoConferida(None, ilegivel=True)
    if len(agentes) > MAX_MEMBROS or len(decisao.pergunta or "") > MAX_PERGUNTA_LIDER:
        return DecisaoConferida(None, ilegivel=True)
    disponiveis = {m.id for m in membros if m.disponivel}
    if decisao.acao == "sem_resposta":
        return DecisaoConferida(None, sem_resposta=True)
    if decisao.acao == "perguntar":
        pergunta = (decisao.pergunta or "").strip()
        return (
            DecisaoConferida(None, pergunta=pergunta)
            if pergunta
            else DecisaoConferida(None, ilegivel=True)
        )
    if decisao.acao == "tarefa_existente":
        tarefa = next((t for t in tarefas if t.id == tarefa_id), None)
        if tarefa is None or tarefa.status in (StatusTarefa.CONCLUIDA, StatusTarefa.CANCELADA):
            return DecisaoConferida(None, ilegivel=True)
        return DecisaoConferida(
            Rota("seguimento", (tarefa.dono_id,), (tarefa.id,), texto=texto, determinista=False)
        )
    escolhidos = tuple(dict.fromkeys(a for a in agentes if a in disponiveis))
    if not escolhidos:
        return DecisaoConferida(None, ilegivel=True)
    return DecisaoConferida(Rota("donos", escolhidos, texto=texto, determinista=False))
