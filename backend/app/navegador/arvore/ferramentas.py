"""Ferramentas dos agentes para o navegador por árvore e o texto que o modelo recebe.

- ``navegador_observar``: lê a aba como árvore (papel, nome, valor, estados) com refs
  ``@sXXXXXXX:eN``;
- ``navegador_procurar``: acha elementos por papel, nome, valor, texto ou id;
- ``navegador_elemento``: lê uma propriedade de uma ref ou responde sim/não;
- ``navegador_acao``: age numa ref (clicar, digitar, definir valor, marcar, selecionar, rolar…);
- ``navegador_tecla``: aperta uma tecla ou combinação (``Enter``, ``ctrl+a``);
- ``navegador_esperar``: espera uma condição (elemento, texto, URL, evento);
- ``navegador_lote``: vários comandos em ordem numa chamada só (não é transação).

Ler, procurar e esperar não mudam nada (política livre); ``navegador_acao``, ``navegador_tecla`` e
``navegador_lote`` passam pelo revisor de ações (``app/revisor/politica.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ferramentas.base import LIMITE_RESULTADO_CARACTERES, ContextoFerramenta, ErroFerramenta
from app.navegador.arvore.acionabilidade import Politica
from app.navegador.arvore.motor import (
    PRAZO_ESPERA_MAXIMO_MS,
    Acao,
    CursorAgente,
    NavegadorArvore,
)
from app.navegador.arvore.resposta import Codigo, ErroNavegador, Resposta

_REF = r"^@?s[a-z0-9]{7}:e[0-9]+$"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aba_id: UUID | None = Field(
        default=None, description="Aba a usar. Sem ela, vale a aba que você usou por último."
    )


class NavegadorObservar(_Base):
    """Lê a página como árvore: cada elemento acionável vem com uma ref para as outras
    ferramentas. Página grande: use ``esqueleto`` e depois perfure uma região com ``raiz``."""

    somente_interativos: bool = Field(default=True, description="Só o que tem ref + títulos.")
    compacto: bool = Field(default=True, description="Junta contêineres vazios.")
    esqueleto: bool = Field(
        default=False, description="Mapa raso (3 níveis) com a contagem do que ficou dentro."
    )
    raiz: str | None = Field(
        default=None, pattern=_REF, description="Ref para ler só aquela região (perfurar)."
    )
    profundidade_max: int = Field(default=10, ge=1, le=30)
    incluir_limites: bool = Field(default=False, description="Inclui posição e tamanho.")


class NavegadorProcurar(_Base):
    """Acha elementos sem ler a página toda. ``exato`` compara o texto inteiro."""

    papel: str | None = Field(default=None, max_length=40, description="Ex.: button, link.")
    nome: str | None = Field(default=None, max_length=200)
    valor: str | None = Field(default=None, max_length=200)
    texto: str | None = Field(
        default=None, max_length=200, description="Texto visível dentro do elemento."
    )
    id_nativo: str | None = Field(default=None, max_length=200, description="id/data-testid/name.")
    exato: bool = False
    primeiro: bool = False
    contar: bool = False
    limite: int = Field(default=20, ge=1, le=50)
    raiz: str | None = Field(default=None, pattern=_REF)


class NavegadorElemento(_Base):
    """Lê uma propriedade de uma ref ou responde sim/não sobre ela."""

    ref: str = Field(pattern=_REF)
    propriedade: Literal[
        "texto", "valor", "titulo", "limites", "papel", "estados",
        "visivel", "habilitado", "marcado", "focado", "expandido", "selecionado",
    ] = "texto"  # fmt: skip


class NavegadorAcao(_Base):
    """Age numa ref. Prefira ``definir_valor`` para preencher campos e ``marcar``/``desmarcar``
    em vez de ``alternar``. Leia ``entrega.repetir`` antes de repetir qualquer ação."""

    ref: str | None = Field(
        default=None, pattern=_REF, description="Sem ref, só 'rolar' (a página inteira)."
    )
    acao: Acao
    texto: str | None = Field(default=None, max_length=5_000)
    opcao: str | None = Field(default=None, max_length=300, description="Para 'selecionar'.")
    direcao: Literal["cima", "baixo", "esquerda", "direita"] | None = None
    quantidade: int = Field(default=3, ge=1, le=20, description="Passos de rolagem (100 px).")
    destino: str | None = Field(default=None, pattern=_REF, description="Para 'arrastar'.")
    prazo_ms: int | None = Field(default=None, ge=0, le=PRAZO_ESPERA_MAXIMO_MS)
    esperar_por: str | None = Field(
        default=None, max_length=200, description="Depois de agir, espera 'papel:texto'."
    )
    esperar_sumir: str | None = Field(default=None, max_length=200)
    prazo_espera_ms: int | None = Field(default=None, ge=0, le=PRAZO_ESPERA_MAXIMO_MS)


class NavegadorTecla(_Base):
    """Aperta uma tecla ou combinação na aba (``Enter``, ``Tab``, ``ctrl+a``, ``shift+Tab``)."""

    tecla: str = Field(min_length=1, max_length=40)
    esperar_por: str | None = Field(default=None, max_length=200)
    esperar_sumir: str | None = Field(default=None, max_length=200)
    prazo_espera_ms: int | None = Field(default=None, ge=0, le=PRAZO_ESPERA_MAXIMO_MS)


class NavegadorEsperar(_Base):
    """Espera uma condição, nunca um tempo fixo às cegas. Use um modo só: ``ms``, ``ref``
    (+ ``predicado``), ``texto``/``papel`` (aparecer, ou ``sumir``), ``url_contem`` ou
    ``evento``."""

    ms: int | None = Field(default=None, ge=0, le=PRAZO_ESPERA_MAXIMO_MS)
    ref: str | None = Field(default=None, pattern=_REF)
    predicado: Literal["existe", "visivel", "habilitado", "acionavel", "valor"] = "existe"
    valor: str | None = Field(default=None, max_length=300)
    acao: str = Field(default="clicar", max_length=20)
    texto: str | None = Field(default=None, max_length=200)
    papel: str | None = Field(default=None, max_length=40)
    contagem: int | None = Field(default=None, ge=0, le=1000)
    sumir: bool = False
    url_contem: str | None = Field(default=None, max_length=300)
    evento: Literal["navegou", "dialogo_nativo", "superficie_abriu", "superficie_fechou"] | None = (
        None
    )
    prazo_ms: int | None = Field(default=None, ge=0, le=PRAZO_ESPERA_MAXIMO_MS)


class PassoLote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comando: Literal["observar", "procurar", "elemento", "agir", "tecla", "esperar"]
    args: dict[str, Any] = Field(default_factory=dict)


class NavegadorLote(_Base):
    """Vários comandos em ordem numa chamada (ex.: preencher três campos e enviar)."""

    passos: list[PassoLote] = Field(min_length=1, max_length=20)
    parar_no_erro: bool = True


ESQUEMAS: dict[str, type[BaseModel]] = {
    "navegador_observar": NavegadorObservar,
    "navegador_procurar": NavegadorProcurar,
    "navegador_elemento": NavegadorElemento,
    "navegador_acao": NavegadorAcao,
    "navegador_tecla": NavegadorTecla,
    "navegador_esperar": NavegadorEsperar,
    "navegador_lote": NavegadorLote,
}
COMANDO_DA_FERRAMENTA = {
    "navegador_observar": "observar",
    "navegador_procurar": "procurar",
    "navegador_elemento": "elemento",
    "navegador_acao": "agir",
    "navegador_tecla": "tecla",
    "navegador_esperar": "esperar",
    "navegador_lote": "lote",
}
ESQUEMAS_DO_LOTE: dict[str, type[BaseModel]] = {
    "observar": NavegadorObservar,
    "procurar": NavegadorProcurar,
    "elemento": NavegadorElemento,
    "agir": NavegadorAcao,
    "tecla": NavegadorTecla,
    "esperar": NavegadorEsperar,
}


# ---------- texto para o modelo ----------


def _linha_no(no: dict[str, Any], nivel: int) -> str:
    partes = ["  " * nivel + "- " + (no.get("papel") or "?")]
    if no.get("papel") == "text":
        return "  " * nivel + "- texto: " + json.dumps(no.get("nome", ""), ensure_ascii=False)
    if no.get("nome"):
        partes.append(json.dumps(no["nome"], ensure_ascii=False))
    if no.get("ref"):
        partes.append(no["ref"])
    if no.get("estados"):
        partes.append("[" + ", ".join(no["estados"]) + "]")
    if no.get("valor") is not None:
        partes.append("valor=" + json.dumps(no["valor"], ensure_ascii=False))
    if no.get("limites"):
        partes.append("@" + ",".join(str(round(v)) for v in no["limites"]))
    if no.get("filhos_cortados"):
        partes.append(f"(+{no['filhos_cortados']} dentro; perfure com raiz={no.get('ref')})")
    if no.get("subarvore_cortada"):
        partes.append("(… resto cortado pelo orçamento)")
    return " ".join(partes)


def _linhas_arvore(nos: list[dict[str, Any]], nivel: int = 0) -> list[str]:
    linhas: list[str] = []
    for no in nos:
        linhas.append(_linha_no(no, nivel))
        if no.get("filhos"):
            linhas.extend(_linhas_arvore(no["filhos"], nivel + 1))
    return linhas


def _cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    return texto[:limite] + "\n… (resposta cortada; use esqueleto, raiz ou navegador_procurar)"


def para_modelo(resposta: Resposta, limite: int = LIMITE_RESULTADO_CARACTERES) -> str:
    """Texto compacto (vai dentro da cerca ``<dado_externo>``): árvore em linhas, o resto JSON."""
    if not resposta.ok:
        assert resposta.erro is not None
        erro = resposta.erro.para_json()
        linhas = [f"ERRO {erro['codigo']}: {erro['mensagem']}"]
        entrega = erro["entrega"]
        linhas.append(f"entrega: {entrega['entrega']} · repetir: {entrega['repetir']}")
        if erro.get("sugestao"):
            linhas.append(f"sugestão: {erro['sugestao']}")
        if erro.get("detalhes"):
            linhas.append("detalhes: " + json.dumps(erro["detalhes"], ensure_ascii=False))
        return _cortar("\n".join(linhas), limite)
    dados = dict(resposta.dados)
    if resposta.comando == "observar" and "arvore" in dados:
        arvore = dados.pop("arvore")
        cabecalho = [
            f"Página: {dados.get('titulo') or '(sem título)'} — {dados.get('url', '')}",
            f"Leitura {dados['leitura']} · {dados['refs']} refs · "
            + (
                "completa"
                if dados.get("completa")
                else f"PARCIAL ({dados.get('nos_observados')} nós; perfure com raiz)"
            ),
        ]
        if dados.get("raiz"):
            cabecalho[1] += f" · região {dados['raiz']}"
        rolagem = dados.get("rolagem") or {}
        if rolagem.get("tem_mais_abaixo"):
            cabecalho.append("Há mais página abaixo (navegador_acao acao=rolar).")
        if dados.get("superficies"):
            cabecalho.append(
                "Abertos agora: " + json.dumps(dados["superficies"], ensure_ascii=False)
            )
        corpo = _linhas_arvore(arvore) or ["(nenhum elemento)"]
        return _cortar("\n".join([*cabecalho, "", *corpo]), limite)
    return _cortar(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), limite)


# ---------- serviço: liga as ferramentas às abas ----------


class ServicoArvore:
    """Liga as ferramentas às abas do navegador persistente (``app/navegador/abas.py``).

    ``obter_pagina`` devolve a página do Playwright de uma aba já carregada (o
    ``MotorPlaywright`` do worker). ``cursor_do_agente`` dá a cor e o nome do agente para o
    cursor colorido (``None`` desliga).
    """

    def __init__(
        self,
        gerente: Any,
        obter_pagina: Callable[[Any], Any],
        *,
        politica: Politica = Politica.FISICA,
        cursor_do_agente: Callable[[UUID], CursorAgente | None] | None = None,
    ) -> None:
        self._gerente = gerente
        self._obter_pagina = obter_pagina
        self._politica = politica
        self._cursor_do_agente = cursor_do_agente
        self._por_aba: dict[UUID, tuple[Any, NavegadorArvore]] = {}

    async def _navegador(
        self, contexto: ContextoFerramenta, aba_id: UUID | None
    ) -> NavegadorArvore:
        if aba_id is None:
            abas = sorted(
                self._gerente.do_agente(contexto.agente_id, so_efemeras=contexto.sem_supervisao),
                key=lambda a: a.usada_em,
            )
            if not abas:
                raise ErroNavegador(
                    Codigo.ABA_NAO_ENCONTRADA, "Você não tem abas abertas. Abra uma página antes."
                )
            aba_id = abas[-1].id
        try:
            aba = await self._gerente.usar(
                aba_id, contexto.agente_id, sem_supervisao=contexto.sem_supervisao
            )
        except ErroFerramenta as erro:
            codigo = Codigo.POLITICA_NEGADA if "usuário" in str(erro) else Codigo.ABA_NAO_ENCONTRADA
            raise ErroNavegador(codigo, str(erro)) from erro
        pagina = self._obter_pagina(aba)
        guardado = self._por_aba.get(aba.id)
        if guardado is None or guardado[0] is not pagina:
            # página nova (aba recarregada depois de descarregar): refs antigas não valem mais
            cursor = self._cursor_do_agente(contexto.agente_id) if self._cursor_do_agente else None
            guardado = (pagina, NavegadorArvore(pagina, politica=self._politica, cursor=cursor))
            self._por_aba[aba.id] = guardado
        return guardado[1]

    def esquecer_aba(self, aba_id: UUID) -> None:
        self._por_aba.pop(aba_id, None)

    def ultimo_rastro(self, aba_id: UUID) -> dict[str, Any] | None:
        guardado = self._por_aba.get(aba_id)
        if guardado is None or not guardado[1].rastro.eventos:
            return None
        return dict(guardado[1].rastro.eventos[-1])

    async def executar(self, nome: str, args: BaseModel, contexto: ContextoFerramenta) -> Resposta:
        comando = COMANDO_DA_FERRAMENTA.get(nome)
        if comando is None:
            raise ErroFerramenta(f"Ferramenta desconhecida: {nome}")
        try:
            navegador = await self._navegador(contexto, getattr(args, "aba_id", None))
        except ErroNavegador as erro:
            return Resposta.falha(comando, erro)
        return await navegador.executar_comando(comando, args)

    async def executar_para_modelo(
        self, nome: str, args: BaseModel, contexto: ContextoFerramenta
    ) -> str:
        return para_modelo(await self.executar(nome, args, contexto))
