"""Clientes HTTP **só de leitura** das APIs oficiais.

- Slack (``slack.com/api``): ``auth.test`` (teste de conexão), ``conversations.list``
  (``channels:read``/``groups:read``) e ``users.info`` (``users:read``). O histórico chega pelo
  webhook (Events API); o app pede ``channels:history`` e ``groups:history``.
- WhatsApp Cloud API (``graph.facebook.com``): só ``GET /{phone_number_id}`` para testar o token.

Não existe nenhum método de envio aqui, de propósito: a Sora não manda mensagens por esses
canais. O token nunca aparece em erro nem em log.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.redacao import sanitizar_erro

SLACK_API = "https://slack.com/api"
GRAPH_API = "https://graph.facebook.com/v21.0"

ESCOPOS_DE_LEITURA = ("channels:history", "groups:history", "channels:read", "users:read")
"""Os escopos que o app do Slack deve pedir. Mais do que isso não é necessário."""

PREFIXOS_DE_ESCRITA = ("chat:write", "im:write", "mpim:write", "groups:write", "channels:write")


class ErroCanalEmpresa(Exception):
    """Falha ao falar com a API do canal (mensagem já sem o token)."""


def escopos_de_escrita(escopos: list[str]) -> list[str]:
    return sorted(e for e in escopos if e.startswith(PREFIXOS_DE_ESCRITA))


class ClienteSlackLeitura:
    def __init__(self, token: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._cliente = cliente

    async def _chamar(self, metodo: str, dados: dict[str, Any] | None = None) -> httpx.Response:
        proprio = self._cliente is None
        cliente = self._cliente or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            return await cliente.post(
                f"{SLACK_API}/{metodo}",
                data=dados or {},
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.HTTPError as erro:
            raise ErroCanalEmpresa(
                f"Falha ao falar com o Slack: {sanitizar_erro(erro, [self._token])}"
            ) from erro
        finally:
            if proprio:
                await cliente.aclose()

    @staticmethod
    def _corpo(resposta: httpx.Response) -> dict[str, Any]:
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        if not corpo.get("ok"):
            raise ErroCanalEmpresa(f"O Slack recusou: {corpo.get('error') or resposta.status_code}")
        return corpo

    async def testar(self) -> dict[str, Any]:
        """``auth.test``: devolve ``{team_id, team, user_id, url, escopos}``."""
        resposta = await self._chamar("auth.test")
        corpo = self._corpo(resposta)
        escopos = [
            e.strip() for e in resposta.headers.get("x-oauth-scopes", "").split(",") if e.strip()
        ]
        return {
            "team_id": corpo.get("team_id", ""),
            "team": corpo.get("team", ""),
            "user_id": corpo.get("user_id", ""),
            "url": corpo.get("url", ""),
            "escopos": escopos,
        }

    async def listar_canais(self) -> list[dict[str, Any]]:
        """Canais que o bot enxerga. Sem o escopo opcional ``groups:read``, só os públicos."""
        for tipos in ("public_channel,private_channel", "public_channel"):
            resposta = await self._chamar(
                "conversations.list", {"types": tipos, "exclude_archived": "true", "limit": "200"}
            )
            try:
                corpo = self._corpo(resposta)
            except ErroCanalEmpresa as erro:
                if "missing_scope" in str(erro) and tipos != "public_channel":
                    continue
                raise
            return [
                {"id": c["id"], "nome": c.get("name", ""), "privado": bool(c.get("is_private"))}
                for c in corpo.get("channels", [])
                if isinstance(c, dict) and c.get("id")
            ]
        return []

    async def nome_do_usuario(self, usuario_id: str) -> str:
        resposta = await self._chamar("users.info", {"user": usuario_id})
        usuario = self._corpo(resposta).get("user") or {}
        perfil = usuario.get("profile") or {}
        return str(perfil.get("real_name") or usuario.get("real_name") or usuario.get("name") or "")


class ClienteWhatsAppLeitura:
    def __init__(self, token: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._cliente = cliente

    async def testar(self, phone_number_id: str) -> dict[str, Any]:
        """``GET /{phone_number_id}``: confere que o token enxerga o número."""
        proprio = self._cliente is None
        cliente = self._cliente or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            resposta = await cliente.get(
                f"{GRAPH_API}/{phone_number_id}",
                params={"fields": "display_phone_number,verified_name"},
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.HTTPError as erro:
            raise ErroCanalEmpresa(
                f"Falha ao falar com a Meta: {sanitizar_erro(erro, [self._token])}"
            ) from erro
        finally:
            if proprio:
                await cliente.aclose()
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        if resposta.status_code >= 400 or "error" in corpo:
            detalhe = (corpo.get("error") or {}).get("message") or resposta.status_code
            raise ErroCanalEmpresa(
                f"A Meta recusou o token: {sanitizar_erro(str(detalhe), [self._token])}"
            )
        return {
            "numero": str(corpo.get("display_phone_number") or ""),
            "nome": str(corpo.get("verified_name") or ""),
        }


def fabrica_http() -> httpx.AsyncClient | None:
    """Gancho dos testes: devolve um ``AsyncClient`` com transporte falso. ``None`` = rede real."""
    return None
