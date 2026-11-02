"""Perfis do navegador persistente: onde ficam os logins e cookies que cada agente usa.

Ideia vista no OpenBot (github.com/nightly-labs/openbot, PolyForm Noncommercial). **Nenhum código
foi copiado**; esta é uma implementação própria da Sora — veja ``docs/referencias/openbot.md``.

Cada agente usa um destes:

- **compartilhado** (padrão): um perfil por conta; todos os agentes da conta veem os mesmos
  logins (entrou no Instagram uma vez, todos podem usar);
- **só deste agente**: logins separados, só dele;
- **perfil nomeado** ("Cliente A", "Pessoal"): vários agentes podem usar o mesmo. O nome é só
  rótulo: renomear não perde nada, porque a pasta e a chave usam o id, nunca o nome.

O estado (cookies e ``localStorage``) sai do Playwright como JSON e vai para o banco **cifrado**
com a chave mestra, com AAD ``usuario:navegador:<partição>`` — copiar a coluna para outra conta
ou outro perfil não decifra. Partição com chave malformada ou de perfil apagado é descartada:
nunca abre uma aba "logada" na conta errada.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.core.seguranca import cifrar_segredo, decifrar_segredo
from app.ferramentas.base import ErroFerramenta

MAX_PERFIS_NOMEADOS = 20
MAX_NOME_PERFIL = 60
MAX_ESTADO_BYTES = 2 * 1024 * 1024
"""Estado maior que isso não é salvo (sinal de site guardando lixo no ``localStorage``)."""

CORES_PERFIL = ("#56A8FF", "#AC80FF", "#46E8A8", "#FFB547", "#FF6B8B", "#4DD7E8")
"""Cores para diferenciar os perfis na interface (nunca o branco da Sora)."""


class TipoPerfil(StrEnum):
    COMPARTILHADO = "compartilhado"
    AGENTE = "agente"
    NOMEADO = "nomeado"


CHAVE_METADADOS = "_sora"
"""Metadados cifrados junto do perfil, mas nunca entregues ao Playwright."""


@dataclass(frozen=True, slots=True)
class EscolhaPerfil:
    """O que está salvo no agente."""

    tipo: TipoPerfil = TipoPerfil.COMPARTILHADO
    perfil_id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.tipo is TipoPerfil.NOMEADO) != (self.perfil_id is not None):
            raise ValueError("Só o perfil nomeado tem id.")


@dataclass(slots=True)
class PerfilNomeado:
    id: UUID
    usuario_id: UUID
    nome: str
    cor: str
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


_PARTICAO = re.compile(
    r"^u(?P<u>[0-9a-f]{32})-(?:(?P<c>compartilhado)|agente-(?P<a>[0-9a-f]{32})|perfil-(?P<p>[0-9a-f]{32}))$"
)


def _hex(valor: UUID) -> str:
    return valor.hex


def particao(usuario_id: UUID, agente_id: UUID, escolha: EscolhaPerfil) -> str:
    """Nome estável da partição (pasta de dados e AAD da cifra). Nunca usa o nome do perfil."""
    base = f"u{_hex(usuario_id)}"
    if escolha.tipo is TipoPerfil.COMPARTILHADO:
        return f"{base}-compartilhado"
    if escolha.tipo is TipoPerfil.AGENTE:
        chave = hashlib.sha256(str(agente_id).encode()).hexdigest()[:32]
        return f"{base}-agente-{chave}"
    assert escolha.perfil_id is not None
    return f"{base}-perfil-{_hex(escolha.perfil_id)}"


def particao_efemera() -> str:
    """Partição descartável de uma execução sem supervisão; não identifica o perfil do agente."""
    return f"efemero-{uuid4().hex}"


def estado_playwright(estado: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove metadados da Sora antes de passar o estado ao Playwright."""
    if not estado:
        return None
    return {chave: estado[chave] for chave in ("cookies", "origins") if chave in estado}


def perfil_tem_login(estado: dict[str, Any] | None) -> bool:
    estado = estado_playwright(estado) or {}
    return bool(estado.get("cookies") or estado.get("origins"))


def dominios_aprovados(estado: dict[str, Any] | None) -> set[str]:
    metadados = (estado or {}).get(CHAVE_METADADOS) or {}
    valores = metadados.get("dominios_aprovados") or [] if isinstance(metadados, dict) else []
    return {str(valor).lower() for valor in valores if isinstance(valor, str) and valor}


def com_dominio_aprovado(estado: dict[str, Any] | None, dominio: str) -> dict[str, Any]:
    """Devolve o estado com a aprovação persistida no mesmo registro cifrado do perfil."""
    novo = dict(estado or {"cookies": [], "origins": []})
    metadados = dict(novo.get(CHAVE_METADADOS) or {})
    aprovados = dominios_aprovados(novo)
    aprovados.add(dominio.lower())
    metadados["dominios_aprovados"] = sorted(aprovados)
    novo[CHAVE_METADADOS] = metadados
    return novo


@dataclass(frozen=True, slots=True)
class ParticaoLida:
    usuario_id: UUID
    tipo: TipoPerfil
    perfil_id: UUID | None


def ler_particao(nome: str) -> ParticaoLida | None:
    """Confere uma partição salva. ``None`` = descartar (malformada)."""
    achou = _PARTICAO.match(nome)
    if achou is None:
        return None
    usuario = UUID(hex=achou["u"])
    if achou["c"]:
        return ParticaoLida(usuario, TipoPerfil.COMPARTILHADO, None)
    if achou["a"]:
        return ParticaoLida(usuario, TipoPerfil.AGENTE, None)
    return ParticaoLida(usuario, TipoPerfil.NOMEADO, UUID(hex=achou["p"]))


def particao_valida(nome: str, *, usuario_id: UUID, perfis_existentes: set[UUID]) -> bool:
    lida = ler_particao(nome)
    if lida is None or lida.usuario_id != usuario_id:
        return False
    return lida.tipo is not TipoPerfil.NOMEADO or lida.perfil_id in perfis_existentes


def novo_perfil(usuario_id: UUID, nome: str, existentes: list[PerfilNomeado]) -> PerfilNomeado:
    nome = " ".join(nome.split())
    if not 1 <= len(nome) <= MAX_NOME_PERFIL:
        raise ErroFerramenta(f"O nome do perfil precisa ter de 1 a {MAX_NOME_PERFIL} caracteres.")
    if len(existentes) >= MAX_PERFIS_NOMEADOS:
        raise ErroFerramenta(f"Cada conta tem no máximo {MAX_PERFIS_NOMEADOS} perfis.")
    if any(p.nome.casefold() == nome.casefold() for p in existentes):
        raise ErroFerramenta("Já existe um perfil com esse nome.")
    usadas = [p.cor for p in existentes]
    cor = min(CORES_PERFIL, key=lambda c: (usadas.count(c), CORES_PERFIL.index(c)))
    return PerfilNomeado(id=uuid4(), usuario_id=usuario_id, nome=nome, cor=cor)


def _aad(particao_: str) -> str:
    return f"navegador:{particao_}"


def cifrar_estado(estado: dict[str, Any], *, usuario_id: UUID, particao_: str) -> bytes:
    """Cifra o ``storage_state`` do Playwright para gravar no banco."""
    texto = json.dumps(estado, separators=(",", ":"), ensure_ascii=False)
    if len(texto.encode()) > MAX_ESTADO_BYTES:
        raise ErroFerramenta(
            "Os dados de login deste perfil passaram do limite e não foram salvos."
        )
    return cifrar_segredo(texto, usuario_id=usuario_id, provedor=_aad(particao_))


def decifrar_estado(valor: bytes, *, usuario_id: UUID, particao_: str) -> dict[str, Any]:
    texto = decifrar_segredo(valor, usuario_id=usuario_id, provedor=_aad(particao_))
    estado = json.loads(texto)
    if not isinstance(estado, dict):
        raise ValueError("Estado do navegador inválido.")
    return estado
