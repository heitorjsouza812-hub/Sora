"""Limite do provedor por minuto (429 de TPM/RPM) e pedido grande demais (Âncora, rodada 4).

- 429 com ``retry-after`` **não** vira troca de modelo: espera-se o tempo pedido (com teto) e
  tenta-se o mesmo modelo de novo;
- "Request too large" (pedido maior que o limite do plano) pede um pedido menor, não espera;
- quando nada resolve, o erro final é ``ErroLimiteDoProvedor`` com texto claro em PT-BR.
"""

from __future__ import annotations

import re
from typing import Any

TETO_DA_ESPERA_S = 60.0
ESPERA_PADRAO_S = 5.0
TENTATIVAS_NO_LIMITE = 3

MENSAGEM_LIMITE = (
    "O provedor recusou: limite por minuto do plano. Tente de novo em alguns instantes "
    "ou use um modelo com limite maior."
)


class ErroLimiteDoProvedor(Exception):
    """O limite do provedor não cedeu depois das esperas e dos pedidos enxutos.

    ``classificar_erro`` não vê este erro como trocável: outro modelo do mesmo plano falharia
    do mesmo jeito, e o texto para o usuário já está pronto em ``MENSAGEM_LIMITE``.
    """

    def __init__(self, detalhe: str = "") -> None:
        super().__init__(MENSAGEM_LIMITE + (f" [{detalhe}]" if detalhe else ""))


def _cadeia(erro: BaseException) -> list[BaseException]:
    achados: list[BaseException] = []
    atual: BaseException | None = erro
    for _ in range(5):
        if atual is None:
            break
        achados.append(atual)
        atual = atual.__cause__ or atual.__context__
    return achados


def limite_do_provedor(erro: BaseException) -> bool:
    return any(isinstance(e, ErroLimiteDoProvedor) for e in _cadeia(erro))


def _texto(erro: BaseException) -> str:
    return " ".join(str(e) for e in _cadeia(erro)).lower()


def pedido_grande_demais(erro: BaseException) -> bool:
    texto = _texto(erro)
    if "request too large" in texto or "reduce your message size" in texto:
        return True
    return any(getattr(e, "status_code", None) == 413 for e in _cadeia(erro))


_NUMERO = r"(\d+(?:\.\d+)?)"
_DURACAO = re.compile(rf"(?:{_NUMERO}h)?(?:{_NUMERO}m(?!s))?(?:{_NUMERO}s)?")


def _segundos_do_texto(texto: str) -> float | None:
    achado = re.search(r"try again in\s+([0-9hms. ]+?)(?:[,.]?\s|$|\.\s)", texto)
    if achado is None:
        return None
    bruto = achado.group(1).strip().rstrip(".")
    if bruto.endswith("ms") and re.fullmatch(r"\d+(?:\.\d+)?ms", bruto):
        return float(bruto[:-2]) / 1000
    partes = _DURACAO.fullmatch(bruto.replace(" ", ""))
    if partes is None or not any(partes.groups()):
        return None
    horas, minutos, segundos = (float(p) if p else 0.0 for p in partes.groups())
    return horas * 3600 + minutos * 60 + segundos


def espera_pedida(erro: BaseException) -> float | None:
    """Segundos que o provedor pediu (cabeçalho ``retry-after`` ou "try again in 26s")."""
    for e in _cadeia(erro):
        cabecalhos: Any = getattr(getattr(e, "response", None), "headers", None)
        if cabecalhos is None:
            cabecalhos = getattr(e, "litellm_response_headers", None)
        if cabecalhos:
            try:
                bruto = cabecalhos.get("retry-after") or cabecalhos.get("Retry-After")
                if bruto is not None:
                    return max(0.0, float(bruto))
            except (TypeError, ValueError, AttributeError):
                pass
    return _segundos_do_texto(_texto(erro))


def espera_com_teto(erro: BaseException) -> float | None:
    """Espera a fazer (com um respiro de 0,5 s) ou ``None`` se passa do teto."""
    pedida = espera_pedida(erro)
    if pedida is None:
        return ESPERA_PADRAO_S
    if pedida > TETO_DA_ESPERA_S:
        return None
    return pedida + 0.5


async def com_espera_de_limite(chamar: Any, *, ao_esperar: Any = None, dormir: Any = None) -> Any:
    """Roda ``chamar()``; num 429 espera o ``retry-after`` (teto 60 s, até 3 vezes) e repete.

    Para chamadas avulsas (o juiz do revisor) que não passam pelo middleware do agente. Esgotadas
    as esperas, sobe ``ErroLimiteDoProvedor``.
    """
    import asyncio

    from app.llm.troca import MotivoTroca, classificar_erro

    dormir = dormir or asyncio.sleep
    esperas = 0
    while True:
        try:
            return await chamar()
        except Exception as erro:
            if classificar_erro(erro) is not MotivoTroca.LIMITE_DE_TAXA:
                raise
            espera = espera_com_teto(erro)
            if espera is None or esperas >= TENTATIVAS_NO_LIMITE:
                raise ErroLimiteDoProvedor("limite por minuto") from None
            esperas += 1
            if ao_esperar is not None:
                await ao_esperar(round(espera))
            await dormir(espera)


def enxugar(mensagens: list[Any], nivel: int) -> list[Any]:
    """Cópia da lista com resultados de ferramentas encurtados.

    Nível 1: resultados do navegador mais antigos que o último viram resumo curto.
    Nível 2: todo resultado de ferramenta, menos o último, vira resumo; o último é cortado.
    A lista original (o estado do agente) não é alterada.
    """
    from langchain_core.messages import ToolMessage

    indices = [i for i, m in enumerate(mensagens) if isinstance(m, ToolMessage)]
    if not indices:
        return list(mensagens)
    ultimo = indices[-1]
    # A leitura mais recente de CADA ferramenta do navegador fica inteira (as refs de uma
    # observação continuam valendo enquanto a página não muda); só as repetidas antigas encolhem.
    ultimas_do_navegador: dict[str, int] = {}
    for i in indices:
        nome = str(getattr(mensagens[i], "name", "") or "")
        if nome.startswith("navegador_"):
            ultimas_do_navegador[nome] = i
    manter = set(ultimas_do_navegador.values())
    saida = list(mensagens)
    for i in indices:
        m = mensagens[i]
        texto = m.content if isinstance(m.content, str) else str(m.content)
        navegador = str(getattr(m, "name", "") or "").startswith("navegador_")
        if nivel >= 2 and i != ultimo:
            limite = 200
        elif nivel >= 1 and navegador and i not in manter:
            limite = 300
        elif nivel >= 2 and i == ultimo:
            limite = 3000
        else:
            continue
        if len(texto) > limite:
            saida[i] = m.model_copy(
                update={"content": texto[:limite] + " … [resultado antigo resumido]"}
            )
    return saida
