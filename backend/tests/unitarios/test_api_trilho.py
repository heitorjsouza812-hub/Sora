"""Regressões do contrato HTTP -> banco -> ARQ do agente Trilho."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.api import cadeias as api_cadeias
from app.api import conversas as api_conversas
from app.modelos.enumeracoes import (
    Movimento,
    StatusCadeia,
    TipoAgente,
    TipoConversa,
)
from app.sistema1.esquemas import Especialista, ModoTriagem, Risco, SaidaSistema1, Superficie


class _Resultado:
    def __init__(self, valor=None) -> None:
        self.valor = valor

    def all(self):
        return [] if self.valor is None else self.valor


class _Sessao:
    def __init__(self, ordem: list[str]) -> None:
        self.ordem = ordem
        self.adicionados = []

    def add(self, objeto) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        for objeto in self.adicionados:
            if hasattr(objeto, "id") and objeto.id is None:
                objeto.id = uuid4()
        self.ordem.append("flush")

    async def commit(self) -> None:
        self.ordem.append("commit")

    async def scalars(self, _consulta):
        return _Resultado()

    async def scalar(self, _consulta):
        return 0


class _Fila:
    def __init__(self, ordem: list[str]) -> None:
        self.ordem = ordem
        self.jobs: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, nome: str, *args, **kwargs):
        assert "commit" in self.ordem
        self.ordem.append(f"job:{nome}")
        self.jobs.append((nome, args, kwargs))


@pytest.mark.asyncio
async def test_agente_individual_confirma_antes_de_enfileirar() -> None:
    ordem: list[str] = []
    fila = _Fila(ordem)
    mensagem_id = uuid4()
    await api_conversas._encaminhar(
        _Sessao(ordem),  # type: ignore[arg-type]
        SimpleNamespace(),
        fila,  # type: ignore[arg-type]
        usuario_id=uuid4(),
        conversa=SimpleNamespace(id=uuid4()),
        mensagem=SimpleNamespace(id=mensagem_id),
        agente=SimpleNamespace(tipo=TipoAgente.INDIVIDUAL),
    )
    assert ordem == ["commit", "job:responder_direto"]
    assert fila.jobs == [
        ("responder_direto", (str(mensagem_id),), {"_job_id": f"responder:{mensagem_id}"})
    ]


@pytest.mark.asyncio
async def test_modelo_falso_cria_cadeia_e_job_serializavel(monkeypatch) -> None:
    ordem: list[str] = []
    fila = _Fila(ordem)
    usuario_id, conversa_id, mensagem_id, agente_id = (uuid4() for _ in range(4))

    monkeypatch.setattr(
        api_conversas,
        "obter_configuracao",
        lambda: SimpleNamespace(sora_modelo_falso=True),
    )

    async def contexto(*_args, **_kwargs):
        from app.seletor.tipos import ContextoSeletor

        return ContextoSeletor()

    async def contexto_triagem(*_args, **_kwargs):
        from app.sistema1.triagem import ContextoTriagem

        return ContextoTriagem()

    async def triagem(_texto, _contexto, seletor, configs):
        assert seletor.modelos[0].modelo == "sora/falso"
        assert list(configs) == [str(UUID(int=0))]
        return SimpleNamespace(
            saida=SaidaSistema1(
                primeira_resposta="Vou montar a equipe.",
                modo=ModoTriagem.CADEIA,
                dificuldade=3,
                especialistas=[Especialista.PESQUISADOR, Especialista.VERIFICADOR],
                superficie=Superficie.WEB,
                risco=Risco.NENHUM,
                idioma="pt-BR",
                confianca=1,
            ),
            modelo="sora/falso",
            provedor_id=UUID(int=0),
            escalou=False,
            latencia_ms=1,
            chamadas=[],
        )

    eventos = []

    async def publicar(_redis, evento, *_args):
        eventos.append(evento)

    async def primeira(*_args, **_kwargs):
        ordem.append("primeira-resposta")

    monkeypatch.setattr(api_conversas, "contexto_do_usuario", contexto)
    monkeypatch.setattr(api_conversas, "_contexto_triagem", contexto_triagem)
    monkeypatch.setattr(api_conversas, "triar", triagem)
    monkeypatch.setattr(api_conversas, "publicar_evento", publicar)
    monkeypatch.setattr(api_conversas, "_publicar_primeira_resposta", primeira)

    conversa = SimpleNamespace(
        id=conversa_id,
        privada=False,
        tipo=TipoConversa.CHAT,
    )
    await api_conversas._encaminhar(
        _Sessao(ordem),  # type: ignore[arg-type]
        SimpleNamespace(),
        fila,  # type: ignore[arg-type]
        usuario_id=usuario_id,
        conversa=conversa,
        mensagem=SimpleNamespace(id=mensagem_id, conteudo="crie uma campanha"),
        agente=SimpleNamespace(id=agente_id, tipo=TipoAgente.SORA),
    )

    assert eventos[0].evento == "roteamento"
    assert conversa.tipo == TipoConversa.PROJETO
    assert fila.jobs[0][0] == "planejar_cadeia"
    assert fila.jobs[0][1] == (fila.jobs[0][1][0],)
    UUID(fila.jobs[0][1][0])


@pytest.mark.asyncio
async def test_cancelamento_idempotente_grava_sinal_e_evento(monkeypatch) -> None:
    cadeia_id, conversa_id, usuario_id = uuid4(), uuid4(), uuid4()
    ordem: list[str] = []
    cadeia = SimpleNamespace(
        id=cadeia_id,
        conversa_id=conversa_id,
        status=StatusCadeia.CANCELADA,
        tokens_usados=12,
        custo_usd=Decimal("0.01"),
    )

    async def cancelar(*_args):
        return cadeia

    async def publicar(*_args):
        ordem.append("evento")

    class Redis:
        async def set(self, chave, valor, ex):
            ordem.append(f"redis:{chave}:{valor}:{ex}")

    monkeypatch.setattr(api_cadeias.repositorio, "cancelar", cancelar)
    monkeypatch.setattr(api_cadeias, "publicar_evento", publicar)
    await api_cadeias.cancelar_cadeia(
        cadeia_id,
        usuario_id,
        _Sessao(ordem),  # type: ignore[arg-type]
        Redis(),  # type: ignore[arg-type]
    )
    assert ordem[0] == "commit"
    assert ordem[-1] == "evento"


def test_conversa_saida_mantem_aparencia_fora_do_contrato() -> None:
    """Sentinela simples: Trilho não acrescenta cor/movimento ao contrato da conversa."""
    campos = set(api_conversas.ConversaSaida.model_fields)
    assert "cor" not in campos and "movimento" not in campos
    assert Movimento.GIRA.value == "gira"
