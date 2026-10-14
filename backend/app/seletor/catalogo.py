"""Catálogo de modelos: carrega ``config/catalogo_modelos.yaml``.

Especificação: §5 "Catálogo de modelos". Diz nível, capacidades, contexto, preço e velocidade de
cada modelo conhecido. Preço e contexto que faltarem no YAML vêm do ``litellm.model_cost``.
Modelo fora do catálogo entra como N2 e sem capacidades confirmadas, até ser testado ou
classificado pelo usuário. Modelos do OpenRouter (``openrouter/<provedor>/<modelo>``) são
cruzados pelo nome sem o prefixo ``openrouter/``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.llm.custo import PrecoModelo, contexto_litellm, precos_litellm
from app.modelos.enumeracoes import Nivel
from app.seletor.politica import diretorio_config, ler_yaml
from app.seletor.tipos import Capacidade, NivelDeModelo

CONTEXTO_DESCONHECIDO = 8_192
"""Contexto assumido para modelo sem dado no catálogo nem no LiteLLM (conservador)."""

_PREFIXO_OPENROUTER = "openrouter/"
# Nome do provedor no OpenRouter → prefixo usado no catálogo (LiteLLM).
_APELIDOS_OPENROUTER = {"google": "gemini", "x-ai": "xai", "z-ai": "zai", "mistralai": "mistral"}


class EntradaCatalogo(BaseModel):
    modelo: str  # nome no LiteLLM
    provedor: str  # origem: groq, openai, anthropic, google, xai, deepseek, zai, mistral, ollama
    nivel: NivelDeModelo
    capacidades: list[Capacidade] = Field(default_factory=list)
    uso: str = ""
    contexto: int | None = None
    preco_entrada: Decimal | None = None  # US$ por 1M tokens
    preco_saida: Decimal | None = None
    velocidade_tps: int | None = None
    observacao: str | None = None
    confirmar_nome: bool = False
    somente_se_escolhido: bool = False  # ex.: claude-fable-5-1 nunca é escolhido sozinho


class ClassificacaoModelo(BaseModel):
    """Resultado do cruzamento de um modelo listado pelo provedor com o catálogo."""

    modelo: str
    nivel: NivelDeModelo
    capacidades: list[Capacidade]
    contexto: int
    preco_entrada: Decimal | None
    preco_saida: Decimal | None
    velocidade_tps: int | None
    somente_se_escolhido: bool = False
    origem: str  # "catalogo" ou "usuario" (valores de modelos_disponiveis.origem)


def _variantes_do_nome(nome: str) -> list[str]:
    """Nomes sob os quais procurar no catálogo, do mais exato ao mais frouxo."""
    variantes = [nome]
    if nome.startswith(_PREFIXO_OPENROUTER):
        sem_prefixo = nome.removeprefix(_PREFIXO_OPENROUTER)
        variantes.append(sem_prefixo)
        provedor, _, resto = sem_prefixo.partition("/")
        if resto and provedor in _APELIDOS_OPENROUTER:
            variantes.append(f"{_APELIDOS_OPENROUTER[provedor]}/{resto}")
    return variantes


class Catalogo(BaseModel):
    versao: int
    conferido_em: date
    modelos: list[EntradaCatalogo]

    def buscar(self, nome_modelo: str) -> EntradaCatalogo | None:
        """Acha a entrada pelo nome no LiteLLM (aceita o prefixo ``openrouter/``).

        Tenta o nome exato, depois sem ``openrouter/`` (com o apelido do provedor do OpenRouter,
        ex.: ``google/`` → ``gemini/``) e, por fim, entradas cujo nome termina com
        ``/<nome sem prefixo>`` (ex.: ``openai/gpt-oss-120b`` do OpenRouter → ``groq/openai/...``).
        """
        por_nome = {entrada.modelo: entrada for entrada in self.modelos}
        variantes = _variantes_do_nome(nome_modelo)
        for variante in variantes:
            if variante in por_nome:
                return por_nome[variante]
        if nome_modelo.startswith(_PREFIXO_OPENROUTER):
            sufixo = "/" + variantes[1]
            terminam_igual = [e for e in self.modelos if e.modelo.endswith(sufixo)]
            if len(terminam_igual) == 1:
                return terminam_igual[0]
        return None

    def classificar(self, nome_modelo: str) -> ClassificacaoModelo:
        """Cruza o modelo com o catálogo, completando preço/contexto pelo LiteLLM.

        Fora do catálogo: N2, sem capacidades confirmadas, ``origem = "usuario"``.
        """
        entrada = self.buscar(nome_modelo)
        preco_litellm = precos_litellm(nome_modelo) or PrecoModelo()
        if entrada is None:
            return ClassificacaoModelo(
                modelo=nome_modelo,
                nivel=Nivel.N2,
                capacidades=[],
                contexto=contexto_litellm(nome_modelo) or CONTEXTO_DESCONHECIDO,
                preco_entrada=preco_litellm.entrada,
                preco_saida=preco_litellm.saida,
                velocidade_tps=None,
                origem="usuario",
            )
        entrada_litellm = precos_litellm(entrada.modelo) or preco_litellm
        return ClassificacaoModelo(
            modelo=nome_modelo,
            nivel=entrada.nivel,
            capacidades=list(entrada.capacidades),
            contexto=entrada.contexto
            or contexto_litellm(entrada.modelo)
            or contexto_litellm(nome_modelo)
            or CONTEXTO_DESCONHECIDO,
            preco_entrada=entrada.preco_entrada
            if entrada.preco_entrada is not None
            else entrada_litellm.entrada,
            preco_saida=entrada.preco_saida
            if entrada.preco_saida is not None
            else entrada_litellm.saida,
            velocidade_tps=entrada.velocidade_tps,
            somente_se_escolhido=entrada.somente_se_escolhido,
            origem="catalogo",
        )


def carregar_catalogo(caminho: Path | None = None) -> Catalogo:
    """Lê e valida o YAML. Nome de modelo repetido é erro."""
    catalogo = Catalogo.model_validate(
        ler_yaml(caminho or diretorio_config() / "catalogo_modelos.yaml")
    )
    nomes = [entrada.modelo for entrada in catalogo.modelos]
    repetidos = sorted({n for n in nomes if nomes.count(n) > 1})
    if repetidos:
        raise ValueError(f"catalogo_modelos.yaml com modelos repetidos: {', '.join(repetidos)}")
    return catalogo


@cache
def obter_catalogo() -> Catalogo:
    """O catálogo do processo (carregado uma vez, em cache)."""
    return carregar_catalogo()
