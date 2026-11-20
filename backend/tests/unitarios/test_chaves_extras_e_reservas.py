"""Chaves extras por conexão e modelos reserva (migração 0019), sem banco.

- o aviso de troca diz "outra chave" quando o mesmo modelo segue com a próxima chave;
- o limite que não cedeu na espera (``ErroLimiteDoProvedor``) também é avisado quando há próximo;
- as reservas da conta que não servem agora ficam de fora em silêncio.

Com PostgreSQL (rotas, cifra, apagar a conexão, lista do worker): ``tests/integracao/
test_provedores.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import litellm
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.llm.limite import ErroLimiteDoProvedor
from app.llm.troca import EventoTroca, MotivoTroca, marcar_chave, montar_middleware_de_troca
from app.modelos.enumeracoes import Nivel, Prioridade, TipoProvedor
from app.orquestrador import modelos as orquestrador
from app.seletor.tipos import (
    Capacidade,
    ContextoSeletor,
    ModeloCandidato,
    ProvedorSeletor,
)


class Modelo(GenericFakeChatModel):
    model: str = "groq/llama"
    erro: Any = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        if self.erro is not None:
            raise self.erro
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _limite() -> Exception:
    return litellm.RateLimitError(message="429", llm_provider="groq", model="groq/llama")


async def _rodar(modelos: list[Modelo]) -> tuple[str, list[EventoTroca]]:
    eventos: list[EventoTroca] = []

    async def ao_trocar(evento: EventoTroca) -> None:
        eventos.append(evento)

    agente = create_agent(
        modelos[0],
        middleware=montar_middleware_de_troca(modelos, ao_trocar=ao_trocar, espera_inicial_s=0),
    )
    resultado = await agente.ainvoke({"messages": [HumanMessage("oi")]})
    return str(resultado["messages"][-1].content), eventos


async def test_mesmo_modelo_com_outra_chave_avisa_outra_chave() -> None:
    principal = Modelo(erro=_limite(), messages=iter([AIMessage("nunca")] * 5))
    extra = Modelo(messages=iter([AIMessage("pronto")]))
    marcar_chave(principal, 0)
    marcar_chave(extra, 1)
    texto, eventos = await _rodar([principal, extra])
    assert texto == "pronto"
    assert eventos and all(e.outra_chave for e in eventos)
    assert eventos[0].motivo is MotivoTroca.LIMITE_DE_TAXA


async def test_limite_que_nao_cedeu_tambem_e_avisado_e_passa_para_a_reserva() -> None:
    principal = Modelo(
        erro=ErroLimiteDoProvedor("limite por minuto"), messages=iter([AIMessage("nunca")])
    )
    reserva = Modelo(model="gemini/gemini-2.5-flash", messages=iter([AIMessage("pronto")]))
    texto, eventos = await _rodar([principal, reserva])
    assert texto == "pronto"
    [evento] = eventos
    assert (evento.de_modelo, evento.para_modelo, evento.outra_chave) == (
        "groq/llama",
        "gemini/gemini-2.5-flash",
        False,
    )


async def test_limite_sem_proximo_nao_vira_aviso_de_troca() -> None:
    principal = Modelo(erro=ErroLimiteDoProvedor("x"), messages=iter([AIMessage("nunca")]))
    with pytest.raises(ErroLimiteDoProvedor):
        await _rodar([principal])


# ---------- reservas que servem agora ----------


def _provedor(tipo: TipoProvedor = TipoProvedor.GROQ, **campos: Any) -> ProvedorSeletor:
    return ProvedorSeletor(id=uuid4(), tipo=tipo, **campos)


def _candidato(provedor: ProvedorSeletor, modelo: str, **campos: Any) -> ModeloCandidato:
    base: dict[str, Any] = {
        "modelo": modelo,
        "provedor": provedor,
        "nivel": Nivel.N2,
        "capacidades": frozenset({Capacidade.FERRAMENTAS}),
        "contexto": 8192,
    }
    return ModeloCandidato(**{**base, **campos})


async def test_reservas_validas_pulam_o_que_nao_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _provedor()
    gemini = _provedor(TipoProvedor.GOOGLE)
    cara = _provedor(TipoProvedor.OPENAI, teto_mensal_usd=Decimal("1"), gasto_mes_usd=Decimal("2"))
    escolhido = _candidato(groq, "groq/a")
    boa = _candidato(gemini, "gemini/b")
    desligada = _candidato(groq, "groq/c", ativo=False)
    sem_ferramenta = _candidato(gemini, "gemini/d", capacidades=frozenset())
    no_teto = _candidato(cara, "openai/e")
    contexto = ContextoSeletor(
        modelos=[escolhido, boa, desligada, sem_ferramenta, no_teto], prioridade=Prioridade.CUSTO
    )

    class Reserva:
        def __init__(self, provedor_id: UUID, modelo: str) -> None:
            self.provedor_id, self.modelo = provedor_id, modelo

    lista = [
        Reserva(groq.id, "groq/a"),  # é o próprio escolhido
        Reserva(cara.id, "openai/e"),
        Reserva(groq.id, "groq/c"),
        Reserva(gemini.id, "gemini/d"),
        Reserva(gemini.id, "gemini/b"),
        Reserva(uuid4(), "sumiu/x"),
    ]

    async def listar(_sessao: Any, _usuario: UUID) -> list[Reserva]:
        return lista

    monkeypatch.setattr("app.core.reservas.listar_reservas", listar)
    validas = await orquestrador._reservas_validas(
        None,  # type: ignore[arg-type]
        uuid4(),
        contexto,
        escolhido,
        {Capacidade.FERRAMENTAS},
        conversa_privada=False,
    )
    assert [c.modelo for c in validas] == ["gemini/b"]
    # conversa privada: só local (Ollama)
    privada = await orquestrador._reservas_validas(
        None,  # type: ignore[arg-type]
        uuid4(),
        contexto,
        escolhido,
        {Capacidade.FERRAMENTAS},
        conversa_privada=True,
    )
    assert privada == []
