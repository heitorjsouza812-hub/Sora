"""Registro das ferramentas e montagem como ``@tool`` do LangChain (especificação
§4 e §6.1: ``@tool`` com ``args_schema`` = a classe Pydantic).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.buscar_web import BuscarWeb
from app.ferramentas.criar_agente import CriarAgente
from app.ferramentas.disparar_especialista import DispararEspecialista
from app.ferramentas.entregar import Entregar
from app.ferramentas.escrever_arquivo import EscreverArquivo
from app.ferramentas.falar import Falar
from app.ferramentas.gerar_imagem import GerarImagem
from app.ferramentas.ler_anexo import LerAnexo
from app.ferramentas.ler_pagina import LerPagina
from app.ferramentas.mensagem_especialista import MensagemEspecialista
from app.ferramentas.parar_especialista import PararEspecialista
from app.ferramentas.perguntar import Perguntar
from app.ferramentas.ver_especialista import VerEspecialista
from app.ferramentas.veredito import Veredito

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

ESQUEMAS: dict[str, type[BaseModel]] = {
    "falar": Falar,
    "perguntar": Perguntar,
    "disparar_especialista": DispararEspecialista,
    "ver_especialista": VerEspecialista,
    "mensagem_especialista": MensagemEspecialista,
    "parar_especialista": PararEspecialista,
    "buscar_web": BuscarWeb,
    "ler_pagina": LerPagina,
    "ler_anexo": LerAnexo,
    "escrever_arquivo": EscreverArquivo,
    "gerar_imagem": GerarImagem,
    "entregar": Entregar,
    "veredito": Veredito,
    "criar_agente": CriarAgente,
}
"""Ferramentas da fase 1: nome → esquema dos argumentos."""


def criar_ferramentas(nomes: list[str], contexto: ContextoFerramenta) -> list[BaseTool]:
    """Monta as ferramentas pedidas como ``@tool`` do LangChain, presas ao contexto."""
    raise NotImplementedError
