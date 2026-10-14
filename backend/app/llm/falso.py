"""Modelo falso para desenvolver sem chave e sem custo.

Especificação: §8.5 "Modelo falso para desenvolver". Com ``SORA_MODELO_FALSO=1`` o ``llm/`` troca
todos os modelos por um ``GenericFakeChatModel`` com respostas prontas (triagem, plano, entregas
e veredito de exemplo). O backend inteiro roda no PC emitindo os mesmos eventos do modo real.
Nunca fica ligado em produção: o startup chama ``verificar_modelo_falso_permitido``.

Como o modelo se comporta, por papel (nome do papel da política do seletor, §5):

- ``sistema1``: lê o pedido no fim do prompt e devolve a triagem em JSON. Saudação ou pergunta
  curta → ``direto``; qualquer outra coisa → ``cadeia`` com pesquisador, redator e verificador.
- ``planejador``: o plano de exemplo (3 etapas) em JSON, aceito por ``with_structured_output``.
- ``pesquisador``: chama ``buscar_web`` e depois ``entregar`` (links). ``redator`` e ``designer``:
  ``entregar`` (texto). ``verificador``: ``veredito`` aprovado. ``sora`` e ``agente_individual``:
  ``falar``. ``resposta_direta``: texto simples. ``revisor``: BLOQUEAR (falha fechada).
- Qualquer outro papel: um texto de exemplo.

As respostas se repetem em ciclo, então um laço de agente nunca fica sem resposta. Todas as
respostas de ferramenta e de JSON são montadas com os esquemas reais (``Plano``, ``Entregar``,
``Veredito``, ``SaidaSistema1``…): se um esquema mudar, o modelo falso quebra alto em vez de
mentir. As classes do LangChain só são importadas na primeira vez que o modelo é criado.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from functools import cache
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage

VARIAVEL_MODELO_FALSO = "SORA_MODELO_FALSO"
AMBIENTES_DE_PRODUCAO = frozenset({"producao", "produção", "production", "prod"})
_VALORES_LIGADOS = frozenset({"1", "true", "sim", "yes", "on"})

# Papéis (política do seletor, §5) que ganham uma sequência de respostas prontas.
PAPEIS_COM_RESPOSTA_PRONTA: tuple[str, ...] = (
    "sistema1",
    "resposta_direta",
    "sora",
    "planejador",
    "pesquisador",
    "redator",
    "designer",
    "verificador",
    "agente_individual",
    "revisor",
)

_TEXTO_PADRAO = "(modelo falso) Esta é uma resposta de exemplo para desenvolvimento."


class ModeloFalsoEmProducao(RuntimeError):
    """``SORA_MODELO_FALSO`` ligado num ambiente de produção."""


def modelo_falso_ativo() -> bool:
    """True quando ``SORA_MODELO_FALSO=1`` (ou ``true``/``sim``) está no ambiente."""
    return os.environ.get(VARIAVEL_MODELO_FALSO, "").strip().lower() in _VALORES_LIGADOS


def verificar_modelo_falso_permitido(ambiente: str, ligado: bool) -> None:
    """Levanta ``ModeloFalsoEmProducao`` se o modelo falso estiver ligado em produção.

    O startup do Alicerce chama com ``ambiente`` (ex.: ``"producao"``, ``"desenvolvimento"``) e
    ``ligado`` (a configuração ``sora_modelo_falso``). Fora de produção, não faz nada.
    """
    if ligado and ambiente.strip().lower() in AMBIENTES_DE_PRODUCAO:
        raise ModeloFalsoEmProducao(
            f"{VARIAVEL_MODELO_FALSO} não pode ficar ligado em produção. "
            "Desligue a variável e reinicie."
        )


# ---------------------------------------------------------------- montagem das respostas


def _texto(conteudo: str) -> AIMessage:
    from langchain_core.messages import AIMessage

    return AIMessage(content=conteudo)


def _chamada(ferramenta: str, argumentos: dict[str, Any]) -> AIMessage:
    from langchain_core.messages import AIMessage

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": ferramenta,
                "args": argumentos,
                "id": f"falso_{uuid4().hex}",
                "type": "tool_call",
            }
        ],
    )


def _triagem_json(*, direto: bool) -> str:
    from app.sistema1.esquemas import (
        CapacidadeTriagem,
        Especialista,
        ModoTriagem,
        Risco,
        SaidaSistema1,
        Superficie,
    )

    if direto:
        saida = SaidaSistema1(
            primeira_resposta="Claro, já te respondo.",
            modo=ModoTriagem.DIRETO,
            resposta_direta="Olá! Sou a Sora. (resposta do modelo falso)",
            dificuldade=1,
            idioma="pt-BR",
            confianca=0.95,
        )
    else:
        saida = SaidaSistema1(
            primeira_resposta="Entendi! Vou montar uma equipe para isso.",
            modo=ModoTriagem.CADEIA,
            dificuldade=2,
            especialistas=[
                Especialista.PESQUISADOR,
                Especialista.REDATOR,
                Especialista.VERIFICADOR,
            ],
            superficie=Superficie.WEB,
            risco=Risco.NENHUM,
            idioma="pt-BR",
            capacidades=[CapacidadeTriagem.FERRAMENTAS],
            confianca=0.9,
        )
    return saida.model_dump_json()


def _plano_json() -> str:
    from app.modelos.enumeracoes import Nivel
    from app.orquestrador.planejador import EtapaPlano, Plano

    plano = Plano(
        objetivo="Atender o pedido do usuário com uma pesquisa e um texto conferido.",
        requisitos=["O pedido foi atendido", "As afirmações têm fonte"],
        etapas=[
            EtapaPlano(
                ordem=1,
                especialista="pesquisador",
                nivel=Nivel.N2,
                tarefa="Pesquisar referências sobre o pedido do usuário.",
                pronto_quando="Há pelo menos duas referências com link.",
            ),
            EtapaPlano(
                ordem=2,
                especialista="redator",
                nivel=Nivel.N2,
                tarefa="Escrever o texto final com base nas referências.",
                pronto_quando="O texto responde ao pedido e cita as fontes.",
                depende_de=[1],
            ),
            EtapaPlano(
                ordem=3,
                especialista="verificador",
                nivel=Nivel.N2,
                tarefa="Conferir os requisitos do plano contra as entregas.",
                pronto_quando="Cada requisito tem evidência e status.",
                depende_de=[1, 2],
            ),
        ],
    )
    return plano.model_dump_json()


def _entrega(**campos: Any) -> dict[str, Any]:
    from app.ferramentas.entregar import Entregar

    return Entregar(**campos).model_dump(mode="json")


def _veredito() -> dict[str, Any]:
    from app.ferramentas.veredito import RequisitoVerificado, Veredito

    return Veredito(
        aprovado=True,
        requisitos=[
            RequisitoVerificado(
                requisito="O pedido foi atendido",
                evidencia="Entrega de exemplo do modelo falso.",
                status="atendido",
            )
        ],
        motivo="Aprovado pelo modelo falso.",
    ).model_dump(mode="json")


def _avaliacao_revisor() -> str:
    from app.revisor.esquemas import AvaliacaoRevisor, Dano, DecisaoRevisor, Destino

    return AvaliacaoRevisor(
        dano=Dano.EFEITO_EXTERNO,
        quem_recebe=None,
        destino=Destino.NAO_AUTORIZADO,
        decisao=DecisaoRevisor.BLOQUEAR,
        motivo="O modelo falso bloqueia toda ação por segurança.",
    ).model_dump_json()


def respostas_prontas(papel: str) -> list[AIMessage]:
    """Uma volta completa de respostas de exemplo do papel (JSON válido nos papéis de JSON).

    ``sistema1`` devolve a triagem de cadeia; o modelo falso do Sistema 1 escolhe a resposta pelo
    pedido (ver ``ModeloFalso``). Papel desconhecido devolve um texto de exemplo.
    """
    from app.ferramentas.buscar_web import BuscarWeb
    from app.ferramentas.falar import Falar

    if papel == "sistema1":
        return [_texto(_triagem_json(direto=False))]
    if papel == "planejador":
        return [_texto(_plano_json())]
    if papel == "revisor":
        return [_texto(_avaliacao_revisor())]
    if papel == "resposta_direta":
        return [_texto(_TEXTO_PADRAO)]
    if papel in ("sora", "agente_individual"):
        texto = "Pronto! Aqui está o resultado de exemplo. (modelo falso)"
        return [_chamada("falar", Falar(texto=texto).model_dump(mode="json", exclude_none=True))]
    if papel == "pesquisador":
        busca = BuscarWeb(consulta="referências sobre o pedido", max_resultados=2)
        links = [
            {"titulo": "Referência de exemplo A", "url": "https://example.com/a"},
            {"titulo": "Referência de exemplo B", "url": "https://example.com/b"},
        ]
        return [
            _chamada("buscar_web", busca.model_dump(mode="json")),
            _chamada(
                "entregar",
                _entrega(
                    tipo="links",
                    titulo="Pesquisa",
                    resumo="2 referências",
                    conteudo=links,
                    fontes=[item["url"] for item in links],
                ),
            ),
        ]
    if papel == "redator":
        return [
            _chamada(
                "entregar",
                _entrega(
                    tipo="texto",
                    titulo="Texto",
                    resumo="1 texto",
                    conteudo="Texto de exemplo escrito pelo modelo falso.",
                ),
            )
        ]
    if papel == "designer":
        return [
            _chamada(
                "entregar",
                _entrega(
                    tipo="texto",
                    titulo="Peças",
                    resumo="1 peça (descrição)",
                    conteudo="Descrição de exemplo de uma peça visual (modelo falso).",
                ),
            )
        ]
    if papel == "verificador":
        return [_chamada("veredito", _veredito())]
    return [_texto(_TEXTO_PADRAO)]


def _ciclo(papel: str) -> Iterator[AIMessage]:
    """Respostas do papel em ciclo infinito, com ids de chamada de ferramenta sempre novos."""
    while True:
        yield from respostas_prontas(papel)


# ------------------------------------------------------------------------- o modelo


def _pedido_do_prompt(mensagens: list[BaseMessage]) -> str:
    """O pedido do usuário: o que vem depois do último ``Pedido:`` do prompt do Sistema 1."""
    texto = ""
    for mensagem in reversed(mensagens):
        if isinstance(mensagem.content, str) and mensagem.type == "human":
            texto = mensagem.content
            break
    marcador = "Pedido:"
    posicao = texto.rfind(marcador)
    return (texto[posicao + len(marcador) :] if posicao >= 0 else texto).strip()


def _triagem_para(mensagens: list[BaseMessage]) -> AIMessage:
    from app.sistema1.regras import aplicar_regras

    pedido = _pedido_do_prompt(mensagens)
    curto = len(pedido.split()) <= 8 and pedido.endswith("?")
    return _texto(_triagem_json(direto=aplicar_regras(pedido).saudacao or curto))


def _tokens(texto: str) -> int:
    return max(len(texto) // 4, 1)


def _com_uso(resposta: AIMessage, entrada: list[BaseMessage]) -> AIMessage:
    """Anexa uma estimativa de uso para o custo e o orçamento terem o que somar."""
    texto_entrada = " ".join(str(m.content) for m in entrada)
    texto_saida = str(resposta.content) + json.dumps(resposta.tool_calls, ensure_ascii=False)
    tokens_entrada, tokens_saida = _tokens(texto_entrada), _tokens(texto_saida)
    return resposta.model_copy(
        update={
            "usage_metadata": {
                "input_tokens": tokens_entrada,
                "output_tokens": tokens_saida,
                "total_tokens": tokens_entrada + tokens_saida,
            }
        }
    )


@cache
def classe_modelo_falso() -> type[BaseChatModel]:
    """A classe ``ModeloFalso`` (``GenericFakeChatModel`` com ferramentas e saída estruturada).

    Criada na primeira chamada para o ``import`` do módulo não puxar o LangChain.
    """
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
    from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
    from pydantic import BaseModel

    class ModeloFalso(GenericFakeChatModel):
        """Modelo de mentira: ignora o prompt (exceto no Sistema 1) e segue o roteiro do papel."""

        papel: str = ""
        model_name: str = "falso"

        def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
            """O roteiro já sabe quais ferramentas chamar; vincular não muda nada."""
            return self

        def with_structured_output(
            self, schema: Any, *, include_raw: bool = False, **kwargs: Any
        ) -> Any:
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return self | PydanticOutputParser(pydantic_object=schema)
            return self | JsonOutputParser()

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            if self.papel == "sistema1":
                resposta = _triagem_para(messages)
            else:
                proxima = next(self.messages)
                resposta = _texto(proxima) if isinstance(proxima, str) else proxima
            resposta = _com_uso(resposta, messages)
            return ChatResult(generations=[ChatGeneration(message=resposta)])

        def _stream(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> Iterator[ChatGenerationChunk]:
            # O _stream do GenericFakeChatModel perde as chamadas de ferramenta; este não.
            resposta = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            mensagem = resposta.generations[0].message
            if isinstance(mensagem.content, str):
                for pedaco in filter(None, re.split(r"(\s)", mensagem.content)):
                    bloco = ChatGenerationChunk(message=AIMessageChunk(content=pedaco))
                    if run_manager:
                        run_manager.on_llm_new_token(pedaco, chunk=bloco)
                    yield bloco
            chamadas = [
                {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                for i, c in enumerate(getattr(mensagem, "tool_calls", []))
            ]
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=chamadas,
                    usage_metadata=getattr(mensagem, "usage_metadata", None),
                )
            )

        @property
        def _llm_type(self) -> str:
            return "modelo-falso-sora"

    return ModeloFalso


def criar_modelo_falso(papel: str) -> BaseChatModel:
    """``GenericFakeChatModel`` com as respostas do papel, com suporte a ``bind_tools``."""
    classe = classe_modelo_falso()
    return classe(messages=_ciclo(papel), papel=papel, model_name=f"falso/{papel or 'geral'}")
