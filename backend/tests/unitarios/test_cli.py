"""Comando local de criação de convites."""

import re

import pytest

from app import cli


class SessaoFalsa:
    def __init__(self) -> None:
        self.adicionado = None
        self.confirmou = False

    def add(self, objeto: object) -> None:
        self.adicionado = objeto

    async def commit(self) -> None:
        self.confirmou = True


class ContextoSessao:
    def __init__(self, sessao: SessaoFalsa) -> None:
        self.sessao = sessao

    async def __aenter__(self) -> SessaoFalsa:
        return self.sessao

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.asyncio
async def test_criar_convite_persiste_codigo_e_usos(monkeypatch: pytest.MonkeyPatch) -> None:
    sessao = SessaoFalsa()
    monkeypatch.setattr(cli, "fabrica_sessoes", lambda: lambda: ContextoSessao(sessao))

    codigo = await cli.criar_convite(" RODADA-1 ", 3)

    assert codigo == "RODADA-1"
    assert sessao.adicionado.codigo == "RODADA-1"
    assert sessao.adicionado.usos_restantes == 3
    assert sessao.confirmou


@pytest.mark.asyncio
async def test_criar_convite_gera_codigo_quando_omitido(monkeypatch: pytest.MonkeyPatch) -> None:
    sessao = SessaoFalsa()
    monkeypatch.setattr(cli, "fabrica_sessoes", lambda: lambda: ContextoSessao(sessao))

    codigo = await cli.criar_convite(None, 1)

    assert re.fullmatch(r"SORA-[A-Z0-9_-]{16}", codigo)


@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_parser_rejeita_usos_invalidos(valor: str) -> None:
    with pytest.raises(SystemExit):
        cli.construir_parser().parse_args(["convite", "criar", "--usos", valor])
