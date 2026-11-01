"""Resposta padronizada das ferramentas do navegador por árvore.

Toda chamada devolve um envelope: ``ok`` e ``dados``, ou ``ok: false`` e ``erro``. O erro diz
**o que aconteceu** (``codigo``), **se a ação chegou na página** (``entrega``) e, só quando é
seguro, **como se recuperar** (``recuperacao``). O agente decide repetir pelo campo
``entrega.repetir``, nunca pelo texto da mensagem.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0): envelope JSON com
códigos de erro e "delivery disposition". Os nomes, os códigos e as regras abaixo são da Sora.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Codigo(StrEnum):
    REF_VELHA = "REF_VELHA"
    """A ref não bate mais com nenhum elemento vivo da página."""
    ALVO_AMBIGUO = "ALVO_AMBIGUO"
    """Mais de um elemento vivo bate com a ref antiga (ou com a busca)."""
    ELEMENTO_NAO_ENCONTRADO = "ELEMENTO_NAO_ENCONTRADO"
    LEITURA_NAO_ENCONTRADA = "LEITURA_NAO_ENCONTRADA"
    """O id da leitura não existe mais (expirou ou é de outra aba)."""
    POLITICA_NEGADA = "POLITICA_NEGADA"
    ACAO_FALHOU = "ACAO_FALHOU"
    ACAO_NAO_SUPORTADA = "ACAO_NAO_SUPORTADA"
    PRAZO_ESGOTADO = "PRAZO_ESGOTADO"
    ARGUMENTOS_INVALIDOS = "ARGUMENTOS_INVALIDOS"
    ABA_NAO_ENCONTRADA = "ABA_NAO_ENCONTRADA"
    ENDERECO_BLOQUEADO = "ENDERECO_BLOQUEADO"
    PAGINA_SEM_RESPOSTA = "PAGINA_SEM_RESPOSTA"
    INTERNO = "INTERNO"


class Entrega(StrEnum):
    """O que se sabe sobre a ação ter chegado (ou não) na página."""

    DESCONHECIDA = "desconhecida"
    NAO_ENTREGUE = "nao_entregue"
    INCERTA = "incerta"
    ENTREGUE_SEM_CONFIRMAR = "entregue_sem_confirmar"
    ENTREGUE_CONFIRMADA = "entregue_confirmada"


class Repetir(StrEnum):
    DESCONHECIDO = "desconhecido"
    SEGURO = "seguro"
    INSEGURO = "inseguro"


def repetir_de(entrega: Entrega) -> Repetir:
    """Só o que **não chegou** pode ser repetido sem risco de clicar ou enviar duas vezes."""
    if entrega is Entrega.DESCONHECIDA:
        return Repetir.DESCONHECIDO
    return Repetir.SEGURO if entrega is Entrega.NAO_ENTREGUE else Repetir.INSEGURO


@dataclass(frozen=True, slots=True)
class Disposicao:
    entrega: Entrega

    @property
    def repetir(self) -> Repetir:
        return repetir_de(self.entrega)

    def para_json(self) -> dict[str, str]:
        return {"entrega": self.entrega.value, "repetir": self.repetir.value}


NAO_ENTREGUE = Disposicao(Entrega.NAO_ENTREGUE)

# Estratégia de recuperação por código; só vai no erro quando repetir é seguro.
_RECUPERACAO: dict[Codigo, tuple[str, str]] = {
    Codigo.REF_VELHA: (
        "nova_leitura_e_repetir",
        "Leia a página de novo (navegador_observar) e use a ref nova.",
    ),
    Codigo.ALVO_AMBIGUO: (
        "estreitar_e_repetir",
        "Estreite o alvo com navegador_procurar (papel + nome exato) ou com 'raiz', e use a ref "
        "nova.",
    ),
    Codigo.LEITURA_NAO_ENCONTRADA: (
        "nova_leitura_e_repetir",
        "Essa leitura expirou. Leia a página de novo.",
    ),
    Codigo.ELEMENTO_NAO_ENCONTRADO: (
        "nova_leitura_e_repetir",
        "Leia a página de novo; o elemento pode ter mudado de lugar.",
    ),
    Codigo.PRAZO_ESGOTADO: (
        "esperar_e_repetir",
        "A página ainda não estava pronta. Espere (navegador_esperar) e tente de novo.",
    ),
    Codigo.PAGINA_SEM_RESPOSTA: (
        "esperar_e_repetir",
        "A página parou de responder. Espere alguns segundos e leia de novo.",
    ),
}
_ESPERA_SUGERIDA_MS = {Codigo.PRAZO_ESGOTADO: 1_000, Codigo.PAGINA_SEM_RESPOSTA: 3_000}


class ErroNavegador(Exception):
    """Erro estruturado. Vira ``Resposta.falha`` na borda da ferramenta."""

    def __init__(
        self,
        codigo: Codigo,
        mensagem: str,
        *,
        entrega: Entrega = Entrega.NAO_ENTREGUE,
        detalhes: dict[str, Any] | None = None,
        sugestao: str | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.disposicao = Disposicao(entrega)
        self.detalhes = detalhes or {}
        self.sugestao = sugestao

    def com_entrega(self, entrega: Entrega) -> ErroNavegador:
        return ErroNavegador(
            self.codigo,
            self.mensagem,
            entrega=entrega,
            detalhes=self.detalhes,
            sugestao=self.sugestao,
        )

    def para_json(self) -> dict[str, Any]:
        erro: dict[str, Any] = {
            "codigo": self.codigo.value,
            "mensagem": self.mensagem,
            "entrega": self.disposicao.para_json(),
        }
        padrao = _RECUPERACAO.get(self.codigo)
        sugestao = self.sugestao or (padrao[1] if padrao else None)
        if sugestao:
            erro["sugestao"] = sugestao
        if padrao and self.disposicao.repetir is Repetir.SEGURO:
            recuperacao: dict[str, Any] = {"estrategia": padrao[0]}
            if self.codigo in _ESPERA_SUGERIDA_MS:
                recuperacao["esperar_ms"] = _ESPERA_SUGERIDA_MS[self.codigo]
            erro["recuperacao"] = recuperacao
        if self.detalhes:
            erro["detalhes"] = self.detalhes
        return erro


def argumentos_invalidos(mensagem: str, **detalhes: Any) -> ErroNavegador:
    return ErroNavegador(Codigo.ARGUMENTOS_INVALIDOS, mensagem, detalhes=detalhes or None)


@dataclass(slots=True)
class Resposta:
    comando: str
    ok: bool
    dados: dict[str, Any] = field(default_factory=dict)
    erro: ErroNavegador | None = None

    @classmethod
    def sucesso(cls, comando: str, dados: dict[str, Any]) -> Resposta:
        return cls(comando=comando, ok=True, dados=dados)

    @classmethod
    def falha(cls, comando: str, erro: ErroNavegador) -> Resposta:
        return cls(comando=comando, ok=False, erro=erro)

    def para_json(self) -> dict[str, Any]:
        corpo: dict[str, Any] = {"ok": self.ok, "comando": self.comando}
        if self.ok:
            corpo["dados"] = self.dados
        else:
            assert self.erro is not None
            corpo["erro"] = self.erro.para_json()
        return corpo

    def texto(self) -> str:
        return json.dumps(self.para_json(), ensure_ascii=False, separators=(",", ":"))
