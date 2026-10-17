"""Catálogo preguiçoso de ferramentas (conectores MCP e afins).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``adapters/src/lazy-tool-catalog.ts``.

Problema: cada servidor MCP conectado traz dezenas de ferramentas. Mandar todos os esquemas
em toda chamada enche o contexto e piora a escolha do modelo. Solução: até
``LIMITE_DIRETO`` (20) ferramentas vão direto para o agente; acima disso o agente recebe só
três meta-ferramentas:

- ``{prefixo}_buscar_ferramentas``: lista nomes por grupo (servidor) ou busca por palavra;
- ``{prefixo}_carregar_ferramenta``: devolve a descrição e o esquema de UMA ferramenta;
- ``{prefixo}_executar_ferramenta``: roda a ferramenta pelo id, com os argumentos validados.

Quando o índice de nomes cabe em ~2 KB ele já vai na descrição da busca, e o modelo
costuma acertar o nome sem buscar.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.ferramentas.base import ErroFerramenta

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

LIMITE_DIRETO = 20
LIMITE_BUSCA = 10
MAX_BYTES_ESQUEMA = 100_000
MAX_NOMES_NO_INDICE = 200
MAX_BYTES_INDICE = 2_048
MAX_DESCRICAO = 500
MAX_CONSULTA = 200
MAX_GRUPO = 200
GRUPO_PADRAO = "outros"

AntesDeExecutar = Callable[["BaseTool", dict[str, Any]], Awaitable[None]]
"""Gancho chamado antes de rodar a ferramenta (revisor de ações, registro, limites)."""


@dataclass(frozen=True, slots=True)
class Entrada:
    id: str
    ferramenta: BaseTool
    grupo: str


def grupo_da_ferramenta(ferramenta: BaseTool) -> str:
    """Grupo = ``metadata["grupo"]`` ou ``metadata["servidor"]``; senão ``mcp__<servidor>__…``."""
    metadata = getattr(ferramenta, "metadata", None) or {}
    for chave in ("grupo", "servidor"):
        valor = str(metadata.get(chave) or "").strip()
        if valor:
            return valor[:MAX_GRUPO]
    if ferramenta.name.startswith("mcp__") and ferramenta.name.count("__") >= 2:
        return ferramenta.name.split("__", 2)[1][:MAX_GRUPO]
    return GRUPO_PADRAO


def nome_curto(ferramenta: BaseTool) -> str:
    """``mcp__notion__buscar`` → ``buscar``."""
    if ferramenta.name.startswith("mcp__") and ferramenta.name.count("__") >= 2:
        return ferramenta.name.split("__", 2)[2]
    return ferramenta.name


def somente_leitura(ferramenta: BaseTool) -> bool:
    """Anotação do MCP (``readOnlyHint``) ou, sem ela, o nome (``get``/``list``/``buscar``…)."""
    from app.revisor.politica import parece_somente_leitura

    metadata = getattr(ferramenta, "metadata", None) or {}
    dica = metadata.get("readOnlyHint", metadata.get("somente_leitura"))
    if isinstance(dica, bool):
        return dica
    return parece_somente_leitura(nome_curto(ferramenta))


def esquema_json(ferramenta: BaseTool) -> dict[str, Any]:
    esquema = ferramenta.args_schema
    if esquema is None:
        return {"type": "object", "properties": {}}
    if isinstance(esquema, dict):
        return esquema
    if isinstance(esquema, type) and issubclass(esquema, BaseModel):
        return esquema.model_json_schema()
    return {"type": "object", "properties": dict(getattr(ferramenta, "args", {}) or {})}


def texto_indice(grupos: list[tuple[str, list[str]]]) -> str:
    return "\n".join(f"{grupo}:\n  {', '.join(nomes)}" for grupo, nomes in grupos)


def indice_cabe(grupos: list[tuple[str, list[str]]]) -> bool:
    if sum(len(nomes) for _, nomes in grupos) > MAX_NOMES_NO_INDICE:
        return False
    return len(texto_indice(grupos).encode()) <= MAX_BYTES_INDICE


def _pontuacao(entrada: Entrada, consulta: str) -> int:
    nome = entrada.ferramenta.name.lower()
    curto = nome_curto(entrada.ferramenta).lower()
    descricao = (entrada.ferramenta.description or "").lower()
    if consulta in (nome, curto):
        return 0
    if nome.startswith(consulta) or curto.startswith(consulta):
        return 1
    if consulta in nome or consulta in curto or consulta in entrada.grupo.lower():
        return 2
    if consulta in descricao:
        return 3
    palavras = [p for p in consulta.split() if len(p) > 2]
    if palavras and all(p in f"{nome} {descricao}" for p in palavras):
        return 3
    return 4


class CatalogoFerramentas:
    """Índice das ferramentas escondidas atrás das três meta-ferramentas."""

    def __init__(self, ferramentas: Sequence[BaseTool]) -> None:
        vistos: set[str] = set()
        entradas: list[Entrada] = []
        for ferramenta in ferramentas:
            if not ferramenta.name or ferramenta.name in vistos:
                continue
            vistos.add(ferramenta.name)
            entradas.append(Entrada(ferramenta.name, ferramenta, grupo_da_ferramenta(ferramenta)))
        self.entradas = entradas

    # ---------- índice ----------

    def grupos(self, entradas: list[Entrada] | None = None) -> list[tuple[str, list[str]]]:
        por_grupo: dict[str, set[str]] = {}
        for entrada in self.entradas if entradas is None else entradas:
            por_grupo.setdefault(entrada.grupo, set()).add(nome_curto(entrada.ferramenta))
        return [(grupo, sorted(nomes)) for grupo, nomes in sorted(por_grupo.items())]

    def buscar(
        self, consulta: str = "", grupo: str = "", limite: int = LIMITE_BUSCA
    ) -> dict[str, Any]:
        consulta = consulta[:MAX_CONSULTA].strip().lower()
        grupo = grupo[:MAX_GRUPO].strip()
        escopo = [e for e in self.entradas if e.grupo == grupo] if grupo else self.entradas
        if not consulta:
            if grupo:
                if not escopo:
                    return {"grupo": grupo, "nomes": [], "erro": "Grupo desconhecido ou vazio."}
                ((nome_grupo, nomes),) = self.grupos(escopo)
                if not indice_cabe([(nome_grupo, nomes)]):
                    return {
                        "grupo": nome_grupo,
                        "quantidade": len(nomes),
                        "dica": "Passe 'consulta' para buscar dentro deste grupo.",
                    }
                return {"grupo": nome_grupo, "nomes": nomes}
            agrupado = self.grupos(escopo)
            if not indice_cabe(agrupado):
                return {
                    "grupos": [{"grupo": g, "quantidade": len(n)} for g, n in agrupado],
                    "dica": "Passe 'grupo' para listar os nomes de um grupo.",
                }
            return {"indice": [{"grupo": g, "nomes": n} for g, n in agrupado]}
        limite = max(1, min(LIMITE_BUSCA, int(limite)))
        pontuados = sorted(
            ((_pontuacao(e, consulta), e) for e in escopo),
            key=lambda par: (par[0], par[1].ferramenta.name),
        )
        return {
            "ferramentas": [
                {
                    "id": e.id,
                    "nome": nome_curto(e.ferramenta),
                    "grupo": e.grupo,
                    "descricao": (e.ferramenta.description or "")[:MAX_DESCRICAO],
                    "somente_leitura": somente_leitura(e.ferramenta),
                }
                for pontos, e in pontuados
                if pontos < 4
            ][:limite]
        }

    def encontrar(self, identificador: str) -> Entrada:
        """Por id; senão por nome curto, se for único."""
        identificador = str(identificador or "")
        for entrada in self.entradas:
            if entrada.id == identificador:
                return self._conferir_tamanho(entrada)
        candidatas = [e for e in self.entradas if nome_curto(e.ferramenta) == identificador]
        if len(candidatas) == 1:
            return self._conferir_tamanho(candidatas[0])
        raise ErroFerramenta("Ferramenta desconhecida ou não autorizada para este agente.")

    @staticmethod
    def _conferir_tamanho(entrada: Entrada) -> Entrada:
        if len(json.dumps(esquema_json(entrada.ferramenta)).encode()) > MAX_BYTES_ESQUEMA:
            raise ErroFerramenta("O esquema desta ferramenta é grande demais.")
        return entrada

    def carregar(self, identificador: str) -> dict[str, Any]:
        entrada = self.encontrar(identificador)
        return {
            "id": entrada.id,
            "nome": nome_curto(entrada.ferramenta),
            "descricao": (entrada.ferramenta.description or "")[:MAX_DESCRICAO],
            "esquema": esquema_json(entrada.ferramenta),
            "somente_leitura": somente_leitura(entrada.ferramenta),
        }

    async def executar(
        self,
        identificador: str,
        argumentos: dict[str, Any],
        antes_de_executar: AntesDeExecutar | None = None,
    ) -> Any:
        entrada = self.encontrar(identificador)
        if not isinstance(argumentos, dict):
            raise ErroFerramenta("Os argumentos precisam ser um objeto.")
        validar_argumentos(esquema_json(entrada.ferramenta), argumentos)
        if antes_de_executar is not None:
            await antes_de_executar(entrada.ferramenta, argumentos)
        return await entrada.ferramenta.ainvoke(argumentos)


# ---------- validação mínima de JSON Schema ----------

_TIPOS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _tipo_confere(valor: Any, tipo: Any) -> bool:
    tipos = tipo if isinstance(tipo, list) else [tipo]
    for nome in tipos:
        esperado = _TIPOS.get(str(nome))
        if esperado is None:
            return True
        if isinstance(valor, bool) and nome in ("integer", "number"):
            continue
        if isinstance(valor, esperado):
            return True
    return False


def validar_argumentos(
    esquema: dict[str, Any], argumentos: dict[str, Any], caminho: str = ""
) -> None:
    """Confere obrigatórios, tipos, ``enum`` e ``additionalProperties: false``.

    Não é um validador completo de JSON Schema; segura os erros comuns do modelo antes de
    gastar uma chamada ao servidor. ``patternProperties`` + ``additionalProperties: false``
    é recusado (não dá para conferir com segurança aqui).
    """
    if (
        esquema.get("patternProperties") is not None
        and esquema.get("additionalProperties") is False
    ):
        raise ErroFerramenta(
            "Esquema não suportado: patternProperties com additionalProperties false."
        )
    propriedades: dict[str, Any] = esquema.get("properties") or {}
    faltando = [c for c in esquema.get("required") or [] if c not in argumentos]
    if faltando:
        raise ErroFerramenta(
            f"Argumentos inválidos: faltam {', '.join(caminho + c for c in faltando)}."
        )
    if esquema.get("additionalProperties") is False:
        sobrando = [c for c in argumentos if c not in propriedades]
        if sobrando:
            raise ErroFerramenta(
                f"Argumentos inválidos: não existem {', '.join(caminho + c for c in sobrando)}."
            )
    for chave, valor in argumentos.items():
        regra = propriedades.get(chave)
        if not isinstance(regra, dict):
            continue
        if "type" in regra and not _tipo_confere(valor, regra["type"]):
            raise ErroFerramenta(
                f"Argumentos inválidos: {caminho}{chave} deveria ser {regra['type']}."
            )
        if "enum" in regra and valor not in regra["enum"]:
            raise ErroFerramenta(f"Argumentos inválidos: {caminho}{chave} fora das opções.")
        if isinstance(valor, dict) and regra.get("type") == "object":
            validar_argumentos(regra, valor, f"{caminho}{chave}.")


# ---------- as três meta-ferramentas ----------


class BuscarFerramentas(BaseModel):
    consulta: str = Field(default="", max_length=MAX_CONSULTA)
    grupo: str = Field(default="", max_length=MAX_GRUPO)
    limite: int = Field(default=LIMITE_BUSCA, ge=1, le=LIMITE_BUSCA)


class CarregarFerramenta(BaseModel):
    id: str = Field(min_length=1, max_length=500, description="Id exato devolvido pela busca.")


class ExecutarFerramenta(BaseModel):
    id: str = Field(min_length=1, max_length=500, description="Id exato devolvido pela busca.")
    argumentos: dict[str, Any] = Field(description="Argumentos conforme o esquema carregado.")


def montar_catalogo(
    ferramentas: Sequence[BaseTool],
    *,
    prefixo: str = "conectores",
    rotulo: str = "dos conectores",
    antes_de_executar: AntesDeExecutar | None = None,
) -> list[BaseTool]:
    """Devolve as ferramentas direto (até 20) ou as três meta-ferramentas."""
    from langchain_core.tools import StructuredTool

    if prefixo.startswith("mcp_"):
        # A Anthropic recusa nomes ``mcp_…`` (um sublinhado) em alguns endpoints.
        raise ValueError("Prefixo do catálogo não pode começar com 'mcp_'.")
    if len(ferramentas) <= LIMITE_DIRETO:
        return list(ferramentas)

    catalogo = CatalogoFerramentas(ferramentas)
    agrupado = catalogo.grupos()
    if indice_cabe(agrupado):
        descricao_busca = (
            f"Busca ferramentas {rotulo}. Sem consulta, lista os nomes por grupo. "
            f"Passe 'grupo' para abrir um grupo.\n{texto_indice(agrupado)}"
        )
    else:
        descricao_busca = (
            f"Busca ferramentas {rotulo}. Sem consulta, lista os grupos. Passe 'grupo' para "
            "listar os nomes de um grupo, ou 'consulta' para buscar."
        )

    async def _buscar(consulta: str = "", grupo: str = "", limite: int = LIMITE_BUSCA) -> str:
        return json.dumps(catalogo.buscar(consulta, grupo, limite), ensure_ascii=False)

    async def _carregar(id: str) -> str:
        return json.dumps(catalogo.carregar(id), ensure_ascii=False)

    async def _executar(id: str, argumentos: dict[str, Any]) -> Any:
        return await catalogo.executar(id, argumentos, antes_de_executar)

    return [
        StructuredTool.from_function(
            coroutine=_buscar,
            name=f"{prefixo}_buscar_ferramentas",
            description=descricao_busca,
            args_schema=BuscarFerramentas,
            metadata={"somente_leitura": True},
        ),
        StructuredTool.from_function(
            coroutine=_carregar,
            name=f"{prefixo}_carregar_ferramenta",
            description=f"Carrega os parâmetros de uma ferramenta {rotulo} pelo id.",
            args_schema=CarregarFerramenta,
            metadata={"somente_leitura": True},
        ),
        StructuredTool.from_function(
            coroutine=_executar,
            name=f"{prefixo}_executar_ferramenta",
            description=f"Roda uma ferramenta {rotulo} pelo id, com os argumentos do esquema.",
            args_schema=ExecutarFerramenta,
        ),
    ]
