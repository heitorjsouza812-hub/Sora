"""Liga as ferramentas dos canais da empresa no catálogo (``app/ferramentas/registro.py``).

Só duas, e as duas só leem: ``consultar_cliente`` e ``consultar_conhecimento``.
"""

from __future__ import annotations

from pydantic import BaseModel

MODULO = "app.canais_empresa.ferramentas"
NOMES = ("consultar_cliente", "consultar_conhecimento")


def registrar(esquemas: dict[str, type[BaseModel]], modulos: dict[str, str]) -> None:
    from app.canais_empresa.ferramentas import ConsultarCliente, ConsultarConhecimento

    esquemas["consultar_cliente"] = ConsultarCliente
    esquemas["consultar_conhecimento"] = ConsultarConhecimento
    for nome in NOMES:
        modulos[nome] = MODULO
