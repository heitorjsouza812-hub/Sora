"""O bot vê a tela: a captura do computador vai ao modelo como imagem (Farol-2, item 1).

Como funciona:

- ``computador_observar`` e ``computador_agir`` continuam devolvendo texto (janelas, conferência).
  A imagem **não** é gravada no histórico do bot: o ``MiddlewareVisaoTela`` a junta, só na
  chamada do modelo, como uma mensagem do usuário no fim, com **a última captura** (a da leitura
  que o último resultado de ``computador_*`` citou). Por isso o contexto nunca acumula telas.
- Mesmo caminho multimodal da visão de anexos (``app/agentes/visao.py``): bloco ``image_url``
  com ``data:`` URL. Até **uma** imagem por chamada, reduzida a no máximo 1280 px de largura.
- A escala fica explicada no texto: o modelo lê x/y na imagem e precisa passar x/y da tela
  **real**; quando a imagem é reduzida, o texto diz por quanto multiplicar.
- Sem visão (o modelo da chamada não tem a capacidade ``visao``), nada de imagem e o prompt de
  sistema diz isso ao bot, com o que fazer no lugar (terminal, atalhos, refs de janela). Quem
  decide é o modelo **da chamada** (``request.model``), então uma troca de provedor no meio do
  turno vale: o middleware roda por dentro da troca.
"""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.computador.interface import Alvo

if TYPE_CHECKING:
    from app.agentes.montagem import ContextoAgente
    from app.computador.servico import ServicoComputador

LARGURA_MAXIMA_VISAO = 1280
"""Largura máxima da imagem enviada ao modelo (px)."""
MAX_BYTES_PNG = 700_000
"""PNG acima disso cai para JPEG; o PNG mantém o texto da tela nítido."""
QUALIDADE_JPEG = 85
FERRAMENTAS_DA_TELA = frozenset({"computador_observar", "computador_agir"})
PREFIXO_FERRAMENTAS = "computador_"

_LEITURA = re.compile(r"leitura @c(\d+)")

COM_VISAO = (
    "Você enxerga a tela do computador. Depois de computador_observar e de computador_agir, a "
    "captura mais recente chega a você como imagem (só a última fica na conversa). Olhe a "
    "imagem antes de clicar e confira nela o resultado de cada ação. As coordenadas x/y que você "
    "passa são sempre da tela REAL, na escala que o texto da captura explica."
)
SEM_VISAO = (
    "O modelo que está respondendo agora não enxerga imagens: você NÃO vê a captura da tela, só "
    "a lista de janelas e a conferência em texto. Não chute coordenadas de clique. Trabalhe pelo "
    "terminal, por atalhos de teclado (ctrl+l e Enter no navegador, por exemplo), pelas refs de "
    "janela @cN:jM e pelos arquivos. Se o pedido só se resolve olhando a tela, diga ao usuário "
    "que é preciso escolher um modelo com visão em Configurações → Modelos de IA."
)


@dataclass(frozen=True, slots=True)
class ImagemParaModelo:
    dados: bytes
    tipo: str
    """``image/png`` ou ``image/jpeg``."""
    largura: int
    altura: int
    """Tamanho da imagem enviada."""
    largura_real: int
    altura_real: int
    """Tamanho da tela de verdade (as coordenadas valem para ela)."""

    @property
    def fator(self) -> float:
        """Quantas vezes a tela real é maior que a imagem (1,0 = sem redução)."""
        return self.largura_real / self.largura

    def bloco(self) -> dict[str, Any]:
        codigo = base64.b64encode(self.dados).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{self.tipo};base64,{codigo}"}}


def preparar_imagem(png: bytes, largura_maxima: int = LARGURA_MAXIMA_VISAO) -> ImagemParaModelo:
    """Reduz a captura para ``largura_maxima`` (se for maior) e escolhe PNG ou JPEG."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as aberta:
        imagem = aberta.convert("RGB")
    real = imagem.size
    if imagem.width > largura_maxima:
        altura = max(1, round(imagem.height * largura_maxima / imagem.width))
        imagem = imagem.resize((largura_maxima, altura), Image.Resampling.LANCZOS)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    tipo = "image/png"
    if saida.tell() > MAX_BYTES_PNG:
        saida = io.BytesIO()
        imagem.save(saida, format="JPEG", quality=QUALIDADE_JPEG, optimize=True)
        tipo = "image/jpeg"
    return ImagemParaModelo(
        dados=saida.getvalue(),
        tipo=tipo,
        largura=imagem.width,
        altura=imagem.height,
        largura_real=real[0],
        altura_real=real[1],
    )


def texto_da_captura(imagem: ImagemParaModelo, geracao: int, alvo: Alvo = Alvo.VIRTUAL) -> str:
    """O que acompanha a imagem: qual leitura ela mostra e como converter as coordenadas."""
    nome = "do computador virtual" if alvo is Alvo.VIRTUAL else "do computador do usuário"
    base = (
        f"[captura da tela {nome}, leitura @c{geracao}: imagem de {imagem.largura}x"
        f"{imagem.altura} px. A tela real tem {imagem.largura_real}x{imagem.altura_real} px. "
    )
    if imagem.largura == imagem.largura_real:
        escala = (
            "A imagem está em escala 1:1: o x/y que você lê nela é o x/y que deve passar nas ações."
        )
    else:
        fator = f"{imagem.fator:.2f}".replace(".", ",")
        escala = (
            f"A imagem foi reduzida {fator} vez(es): as ações usam a tela REAL, então multiplique "
            f"por {fator} o x/y que você lê na imagem. "
        )
    return base + escala + " Só esta captura fica na conversa; as anteriores saem.]"


def _texto(conteudo: Any) -> str:
    return conteudo if isinstance(conteudo, str) else str(conteudo)


def _ultima_leitura_citada(mensagens: list[Any]) -> int | None:
    """Número da leitura (``@cN``) do último resultado de ``computador_*`` desta rodada.

    Só conta depois da última mensagem do usuário: telas de turnos antigos não voltam."""
    for mensagem in reversed(mensagens):
        if isinstance(mensagem, HumanMessage) and not mensagem.additional_kwargs.get(
            "sora_captura"
        ):
            return None
        if isinstance(mensagem, ToolMessage) and mensagem.name in FERRAMENTAS_DA_TELA:
            achada = _LEITURA.search(_texto(mensagem.content))
            return int(achada.group(1)) if achada else None
    return None


class MiddlewareVisaoTela(AgentMiddleware):
    """Põe a última captura na chamada do modelo (ou avisa que o modelo não enxerga)."""

    def __init__(
        self,
        agente_id: UUID,
        *,
        servico: Callable[[], ServicoComputador],
        tem_visao: Callable[[Any], bool],
    ) -> None:
        self._agente_id = agente_id
        self._servico = servico
        self._tem_visao = tem_visao

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]):
        ve = self._tem_visao(request.model)
        nota = COM_VISAO if ve else SEM_VISAO
        sistema = SystemMessage(content=f"{request.system_prompt or ''}\n\n{nota}".strip())
        mensagens = list(request.messages)
        if ve:
            extra = await self._mensagem_da_tela(mensagens)
            if extra is not None:
                mensagens.append(extra)
        return await handler(request.override(system_message=sistema, messages=mensagens))

    async def _mensagem_da_tela(self, mensagens: list[Any]) -> HumanMessage | None:
        geracao = _ultima_leitura_citada(mensagens)
        if geracao is None:
            return None
        servico = self._servico()
        for alvo in Alvo:
            leitura = servico.leituras.get((self._agente_id, alvo))
            if leitura is None or leitura.geracao != geracao:
                continue
            import asyncio

            imagem = await asyncio.to_thread(preparar_imagem, leitura.observacao.tela.png)
            return HumanMessage(
                content=[
                    {"type": "text", "text": texto_da_captura(imagem, geracao, alvo)},
                    imagem.bloco(),
                ],
                additional_kwargs={"sora_captura": True},
            )
        return None  # a leitura já não é a que este worker guarda: melhor sem imagem que errada


def tem_ferramenta_do_computador(nomes: list[str]) -> bool:
    return any(nome.startswith(PREFIXO_FERRAMENTAS) for nome in nomes)


async def nomes_de_modelos_com_visao(usuario_id: UUID) -> frozenset[str]:
    """Modelos do usuário com a capacidade ``visao`` (a do catálogo ou a que ele marcou)."""
    from app.core.banco import fabrica_sessoes
    from app.seletor.repositorio import contexto_do_usuario
    from app.seletor.tipos import Capacidade

    async with fabrica_sessoes()() as sessao:
        contexto = await contexto_do_usuario(sessao, usuario_id)
    return frozenset(
        m.modelo for m in contexto.modelos if m.ativo and Capacidade.VISAO in m.capacidades
    )


def _nome_do_modelo(modelo: Any) -> str:
    return str(getattr(modelo, "model", None) or getattr(modelo, "model_name", None) or "")


async def com_visao_do_computador(contexto: ContextoAgente) -> ContextoAgente:
    """Prepara o contexto do agente que tem ``computador_*``: guarda quem enxerga.

    Sem as ferramentas do computador não faz nada. Com o modelo falso (só desenvolvimento) o
    modelo conta como vidente, como na visão de anexos."""
    from app.agentes.montagem import nomes_das_ferramentas
    from app.llm.falso import modelo_falso_ativo

    if not tem_ferramenta_do_computador(nomes_das_ferramentas(contexto)):
        return contexto
    if modelo_falso_ativo():
        return replace(contexto, modelo_enxerga=lambda _modelo: True)
    nomes = await nomes_de_modelos_com_visao(contexto.usuario_id)
    return replace(contexto, modelo_enxerga=lambda modelo: _nome_do_modelo(modelo) in nomes)
