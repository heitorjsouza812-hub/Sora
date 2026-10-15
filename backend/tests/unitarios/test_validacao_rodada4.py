"""Validação adversarial final (Tranca): cifra com AAD, limites atômicos, trava de produção no
worker e Last-Event-ID extremo. Os ``xfail(strict=True)`` marcam achados abertos (VAL-17+)."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import fakeredis
import pytest
from cryptography.exceptions import InvalidTag

from app.core import contas, seguranca
from app.core.config import obter_configuracao
from app.core.redis import reservar_vaga
from app.eventos.sse import gerar_sse
from app.modelos.esquemas import LoginEntrada


@pytest.fixture
async def redis():
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


# ------------------------------------------------------------------------------ cifra AES-GCM


def test_cifra_ida_e_volta_e_nonce_aleatorio() -> None:
    u = uuid4()
    a = seguranca.cifrar_segredo("sk-segredo", usuario_id=u, provedor="openai")
    b = seguranca.cifrar_segredo("sk-segredo", usuario_id=u, provedor="openai")
    assert a != b and a[1:13] != b[1:13]
    assert a[0] == seguranca.VERSAO_CHAVE
    assert b"sk-segredo" not in a
    assert seguranca.decifrar_segredo(a, usuario_id=u, provedor="openai") == "sk-segredo"


def test_aad_trocado_nao_decifra() -> None:
    u = uuid4()
    blob = seguranca.cifrar_segredo("sk-x", usuario_id=u, provedor="openai")
    with pytest.raises(InvalidTag):
        seguranca.decifrar_segredo(blob, usuario_id=uuid4(), provedor="openai")
    with pytest.raises(InvalidTag):
        seguranca.decifrar_segredo(blob, usuario_id=u, provedor="anthropic")


def test_adulteracao_e_formatos_ruins_falham_fechado() -> None:
    u = uuid4()
    blob = bytearray(seguranca.cifrar_segredo("sk-x", usuario_id=u, provedor="p"))
    for posicao in (5, 13, len(blob) - 1):
        ruim = bytearray(blob)
        ruim[posicao] ^= 1
        with pytest.raises(InvalidTag):
            seguranca.decifrar_segredo(bytes(ruim), usuario_id=u, provedor="p")
    with pytest.raises(ValueError):
        seguranca.decifrar_segredo(b"", usuario_id=u, provedor="p")
    with pytest.raises(ValueError):
        seguranca.decifrar_segredo(bytes([2]) + bytes(blob[1:]), usuario_id=u, provedor="p")


def test_rotacao_da_chave_mestra_mantem_segredos_antigos(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64
    import os

    u = uuid4()
    antigo = seguranca.cifrar_segredo("sk-x", usuario_id=u, provedor="p")
    assert antigo[0] == 1
    # Rotação (VAL-17): a chave nova vira a versão 2; a antiga fica só para decifrar.
    monkeypatch.setenv("CHAVES_MESTRAS_ANTIGAS", f"1:{os.environ['CHAVE_MESTRA']}")
    monkeypatch.setenv("CHAVE_MESTRA", base64.b64encode(b"N" * 32).decode())
    monkeypatch.setenv("CHAVE_MESTRA_VERSAO", "2")
    obter_configuracao.cache_clear()
    try:
        assert seguranca.decifrar_segredo(antigo, usuario_id=u, provedor="p") == "sk-x"
        novo = seguranca.cifrar_segredo("sk-y", usuario_id=u, provedor="p")
        assert novo[0] == 2
        assert seguranca.precisa_recifrar(antigo) and not seguranca.precisa_recifrar(novo)
        migrado = seguranca.recifrar_segredo(antigo, usuario_id=u, provedor="p")
        assert migrado[0] == 2
        assert seguranca.recifrar_segredo(migrado, usuario_id=u, provedor="p") == migrado
        # Depois da migração, a chave antiga pode sair: o migrado continua legível.
        monkeypatch.delenv("CHAVES_MESTRAS_ANTIGAS")
        obter_configuracao.cache_clear()
        assert seguranca.decifrar_segredo(migrado, usuario_id=u, provedor="p") == "sk-x"
        with pytest.raises(ValueError):
            seguranca.decifrar_segredo(antigo, usuario_id=u, provedor="p")
    finally:
        obter_configuracao.cache_clear()


def test_recifrar_nao_aceita_segredo_adulterado() -> None:
    u = uuid4()
    blob = bytearray(seguranca.cifrar_segredo("sk-x", usuario_id=u, provedor="p"))
    blob[-1] ^= 1
    with pytest.raises(InvalidTag):
        seguranca.recifrar_segredo(bytes(blob), usuario_id=u, provedor="p")


@pytest.mark.parametrize(
    ("versao", "antigas"),
    [
        ("0", ""),
        ("256", ""),
        ("1", "1:{b64}"),  # versão repetida
        ("2", "1:curta"),  # base64 inválido
        ("2", "1:QUFB"),  # 3 bytes, não 32
        ("2", "x:{b64}"),  # versão não numérica
        ("2", "{b64}"),  # sem versão
        ("2", "300:{b64}"),  # fora da faixa
    ],
)
def test_chaveiro_invalido_quebra_na_configuracao(
    monkeypatch: pytest.MonkeyPatch, versao: str, antigas: str
) -> None:
    import base64

    from pydantic import ValidationError

    b64 = base64.b64encode(b"A" * 32).decode()
    monkeypatch.setenv("CHAVE_MESTRA_VERSAO", versao)
    monkeypatch.setenv("CHAVES_MESTRAS_ANTIGAS", antigas.format(b64=b64))
    obter_configuracao.cache_clear()
    try:
        with pytest.raises((ValidationError, ValueError)):
            obter_configuracao()
    finally:
        obter_configuracao.cache_clear()


# ----------------------------------------------------------------------- limites atômicos


async def test_reservas_simultaneas_nunca_passam_do_limite(redis) -> None:
    resultados = await asyncio.gather(*(reservar_vaga(redis, "k", 5, 60) for _ in range(60)))
    assert sum(1 for espera, _ in resultados if espera == 0) == 5
    assert await redis.zcard("limite:k") == 5
    assert 0 < await redis.ttl("limite:k") <= 60


class SessaoNula:
    def __init__(self, usuario=None) -> None:
        self.usuario = usuario

    async def scalar(self, *_a, **_k):
        return self.usuario

    def add(self, *_a) -> None:
        pass

    async def flush(self) -> None:
        pass


async def test_login_em_rajada_deixa_passar_so_cinco_por_email_e_ip(redis) -> None:
    async def tentar():
        try:
            await contas.entrar(
                SessaoNula(),
                redis,
                LoginEntrada(email="v@x.com", senha="errada-errada"),
                "web",
                "1.1.1.1",
                None,
            )
        except contas.ErroConta as erro:
            return type(erro).__name__

    saidas = await asyncio.gather(*(tentar() for _ in range(40)))
    assert saidas.count("ErroCredenciais") == 5
    assert saidas.count("ErroLimite") == 35


async def test_login_certo_limpa_falhas_e_outro_ip_nao_e_afetado(redis) -> None:
    usuario = SimpleNamespace(id=uuid4(), senha_hash=seguranca.gerar_hash_senha("senha-correta-1"))

    async def entrar(senha: str, ip: str):
        return await contas.entrar(
            SessaoNula(usuario), redis, LoginEntrada(email="v@x.com", senha=senha), "web", ip, None
        )

    for _ in range(4):
        with pytest.raises(contas.ErroCredenciais):
            await entrar("errada-errada", "9.9.9.9")  # atacante, mesmo e-mail
    await entrar("senha-correta-1", "2.2.2.2")  # vítima, outro IP, não é bloqueada
    with pytest.raises(contas.ErroCredenciais):
        await entrar("errada-errada", "9.9.9.9")  # o 5º do atacante ainda cabe...
    with pytest.raises(contas.ErroLimite):
        await entrar("errada-errada", "9.9.9.9")  # ...o 6º não


# --------------------------------------------------------------- trava de produção no worker


@pytest.mark.parametrize("busca", ["falso", "FALSO ", "searxng", " SearXNG"])
def test_worker_recusa_busca_de_desenvolvimento_em_producao(
    monkeypatch: pytest.MonkeyPatch, busca: str
) -> None:
    from workers.configuracao import verificar_trava_de_producao

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("JWT_SEGREDO", "j" * 40 + "Qz9")
    monkeypatch.setenv("BUSCA_PROVEDOR", busca)
    obter_configuracao.cache_clear()
    try:
        with pytest.raises(Exception):  # noqa: B017 (falha fechada: trava ou validação da config)
            verificar_trava_de_producao()
    finally:
        obter_configuracao.cache_clear()


# ---------------------------------------------------------------------- Last-Event-ID extremo


@pytest.mark.parametrize(
    "valor",
    [
        "9" * 20 + "-" + "9" * 20,
        "9" * 5000 + "-0",
        "1-1\n",
        chr(0x661) + "-1",
        "1-1-1",
        "-1",
        "1-",
        " 1-1",
    ],
)
def test_id_valido_recusa_ids_gigantes_e_estranhos(valor: str) -> None:
    from app.eventos.streams import id_valido

    assert not id_valido(valor)


def test_id_valido_aceita_ids_reais_do_redis() -> None:
    from app.eventos.streams import id_valido

    assert id_valido("0-0")
    assert id_valido("1760000000000-18446744073709551615")


async def test_last_event_id_gigante_nao_derruba_o_stream(redis) -> None:
    import time

    from app.eventos.streams import canal_usuario

    mensagens = []

    async def ler() -> None:
        # Sem eventos, o stream só termina quando o token vence (expira_em); antes da correção
        # o int() de 5000 dígitos levantava ValueError aqui dentro.
        async for m in gerar_sse(
            redis,
            canal_usuario(uuid4()),
            "9" * 5000 + "-0",
            bloquear_ms=20,
            expira_em=time.time() + 0.3,
        ):
            mensagens.append(m)

    await asyncio.wait_for(ler(), timeout=10)
    assert mensagens == []  # id inválido é ignorado: começa no fim do stream, sem exceção
