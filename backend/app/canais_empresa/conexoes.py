"""Conexões do usuário com Slack e WhatsApp Business: segredos cifrados (AES-GCM com AAD
``usuario:canal_empresa:<canal>``, o mesmo cofre das chaves de provedor) e canais escolhidos.

Nenhuma rota devolve segredo: só ``segredos_definidos`` (quais campos existem).
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.tabelas import ConexaoCanalEmpresa
from app.core.seguranca import cifrar_segredo, decifrar_segredo

CANAIS = ("slack", "whatsapp")

SEGREDOS_DO_CANAL: dict[str, tuple[str, ...]] = {
    "slack": ("bot_token", "signing_secret"),
    "whatsapp": ("access_token", "app_secret", "verify_token"),
}
"""Campos secretos de cada canal; todos obrigatórios ao criar."""

CONFIG_DO_CANAL: dict[str, tuple[str, ...]] = {
    "slack": ("team_id", "dominio", "ids_funcionarios"),
    "whatsapp": ("phone_number_id", "numero_exibicao"),
}
"""Campos não secretos de cada canal."""

_ID_SLACK = re.compile(r"^[CG][A-Z0-9]{6,}$")
_ID_TELEFONE = re.compile(r"^\d{6,20}$")
_DOMINIO_SLACK = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


class ErroConexao(ValueError):
    """Entrada inválida (a mensagem vai para o usuário, em PT-BR)."""


def _provedor(canal: str) -> str:
    return f"canal_empresa:{canal}"


def cifrar_segredos(valores: dict[str, str], *, usuario_id: UUID, canal: str) -> bytes:
    return cifrar_segredo(
        json.dumps(valores, ensure_ascii=False), usuario_id=usuario_id, provedor=_provedor(canal)
    )


def decifrar_segredos(conexao: ConexaoCanalEmpresa) -> dict[str, str]:
    bruto = decifrar_segredo(
        conexao.segredos, usuario_id=conexao.usuario_id, provedor=_provedor(conexao.canal)
    )
    dados = json.loads(bruto)
    return {k: str(v) for k, v in dados.items()} if isinstance(dados, dict) else {}


def validar_canal(canal: str) -> str:
    if canal not in CANAIS:
        raise ErroConexao("Canal desconhecido. Use slack ou whatsapp.")
    return canal


def limpar_segredos(canal: str, valores: dict[str, Any], *, completo: bool) -> dict[str, str]:
    permitidos = SEGREDOS_DO_CANAL[canal]
    desconhecidos = set(valores) - set(permitidos)
    if desconhecidos:
        raise ErroConexao("Campo desconhecido: " + ", ".join(sorted(desconhecidos)) + ".")
    limpos = {k: str(v).strip() for k, v in valores.items() if v is not None and str(v).strip()}
    if completo:
        faltam = [k for k in permitidos if k not in limpos]
        if faltam:
            raise ErroConexao("Faltam: " + ", ".join(faltam) + ".")
    return limpos


def limpar_config(canal: str, valores: dict[str, Any], *, completo: bool) -> dict[str, Any]:
    permitidos = CONFIG_DO_CANAL[canal]
    desconhecidos = set(valores) - set(permitidos)
    if desconhecidos:
        raise ErroConexao("Campo desconhecido: " + ", ".join(sorted(desconhecidos)) + ".")
    saida: dict[str, Any] = {}
    for chave, valor in valores.items():
        if chave == "ids_funcionarios":
            lista = [str(v).strip() for v in (valor or [])]
            if len(lista) > 500 or any(not re.fullmatch(r"[UW][A-Z0-9]{4,}", i) for i in lista):
                raise ErroConexao("ids_funcionarios: use ids de usuário do Slack (ex.: U0123ABC).")
            saida[chave] = lista
        elif chave == "dominio":
            texto = str(valor or "").strip().lower().removesuffix(".slack.com")
            if texto and not _DOMINIO_SLACK.fullmatch(texto):
                raise ErroConexao("dominio: informe só o nome do workspace (ex.: minhaempresa).")
            saida[chave] = texto
        elif chave == "phone_number_id":
            texto = str(valor or "").strip()
            if not _ID_TELEFONE.fullmatch(texto):
                raise ErroConexao("phone_number_id: use só números (id do número na Meta).")
            saida[chave] = texto
        else:
            saida[chave] = str(valor or "").strip()[:120]
    if completo and canal == "whatsapp" and not saida.get("phone_number_id"):
        raise ErroConexao("Informe o phone_number_id do número da empresa.")
    return saida


def validar_canais_escolhidos(canal: str, ids: list[str]) -> list[str]:
    limpos = list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))
    if len(limpos) > 200:
        raise ErroConexao("Escolha no máximo 200 canais.")
    padrao = _ID_SLACK if canal == "slack" else _ID_TELEFONE
    for i in limpos:
        if not padrao.fullmatch(i):
            raise ErroConexao(
                f"Identificador inválido: {i}."
                if canal == "slack"
                else "Use o phone_number_id (só números)."
            )
    return limpos


async def obter(sessao: AsyncSession, usuario_id: UUID, canal: str) -> ConexaoCanalEmpresa | None:
    return await sessao.scalar(
        select(ConexaoCanalEmpresa).where(
            ConexaoCanalEmpresa.usuario_id == usuario_id, ConexaoCanalEmpresa.canal == canal
        )
    )


def caminho_do_webhook(conexao: ConexaoCanalEmpresa) -> str:
    return f"/v1/canais-empresa/webhooks/{conexao.canal}/{conexao.id}"
