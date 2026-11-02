"""Registro ativo do navegador do worker (sem ``navegador_ler``/``navegador_agir``)."""

from __future__ import annotations

from typing import Any

from app.navegador import NavegadorAbrir
from app.navegador.abas import (
    NavegadorAbas,
    NavegadorCapturar,
    NavegadorConsole,
    NavegadorFecharAba,
    NavegadorPedirAjuda,
)
from app.navegador.arvore import ESQUEMAS as ESQUEMAS_ARVORE

MODULO = "app.ferramentas.navegador_worker"


def registrar(esquemas: dict[str, Any], modulos: dict[str, str]) -> None:
    ativos = {
        "navegador_abrir": NavegadorAbrir,
        "navegador_abas": NavegadorAbas,
        "navegador_fechar_aba": NavegadorFecharAba,
        "navegador_capturar": NavegadorCapturar,
        "navegador_console": NavegadorConsole,
        "navegador_pedir_ajuda": NavegadorPedirAjuda,
        **ESQUEMAS_ARVORE,
    }
    esquemas.update(ativos)
    modulos.update(dict.fromkeys(ativos, MODULO))
