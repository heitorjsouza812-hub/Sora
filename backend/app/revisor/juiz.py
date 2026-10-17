"""Execução do revisor de ações como "juiz rápido": prompt montado com dados redigidos e
truncados, prazo curto e falha fechada.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``adapters/src/auto-review.ts``
(``buildAutoReviewPrompt``, ``runAutoReviewJudge``, limites de tamanho e prazo).

Diferença para o Rakazo: lá a falha do juiz vira "perguntar ao usuário"; aqui segue a regra
da especificação da Sora (``revisar_acao``): qualquer erro, prazo estourado ou JSON inválido
vira BLOQUEAR, e o bloqueio abre o cartão de aprovação. O efeito para o usuário é o mesmo:
na dúvida, a Sora pergunta.

O mesmo formato serve para o Sistema 1 e para qualquer decisão curta em JSON: modelo
pequeno, prompt com o dado cercado, ``asyncio.wait_for`` e um padrão seguro.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence

from pydantic import ValidationError

from app.agentes.prompts import carregar_prompt, neutralizar_cerca, preencher
from app.core.redacao import ocultar_argumentos_sensiveis, redigir
from app.revisor.esquemas import AcaoProposta, AvaliacaoRevisor, Dano, DecisaoRevisor, Destino
from app.sistema1.saida_json import SaidaInvalida, extrair_json

PRAZO_PADRAO_SEGUNDOS = 5.0
MAX_CARACTERES_PEDIDO = 400
MAX_PEDIDOS = 5
MAX_CARACTERES_ARGUMENTOS = 1_200
MAX_CARACTERES_MOTIVO = 160

ChamarModelo = Callable[[str, str], Awaitable[str]]
"""``(instrucoes_de_sistema, prompt) -> texto``. O worker liga no modelo do papel ``revisor``."""


def _cortar(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else f"{texto[:limite]}…"


def montar_prompt_revisor(
    acao: AcaoProposta,
    pedidos_do_usuario: Sequence[str],
    regras_bloqueio: Sequence[str] = (),
    segredos: Sequence[str] = (),
) -> str:
    """Preenche ``revisor_acoes`` com os dados já limpos.

    Argumentos com nome sensível viram ``[oculto]``, segredos conhecidos somem, tudo é
    truncado e vai como JSON (aspas e quebras escapadas). Só os últimos pedidos do usuário
    entram, porque são eles que dizem se o destino é confiável.
    """
    argumentos = ocultar_argumentos_sensiveis(acao.argumentos)
    acao_json = _cortar(
        redigir(
            json.dumps(
                {"ferramenta": acao.ferramenta, "argumentos": argumentos},
                ensure_ascii=False,
                default=str,
            ),
            segredos,
        ),
        MAX_CARACTERES_ARGUMENTOS,
    )
    pedidos = [
        _cortar(redigir(p, segredos), MAX_CARACTERES_PEDIDO)
        for p in list(pedidos_do_usuario)[-MAX_PEDIDOS:]
        if p.strip()
    ]
    regras = [_cortar(r, MAX_CARACTERES_PEDIDO) for r in regras_bloqueio if r.strip()]
    return preencher(
        carregar_prompt("revisor_acoes"),
        pedidos_do_usuario=neutralizar_cerca(
            json.dumps(pedidos, ensure_ascii=False) if pedidos else "nenhum"
        ),
        regras_bloqueio=neutralizar_cerca(
            json.dumps(regras, ensure_ascii=False) if regras else "nenhuma"
        ),
        acao_json=neutralizar_cerca(acao_json),
    )


def bloqueio(motivo: str) -> AvaliacaoRevisor:
    """Avaliação de falha fechada: o cartão de aprovação aparece para o usuário."""
    return AvaliacaoRevisor(
        dano=Dano.EFEITO_EXTERNO,
        quem_recebe=None,
        destino=Destino.NAO_AUTORIZADO,
        decisao=DecisaoRevisor.BLOQUEAR,
        motivo=motivo,
    )


def interpretar_avaliacao(texto: str) -> AvaliacaoRevisor:
    """Lê o JSON do revisor. Qualquer problema vira BLOQUEAR."""
    try:
        avaliacao = AvaliacaoRevisor.model_validate_json(extrair_json(texto))
    except (SaidaInvalida, ValidationError, ValueError):
        return bloqueio("O revisor não respondeu num formato válido.")
    motivo = " ".join(avaliacao.motivo.split()).replace("—", "-")
    return avaliacao.model_copy(update={"motivo": _cortar(motivo, MAX_CARACTERES_MOTIVO)})


async def avaliar_acao(
    chamar_modelo: ChamarModelo,
    acao: AcaoProposta,
    pedidos_do_usuario: Sequence[str],
    regras_bloqueio: Sequence[str] = (),
    *,
    segredos: Sequence[str] = (),
    prazo_segundos: float = PRAZO_PADRAO_SEGUNDOS,
) -> AvaliacaoRevisor:
    """Roda o revisor com prazo. Prazo estourado ou erro do provedor → BLOQUEAR."""
    prompt = montar_prompt_revisor(acao, pedidos_do_usuario, regras_bloqueio, segredos)
    try:
        texto = await asyncio.wait_for(
            chamar_modelo(carregar_prompt("juiz_rapido"), prompt), timeout=prazo_segundos
        )
    except TimeoutError:
        return bloqueio("O revisor demorou demais; a decisão fica com você.")
    except Exception:
        return bloqueio("O revisor falhou; a decisão fica com você.")
    return interpretar_avaliacao(texto)
