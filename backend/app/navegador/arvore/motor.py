"""O navegador por árvore: observar, procurar, ler, agir, teclar, esperar e lote.

Um ``NavegadorArvore`` por aba (página do Playwright). O ciclo do agente é sempre o mesmo:

    observar → agir numa ref → observar de novo (ou esperar) para conferir

Regras desta peça:

- a ref é reencontrada **e conferida** antes de agir (``identidade.py``); nunca se chuta;
- antes de agir, espera o elemento ficar pronto (``acionabilidade.py``) até o prazo;
- a ação em si roda sob a **trava da aba** (só um agente/pista mexe por vez). A espera
  acontece fora da trava; dentro dela a ref é resolvida e conferida **de novo**, porque o que se
  viu durante a espera pode ter mudado;
- ações com estado (digitar, definir valor, limpar, marcar, desmarcar, alternar, expandir,
  recolher, selecionar, focar) releem o elemento depois. Contradição legível → ``ACAO_FALHOU``;
  sem evidência → sucesso ``entregue_sem_confirmar``;
- o resultado sempre diz se a ação chegou (``entrega``) e se é seguro repetir.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0), reescrita para o
Playwright e para as regras da Sora.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.navegador.arvore.acionabilidade import (
    INTERVALO_MS,
    Exigencia,
    Politica,
    avaliar,
    erro_do_relatorio,
    prazo_para,
)
from app.navegador.arvore.identidade import Candidato, escolher, normalizar
from app.navegador.arvore.rastro import Rastro
from app.navegador.arvore.refs import ArmazemLeituras, EntradaRef, Leitura, ler_ref
from app.navegador.arvore.resposta import (
    Codigo,
    Disposicao,
    Entrega,
    ErroNavegador,
    Resposta,
    argumentos_invalidos,
)

SCRIPT = (Path(__file__).with_name("pagina.js")).read_text(encoding="utf-8")

PRAZO_ESPERA_PADRAO_MS = 10_000
PRAZO_ESPERA_MAXIMO_MS = 30_000
PASSO_ROLAGEM_PX = 100
MAX_PASSOS_LOTE = 20
ATRASO_SOLTAR_S = 0.15
PAUSA_CURSOR_S = 0.28

Acao = Literal[
    "clicar",
    "clique_duplo",
    "clique_direito",
    "pairar",
    "focar",
    "digitar",
    "definir_valor",
    "limpar",
    "selecionar",
    "marcar",
    "desmarcar",
    "alternar",
    "expandir",
    "recolher",
    "rolar",
    "rolar_ate",
    "arrastar",
]

EXIGENCIAS: dict[str, Exigencia] = {
    "clicar": Exigencia("clicar", ponteiro=True),
    "clique_duplo": Exigencia("clicar", ponteiro=True, so_fisica=True),
    "clique_direito": Exigencia(None, ponteiro=True, so_fisica=True),
    "pairar": Exigencia(None, ponteiro=True, so_fisica=True, habilitado=False),
    "focar": Exigencia("focar"),
    "digitar": Exigencia("editar", edicao=True),
    "definir_valor": Exigencia("editar", edicao=True),
    "limpar": Exigencia("editar", edicao=True),
    "selecionar": Exigencia("selecionar", ponteiro=True),
    "marcar": Exigencia("marcar", ponteiro=True),
    "desmarcar": Exigencia("marcar", ponteiro=True),
    "alternar": Exigencia("marcar", ponteiro=True),
    "expandir": Exigencia("expandir", ponteiro=True),
    "recolher": Exigencia("expandir", ponteiro=True),
    "rolar": Exigencia("rolar", habilitado=False),
    "rolar_ate": Exigencia(None, habilitado=False),
    "arrastar": Exigencia(None, ponteiro=True, so_fisica=True),
}
COM_TEXTO = frozenset({"digitar", "definir_valor"})
PAPEIS_DE_CONTEUDO = frozenset({"textbox", "combobox", "listbox", "spinbutton", "slider"})
PROPRIEDADES_LEITURA = frozenset({"texto", "valor", "titulo", "limites", "papel", "estados"})
PROPRIEDADES_SIM_NAO = frozenset(
    {"visivel", "habilitado", "marcado", "focado", "expandido", "selecionado"}
)

TECLAS = frozenset(
    {
        "Enter", "Tab", "Escape", "Backspace", "Delete", "Space", "Home", "End", "PageUp",
        "PageDown", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Insert",
        *(f"F{n}" for n in range(1, 13)),
    }
)  # fmt: skip
_APELIDOS_TECLA = {
    "enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape", "escape": "Escape",
    "backspace": "Backspace", "delete": "Delete", "del": "Delete", "space": "Space",
    "espaco": "Space", "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "cima": "ArrowUp", "baixo": "ArrowDown", "esquerda": "ArrowLeft", "direita": "ArrowRight",
}  # fmt: skip
_MODIFICADORES = {
    "ctrl": "Control", "control": "Control", "shift": "Shift", "alt": "Alt", "meta": "Meta",
    "cmd": "Meta",
}  # fmt: skip


def normalizar_tecla(combinacao: str) -> str:
    """``ctrl+a`` → ``Control+a``; recusa tecla fora da lista."""
    partes = [p.strip() for p in (combinacao or "").split("+")]
    if not partes or any(not p for p in partes):
        raise argumentos_invalidos(f"Tecla inválida: {combinacao!r}.")
    *mods, tecla = partes
    saida = []
    for mod in mods:
        nome = _MODIFICADORES.get(mod.casefold())
        if nome is None:
            raise argumentos_invalidos(f"Modificador desconhecido: {mod!r}.")
        saida.append(nome)
    if len(tecla) == 1 and tecla.isprintable():
        principal = tecla
    else:
        principal = _APELIDOS_TECLA.get(tecla.casefold(), tecla)
        if principal not in TECLAS:
            raise argumentos_invalidos(f"Tecla não permitida: {tecla!r}.")
    return "+".join([*saida, principal])


@dataclass(frozen=True, slots=True)
class Seletor:
    """``papel:texto`` para esperas. ``"button"`` só papel; ``":Salvo!"`` só texto."""

    papel: str | None
    texto: str | None

    @classmethod
    def ler(cls, valor: str) -> Seletor:
        papel, _, texto = valor.partition(":")
        papel, texto = papel.strip() or None, texto.strip() or None
        if papel is None and texto is None:
            raise argumentos_invalidos("Seletor vazio. Use 'papel:texto', 'papel' ou ':texto'.")
        return cls(papel.casefold() if papel else None, texto)

    def descricao(self) -> str:
        return f"{self.papel or ''}:{self.texto or ''}"


@dataclass(frozen=True, slots=True)
class CursorAgente:
    """Cursor colorido que mostra onde o agente vai agir (só apresentação; não muda a ação)."""

    cor: str
    rotulo: str


@dataclass(slots=True)
class Passo:
    rotulo: str
    resultado: Literal["tentado", "pulado", "sucesso", "falhou"]
    mecanismo: Literal["fisico", "semantico"]

    def para_json(self) -> dict[str, str]:
        return {"rotulo": self.rotulo, "resultado": self.resultado, "mecanismo": self.mecanismo}


@dataclass(slots=True)
class _Feito:
    entrega: Entrega
    passos: list[Passo] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


Pagina = Any  # playwright.async_api.Page (opcional no servidor)


class NavegadorArvore:
    def __init__(
        self,
        pagina: Pagina,
        *,
        politica: Politica = Politica.FISICA,
        cursor: CursorAgente | None = None,
        rastro: Rastro | None = None,
    ) -> None:
        self._pagina = pagina
        self.politica = politica
        self.cursor = cursor
        self.rastro = rastro or Rastro()
        self.leituras = ArmazemLeituras()
        self._trava = asyncio.Lock()
        self._dialogos: deque[dict[str, str]] = deque(maxlen=20)
        self._dialogos_vistos = 0
        pagina.on("dialog", self._ao_dialogo)

    # ---------- infraestrutura ----------

    async def _ao_dialogo(self, dialogo: Any) -> None:
        """alert/confirm/prompt nativos: anota e dispensa (o agente vê em ``dialogos``)."""
        self._dialogos.append({"tipo": str(dialogo.type), "mensagem": str(dialogo.message)[:300]})
        self._dialogos_vistos += 1
        try:
            await dialogo.dismiss()
        except Exception:  # pragma: no cover - diálogo já fechado
            pass

    async def _js(self, op: str, arg: dict[str, Any] | None = None) -> Any:
        for tentativa in range(2):
            try:
                return await self._pagina.evaluate(SCRIPT, {"op": op, "arg": arg or {}})
            except Exception as erro:  # navegação no meio da leitura destrói o contexto
                texto = str(erro)
                if tentativa == 0 and ("context was destroyed" in texto or "navigat" in texto):
                    try:
                        await self._pagina.wait_for_load_state("domcontentloaded", timeout=3_000)
                    except Exception:
                        pass
                    continue
                raise ErroNavegador(
                    Codigo.PAGINA_SEM_RESPOSTA,
                    "A página não respondeu à leitura.",
                    entrega=Entrega.NAO_ENTREGUE,
                    detalhes={"operacao": op},
                ) from erro
        raise AssertionError("inalcançável")  # pragma: no cover

    async def _executar(
        self, comando: str, args: dict[str, Any], corpo: Callable[[], Awaitable[dict[str, Any]]]
    ) -> Resposta:
        inicio = time.monotonic()
        senha = False
        try:
            dados = await corpo()
            resposta = Resposta.sucesso(comando, dados)
            senha = bool(dados.pop("_senha", False))
        except ErroNavegador as erro:
            senha = bool(erro.detalhes.pop("_senha", False))
            resposta = Resposta.falha(comando, erro)
        except Exception as erro:  # nada de exceção crua para o modelo
            resposta = Resposta.falha(
                comando,
                ErroNavegador(
                    Codigo.INTERNO,
                    f"Falha inesperada no navegador ({type(erro).__name__}).",
                    entrega=Entrega.DESCONHECIDA,
                ),
            )
        entrega = None
        if resposta.erro is not None:
            entrega = resposta.erro.disposicao.entrega.value
        elif isinstance(resposta.dados.get("entrega"), dict):
            entrega = resposta.dados["entrega"].get("entrega")
        self.rastro.anotar(
            comando,
            args,
            ok=resposta.ok,
            codigo=resposta.erro.codigo.value if resposta.erro else None,
            entrega=entrega,
            inicio=inicio,
            senha=senha,
        )
        return resposta

    # ---------- refs ----------

    async def _resolver(self, ref: str) -> tuple[Leitura, EntradaRef]:
        """Reencontra o elemento da ref e o deixa como alvo na página. Falha fechado."""
        leitura, entrada = self.leituras.resolver(ref)
        chave = f"{leitura.id}:{entrada.numero}"
        bruto = await self._js("localizar", {"chave": chave, "evidencia": entrada.evidencia()})
        camadas = {
            camada: [Candidato.do_json(c, camada) for c in bruto.get(camada) or []]
            for camada in ("memoria", "id", "caminho", "busca")
        }
        memoria = str(bruto.get("memoria_estado") or "desconhecido")
        resolucao = escolher(entrada, ler_ref(ref).texto, camadas, memoria)
        if not await self._js("fixar", {"indice": resolucao.candidato.indice, "chave": chave}):
            raise ErroNavegador(Codigo.REF_VELHA, f"{ref} sumiu enquanto era conferida.")
        return leitura, entrada

    async def _resolver_esperando(self, ref: str, fim: float) -> tuple[Leitura, EntradaRef]:
        """Espera a ref voltar a existir até o prazo (página carregando)."""
        while True:
            try:
                return await self._resolver(ref)
            except ErroNavegador as erro:
                if erro.codigo not in {Codigo.REF_VELHA, Codigo.PAGINA_SEM_RESPOSTA}:
                    raise
                if time.monotonic() >= fim:
                    raise
            await asyncio.sleep(INTERVALO_MS / 1000)

    # ---------- observar ----------

    async def observar(
        self,
        *,
        somente_interativos: bool = True,
        compacto: bool = True,
        esqueleto: bool = False,
        raiz: str | None = None,
        profundidade_max: int = 10,
        incluir_limites: bool = False,
        max_nos: int = 1_500,
        prazo_ms: int = 3_000,
    ) -> Resposta:
        args = {
            "somente_interativos": somente_interativos,
            "compacto": compacto,
            "esqueleto": esqueleto,
            "raiz": raiz,
            "profundidade_max": profundidade_max,
        }

        async def corpo() -> dict[str, Any]:
            if not 1 <= profundidade_max <= 30:
                raise argumentos_invalidos("profundidade_max vai de 1 a 30.")
            opcoes = {
                "somente_interativos": somente_interativos,
                "compacto": compacto,
                "esqueleto": esqueleto,
                "profundidade_max": profundidade_max,
                "incluir_limites": incluir_limites,
                "max_nos": max_nos,
                "prazo_ms": prazo_ms,
            }
            if raiz is not None:
                return await self._perfurar(raiz, opcoes)
            leitura = self.leituras.nova(url=self._pagina.url, completa=True)
            bruto = await self._js("observar", {**opcoes, "id_leitura": leitura.id})
            leitura.url = str(bruto.get("url") or "")
            leitura.completa = bool(bruto.get("completo"))
            entradas = [EntradaRef.do_json(r) for r in bruto.get("refs") or []]
            self.leituras.registrar(leitura, entradas)
            dados: dict[str, Any] = {
                "url": leitura.url,
                "titulo": bruto.get("titulo") or "",
                "leitura": leitura.id,
                "refs": len(entradas),
                "completa": leitura.completa,
                "arvore": bruto.get("arvore") or [],
                "rolagem": _rolagem(bruto.get("rolagem")),
            }
            if not leitura.completa:
                dados["parcial"] = True
                dados["nos_observados"] = bruto.get("nos_observados")
            superficies = await self._superficies()
            if superficies:
                dados["superficies"] = superficies
            return dados

        return await self._executar("observar", args, corpo)

    async def _perfurar(self, raiz: str, opcoes: dict[str, Any]) -> dict[str, Any]:
        leitura, entrada = await self._resolver(raiz)
        if not leitura.completa:
            raise ErroNavegador(
                Codigo.PRAZO_ESGOTADO,
                "Só dá para perfurar uma leitura completa. Leia a página de novo (com "
                "esqueleto) e perfure a partir dela.",
            )
        bruto = await self._js(
            "observar",
            {
                **opcoes,
                "id_leitura": leitura.id,
                "comeco": leitura.proximo_numero,
                "usar_alvo": True,
                "esqueleto": False,
            },
        )
        if bruto.get("erro"):
            raise ErroNavegador(Codigo.REF_VELHA, f"{raiz} sumiu durante a leitura.")
        if not bruto.get("completo"):
            raise ErroNavegador(
                Codigo.PRAZO_ESGOTADO,
                "A região é grande demais para ler de uma vez. Perfure uma parte menor dela.",
                detalhes={"tipo": "perfuracao_incompleta"},
            )
        # a própria raiz já tem ref: a nova leitura dela não ganha outra
        entradas = [EntradaRef.do_json(r, raiz=entrada.numero) for r in bruto.get("refs") or []]
        leitura.perfurar(entrada.numero, entradas)
        return {
            "url": leitura.url,
            "leitura": leitura.id,
            "raiz": raiz,
            "refs": len(entradas),
            "completa": True,
            "arvore": bruto.get("arvore") or [],
        }

    async def _superficies(self) -> list[dict[str, Any]]:
        saida: list[dict[str, Any]] = []
        try:
            saida = list(await self._js("superficies"))
        except ErroNavegador:
            pass
        return saida

    # ---------- procurar ----------

    async def procurar(
        self,
        *,
        papel: str | None = None,
        nome: str | None = None,
        valor: str | None = None,
        texto: str | None = None,
        id_nativo: str | None = None,
        exato: bool = False,
        primeiro: bool = False,
        contar: bool = False,
        limite: int = 20,
        raiz: str | None = None,
    ) -> Resposta:
        args = {"papel": papel, "nome": nome, "valor": valor, "texto": texto,
                "id_nativo": id_nativo, "exato": exato, "raiz": raiz}  # fmt: skip

        async def corpo() -> dict[str, Any]:
            if not any(v is not None for v in (papel, nome, valor, texto, id_nativo)):
                raise argumentos_invalidos("Diga o que procurar: papel, nome, valor, texto ou id.")
            filtro = {
                "papel": _papel_canonico(papel),
                "nome": nome,
                "valor": valor,
                "texto": texto,
                "id_nativo": id_nativo,
                "exato": exato,
                "primeiro": primeiro,
                "contar": contar,
                "limite": max(1, min(limite, 50)),
            }
            if raiz is not None:
                leitura, _ = await self._resolver(raiz)
                filtro.update(usar_alvo=True, id_leitura=leitura.id, comeco=leitura.proximo_numero)
            elif not contar:
                leitura = self.leituras.nova(url=self._pagina.url, completa=False)
                filtro["id_leitura"] = leitura.id
            bruto = await self._js("procurar", filtro)
            if bruto.get("erro"):
                raise ErroNavegador(Codigo.REF_VELHA, f"{raiz} sumiu durante a busca.")
            if contar:
                return {"total": bruto.get("total", 0), "completa": bool(bruto.get("completo"))}
            entradas = [EntradaRef.do_json(r) for r in bruto.get("refs") or []]
            self.leituras.registrar(leitura, entradas)
            dados: dict[str, Any] = {
                "leitura": leitura.id,
                "total": bruto.get("total", 0),
                "correspondencias": bruto.get("correspondencias") or [],
                "completa": bool(bruto.get("completo")),
            }
            if "papeis_presentes" in bruto:
                dados["papeis_presentes"] = bruto["papeis_presentes"]
            return dados

        return await self._executar("procurar", args, corpo)

    # ---------- ler um elemento ----------

    async def elemento(self, ref: str, propriedade: str = "texto") -> Resposta:
        async def corpo() -> dict[str, Any]:
            if propriedade not in PROPRIEDADES_LEITURA | PROPRIEDADES_SIM_NAO:
                raise argumentos_invalidos(f"Propriedade desconhecida: {propriedade!r}.")
            await self._resolver(ref)
            estado = await self._js("estado")
            if not estado.get("conectado"):
                raise ErroNavegador(Codigo.REF_VELHA, f"{ref} sumiu durante a leitura.")
            dados: dict[str, Any] = {"ref": ref, "propriedade": propriedade}
            if propriedade in PROPRIEDADES_SIM_NAO:
                bruto = estado.get(propriedade)
                dados["aplicavel"] = bruto is not None
                dados["resultado"] = bool(bruto)
                return dados
            senha = bool(estado.get("senha"))
            if senha:
                dados["senha"] = True
            if propriedade == "texto":
                conteudo = estado.get("papel") in PAPEIS_DE_CONTEUDO
                primeiro, segundo = (
                    (estado.get("valor"), estado.get("nome"))
                    if conteudo
                    else (estado.get("nome"), estado.get("valor"))
                )
                dados["valor"] = None if senha and conteudo else (primeiro or segundo or None)
            elif propriedade == "valor":
                dados["valor"] = None if senha else estado.get("valor")
            elif propriedade == "titulo":
                dados["valor"] = estado.get("nome") or None
            elif propriedade == "limites":
                dados["valor"] = estado.get("limites")
                dados["ao_vivo"] = True
            else:
                dados["valor"] = estado.get(propriedade)
            return dados

        return await self._executar("elemento", {"ref": ref, "propriedade": propriedade}, corpo)

    # ---------- agir ----------

    async def agir(
        self,
        ref: str | None,
        acao: str,
        *,
        texto: str | None = None,
        opcao: str | None = None,
        direcao: str | None = None,
        quantidade: int = 3,
        destino: str | None = None,
        prazo_ms: int | None = None,
        esperar_por: str | None = None,
        esperar_sumir: str | None = None,
        prazo_espera_ms: int | None = None,
    ) -> Resposta:
        args = {"ref": ref, "acao": acao, "texto": texto, "opcao": opcao, "direcao": direcao,
                "quantidade": quantidade, "destino": destino}  # fmt: skip

        async def corpo() -> dict[str, Any]:
            _validar_acao(ref, acao, texto, opcao, direcao, quantidade, destino)
            if esperar_por and esperar_sumir:
                raise argumentos_invalidos("Use esperar_por ou esperar_sumir, não os dois.")
            if ref is None:  # rolar a página inteira
                dados = await self._rolar_pagina(direcao or "baixo", quantidade)
            else:
                dados = await self._agir_na_ref(
                    ref, acao, texto=texto, opcao=opcao, direcao=direcao,
                    quantidade=quantidade, destino=destino, prazo_ms=prazo_ms,
                )  # fmt: skip
            await self._esperar_depois(dados, esperar_por, esperar_sumir, prazo_espera_ms)
            return dados

        return await self._executar("agir", args, corpo)

    async def _agir_na_ref(
        self,
        ref: str,
        acao: str,
        *,
        texto: str | None,
        opcao: str | None,
        direcao: str | None,
        quantidade: int,
        destino: str | None,
        prazo_ms: int | None,
    ) -> dict[str, Any]:
        exigencia = EXIGENCIAS[acao]
        prazo = prazo_para(acao, texto, prazo_ms)
        fim = time.monotonic() + prazo / 1000
        rolou_antes = await self._esperar_pronto(ref, exigencia, fim, prazo)

        async with self._trava:
            # segunda resolução, já com a trava: é ela que vale
            _, entrada = await self._resolver(ref)
            evidencia = await self._js("evidencia", {"ponteiro": exigencia.ponteiro})
            relatorio = avaliar(evidencia, exigencia, self.politica)
            if not evidencia.get("conectado") or not relatorio.pronto:
                raise erro_do_relatorio(relatorio, esgotou=False, prazo_ms=prazo)
            senha = bool(evidencia.get("senha"))
            antes = await self._js("estado")
            url_antes = self._pagina.url
            dialogos_antes = self._dialogos_vistos
            try:
                feito = await self._despachar(
                    acao, ref, entrada, relatorio.ponto, evidencia, antes,
                    texto=texto, opcao=opcao, direcao=direcao, quantidade=quantidade,
                    destino=destino, fim=fim,
                )  # fmt: skip
            except ErroNavegador as erro:
                if senha:
                    erro.detalhes["_senha"] = True
                if rolou_antes:
                    erro.detalhes["rolagem_preparatoria"] = True
                raise

        dados: dict[str, Any] = {
            "acao": acao,
            "ref": ref,
            "entrega": Disposicao(feito.entrega).para_json(),
            "passos": [p.para_json() for p in feito.passos],
            **feito.extra,
        }
        if senha:
            dados["_senha"] = True
        if rolou_antes:
            dados["rolagem_preparatoria"] = True
        await self._assentar(url_antes, dados, dialogos_antes)
        return dados

    async def _esperar_pronto(self, ref: str, exigencia: Exigencia, fim: float, prazo: int) -> bool:
        """Espera (fora da trava) até o elemento passar nas checagens. Devolve se rolou a tela."""
        rolou = False
        while True:
            await self._resolver_esperando(ref, fim)
            evidencia = await self._js("evidencia", {"ponteiro": exigencia.ponteiro})
            if evidencia.get("conectado"):
                precisa_rolar = (
                    exigencia.ponteiro
                    and evidencia.get("visivel")
                    and not evidencia.get("na_tela")
                    and not evidencia.get("desabilitado")
                )
                if precisa_rolar and not rolou:
                    await self._js("semantica", {"tipo": "rolar_ate"})
                    rolou = True
                    continue
                relatorio = avaliar(evidencia, exigencia, self.politica)
                if relatorio.falha_definitiva is not None:
                    raise erro_do_relatorio(relatorio, esgotou=False, prazo_ms=prazo)
                if relatorio.pronto:
                    return rolou
                if time.monotonic() >= fim:
                    raise erro_do_relatorio(relatorio, esgotou=True, prazo_ms=prazo)
            elif time.monotonic() >= fim:
                raise ErroNavegador(Codigo.REF_VELHA, f"{ref} sumiu da página.")
            await asyncio.sleep(INTERVALO_MS / 1000)

    async def _mostrar_cursor(self, ponto: tuple[int, int] | None, *, clique: bool) -> None:
        if self.cursor is None or ponto is None:
            return
        try:
            await self._js(
                "cursor",
                {"x": ponto[0], "y": ponto[1], "cor": self.cursor.cor,
                 "rotulo": self.cursor.rotulo, "clique": clique},
            )  # fmt: skip
            await asyncio.sleep(PAUSA_CURSOR_S)
        except ErroNavegador:  # o cursor nunca derruba a ação
            pass

    async def _clicar(
        self, ponto: tuple[int, int] | None, passos: list[Passo], *, botao: str = "left",
        vezes: int = 1,
    ) -> None:  # fmt: skip
        """Cadeia do clique: ponteiro no ponto conferido; sem ponto, ``click()`` do DOM."""
        if self.politica is Politica.FISICA and ponto is not None:
            await self._mostrar_cursor(ponto, clique=True)
            passos.append(Passo("ponteiro", "tentado", "fisico"))
            await self._pagina.mouse.click(ponto[0], ponto[1], button=botao, click_count=vezes)
            passos[-1].resultado = "sucesso"
            return
        if botao != "left" or vezes != 1:
            raise ErroNavegador(
                Codigo.ACAO_FALHOU,
                "Não achei um ponto da tela que chegue no elemento.",
                detalhes={"tipo": "sem_ponto"},
            )
        if self.politica is Politica.FISICA:
            passos.append(Passo("ponteiro", "pulado", "fisico"))
        passos.append(Passo("click_dom", "tentado", "semantico"))
        resposta = await self._js("semantica", {"tipo": "clicar"})
        if not resposta.get("feito"):
            raise ErroNavegador(Codigo.REF_VELHA, "O elemento sumiu antes do clique.")
        passos[-1].resultado = "sucesso"

    async def _ler_ate(
        self, condicao: Callable[[dict[str, Any]], bool], fim: float, minimo_s: float = 1.0
    ) -> tuple[bool, dict[str, Any]]:
        """Relê o estado do alvo até a condição valer (ou o tempo acabar)."""
        limite = max(fim, time.monotonic() + minimo_s)
        estado: dict[str, Any] = {}
        while True:
            estado = await self._js("estado")
            if estado.get("conectado") and condicao(estado):
                return True, estado
            if time.monotonic() >= limite:
                return False, estado
            await asyncio.sleep(INTERVALO_MS / 1000)

    async def _despachar(
        self,
        acao: str,
        ref: str,
        entrada: EntradaRef,
        ponto: tuple[int, int] | None,
        evidencia: dict[str, Any],
        antes: dict[str, Any],
        *,
        texto: str | None,
        opcao: str | None,
        direcao: str | None,
        quantidade: int,
        destino: str | None,
        fim: float,
    ) -> _Feito:
        passos: list[Passo] = []
        fisica = self.politica is Politica.FISICA
        mecanismo: Literal["fisico", "semantico"] = "fisico" if fisica else "semantico"
        try:
            if acao == "clicar":
                await self._clicar(ponto, passos)
                return _Feito(Entrega.ENTREGUE_SEM_CONFIRMAR, passos)
            if acao in {"clique_duplo", "clique_direito"}:
                await self._clicar(
                    ponto, passos, botao="right" if acao == "clique_direito" else "left",
                    vezes=2 if acao == "clique_duplo" else 1,
                )  # fmt: skip
                return _Feito(Entrega.ENTREGUE_SEM_CONFIRMAR, passos)
            if acao == "pairar":
                if ponto is None:
                    raise ErroNavegador(Codigo.ACAO_FALHOU, "Sem ponto da tela no elemento.")
                await self._mostrar_cursor(ponto, clique=False)
                passos.append(Passo("ponteiro_mover", "sucesso", "fisico"))
                await self._pagina.mouse.move(ponto[0], ponto[1])
                return _Feito(Entrega.ENTREGUE_SEM_CONFIRMAR, passos)
            if acao == "focar":
                passos.append(Passo("focar_dom", "sucesso", "semantico"))
                await self._js("semantica", {"tipo": "focar"})
                ok, depois = await self._ler_ate(lambda e: bool(e.get("focado")), fim, 0.3)
                return self._conferido(ok, passos, depois, entrada, "focado")
            if acao in {"definir_valor", "limpar"}:
                alvo = "" if acao == "limpar" else (texto or "")
                await self._mostrar_cursor(_centro(evidencia), clique=False)
                passos.append(Passo("preencher", "tentado", mecanismo))
                if fisica:
                    await self._preencher_fisico(alvo)
                else:
                    await self._js("semantica", {"tipo": "definir_valor", "texto": alvo})
                passos[-1].resultado = "sucesso"
                return await self._conferir_valor(alvo, passos, fim, exato=True, estado_antes=antes)
            if acao == "digitar":
                await self._mostrar_cursor(_centro(evidencia), clique=False)
                await self._js("semantica", {"tipo": "cursor_no_fim"})
                passos.append(Passo("teclado" if fisica else "inserir_texto", "tentado", mecanismo))
                if fisica:
                    await self._pagina.keyboard.type(texto or "")
                else:
                    await self._js("semantica", {"tipo": "inserir_texto", "texto": texto or ""})
                passos[-1].resultado = "sucesso"
                esperado = (antes.get("valor") or "") + (texto or "")
                return await self._conferir_valor(
                    esperado, passos, fim, exato=False, estado_antes=antes
                )
            if acao in {"marcar", "desmarcar", "alternar"}:
                return await self._marcar(acao, ponto, passos, antes, entrada, fim)
            if acao in {"expandir", "recolher"}:
                return await self._expandir(acao, ponto, passos, antes, entrada, fim)
            if acao == "selecionar":
                return await self._selecionar(ref, opcao or "", ponto, passos, fim)
            if acao == "rolar":
                dx, dy = _deslocamento(direcao or "baixo", quantidade)
                passos.append(Passo("rolar_dom", "sucesso", "semantico"))
                r = await self._js("semantica", {"tipo": "rolar", "dx": dx, "dy": dy})
                return _feito_rolagem(r, passos)
            if acao == "rolar_ate":
                passos.append(Passo("rolar_ate_dom", "sucesso", "semantico"))
                r = await self._js("semantica", {"tipo": "rolar_ate"})
                entrega = (
                    Entrega.ENTREGUE_CONFIRMADA
                    if r.get("na_tela")
                    else Entrega.ENTREGUE_SEM_CONFIRMAR
                )
                return _Feito(entrega, passos, {"na_tela": bool(r.get("na_tela"))})
            if acao == "arrastar":
                return await self._arrastar(ponto, destino or "", passos, fim)
        except ErroNavegador as erro:
            if passos and any(p.resultado in {"tentado", "sucesso"} for p in passos):
                if erro.disposicao.entrega is Entrega.NAO_ENTREGUE and erro.codigo not in {
                    Codigo.ACAO_FALHOU
                }:
                    erro = erro.com_entrega(Entrega.INCERTA)
            erro.detalhes.setdefault("passos", [p.para_json() for p in passos])
            raise erro
        except Exception as erro:
            entrega = (
                Entrega.INCERTA if any(p.resultado == "tentado" for p in passos)
                else Entrega.NAO_ENTREGUE
            )  # fmt: skip
            raise ErroNavegador(
                Codigo.ACAO_FALHOU,
                f"A ação {acao} falhou no meio ({type(erro).__name__}).",
                entrega=entrega,
                detalhes={"passos": [p.para_json() for p in passos]},
            ) from erro
        raise argumentos_invalidos(f"Ação desconhecida: {acao!r}.")  # pragma: no cover

    async def _preencher_fisico(self, valor: str) -> None:
        alca = await self._pagina.evaluate_handle("() => window.__soraArvore.alvo_atual()")
        try:
            elemento = alca.as_element()
            if elemento is None:
                raise ErroNavegador(Codigo.REF_VELHA, "O elemento sumiu antes de preencher.")
            await elemento.fill(valor, timeout=2_000)
        finally:
            await alca.dispose()

    def _conferido(
        self, ok: bool, passos: list[Passo], depois: dict[str, Any], entrada: EntradaRef,
        campo: str,
    ) -> _Feito:  # fmt: skip
        if ok:
            passos[-1].resultado = "sucesso"
            return _Feito(Entrega.ENTREGUE_CONFIRMADA, passos, {"estado_depois": _publico(depois)})
        raise ErroNavegador(
            Codigo.ACAO_FALHOU,
            f"A página não mostrou o efeito esperado ({campo}).",
            entrega=Entrega.ENTREGUE_SEM_CONFIRMAR,
            detalhes={"tipo": "verificacao_pos_acao", "estado_depois": _publico(depois)},
        )

    async def _conferir_valor(
        self, esperado: str, passos: list[Passo], fim: float, *, exato: bool,
        estado_antes: dict[str, Any],
    ) -> _Feito:  # fmt: skip
        if estado_antes.get("senha"):
            # campo de senha: nunca devolve nem compara o conteúdo
            return _Feito(
                Entrega.ENTREGUE_SEM_CONFIRMAR, passos,
                {"verificacao": {"escopo": "indisponivel", "motivo": "campo_secreto"}},
            )  # fmt: skip

        def bate(estado: dict[str, Any]) -> bool:
            return normalizar(estado.get("valor")) == normalizar(esperado)

        ok, depois = await self._ler_ate(bate, fim, minimo_s=1.0)
        if ok:
            return _Feito(
                Entrega.ENTREGUE_CONFIRMADA, passos,
                {"estado_depois": _publico(depois),
                 "verificacao": {"escopo": "valor_do_elemento", "aplicacao": "nao_conferida"}},
            )  # fmt: skip
        if not depois.get("conectado") or depois.get("valor") is None:
            return _Feito(
                Entrega.ENTREGUE_SEM_CONFIRMAR, passos,
                {"verificacao": {"escopo": "indisponivel", "motivo": "sem_evidencia"}},
            )  # fmt: skip
        if not exato:
            # teclas passam pela fila de eventos da página (máscaras, autocompletar): divergir
            # não prova que falhou
            return _Feito(
                Entrega.ENTREGUE_SEM_CONFIRMAR, passos,
                {"estado_depois": _publico(depois),
                 "verificacao": {"escopo": "valor_do_elemento",
                                 "motivo": "postcondicao_divergente"}},
            )  # fmt: skip
        raise ErroNavegador(
            Codigo.ACAO_FALHOU,
            "O campo ficou com outro valor depois de preencher.",
            entrega=Entrega.ENTREGUE_SEM_CONFIRMAR,
            detalhes={"tipo": "verificacao_pos_acao", "estado_depois": _publico(depois)},
        )

    async def _marcar(
        self, acao: str, ponto: tuple[int, int] | None, passos: list[Passo],
        antes: dict[str, Any], entrada: EntradaRef, fim: float,
    ) -> _Feito:  # fmt: skip
        atual = antes.get("marcado")
        if acao == "alternar":
            if atual is None:
                raise ErroNavegador(
                    Codigo.ACAO_NAO_SUPORTADA,
                    "Não consigo ler se o elemento está marcado; use marcar ou desmarcar.",
                )
            desejado = not atual
        else:
            desejado = acao == "marcar"
            if atual is desejado:
                return _Feito(
                    Entrega.NAO_ENTREGUE, [Passo("ja_satisfeito", "pulado", "semantico")],
                    {"ja_satisfeito": True, "estado_depois": _publico(antes)},
                )  # fmt: skip
            if not desejado and entrada.papel == "radio":
                raise ErroNavegador(
                    Codigo.ACAO_NAO_SUPORTADA,
                    "Um botão de opção não se desmarca sozinho; marque outra opção do grupo.",
                )
        await self._clicar(ponto, passos)
        ok, depois = await self._ler_ate(lambda e: e.get("marcado") is desejado, fim, 1.0)
        return self._conferido(ok, passos, depois, entrada, "marcado" if desejado else "desmarcado")

    async def _expandir(
        self, acao: str, ponto: tuple[int, int] | None, passos: list[Passo],
        antes: dict[str, Any], entrada: EntradaRef, fim: float,
    ) -> _Feito:  # fmt: skip
        desejado = acao == "expandir"
        if antes.get("expandido") is desejado:
            return _Feito(
                Entrega.NAO_ENTREGUE, [Passo("ja_satisfeito", "pulado", "semantico")],
                {"ja_satisfeito": True, "estado_depois": _publico(antes)},
            )  # fmt: skip
        if self.politica is Politica.SEMANTICA:
            passos.append(Passo("details_dom", "tentado", "semantico"))
            r = await self._js("semantica", {"tipo": "abrir_details", "abrir": desejado})
            if not r.get("feito"):
                passos[-1].resultado = "pulado"
                await self._clicar(ponto, passos)
        else:
            await self._clicar(ponto, passos)
        ok, depois = await self._ler_ate(lambda e: e.get("expandido") is desejado, fim, 1.0)
        return self._conferido(
            ok, passos, depois, entrada, "expandido" if desejado else "recolhido"
        )

    async def _selecionar(
        self, ref: str, opcao: str, ponto: tuple[int, int] | None, passos: list[Passo],
        fim: float,
    ) -> _Feito:  # fmt: skip
        opcoes_nativas = await self._js("opcoes_select")

        def tem_opcao(estado: dict[str, Any]) -> bool:
            alvo = normalizar(opcao)
            return alvo in normalizar(estado.get("valor")) or alvo == normalizar(estado.get("nome"))

        if opcoes_nativas is not None:
            passos.append(Passo("select_nativo", "tentado", "semantico"))
            r = await self._js("semantica", {"tipo": "selecionar_opcao", "texto": opcao})
            if not r.get("feito"):
                raise ErroNavegador(
                    Codigo.ACAO_FALHOU,
                    f"A lista não tem a opção {opcao!r}.",
                    detalhes={"tipo": "opcao_nao_encontrada", "opcoes": r.get("opcoes") or []},
                )
            passos[-1].resultado = "sucesso"
            ok, depois = await self._ler_ate(tem_opcao, fim, 1.0)
            if ok:
                return _Feito(Entrega.ENTREGUE_CONFIRMADA, passos,
                              {"estado_depois": _publico(depois)})  # fmt: skip
            raise ErroNavegador(
                Codigo.ACAO_FALHOU, "A lista não ficou com a opção pedida.",
                entrega=Entrega.ENTREGUE_SEM_CONFIRMAR,
                detalhes={"tipo": "verificacao_pos_acao", "estado_depois": _publico(depois)},
            )  # fmt: skip
        # combobox/listbox em ARIA: abre, acha a opção visível, clica
        await self._clicar(ponto, passos)
        achou: dict[str, Any] = {}
        limite = max(fim, time.monotonic() + 2.0)
        while time.monotonic() < limite:
            achou = await self._js("fixar_opcao", {"texto": opcao})
            if achou.get("total") == 1:
                break
            await asyncio.sleep(INTERVALO_MS / 1000)
        if achou.get("total") != 1:
            codigo = Codigo.ALVO_AMBIGUO if (achou.get("total") or 0) > 1 else Codigo.ACAO_FALHOU
            raise ErroNavegador(
                codigo,
                f"Abri a lista, mas não achei uma única opção {opcao!r}.",
                entrega=Entrega.ENTREGUE_SEM_CONFIRMAR,
                detalhes={"tipo": "opcao_nao_encontrada", "opcoes": achou.get("opcoes") or []},
            )
        evidencia = await self._js("evidencia", {"ponteiro": True})
        relatorio = avaliar(evidencia, Exigencia("clicar", ponteiro=True), self.politica)
        await self._clicar(relatorio.ponto, passos)
        await self._resolver(ref)
        ok, depois = await self._ler_ate(tem_opcao, fim, 1.0)
        if ok:
            return _Feito(Entrega.ENTREGUE_CONFIRMADA, passos, {"estado_depois": _publico(depois)})
        return _Feito(
            Entrega.ENTREGUE_SEM_CONFIRMAR, passos,
            {"verificacao": {"escopo": "valor_do_elemento", "motivo": "sem_evidencia"}},
        )  # fmt: skip

    async def _arrastar(
        self, ponto: tuple[int, int] | None, destino: str, passos: list[Passo], fim: float
    ) -> _Feito:
        if ponto is None:
            raise ErroNavegador(Codigo.ACAO_FALHOU, "Sem ponto da tela no elemento de origem.")
        await self._resolver_esperando(destino, fim)
        ev_destino = await self._js("evidencia", {"ponteiro": True})
        rel_destino = avaliar(ev_destino, Exigencia(None, ponteiro=True, habilitado=False),
                              self.politica)  # fmt: skip
        alvo = rel_destino.ponto or _centro(ev_destino)
        if alvo is None:
            raise ErroNavegador(Codigo.ACAO_FALHOU, "Sem ponto da tela no destino.")
        mouse = self._pagina.mouse
        await self._mostrar_cursor(ponto, clique=False)
        await mouse.move(ponto[0], ponto[1])
        passos.append(Passo("ponteiro_arrastar", "tentado", "fisico"))
        segurando = False
        try:
            await mouse.down()
            segurando = True
            await mouse.move(alvo[0], alvo[1], steps=12)
            await self._mostrar_cursor(alvo, clique=False)
            await asyncio.sleep(ATRASO_SOLTAR_S)
            await mouse.up()
            segurando = False
        except Exception as erro:
            if segurando:  # solta o botão para não deixar a página num arrasto pela metade
                try:
                    await mouse.up()
                except Exception:
                    pass
            raise ErroNavegador(
                Codigo.ACAO_FALHOU,
                "O arrasto parou no meio.",
                entrega=Entrega.INCERTA,
                detalhes={"tipo": "arrasto_interrompido", "soltura_de_emergencia": segurando},
            ) from erro
        passos[-1].resultado = "sucesso"
        return _Feito(Entrega.ENTREGUE_SEM_CONFIRMAR, passos,
                      {"de": list(ponto), "para": list(alvo)})  # fmt: skip

    async def _rolar_pagina(self, direcao: str, quantidade: int) -> dict[str, Any]:
        dx, dy = _deslocamento(direcao, quantidade)
        async with self._trava:
            r = await self._js("semantica", {"tipo": "rolar", "pagina": True, "dx": dx, "dy": dy})
        feito = _feito_rolagem(r, [Passo("rolar_pagina", "sucesso", "semantico")])
        return {
            "acao": "rolar",
            "ref": None,
            "entrega": Disposicao(feito.entrega).para_json(),
            "passos": [p.para_json() for p in feito.passos],
            **feito.extra,
        }

    async def _assentar(self, url_antes: str, dados: dict[str, Any], dialogos_antes: int) -> None:
        """Depois da ação: espera a navegação começar/terminar e diz o que abriu."""
        await asyncio.sleep(0.05)
        if self._pagina.url != url_antes:
            try:
                await self._pagina.wait_for_load_state("domcontentloaded", timeout=5_000)
            except Exception:
                pass
            dados["navegou"] = {"de": url_antes, "para": self._pagina.url}
        superficies = await self._superficies()
        if superficies:
            dados["superficies"] = superficies
        if self._dialogos_vistos > dialogos_antes:
            novos = self._dialogos_vistos - dialogos_antes
            dados["dialogos_nativos"] = list(self._dialogos)[-novos:]

    # ---------- teclado ----------

    async def tecla(
        self,
        tecla: str,
        *,
        esperar_por: str | None = None,
        esperar_sumir: str | None = None,
        prazo_espera_ms: int | None = None,
    ) -> Resposta:
        async def corpo() -> dict[str, Any]:
            combinacao = normalizar_tecla(tecla)
            if self.politica is Politica.SEMANTICA:
                raise ErroNavegador(
                    Codigo.POLITICA_NEGADA, "Teclas só existem com a política física."
                )
            async with self._trava:
                url_antes = self._pagina.url
                dialogos_antes = self._dialogos_vistos
                try:
                    await self._pagina.keyboard.press(combinacao)
                except Exception as erro:
                    raise ErroNavegador(
                        Codigo.ACAO_FALHOU, "A tecla não foi enviada.", entrega=Entrega.INCERTA
                    ) from erro
            dados: dict[str, Any] = {
                "tecla": combinacao,
                "entrega": Disposicao(Entrega.ENTREGUE_SEM_CONFIRMAR).para_json(),
            }
            await self._assentar(url_antes, dados, dialogos_antes)
            await self._esperar_depois(dados, esperar_por, esperar_sumir, prazo_espera_ms)
            return dados

        return await self._executar("tecla", {"tecla": tecla}, corpo)

    # ---------- esperar ----------

    async def _esperar_depois(
        self, dados: dict[str, Any], esperar_por: str | None, esperar_sumir: str | None,
        prazo_ms: int | None,
    ) -> None:  # fmt: skip
        if not esperar_por and not esperar_sumir:
            return
        seletor = Seletor.ler(esperar_por or esperar_sumir or "")
        try:
            achou = await self._esperar_seletor(seletor, presente=bool(esperar_por),
                                                prazo_ms=_prazo_espera(prazo_ms))  # fmt: skip
        except ErroNavegador as erro:
            entrega = Entrega(dados["entrega"]["entrega"])
            erro.detalhes["apos_acao"] = {k: v for k, v in dados.items() if not k.startswith("_")}
            raise erro.com_entrega(entrega) from None
        dados["espera"] = achou

    async def _esperar_seletor(
        self, seletor: Seletor, *, presente: bool, prazo_ms: int
    ) -> dict[str, Any]:
        fim = time.monotonic() + prazo_ms / 1000
        contagem = 0
        while True:
            contagem = int(
                await self._js(
                    "contar_texto",
                    {"papel": _papel_canonico(seletor.papel), "texto": seletor.texto},
                )
            )
            if (contagem > 0) == presente:
                return {"seletor": seletor.descricao(), "presente": presente, "contagem": contagem}
            if time.monotonic() >= fim:
                raise ErroNavegador(
                    Codigo.PRAZO_ESGOTADO,
                    f"O seletor {seletor.descricao()!r} não "
                    f"{'apareceu' if presente else 'sumiu'} a tempo.",
                    detalhes={"tipo": "espera", "predicado": seletor.descricao(),
                              "prazo_ms": prazo_ms, "ultimo_observado": {"contagem": contagem}},
                )  # fmt: skip
            await asyncio.sleep(INTERVALO_MS / 1000)

    async def esperar(
        self,
        *,
        ms: int | None = None,
        ref: str | None = None,
        predicado: str = "existe",
        valor: str | None = None,
        acao: str = "clicar",
        texto: str | None = None,
        papel: str | None = None,
        contagem: int | None = None,
        sumir: bool = False,
        url_contem: str | None = None,
        evento: str | None = None,
        prazo_ms: int | None = None,
    ) -> Resposta:
        args = {"ms": ms, "ref": ref, "predicado": predicado, "texto": texto, "papel": papel,
                "url_contem": url_contem, "evento": evento}  # fmt: skip

        async def corpo() -> dict[str, Any]:
            modos = [
                ms is not None,
                ref is not None,
                texto is not None or papel is not None,
                url_contem is not None,
                evento is not None,
            ]
            if sum(modos) != 1:
                raise argumentos_invalidos(
                    "Escolha um modo de espera: ms, ref, texto/papel, url_contem ou evento."
                )
            prazo = _prazo_espera(prazo_ms)
            if ms is not None:
                if not 0 <= ms <= PRAZO_ESPERA_MAXIMO_MS:
                    raise argumentos_invalidos(f"ms vai de 0 a {PRAZO_ESPERA_MAXIMO_MS}.")
                await asyncio.sleep(ms / 1000)
                return {"esperou_ms": ms}
            if ref is not None:
                return await self._esperar_elemento(ref, predicado, valor, acao, prazo)
            if url_contem is not None:
                return await self._esperar_condicao(
                    lambda: _casa_url(self._pagina.url, url_contem), prazo,
                    f"url contém {url_contem!r}", lambda: {"url": self._pagina.url},
                )  # fmt: skip
            if evento is not None:
                return await self._esperar_evento(evento, prazo)
            seletor = Seletor(_papel_canonico(papel), texto)
            if contagem is None:
                return await self._esperar_seletor(seletor, presente=not sumir, prazo_ms=prazo)
            ultimo: dict[str, int] = {"contagem": 0}

            async def conta() -> bool:
                ultimo["contagem"] = int(await self._js(
                    "contar_texto", {"papel": seletor.papel, "texto": seletor.texto}))  # fmt: skip
                return ultimo["contagem"] == contagem

            return await self._esperar_condicao(
                conta, prazo, f"{seletor.descricao()} = {contagem} vezes", lambda: dict(ultimo)
            )

        return await self._executar("esperar", args, corpo)

    async def _esperar_condicao(
        self,
        condicao: Callable[[], Any],
        prazo_ms: int,
        descricao: str,
        observado: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        fim = time.monotonic() + prazo_ms / 1000
        while True:
            resultado = condicao()
            if asyncio.iscoroutine(resultado):
                resultado = await resultado
            if resultado:
                return {"predicado": descricao, "satisfeito": True, **observado()}
            if time.monotonic() >= fim:
                raise ErroNavegador(
                    Codigo.PRAZO_ESGOTADO,
                    f"A espera ({descricao}) passou do prazo.",
                    detalhes={"tipo": "espera", "predicado": descricao, "prazo_ms": prazo_ms,
                              "ultimo_observado": observado()},
                )  # fmt: skip
            await asyncio.sleep(INTERVALO_MS / 1000)

    async def _esperar_elemento(
        self, ref: str, predicado: str, valor: str | None, acao: str, prazo: int
    ) -> dict[str, Any]:
        if predicado not in {"existe", "visivel", "habilitado", "acionavel", "valor"}:
            raise argumentos_invalidos(f"Predicado desconhecido: {predicado!r}.")
        if predicado == "valor" and valor is None:
            raise argumentos_invalidos("O predicado 'valor' precisa de 'valor'.")
        if predicado == "acionavel" and acao not in EXIGENCIAS:
            raise argumentos_invalidos(f"Ação desconhecida: {acao!r}.")
        ler_ref(ref)
        ultimo: dict[str, Any] = {}

        async def satisfeito() -> bool:
            try:
                await self._resolver(ref)
            except ErroNavegador as erro:
                if erro.codigo in {Codigo.LEITURA_NAO_ENCONTRADA, Codigo.ARGUMENTOS_INVALIDOS}:
                    raise
                ultimo.clear()
                ultimo["erro"] = erro.codigo.value
                return False
            if predicado == "existe":
                return True
            if predicado == "acionavel":
                exigencia = EXIGENCIAS[acao]
                evidencia = await self._js("evidencia", {"ponteiro": exigencia.ponteiro})
                relatorio = avaliar(evidencia, exigencia, self.politica)
                ultimo.clear()
                ultimo.update(relatorio.para_json())
                return relatorio.pronto
            estado = await self._js("estado")
            ultimo.clear()
            ultimo.update(_publico(estado))
            if predicado == "valor":
                return normalizar(estado.get("valor")) == normalizar(valor)
            return bool(estado.get(predicado))

        return await self._esperar_condicao(
            satisfeito, prazo, f"{ref} {predicado}", lambda: {"ultimo": dict(ultimo)}
        )

    async def _esperar_evento(self, evento: str, prazo: int) -> dict[str, Any]:
        url_inicial = self._pagina.url
        dialogos_iniciais = self._dialogos_vistos
        superficies_iniciais = len(await self._superficies())
        estado: dict[str, Any] = {}

        async def mudou() -> bool:
            if evento == "navegou":
                estado["url"] = self._pagina.url
                return self._pagina.url != url_inicial
            if evento == "dialogo_nativo":
                return self._dialogos_vistos > dialogos_iniciais
            agora = len(await self._superficies())
            estado["superficies"] = agora
            if evento == "superficie_abriu":
                return agora > superficies_iniciais
            return agora < superficies_iniciais

        if evento not in {"navegou", "dialogo_nativo", "superficie_abriu", "superficie_fechou"}:
            raise argumentos_invalidos(f"Evento desconhecido: {evento!r}.")
        return await self._esperar_condicao(mudou, prazo, f"evento {evento}", lambda: dict(estado))

    # ---------- lote ----------

    async def lote(self, passos: list[dict[str, Any]], *, parar_no_erro: bool = True) -> Resposta:
        """Roda vários comandos em ordem. Não é transação: o que já rodou, rodou."""
        from app.navegador.arvore.ferramentas import ESQUEMAS_DO_LOTE  # evita import circular

        async def corpo() -> dict[str, Any]:
            if not 1 <= len(passos) <= MAX_PASSOS_LOTE:
                raise argumentos_invalidos(f"O lote tem de 1 a {MAX_PASSOS_LOTE} passos.")
            validados = []
            for i, passo in enumerate(passos):
                comando = passo.get("comando")
                if comando == "lote":
                    raise argumentos_invalidos("Lote dentro de lote não é permitido.", passo=i)
                esquema = ESQUEMAS_DO_LOTE.get(str(comando))
                if esquema is None or set(passo) - {"comando", "args"}:
                    raise argumentos_invalidos(f"Passo {i} inválido.", passo=i)
                try:
                    validados.append((comando, esquema.model_validate(passo.get("args") or {})))
                except ValidationError as erro:
                    problemas = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc']) or 'args'}: {e['msg']}"
                        for e in erro.errors()[:3]
                    )
                    raise argumentos_invalidos(
                        f"Argumentos do passo {i} inválidos: {problemas}", passo=i
                    ) from erro
            resultados: list[dict[str, Any]] = []
            parou = False
            for i, (comando, modelo) in enumerate(validados):
                if parou:
                    resultados.append({"passo": i, "comando": comando, "status": "nao_iniciado"})
                    continue
                resposta = await self.executar_comando(comando, modelo)
                resultados.append({"passo": i, **resposta.para_json()})
                if not resposta.ok and parar_no_erro:
                    parou = True
            return {
                "resultados": resultados,
                "executados": sum(1 for r in resultados if r.get("status") != "nao_iniciado"),
                "falhas": sum(1 for r in resultados if r.get("ok") is False),
            }

        return await self._executar("lote", {"passos": len(passos)}, corpo)

    async def executar_comando(self, comando: str, modelo: Any) -> Resposta:
        dados = modelo.model_dump(exclude={"aba_id"})
        if comando == "observar":
            return await self.observar(**dados)
        if comando == "procurar":
            return await self.procurar(**dados)
        if comando == "elemento":
            return await self.elemento(**dados)
        if comando == "agir":
            ref = dados.pop("ref")
            acao = dados.pop("acao")
            return await self.agir(ref, acao, **dados)
        if comando == "tecla":
            return await self.tecla(**dados)
        if comando == "esperar":
            return await self.esperar(**dados)
        if comando == "lote":
            return await self.lote(
                [p.model_dump() for p in modelo.passos], parar_no_erro=modelo.parar_no_erro
            )
        raise argumentos_invalidos(f"Comando desconhecido: {comando!r}.")  # pragma: no cover


# ---------- auxiliares ----------


def _validar_acao(
    ref: str | None, acao: str, texto: str | None, opcao: str | None, direcao: str | None,
    quantidade: int, destino: str | None,
) -> None:  # fmt: skip
    if acao not in EXIGENCIAS:
        raise argumentos_invalidos(f"Ação desconhecida: {acao!r}.")
    if ref is None and acao != "rolar":
        raise argumentos_invalidos(f"A ação {acao} precisa de 'ref'.")
    if ref is not None:
        ler_ref(ref)
    if acao in COM_TEXTO and texto is None:
        raise argumentos_invalidos(f"A ação {acao} precisa de 'texto'.")
    if acao == "selecionar" and not opcao:
        raise argumentos_invalidos("A ação selecionar precisa de 'opcao'.")
    if acao == "rolar" and (direcao or "baixo") not in {"cima", "baixo", "esquerda", "direita"}:
        raise argumentos_invalidos("direcao: cima, baixo, esquerda ou direita.")
    if not 1 <= quantidade <= 20:
        raise argumentos_invalidos("quantidade vai de 1 a 20.")
    if acao == "arrastar":
        if not destino:
            raise argumentos_invalidos("A ação arrastar precisa de 'destino' (uma ref).")
        ler_ref(destino)


def _deslocamento(direcao: str, quantidade: int) -> tuple[int, int]:
    passo = PASSO_ROLAGEM_PX * quantidade
    return {
        "cima": (0, -passo), "baixo": (0, passo), "esquerda": (-passo, 0), "direita": (passo, 0),
    }[direcao]  # fmt: skip


def _feito_rolagem(r: dict[str, Any], passos: list[Passo]) -> _Feito:
    antes, depois = r.get("antes"), r.get("depois")
    if antes is not None and antes == depois:
        passos[-1].resultado = "pulado"
        return _Feito(Entrega.NAO_ENTREGUE, passos, {"ja_no_limite": True, "posicao": depois})
    return _Feito(Entrega.ENTREGUE_CONFIRMADA, passos, {"posicao": depois})


def _centro(evidencia: dict[str, Any]) -> tuple[int, int] | None:
    limites = evidencia.get("limites")
    if not limites or limites[2] <= 0 or limites[3] <= 0:
        return None
    return int(limites[0] + limites[2] / 2), int(limites[1] + limites[3] / 2)


def _publico(estado: dict[str, Any]) -> dict[str, Any]:
    """Estado que pode ir para o modelo: sem o valor de campo de senha."""
    saida = {k: estado[k] for k in ("papel", "nome", "valor", "estados") if estado.get(k)}
    if estado.get("senha"):
        saida.pop("valor", None)
    return saida


def _rolagem(bruto: Any) -> dict[str, Any] | None:
    if not bruto or len(bruto) != 6:
        return None
    x, y, largura, altura, vis_l, vis_a = bruto
    return {
        "y": round(y),
        "altura_pagina": round(altura),
        "altura_janela": round(vis_a),
        "tem_mais_abaixo": y + vis_a < altura - 2,
        "tem_mais_acima": y > 2,
        "x": round(x),
        "largura_pagina": round(largura),
        "largura_janela": round(vis_l),
    }


_PAPEIS_EQUIVALENTES = {
    "textfield": "textbox", "searchbox": "textbox", "textarea": "textbox", "campo": "textbox",
    "botao": "button", "botão": "button", "caixa": "checkbox", "titulo": "heading",
    "título": "heading", "imagem": "img", "lista": "list", "opcao": "option", "opção": "option",
}  # fmt: skip


def _papel_canonico(papel: str | None) -> str | None:
    if papel is None:
        return None
    chave = papel.strip().casefold()
    return _PAPEIS_EQUIVALENTES.get(chave, chave)


def _prazo_espera(prazo_ms: int | None) -> int:
    if prazo_ms is None:
        return PRAZO_ESPERA_PADRAO_MS
    return max(0, min(prazo_ms, PRAZO_ESPERA_MAXIMO_MS))


def _casa_url(url: str, trecho: str) -> bool:
    return trecho in url
