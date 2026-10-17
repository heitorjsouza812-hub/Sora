"""Agendamentos (lembretes e rotinas recorrentes) e as ferramentas ``agendar``,
``listar_agendamentos`` e ``cancelar_agendamento``.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``schedule_create`` em
``adapters/src/builtin-tools.ts`` (um único jeito de marcar o tempo por agendamento: cron,
"a cada N unidades", data exata, ou atraso em minutos/segundos) e ``core/src/cron.ts``
(próxima execução no fuso do usuário).

Rotina é um pedido agendado, não um fluxo visual: na hora marcada o worker roda o pedido como
se o usuário tivesse mandado, com as ferramentas seguras para rodar sem supervisão
(``app/revisor/politica.py``) e a resposta silenciosa (``app/rotinas/silencio.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import BaseModel, Field, model_validator

from app.ferramentas.base import ErroFerramenta

FUSO_PADRAO = "America/Sao_Paulo"
INTERVALO_MINIMO = timedelta(minutes=1)
INTERVALO_MINIMO_CRON = timedelta(minutes=5)
MAX_AGENDAMENTOS_ATIVOS = 20
MAX_PEDIDO = 4_000
ATRASO_MAXIMO = timedelta(days=366)

DESCRICAO_AGENDAR = (
    "Cria um lembrete ou uma tarefa recorrente para este agente. Use para 'me lembre em 10 "
    "minutos' ou 'toda manhã me mande um resumo'. Use UM jeito de marcar o tempo: cron (5 "
    "campos), a_cada + unidade (mínimo 1 minuto), em (data e hora) ou daqui_minutos / "
    "daqui_segundos."
)

Unidade = Literal["minutos", "horas", "dias"]
_UNIDADES: dict[str, timedelta] = {
    "minutos": timedelta(minutes=1),
    "horas": timedelta(hours=1),
    "dias": timedelta(days=1),
}
_CAMPOS_DE_TEMPO = ("cron", "a_cada", "em", "daqui_minutos", "daqui_segundos")


def _vazio(valor: object) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


class Agendar(BaseModel):
    """Cria um lembrete ou uma tarefa recorrente."""

    titulo: str = Field(min_length=1, max_length=120)
    pedido: str = Field(min_length=1, max_length=MAX_PEDIDO, description="O que fazer na hora.")
    cron: str | None = Field(default=None, description="Cron de 5 campos, no fuso do usuário.")
    a_cada: float | None = Field(default=None, gt=0)
    unidade: Unidade | None = None
    em: datetime | None = Field(default=None, description="Data e hora de uma execução única.")
    daqui_minutos: float | None = Field(default=None, gt=0)
    daqui_segundos: float | None = Field(default=None, gt=0)
    silencioso: bool = Field(
        default=False, description="Se não houver nada a relatar, não manda mensagem."
    )

    @model_validator(mode="before")
    @classmethod
    def _vazios_viram_nulos(cls, dados: object) -> object:
        # Os modelos costumam mandar campos não usados como "" ou null: não é um 2º jeito.
        if isinstance(dados, dict):
            return {
                k: (None if k in _CAMPOS_DE_TEMPO and _vazio(v) else v) for k, v in dados.items()
            }
        return dados

    @model_validator(mode="after")
    def _um_jeito_so(self) -> Agendar:
        usados = [c for c in _CAMPOS_DE_TEMPO if getattr(self, c) is not None]
        if len(usados) != 1:
            raise ValueError(
                "Use exatamente um jeito de marcar o tempo: cron, a_cada, em, daqui_minutos "
                "ou daqui_segundos."
            )
        if (self.a_cada is None) != (self.unidade is None):
            raise ValueError("a_cada e unidade andam juntos.")
        return self


class ListarAgendamentos(BaseModel):
    """Lista os agendamentos ativos deste agente."""


class CancelarAgendamento(BaseModel):
    """Cancela um agendamento pelo id (veja listar_agendamentos)."""

    agendamento_id: str = Field(min_length=1, max_length=64)


class Plano(BaseModel):
    """Como o agendamento fica guardado em ``rotinas``."""

    tipo: Literal["unico", "cron", "intervalo"]
    expressao: str | None = None
    """Cron (5 campos) ou intervalo em segundos."""
    proxima_execucao: datetime
    fuso: str


def fuso_valido(fuso: str | None) -> str:
    try:
        ZoneInfo(fuso or FUSO_PADRAO)
    except (ZoneInfoNotFoundError, ValueError):
        return FUSO_PADRAO
    return fuso or FUSO_PADRAO


def proxima_cron(expressao: str, depois_de: datetime, fuso: str = FUSO_PADRAO) -> datetime:
    """Próxima execução de um cron de 5 campos no fuso do usuário, devolvida em UTC."""
    if len(expressao.split()) != 5 or not croniter.is_valid(expressao):
        raise ErroFerramenta("Cron inválido: use 5 campos (minuto hora dia mês dia-da-semana).")
    local = depois_de.astimezone(ZoneInfo(fuso_valido(fuso)))
    proxima = croniter(expressao, local).get_next(datetime)
    return proxima.astimezone(UTC)


def intervalo_do_cron(expressao: str, fuso: str = FUSO_PADRAO) -> timedelta:
    """Menor distância entre duas execuções seguidas (amostra das próximas 10)."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    instantes = [proxima_cron(expressao, base, fuso)]
    for _ in range(9):
        instantes.append(proxima_cron(expressao, instantes[-1], fuso))
    return min(b - a for a, b in pairwise(instantes))


def planejar(args: Agendar, *, agora: datetime | None = None, fuso: str | None = None) -> Plano:
    """Valida o pedido e calcula a primeira execução."""
    agora = (agora or datetime.now(UTC)).astimezone(UTC)
    fuso = fuso_valido(fuso)
    if args.cron is not None:
        expressao = " ".join(args.cron.split())
        primeira = proxima_cron(expressao, agora, fuso)
        if intervalo_do_cron(expressao, fuso) < INTERVALO_MINIMO_CRON:
            raise ErroFerramenta("Rotinas por cron rodam no máximo a cada 5 minutos.")
        return Plano(tipo="cron", expressao=expressao, proxima_execucao=primeira, fuso=fuso)
    if args.a_cada is not None and args.unidade is not None:
        passo = _UNIDADES[args.unidade] * args.a_cada
        if passo < INTERVALO_MINIMO:
            raise ErroFerramenta("O intervalo mínimo é de 1 minuto.")
        return Plano(
            tipo="intervalo",
            expressao=str(int(passo.total_seconds())),
            proxima_execucao=agora + passo,
            fuso=fuso,
        )
    if args.em is not None:
        quando = args.em if args.em.tzinfo else args.em.replace(tzinfo=ZoneInfo(fuso))
        quando = quando.astimezone(UTC)
        if quando <= agora:
            raise ErroFerramenta("Essa data já passou.")
        if quando - agora > ATRASO_MAXIMO:
            raise ErroFerramenta("Agendamentos únicos vão no máximo até 1 ano.")
        return Plano(tipo="unico", proxima_execucao=quando, fuso=fuso)
    atraso = (
        timedelta(minutes=args.daqui_minutos)
        if args.daqui_minutos is not None
        else timedelta(seconds=args.daqui_segundos or 0)
    )
    if atraso > ATRASO_MAXIMO:
        raise ErroFerramenta("Agendamentos únicos vão no máximo até 1 ano.")
    return Plano(tipo="unico", proxima_execucao=agora + atraso, fuso=fuso)


def proxima_depois(plano: Plano, executou_em: datetime) -> datetime | None:
    """Próxima execução depois de rodar. ``None`` = agendamento único terminou.

    Se o worker ficou parado e perdeu várias execuções, pula para a próxima no futuro em vez
    de disparar todas de uma vez.
    """
    executou_em = executou_em.astimezone(UTC)
    if plano.tipo == "unico":
        return None
    if plano.tipo == "cron":
        return proxima_cron(plano.expressao or "", executou_em, plano.fuso)
    passo = timedelta(seconds=int(plano.expressao or 60))
    proxima = plano.proxima_execucao + passo
    while proxima <= executou_em:
        proxima += passo
    return proxima


def conferir_limite(ativos: int) -> None:
    if ativos >= MAX_AGENDAMENTOS_ATIVOS:
        raise ErroFerramenta(
            f"Este agente já tem {MAX_AGENDAMENTOS_ATIVOS} agendamentos ativos. Cancele um antes."
        )
