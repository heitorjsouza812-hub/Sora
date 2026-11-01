"""Leituras da página e as refs que cada uma distribuiu.

- Cada leitura (``navegador_observar``/``navegador_procurar``) ganha um id curto, ``s`` + 7
  letras/números. As refs saem **qualificadas**: ``@s4k9x2m1:e7``. Uma ref solta (``@e7``) é
  recusada: sem saber de qual leitura ela veio, não dá para conferir se ainda vale.
- A ref guarda a **evidência de identidade** do elemento (papel, nome estável, id do HTML,
  caminho no DOM, posição). Antes de agir, o elemento é reencontrado e conferido por essa
  evidência (``identidade.py``); se não bater, a ação é recusada em vez de cair no vizinho.
- Perfurar (``raiz=@…``) lê só um pedaço da página e **troca só as refs daquele pedaço** dentro
  da mesma leitura; as outras regiões continuam valendo.
- Cada aba guarda as últimas ``MAX_LEITURAS_POR_ABA`` leituras; as mais velhas expiram.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0): refs qualificadas
pelo snapshot, RefMap com evidência de identidade e "drill-down" que substitui só a região.
"""

from __future__ import annotations

import re
import secrets
import string
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.navegador.arvore.resposta import (
    Codigo,
    ErroNavegador,
    argumentos_invalidos,
)

MAX_LEITURAS_POR_ABA = 8
_ALFABETO = string.ascii_lowercase + string.digits
_REF_QUALIFICADA = re.compile(r"^@?(s[a-z0-9]{7}):e([1-9][0-9]{0,5})$")
_REF_SOLTA = re.compile(r"^@?e[0-9]+$")


def novo_id_leitura() -> str:
    return "s" + "".join(secrets.choice(_ALFABETO) for _ in range(7))


def qualificar(id_leitura: str, numero: int) -> str:
    return f"@{id_leitura}:e{numero}"


@dataclass(frozen=True, slots=True)
class RefLida:
    id_leitura: str
    numero: int

    @property
    def local(self) -> str:
        return f"e{self.numero}"

    @property
    def texto(self) -> str:
        return qualificar(self.id_leitura, self.numero)


def ler_ref(ref: str) -> RefLida:
    valor = (ref or "").strip()
    if _REF_SOLTA.match(valor):
        raise argumentos_invalidos(
            f"A ref {valor!r} está sem a leitura. Use a ref completa, como @s4k9x2m1:e7.",
            ref=valor,
        )
    casamento = _REF_QUALIFICADA.match(valor)
    if not casamento:
        raise argumentos_invalidos(
            f"Ref inválida: {valor!r}. O formato é @<leitura>:e<número>.", ref=valor
        )
    return RefLida(casamento.group(1), int(casamento.group(2)))


@dataclass(frozen=True, slots=True)
class IdNativo:
    """Identificador dado pelo desenvolvedor do site. Sempre com o tipo junto."""

    tipo: str  # "id" | "testid" | "name"
    valor: str


@dataclass(frozen=True, slots=True)
class EntradaRef:
    numero: int
    papel: str
    nome: str | None = None
    nome_estavel: bool = True
    descricao: str | None = None
    id_nativo: IdNativo | None = None
    caminho: str = ""
    limites: tuple[float, float, float, float] | None = None
    acoes: tuple[str, ...] = ()
    senha: bool = False
    raiz: int | None = None
    """Número da ref de onde a perfuração que criou esta ref partiu (``None`` = leitura cheia)."""

    @classmethod
    def do_json(cls, dados: dict[str, Any], raiz: int | None = None) -> EntradaRef:
        id_bruto = dados.get("id_nativo")
        id_nativo = None
        if isinstance(id_bruto, dict) and id_bruto.get("valor"):
            id_nativo = IdNativo(str(id_bruto.get("tipo") or "id"), str(id_bruto["valor"]))
        limites = dados.get("limites")
        return cls(
            numero=int(dados["numero"]),
            papel=str(dados.get("papel") or "generic"),
            nome=(dados.get("nome") or None),
            nome_estavel=bool(dados.get("nome_estavel", True)),
            descricao=(dados.get("descricao") or None),
            id_nativo=id_nativo,
            caminho=str(dados.get("caminho") or ""),
            limites=tuple(float(v) for v in limites) if limites else None,  # type: ignore[arg-type]
            acoes=tuple(str(a) for a in dados.get("acoes") or ()),
            senha=bool(dados.get("senha")),
            raiz=raiz,
        )

    def evidencia(self) -> dict[str, Any]:
        """O que vai para a página procurar candidatos."""
        return {
            "papel": self.papel,
            "nome": self.nome,
            "id_nativo": (
                {"tipo": self.id_nativo.tipo, "valor": self.id_nativo.valor}
                if self.id_nativo
                else None
            ),
            "caminho": self.caminho,
            "limites": list(self.limites) if self.limites else None,
        }


@dataclass(slots=True)
class Leitura:
    id: str
    url: str
    completa: bool
    refs: dict[int, EntradaRef] = field(default_factory=dict)
    proximo_numero: int = 1

    def entrada(self, numero: int) -> EntradaRef:
        entrada = self.refs.get(numero)
        if entrada is None:
            raise ErroNavegador(
                Codigo.REF_VELHA,
                f"A ref {qualificar(self.id, numero)} não existe nesta leitura.",
                detalhes={"ref": qualificar(self.id, numero)},
            )
        return entrada

    def perfurar(self, raiz: int, novas: list[EntradaRef]) -> None:
        """Troca as refs que a perfuração anterior da mesma raiz criou pelas novas."""
        for numero in [n for n, e in self.refs.items() if e.raiz == raiz]:
            del self.refs[numero]
        for entrada in novas:
            self.refs[entrada.numero] = entrada
        if novas:
            self.proximo_numero = max(self.proximo_numero, max(e.numero for e in novas) + 1)


class ArmazemLeituras:
    """Leituras de uma aba. Nada aqui atravessa abas: uma ref só vale na aba que a criou."""

    def __init__(self, limite: int = MAX_LEITURAS_POR_ABA) -> None:
        self._limite = limite
        self._leituras: OrderedDict[str, Leitura] = OrderedDict()

    def nova(self, *, url: str, completa: bool) -> Leitura:
        id_ = novo_id_leitura()
        while id_ in self._leituras:  # pragma: no cover - colisão de 36^7
            id_ = novo_id_leitura()
        leitura = Leitura(id=id_, url=url, completa=completa)
        self._leituras[id_] = leitura
        while len(self._leituras) > self._limite:
            self._leituras.popitem(last=False)
        return leitura

    def registrar(self, leitura: Leitura, entradas: list[EntradaRef]) -> None:
        for entrada in entradas:
            leitura.refs[entrada.numero] = entrada
        if entradas:
            leitura.proximo_numero = max(e.numero for e in entradas) + 1

    def obter(self, id_leitura: str) -> Leitura:
        leitura = self._leituras.get(id_leitura)
        if leitura is None:
            raise ErroNavegador(
                Codigo.LEITURA_NAO_ENCONTRADA,
                f"A leitura {id_leitura} não existe mais nesta aba.",
                detalhes={"leitura": id_leitura},
            )
        self._leituras.move_to_end(id_leitura)
        return leitura

    def resolver(self, ref: str) -> tuple[Leitura, EntradaRef]:
        lida = ler_ref(ref)
        leitura = self.obter(lida.id_leitura)
        return leitura, leitura.entrada(lida.numero)

    def esquecer_tudo(self) -> None:
        self._leituras.clear()

    def __len__(self) -> int:
        return len(self._leituras)
