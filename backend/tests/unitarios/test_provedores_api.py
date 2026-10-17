"""Rotas e regras das APIs de modelos, sem rede nem banco real."""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.api.provedores import obter_listador
from app.core import conexoes
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.llm.provedores import ChaveInvalida, ConfigProvedor
from app.main import criar_aplicacao
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.esquemas import ProvedorAtualizacao, ProvedorCriacao
from app.modelos.tabelas import ModeloDisponivel, Provedor

USUARIO = UUID("12121212-1212-4121-8121-121212121212")
SEGREDO = "sk-TESTE-NAO-VAZAR-1234567890"


class ResultadoEscalares:
    def __init__(self, itens: list[Any]) -> None:
        self.itens = itens

    def all(self) -> list[Any]:
        return self.itens


class SessaoFalsa:
    def __init__(
        self, *, escalares: list[Any] | None = None, listas: list[list[Any]] | None = None
    ) -> None:
        self.escalares = list(escalares or [])
        self.listas = list(listas or [])
        self.adicionados: list[Any] = []
        self.flushes = 0

    async def scalar(self, _consulta: Any) -> Any:
        return self.escalares.pop(0) if self.escalares else None

    async def scalars(self, _consulta: Any) -> ResultadoEscalares:
        return ResultadoEscalares(self.listas.pop(0) if self.listas else [])

    def add(self, item: Any) -> None:
        self.adicionados.append(item)

    def add_all(self, itens: list[Any]) -> None:
        self.adicionados.extend(itens)

    async def flush(self) -> None:
        self.flushes += 1


@pytest.fixture
async def redis_falso() -> AsyncIterator[Any]:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield redis
    await redis.aclose()


def _aplicacao(sessao: SessaoFalsa, redis: Any, listador: Any) -> Any:
    app = criar_aplicacao()
    app.dependency_overrides[usuario_atual] = lambda: USUARIO
    app.dependency_overrides[obter_sessao] = lambda: sessao
    app.dependency_overrides[obter_redis] = lambda: redis
    app.dependency_overrides[obter_listador] = lambda: listador
    return app


def test_repr_dos_esquemas_nao_expoe_a_chave() -> None:
    criacao = ProvedorCriacao(tipo=TipoProvedor.OPENAI, chave=SEGREDO)
    atualizacao = ProvedorAtualizacao(chave=SEGREDO)
    assert SEGREDO not in repr(criacao)
    assert SEGREDO not in repr(atualizacao)


async def test_validacao_global_nao_ecoa_chave_longa_em_post_ou_patch(redis_falso) -> None:
    async def listar(_config: ConfigProvedor) -> list[str]:
        raise AssertionError("A validação deveria impedir a chamada ao listador.")

    chave_longa = SEGREDO + "X" * 2_001
    sessao = SessaoFalsa()
    with TestClient(_aplicacao(sessao, redis_falso, listar)) as cliente:
        post = cliente.post("/v1/provedores", json={"tipo": "openai", "chave": chave_longa})
        patch = cliente.patch(f"/v1/provedores/{uuid4()}", json={"chave": chave_longa})

    for resposta in (post, patch):
        assert resposta.status_code == 422
        assert SEGREDO not in resposta.text
        erro = resposta.json()["detail"][0]
        assert set(erro) == {"loc", "msg", "type"}
        assert "input" not in erro and "ctx" not in erro


async def test_validacao_global_nao_ecoa_senha_longa_no_auth(redis_falso) -> None:
    async def listar(_config: ConfigProvedor) -> list[str]:
        return []

    senha_longa = "senha-TESTE-NAO-VAZAR-" + "X" * 300
    with TestClient(_aplicacao(SessaoFalsa(), redis_falso, listar)) as cliente:
        resposta = cliente.post(
            "/v1/auth/entrar",
            json={"email": "ana@exemplo.com", "senha": senha_longa},
        )

    assert resposta.status_code == 422
    assert senha_longa not in resposta.text
    erro = resposta.json()["detail"][0]
    assert set(erro) == {"loc", "msg", "type"}
    assert "input" not in erro and "ctx" not in erro


async def test_post_testa_com_listador_injetado_cifra_e_nao_vaza_chave(redis_falso) -> None:
    recebidas: list[ConfigProvedor] = []

    async def listar(config: ConfigProvedor) -> list[str]:
        recebidas.append(config)
        return ["openai/z-fora", "openai/gpt-5.6-luna"]

    sessao = SessaoFalsa(escalares=[USUARIO, None, 0])
    with TestClient(_aplicacao(sessao, redis_falso, listar)) as cliente:
        resposta = cliente.post(
            "/v1/provedores",
            json={"tipo": "openai", "chave": f"  {SEGREDO}  "},
        )

    assert resposta.status_code == 201
    assert SEGREDO not in resposta.text
    assert resposta.json()["provedor"]["chave_final"] == "7890"
    assert [modelo["modelo"] for modelo in resposta.json()["modelos"]] == [
        "openai/gpt-5.6-luna",
        "openai/z-fora",
    ]
    assert recebidas[0].api_key is not None
    assert recebidas[0].api_key.get_secret_value() == SEGREDO
    provedor = next(item for item in sessao.adicionados if isinstance(item, Provedor))
    assert provedor.chave_cifrada is not None and SEGREDO.encode() not in provedor.chave_cifrada


@pytest.mark.parametrize(
    ("erro", "mensagem"),
    [
        (ChaveInvalida("O provedor recusou a chave."), "O provedor recusou a chave."),
        (None, "O provedor não devolveu nenhum modelo."),
    ],
)
async def test_post_falha_422_sem_gravar_nem_vazar(
    redis_falso, erro: Exception | None, mensagem: str
) -> None:
    async def listar(_config: ConfigProvedor) -> list[str]:
        if erro is not None:
            raise erro
        return []

    sessao = SessaoFalsa(escalares=[USUARIO, None, 0])
    with TestClient(_aplicacao(sessao, redis_falso, listar)) as cliente:
        resposta = cliente.post("/v1/provedores", json={"tipo": "openai", "chave": SEGREDO})
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": mensagem}
    assert SEGREDO not in resposta.text
    assert sessao.adicionados == []


async def test_decima_primeira_tentativa_recebe_429_e_retry_after(redis_falso) -> None:
    chamadas = 0

    async def listar(_config: ConfigProvedor) -> list[str]:
        nonlocal chamadas
        chamadas += 1
        return []

    sessao = SessaoFalsa(escalares=[USUARIO, None, 0])
    with TestClient(_aplicacao(sessao, redis_falso, listar)) as cliente:
        for tentativa in range(11):
            resposta = cliente.post("/v1/provedores", json={"tipo": "openai", "chave": SEGREDO})
            assert resposta.status_code == (422 if tentativa < 10 else 429)
    assert chamadas == 10
    assert int(resposta.headers["retry-after"]) > 0


async def test_conectar_limita_ordena_e_remove_modelos_repetidos(redis_falso) -> None:
    async def listar(_config: ConfigProvedor) -> list[str]:
        return [f"openai/modelo-{numero:03}" for numero in range(501, -1, -1)] + [
            "openai/modelo-001"
        ]

    sessao = SessaoFalsa(escalares=[USUARIO, None, 0])
    _, modelos = await conexoes.conectar(
        sessao,  # type: ignore[arg-type]
        redis_falso,
        USUARIO,
        ProvedorCriacao(tipo=TipoProvedor.OPENAI, chave=SEGREDO),
        listar,
    )
    assert len(modelos) == 500
    assert modelos[0].modelo == "openai/modelo-000"
    assert modelos[-1].modelo == "openai/modelo-499"


async def test_patch_sincroniza_sem_perder_escolhas_do_usuario(redis_falso) -> None:
    provedor = Provedor(
        id=uuid4(),
        usuario_id=USUARIO,
        tipo=TipoProvedor.OPENAI,
        base_url=None,
        chave_cifrada=b"antiga",
        chave_final="tiga",
        validado_em=None,
        falhas_seguidas=3,
    )
    mantido = ModeloDisponivel(
        id=uuid4(),
        provedor_id=provedor.id,
        modelo="openai/gpt-5.6-luna",
        nivel="N3",
        capacidades=[],
        contexto=1,
        origem="usuario",
        ativo=False,
    )
    removido = ModeloDisponivel(
        id=uuid4(),
        provedor_id=provedor.id,
        modelo="openai/antigo",
        nivel="N1",
        capacidades=[],
        contexto=1,
        origem="catalogo",
        ativo=True,
    )
    sessao = SessaoFalsa(escalares=[provedor], listas=[[mantido, removido]])

    async def listar(_config: ConfigProvedor) -> list[str]:
        return ["openai/gpt-5.6-luna", "openai/novo"]

    atualizado = await conexoes.atualizar(
        sessao,  # type: ignore[arg-type]
        redis_falso,
        USUARIO,
        provedor.id,
        ProvedorAtualizacao(chave=SEGREDO, teto_mensal_usd=Decimal("12.34")),
        listar,
    )
    assert mantido.nivel == "N3" and mantido.ativo is False and mantido.origem == "usuario"
    assert removido.ativo is False
    assert any(
        isinstance(item, ModeloDisponivel) and item.modelo == "openai/novo"
        for item in sessao.adicionados
    )
    assert atualizado.chave_final == "7890"
    assert atualizado.falhas_seguidas == 0 and atualizado.pausado_ate is None
    assert atualizado.teto_mensal_usd == Decimal("12.34")


async def test_patch_invalido_nao_muda_provedor(redis_falso) -> None:
    provedor = Provedor(
        id=uuid4(),
        usuario_id=USUARIO,
        tipo=TipoProvedor.OPENAI,
        chave_cifrada=b"inalterada",
        chave_final="rada",
        teto_mensal_usd=Decimal("5"),
    )
    sessao = SessaoFalsa(escalares=[provedor])

    async def listar(_config: ConfigProvedor) -> list[str]:
        raise ChaveInvalida("O provedor recusou a chave.")

    with pytest.raises(conexoes.ErroDadosProvedor):
        await conexoes.atualizar(
            sessao,  # type: ignore[arg-type]
            redis_falso,
            USUARIO,
            provedor.id,
            ProvedorAtualizacao(chave=SEGREDO, teto_mensal_usd=Decimal("10")),
            listar,
        )
    assert provedor.chave_cifrada == b"inalterada"
    assert provedor.teto_mensal_usd == Decimal("5")
    assert sessao.flushes == 0


async def test_delete_apaga_chave_e_desativa_modelos() -> None:
    provedor = Provedor(
        id=uuid4(),
        usuario_id=USUARIO,
        tipo=TipoProvedor.OPENAI,
        chave_cifrada=b"cifrada",
        chave_final="1234",
    )
    modelo = ModeloDisponivel(
        id=uuid4(),
        provedor_id=provedor.id,
        modelo="openai/x",
        nivel="N2",
        capacidades=[],
        contexto=8192,
        ativo=True,
    )
    sessao = SessaoFalsa(escalares=[provedor], listas=[[modelo]])
    await conexoes.apagar(sessao, USUARIO, provedor.id)  # type: ignore[arg-type]
    assert provedor.apagado_em is not None
    assert provedor.chave_cifrada is None and provedor.chave_final is None
    assert modelo.ativo is False


async def test_outro_usuario_ou_apagado_parece_inexistente() -> None:
    sessao = SessaoFalsa(escalares=[None])
    with pytest.raises(conexoes.ErroProvedorNaoEncontrado):
        await conexoes.apagar(sessao, USUARIO, uuid4())  # type: ignore[arg-type]
