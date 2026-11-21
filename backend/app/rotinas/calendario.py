"""Agenda das rotinas (Onda 2, 2026-11-20): as execuções previstas num intervalo de datas e o
feed iCalendar (``.ics``) que o Google Agenda, o Outlook ou o celular assinam.

Tudo aqui é função pura sobre as rotinas já carregadas: cron (no fuso da rotina), intervalo e
execução única. Rotina pausada não aparece. O feed só leva o título da rotina e o nome do bot,
nunca o pedido (que pode ter dado pessoal): quem assina o endereço é o servidor do calendário.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import Rotina
from app.rotinas.agenda import proxima_cron

MAX_DIAS = 62
MAX_POR_ROTINA = 200
FEED_FUTURO = timedelta(days=30)
DURACAO_EVENTO = "PT15M"


@dataclass(frozen=True)
class Ocorrencia:
    rotina_id: UUID
    agente_id: UUID
    titulo: str
    quando: datetime


def ocorrencias_da_rotina(rotina: Rotina, de: datetime, ate: datetime) -> list[datetime]:
    """Instantes (UTC) em que a rotina vai rodar dentro de ``[de, ate)``."""
    if not rotina.ativa or rotina.proxima_execucao is None:
        return []
    primeira = rotina.proxima_execucao.astimezone(UTC)
    if rotina.tipo == "unico":
        return [primeira] if de <= primeira < ate else []
    instantes: list[datetime] = []
    if rotina.tipo == "intervalo":
        passo = timedelta(seconds=int(rotina.expressao or 0))
        if passo <= timedelta(0):
            return []
        atual = primeira
        if atual < de:  # pula direto para perto do começo do intervalo
            atual += passo * ((de - atual) // passo)
        while atual < ate and len(instantes) < MAX_POR_ROTINA:
            if atual >= de:
                instantes.append(atual)
            atual += passo
        return instantes
    if rotina.tipo == "cron" and rotina.expressao:
        if primeira >= de:
            atual = primeira
            if primeira < ate:
                instantes.append(primeira)
        else:  # intervalo começa depois da próxima execução: conta a partir do começo dele
            atual = de - timedelta(seconds=1)
        try:
            while len(instantes) < MAX_POR_ROTINA:
                atual = proxima_cron(rotina.expressao, atual, rotina.fuso)
                if atual >= ate:
                    break
                instantes.append(atual)
        except ErroFerramenta:
            return []
    return instantes


def ocorrencias(rotinas: list[Rotina], de: datetime, ate: datetime) -> list[Ocorrencia]:
    """Todas as execuções previstas, em ordem de horário."""
    if ate <= de:
        return []
    if ate - de > timedelta(days=MAX_DIAS):
        raise ValueError(f"Peça no máximo {MAX_DIAS} dias de agenda por vez.")
    itens = [
        Ocorrencia(rotina.id, rotina.agente_id, rotina.titulo, quando)
        for rotina in rotinas
        for quando in ocorrencias_da_rotina(rotina, de, ate)
    ]
    return sorted(itens, key=lambda o: (o.quando, o.titulo))


# ---------- iCalendar (RFC 5545) ----------


def _escapar(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _dobrar(linha: str) -> str:
    """Linhas de no máximo 75 bytes; as continuações começam com espaço (RFC 5545 §3.1)."""
    bruto = linha.encode()
    if len(bruto) <= 75:
        return linha
    partes: list[str] = []
    atual = b""
    limite = 75
    for caractere in linha:
        pedaco = caractere.encode()
        if len(atual) + len(pedaco) > limite:
            partes.append(atual.decode())
            atual = b" "
            limite = 75
        atual += pedaco
    partes.append(atual.decode())
    return "\r\n".join(partes)


def _data(instante: datetime) -> str:
    return instante.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def gerar_ics(itens: list[tuple[Ocorrencia, str]], agora: datetime) -> str:
    """``itens`` = (ocorrência, nome do bot). Um VEVENT de 15 min por execução prevista."""
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Sora//Rotinas//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Rotinas da Sora",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for ocorrencia, bot in itens:
        linhas += [
            "BEGIN:VEVENT",
            f"UID:{ocorrencia.rotina_id}-{int(ocorrencia.quando.timestamp())}@sora",
            f"DTSTAMP:{_data(agora)}",
            f"DTSTART:{_data(ocorrencia.quando)}",
            f"DURATION:{DURACAO_EVENTO}",
            f"SUMMARY:{_escapar(ocorrencia.titulo)}",
            f"DESCRIPTION:{_escapar(f'Rotina de {bot} na Sora.')}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return "\r\n".join(_dobrar(linha) for linha in linhas) + "\r\n"
