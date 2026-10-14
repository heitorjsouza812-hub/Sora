"""Contrato de eventos com o app (especificação §2, §3 e §8.5).

Cada JSON de ``tests/contrato`` precisa bater exatamente com o modelo de
``app/eventos/tipos.py``: validar sem erro e voltar idêntico no
``model_dump(mode="json")`` (nada a mais, nada a menos).
"""

import json
import re
import typing
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel

from app.eventos.tipos import TIPOS_EVENTOS_ESTADO, Evento, EventoEstado

PASTA = Path(__file__).parent
PASTA_USUARIO = PASTA / "usuario"
ID_DO_STREAM = re.compile(r"^\d+-\d+$")

MODELOS: dict[str, type[BaseModel]] = {m.evento: m for m in typing.get_args(Evento)}
MODELOS_ESTADO: dict[str, type[BaseModel]] = {m.evento: m for m in typing.get_args(EventoEstado)}

ARQUIVOS_CONVERSA = sorted(PASTA.glob("*.json"))
ARQUIVOS_USUARIO = sorted(PASTA_USUARIO.glob("*.json"))


def _ler(caminho: Path) -> dict[str, typing.Any]:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _confere_envelope(exemplo: dict[str, typing.Any], caminho: Path) -> None:
    assert set(exemplo) == {"id", "event", "data"}
    assert isinstance(exemplo["id"], str)
    assert ID_DO_STREAM.match(exemplo["id"]), "id deve ser o do Redis Stream"
    assert exemplo["event"] == caminho.stem


def _confere_ids_unicos(arquivos: list[Path]) -> None:
    ids = [tuple(map(int, _ler(c)["id"].split("-"))) for c in arquivos]
    assert len(set(ids)) == len(ids), "ids repetidos no mesmo canal"


def test_um_exemplo_por_evento() -> None:
    assert {c.stem for c in ARQUIVOS_CONVERSA} == set(MODELOS)
    assert len(ARQUIVOS_CONVERSA) == 17


def test_canal_do_usuario_tem_todos_os_eventos_de_estado() -> None:
    assert {c.stem for c in ARQUIVOS_USUARIO} == set(TIPOS_EVENTOS_ESTADO)


def test_ids_unicos_por_canal() -> None:
    _confere_ids_unicos(ARQUIVOS_CONVERSA)
    _confere_ids_unicos(ARQUIVOS_USUARIO)


@pytest.mark.parametrize("caminho", ARQUIVOS_CONVERSA, ids=lambda c: c.stem)
def test_evento_da_conversa_bate_com_o_modelo(caminho: Path) -> None:
    exemplo = _ler(caminho)
    _confere_envelope(exemplo, caminho)
    modelo = MODELOS[exemplo["event"]].model_validate(exemplo["data"])
    assert modelo.model_dump(mode="json") == exemplo["data"]


@pytest.mark.parametrize("caminho", ARQUIVOS_USUARIO, ids=lambda c: c.stem)
def test_evento_do_usuario_leva_conversa_id(caminho: Path) -> None:
    exemplo = _ler(caminho)
    _confere_envelope(exemplo, caminho)
    dados = dict(exemplo["data"])
    UUID(dados["conversa_id"])
    modelo_cls = MODELOS_ESTADO[exemplo["event"]]
    if "conversa_id" not in modelo_cls.model_fields:
        dados.pop("conversa_id")
    modelo = modelo_cls.model_validate(dados)
    assert modelo.model_dump(mode="json") == dados
