# ruff: noqa: F811
"""Canais da empresa (Ponte) com PostgreSQL, Redis, API e worker reais: webhooks assinados,
idempotência, máscara de PII antes de gravar, ficha do cliente, retenção, "apagar este cliente",
autorização por bot e por grupo, isolamento entre usuários, conhecimento (fusão e contradição) e
sugestões de melhoria (aplicar, desfazer, descartar). Nenhuma chamada real ao Slack ou à Meta."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update

from app.canais_empresa import clientes, ingestao, lgpd, resumo, sugestoes
from app.canais_empresa.assinaturas import assinatura_meta, assinatura_slack
from app.canais_empresa.extracao import (
    ConhecimentoExtraido,
    Extracao,
    FatoExtraido,
    MensagemParaExtrair,
)
from app.canais_empresa.sugestoes import BotParaAnalise, SugestaoProposta
from app.canais_empresa.tabelas import (
    ConexaoCanalEmpresa,
    ConhecimentoEmpresa,
    ContatoEmpresa,
    FatoCliente,
    MensagemEmpresa,
    SugestaoMelhoria,
)
from app.eventos.streams import canal_usuario
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.tabelas import Agente, Aprovacao, Habilidade, RegraPermissao, Usuario
from tests.integracao.relogio_base import Mundo, mundo  # noqa: F401
from tests.integracao.relogio_base import servicos_relogio as _servicos_testcontainers
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao

PREFIXO = "/v1/canais-empresa"


@pytest.fixture(scope="module")
def servicos_relogio():
    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        yield os.environ["SORA_TESTE_PG"], os.environ["SORA_TESTE_REDIS"]
        return
    yield from _servicos_testcontainers.__wrapped__()


# ------------------------------------------------------------------ ajudantes


async def _uid(m: Mundo, email: str) -> UUID:
    async with m.fabrica() as sessao:
        return await sessao.scalar(select(Usuario.id).where(Usuario.email == email))


async def _conta(m: Mundo, cliente: httpx.AsyncClient, rotulo: str) -> tuple[dict, UUID]:
    email = f"ponte-{rotulo}-{uuid4()}@exemplo.com"
    auth = await entrar(cliente, m.fabrica, email)
    return auth, await _uid(m, email)


async def _bot(cliente: httpx.AsyncClient, auth: dict, nome: str) -> dict:
    r = await cliente.post(
        "/v1/agentes",
        headers=auth,
        json={"nome": nome, "funcao": "Atende", "papel": "pesquisador", "cor": "#56A8FF"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _slack(
    cliente: httpx.AsyncClient, auth: dict, canais: list[str], *, funcionarios=()
) -> tuple[str, str]:
    """Cria a conexão Slack e escolhe os canais. Devolve (id da conexão, signing secret)."""
    segredo = f"seg-{uuid4().hex}"
    r = await cliente.put(
        f"{PREFIXO}/conexoes/slack",
        headers=auth,
        json={
            "segredos": {"bot_token": "xoxb-1111111111-aaaaaaaaaaaa", "signing_secret": segredo},
            "config": {"dominio": "acme", "ids_funcionarios": list(funcionarios)},
        },
    )
    assert r.status_code == 200, r.text
    conexao = r.json()
    assert "xoxb" not in r.text and segredo not in r.text  # nenhuma rota devolve segredo
    r = await cliente.put(f"{PREFIXO}/conexoes/slack/canais", headers=auth, json={"canais": canais})
    assert r.status_code == 200, r.text
    return conexao["id"], segredo


async def _post_slack(
    cliente: httpx.AsyncClient,
    conexao_id: str,
    segredo: str,
    carga: dict,
    *,
    assinar: bool = True,
    ts: str | None = None,
) -> httpx.Response:
    corpo = json.dumps(carga).encode()
    ts = ts or str(int(time.time()))
    cabecalhos = {"Content-Type": "application/json", "X-Slack-Request-Timestamp": ts}
    if assinar:
        cabecalhos["X-Slack-Signature"] = assinatura_slack(segredo, corpo, ts)
    return await cliente.post(
        f"{PREFIXO}/webhooks/slack/{conexao_id}", content=corpo, headers=cabecalhos
    )


def _evento_slack(canal: str, usuario: str, texto: str, ts: str) -> dict:
    return {
        "type": "event_callback",
        "team_id": "T1",
        "event": {"type": "message", "channel": canal, "user": usuario, "text": texto, "ts": ts},
    }


async def _mensagens(m: Mundo, uid: UUID) -> list[MensagemEmpresa]:
    async with m.fabrica() as sessao:
        return list(
            await sessao.scalars(select(MensagemEmpresa).where(MensagemEmpresa.usuario_id == uid))
        )


async def _eventos(m: Mundo, uid: UUID) -> list[tuple[str, dict]]:
    redis = Redis.from_url(m.url_redis)
    try:
        linhas = await redis.xrange(canal_usuario(uid))
    finally:
        await redis.aclose()
    return [(c[b"event"].decode(), json.loads(c[b"data"])) for _, c in linhas if b"event" in c]


async def _processar(m: Mundo, uid: UUID, extrator) -> resumo.ResultadoDaPassada:
    redis = Redis.from_url(m.url_redis)
    try:
        return await resumo.processar_usuario(m.fabrica, redis, uid, extrator=extrator)
    finally:
        await redis.aclose()


def _extrator_faq(titulo: str, conteudo: str, *, fato: str | None = None):
    """Modelo falso: devolve uma FAQ e, opcionalmente, um fato do 1º cliente."""

    async def extrair(mensagens: list[MensagemParaExtrair]) -> Extracao:
        saida = Extracao(
            conhecimento=[ConhecimentoExtraido("faq", titulo, conteudo, mensagens[-1].indice)]
        )
        cliente = next((x for x in mensagens if x.papel == "cliente"), None)
        if fato and cliente:
            saida.fatos.append(FatoExtraido(cliente.apelido, "pedido", fato, None, cliente.indice))
        return saida

    return extrair


# ------------------------------------------------------------------ webhook do Slack


async def test_slack_assinatura_idempotencia_mascara_e_isolamento(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth_a, uid_a = await _conta(mundo, http, "a")
        auth_b, uid_b = await _conta(mundo, http, "b")
        conexao_id, segredo = await _slack(http, auth_a, ["C111AAAA"])

        # assinatura ausente, errada ou fora da janela: 401, e nada é gravado
        carga = _evento_slack(
            "C111AAAA",
            "UCLI1",
            "Oi! Meu CPF é 529.982.247-25 e a senha: abc12345",
            "1700000000.000100",
        )
        assert (
            await _post_slack(http, conexao_id, segredo, carga, assinar=False)
        ).status_code == 401
        assert (await _post_slack(http, conexao_id, "outro-segredo", carga)).status_code == 401
        antigo = str(int(time.time()) - 3600)
        assert (await _post_slack(http, conexao_id, segredo, carga, ts=antigo)).status_code == 401
        assert await _mensagens(mundo, uid_a) == []

        # handshake do Slack
        r = await _post_slack(
            http, conexao_id, segredo, {"type": "url_verification", "challenge": "abc123"}
        )
        assert r.status_code == 200 and r.json() == {"challenge": "abc123"}

        # mensagem válida: grava mascarada; a mesma entregue de novo não duplica
        for _ in range(2):
            assert (await _post_slack(http, conexao_id, segredo, carga)).status_code == 200
        guardadas = await _mensagens(mundo, uid_a)
        assert len(guardadas) == 1
        texto = guardadas[0].texto or ""
        assert "529.982.247-25" not in texto and "abc12345" not in texto and "[CPF]" in texto
        assert guardadas[0].link == "https://acme.slack.com/archives/C111AAAA/p1700000000000100"

        # canal que o usuário não escolheu é ignorado
        fora = _evento_slack("C999ZZZZ", "UCLI1", "nada a ver", "1700000001.000100")
        assert (await _post_slack(http, conexao_id, segredo, fora)).status_code == 200
        assert len(await _mensagens(mundo, uid_a)) == 1

        # conexão desativada: o webhook some (404)
        await http.put(f"{PREFIXO}/conexoes/slack", headers=auth_a, json={"ativa": False})
        assert (await _post_slack(http, conexao_id, segredo, carga)).status_code == 404
        await http.put(f"{PREFIXO}/conexoes/slack", headers=auth_a, json={"ativa": True})

        # isolamento: a outra conta não vê nada e não mexe em nada
        clientes_a = (await http.get(f"{PREFIXO}/clientes", headers=auth_a)).json()
        assert len(clientes_a) == 1
        contato_id = clientes_a[0]["id"]
        assert (await http.get(f"{PREFIXO}/clientes", headers=auth_b)).json() == []
        assert (
            await http.get(f"{PREFIXO}/clientes/{contato_id}", headers=auth_b)
        ).status_code == 404
        assert (
            await http.patch(f"{PREFIXO}/clientes/{contato_id}", headers=auth_b, json={"nome": "x"})
        ).status_code == 404
        assert (
            await http.delete(f"{PREFIXO}/clientes/{contato_id}", headers=auth_b)
        ).status_code == 404
        conexoes_b = (await http.get(f"{PREFIXO}/conexoes", headers=auth_b)).json()
        assert all(not c["configurada"] for c in conexoes_b)
        bot_a = await _bot(http, auth_a, "Lume")
        r = await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth_b,
            json={"alvo_tipo": "agente", "alvo_id": bot_a["id"], "escopos": ["clientes"]},
        )
        assert r.status_code == 404
        # o segredo de uma conta não vale na conexão da outra
        _, segredo_b = await _slack(http, auth_b, ["C222BBBB"])
        assert (await _post_slack(http, conexao_id, segredo_b, carga)).status_code == 401
        assert uid_b != uid_a


async def test_conexao_nunca_devolve_segredo_e_testa_so_leitura(
    mundo: Mundo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[tuple[str, str]] = []
    escopos = {"valor": "channels:history,groups:history,channels:read,users:read"}

    def responder(req: httpx.Request) -> httpx.Response:
        chamadas.append((req.method, req.url.path))
        if req.url.host == "slack.com":
            return httpx.Response(
                200,
                json={"ok": True, "team_id": "T9", "team": "Acme", "user_id": "UBOT9"},
                headers={"x-oauth-scopes": escopos["valor"]},
            )
        return httpx.Response(
            200, json={"display_phone_number": "+55 11 4000-0000", "verified_name": "Acme"}
        )

    monkeypatch.setattr(
        clientes,
        "fabrica_http",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(responder)),
    )
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, _ = await _conta(mundo, http, "teste")
        await _slack(http, auth, [])
        # com permissão de escrita no token, o teste reprova
        escopos["valor"] = "channels:history,chat:write"
        r = await http.post(f"{PREFIXO}/conexoes/slack/testar", headers=auth)
        assert r.status_code == 200 and r.json()["ok"] is False
        assert "chat:write" in r.json()["detalhe"]
        # só leitura: passa e guarda o id do bot (para ignorar as próprias mensagens)
        escopos["valor"] = "channels:history,groups:history,channels:read,users:read"
        r = await http.post(f"{PREFIXO}/conexoes/slack/testar", headers=auth)
        assert r.json()["ok"] is True and r.json()["avisos"] == []
        slack = next(
            c
            for c in (await http.get(f"{PREFIXO}/conexoes", headers=auth)).json()
            if c["canal"] == "slack"
        )
        assert slack["config"]["bot_user_id"] == "UBOT9" and slack["ultimo_teste_ok"] is True
        assert slack["segredos_definidos"] == {"bot_token": True, "signing_secret": True}
        assert slack["escopos_slack"] == list(clientes.ESCOPOS_DE_LEITURA)
        assert slack["webhook_caminho"].endswith(f"/webhooks/slack/{slack['id']}")

        # WhatsApp: precisa de todos os segredos e do phone_number_id
        r = await http.put(
            f"{PREFIXO}/conexoes/whatsapp", headers=auth, json={"segredos": {"access_token": "t"}}
        )
        assert r.status_code == 422
        r = await http.put(
            f"{PREFIXO}/conexoes/whatsapp",
            headers=auth,
            json={
                "segredos": {
                    "access_token": "EAAtoken123456789012345",
                    "app_secret": "s",
                    "verify_token": "v",
                },
                "config": {"phone_number_id": "555000"},
            },
        )
        assert r.status_code == 200, r.text
        assert "EAAtoken" not in r.text
        r = await http.post(f"{PREFIXO}/conexoes/whatsapp/testar", headers=auth)
        assert r.json()["ok"] is True
        # a única chamada à Meta é a leitura do número; nada de envio em lugar nenhum
        assert all(m in {"GET", "POST"} for m, _ in chamadas)
        assert ("POST", "/api/chat.postMessage") not in chamadas
        assert not any(p.endswith("/messages") for _, p in chamadas)
        assert ("GET", "/v21.0/555000") in chamadas
        # apagar a conexão remove contatos e mensagens
        assert (await http.delete(f"{PREFIXO}/conexoes/slack", headers=auth)).status_code == 204
        assert (await http.delete(f"{PREFIXO}/conexoes/slack", headers=auth)).status_code == 404


# ------------------------------------------------------------------ webhook do WhatsApp


async def test_whatsapp_handshake_assinatura_ficha_eventos_e_apagar(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "wa")
        r = await http.put(
            f"{PREFIXO}/conexoes/whatsapp",
            headers=auth,
            json={
                "segredos": {
                    "access_token": "EAAxxxxxxxxxxxxxxxxxxxxxxxx",
                    "app_secret": "app-secret",
                    "verify_token": "vt-123",
                },
                "config": {"phone_number_id": "555000"},
            },
        )
        conexao_id = r.json()["id"]
        url = f"{PREFIXO}/webhooks/whatsapp/{conexao_id}"
        assert (
            await http.put(
                f"{PREFIXO}/conexoes/whatsapp/canais", headers=auth, json={"canais": ["555000"]}
            )
        ).status_code == 200

        # handshake da Meta
        params = {"hub.mode": "subscribe", "hub.verify_token": "vt-123", "hub.challenge": "777"}
        ok = await http.get(url, params=params)
        assert ok.status_code == 200 and ok.text == "777"
        assert (
            await http.get(url, params={**params, "hub.verify_token": "errado"})
        ).status_code == 403

        def carga(mid: str, texto: str, de: str = "5511999990000", ts: str = "1700000000") -> dict:
            return {
                "object": "whatsapp_business_account",
                "entry": [{"id": "W", "changes": [{"field": "messages", "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "555000"},
                    "contacts": [{"profile": {"name": "Maria Souza"}, "wa_id": de}],
                    "messages": [{"from": de, "id": mid, "timestamp": ts, "type": "text",
                                  "text": {"body": texto}}],
                }}]}],
            }  # fmt: skip

        async def enviar(corpo_json: dict, *, segredo: str = "app-secret") -> httpx.Response:
            corpo = json.dumps(corpo_json).encode()
            return await http.post(
                url,
                content=corpo,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": assinatura_meta(segredo, corpo),
                },
            )

        assert (await enviar(carga("wamid.1", "oi"), segredo="errado")).status_code == 401
        assert (await http.post(url, json=carga("wamid.1", "oi"))).status_code == 401
        assert await _mensagens(mundo, uid) == []
        assert (
            await enviar(carga("wamid.1", "Quero trocar o tênis. Cartão 4539 1488 0343 6467"))
        ).status_code == 200
        assert (
            await enviar(carga("wamid.1", "Quero trocar o tênis. Cartão 4539 1488 0343 6467"))
        ).status_code == 200
        # eco do app do celular da empresa (coexistência): vira mensagem do funcionário
        eco = carga("wamid.2", "")
        eco["entry"][0]["changes"][0]["field"] = "smb_message_echoes"
        valor = eco["entry"][0]["changes"][0]["value"]
        valor.pop("messages")
        valor["message_echoes"] = [
            {
                "to": "5511999990000",
                "id": "wamid.2",
                "timestamp": "1700000100",
                "type": "text",
                "text": {"body": "A troca é em até 7 dias."},
            }
        ]
        assert (await enviar(eco)).status_code == 200
        msgs = await _mensagens(mundo, uid)
        assert sorted(m.direcao for m in msgs) == ["entrada", "saida"]
        assert all("4539" not in (m.texto or "") for m in msgs)
        assert len({m.contato_id for m in msgs}) == 1

        # resumo (modelo falso): ficha com origem e conhecimento sem dado pessoal
        extrator = _extrator_faq(
            "Prazo de troca da Maria Souza", "A troca é em até 7 dias. Fale com maria@exemplo.com",
            fato="Quer trocar o tênis",
        )  # fmt: skip
        r = await _processar(mundo, uid, extrator)
        assert r.fatos_novos == 1 and r.conhecimento_novo == 1 and r.falhas == 0
        lista = (await http.get(f"{PREFIXO}/clientes", headers=auth)).json()
        assert lista[0]["nome"] == "Maria Souza" and lista[0]["total_fatos"] == 1
        ficha = (await http.get(f"{PREFIXO}/clientes/{lista[0]['id']}", headers=auth)).json()
        fato = ficha["fatos"][0]
        assert fato["tipo"] == "pedido" and fato["origem_externo_id"] in {"wamid.1", "wamid.2"}
        assert (
            await http.get(f"{PREFIXO}/clientes", headers=auth, params={"busca": "souza"})
        ).json()
        assert (
            await http.get(f"{PREFIXO}/clientes", headers=auth, params={"busca": "zzz"})
        ).json() == []
        item = (await http.get(f"{PREFIXO}/conhecimento", headers=auth)).json()[0]
        assert "Maria" not in item["titulo"] and "@" not in item["conteudo"]
        assert item["ocorrencias"] == 1 and item["origens"][0]["canal"] == "whatsapp"

        # as mensagens já processadas não voltam a ser resumidas
        again = await _processar(mundo, uid, extrator)
        assert again.mensagens == 0

        # eventos SSE no stream do usuário
        nomes = [n for n, _ in await _eventos(mundo, uid)]
        assert "cliente.atualizado" in nomes and "conhecimento.atualizado" in nomes

        # editar e apagar um fato
        r = await http.patch(
            f"{PREFIXO}/fatos/{fato['id']}",
            headers=auth,
            json={"texto": "Quer trocar o tênis 42; CPF 529.982.247-25"},
        )
        assert (
            r.status_code == 200
            and r.json()["editado"] is True
            and "529.982" not in r.json()["texto"]
        )
        assert (await http.delete(f"{PREFIXO}/fatos/{fato['id']}", headers=auth)).status_code == 204
        assert (await http.get(f"{PREFIXO}/clientes/{lista[0]['id']}", headers=auth)).json()[
            "fatos"
        ] == []

        # LGPD: apagar tudo deste cliente (contato, mensagens, fichas e rastros no conhecimento)
        await _processar(mundo, uid, extrator)  # nada pendente; só garante o estado
        r = await http.delete(f"{PREFIXO}/clientes/{lista[0]['id']}", headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["mensagens"] == 2 and r.json()["conhecimento_removido"] == 1
        assert await _mensagens(mundo, uid) == []
        assert (await http.get(f"{PREFIXO}/conhecimento", headers=auth)).json() == []
        async with mundo.fabrica() as sessao:
            assert (
                await sessao.scalars(select(FatoCliente).where(FatoCliente.usuario_id == uid))
            ).all() == []
            assert (
                await sessao.scalars(select(ContatoEmpresa).where(ContatoEmpresa.usuario_id == uid))
            ).all() == []


# ------------------------------------------------------------------ conhecimento


async def _registrar(
    m: Mundo, uid: UUID, textos: list[tuple[str, str, str, datetime]], canal: str = "C111AAAA"
) -> None:
    """Grava mensagens do Slack direto pelo registro (controla a data de cada uma)."""
    async with m.fabrica() as sessao:
        conexao = await sessao.scalar(
            select(ConexaoCanalEmpresa).where(ConexaoCanalEmpresa.usuario_id == uid)
        )
        mensagens = [
            ingestao.MensagemNormalizada(
                canal="slack",
                id_externo=f"{canal}:{ident}",
                canal_externo=canal,
                fio=f"slack:{canal}:{canal}",
                contato_externo=usuario,
                contato_nome="",
                papel="funcionario" if usuario.startswith("UF") else "cliente",
                direcao="saida" if usuario.startswith("UF") else "entrada",
                texto=texto,
                enviada_em=quando,
                link=f"https://acme.slack.com/archives/{canal}/p{ident.replace('.', '')}",
            )
            for ident, usuario, texto, quando in textos
        ]
        await ingestao.registrar_mensagens(sessao, conexao, mensagens)
        await sessao.commit()


async def test_conhecimento_funde_repetidos_marca_contradicao_e_respeita_edicao(
    mundo: Mundo,
) -> None:
    """Só fala de funcionário ensina a empresa; contradição não troca nada sozinha."""
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "conh")
        await _slack(http, auth, ["C111AAAA"], funcionarios=["UFUNC1", "UFUNC2"])
        agora = datetime.now(UTC)

        async def lista() -> list[dict]:
            return (await http.get(f"{PREFIXO}/conhecimento", headers=auth)).json()

        await _registrar(
            mundo, uid, [("1.1", "UFUNC1", "A troca é em até 7 dias.", agora - timedelta(days=3))]
        )
        r = await _processar(
            mundo, uid, _extrator_faq("Qual o prazo de troca?", "A troca é em até 7 dias.")
        )
        assert r.conhecimento_novo == 1
        item = (await lista())[0]
        assert item["estado"] == "pendente" and item["no_prompt"] is False
        # a mesma FAQ, com outras palavras e outro funcionário: funde e soma a contagem
        await _registrar(
            mundo, uid, [("2.1", "UFUNC2", "Pode trocar em 7 dias.", agora - timedelta(days=2))]
        )
        r = await _processar(
            mundo, uid, _extrator_faq("O prazo da troca é qual?", "Você pode trocar em até 7 dias.")
        )
        assert (r.conhecimento_novo, r.conhecimento_atualizado) == (0, 1)
        itens = await lista()
        assert len(itens) == 1 and itens[0]["ocorrencias"] == 2 and not itens[0]["contraditorio"]
        # o usuário aprova: só agora o item vale para os bots
        r = await http.post(f"{PREFIXO}/conhecimento/{item['id']}/aprovar", headers=auth)
        assert r.status_code == 200 and r.json()["estado"] == "aprovado"
        assert r.json()["no_prompt"] is True and r.json()["aprovado_em"]

        # resposta diferente: o item fica contraditório e FORA do prompt; o conteúdo não troca
        await _registrar(
            mundo, uid, [("3.1", "UFUNC1", "Agora é 30 dias.", agora - timedelta(days=1))]
        )
        r = await _processar(
            mundo, uid, _extrator_faq("Prazo de troca?", "Agora a troca é em até 30 dias.")
        )
        item = (await lista())[0]
        assert item["contraditorio"] is True and item["no_prompt"] is False
        assert "7 dias" in item["conteudo"]
        assert [d["conteudo"] for d in item["em_disputa"]] == ["Agora a troca é em até 30 dias."]
        assert (
            await http.get(f"{PREFIXO}/conhecimento", headers=auth, params={"contraditorio": True})
        ).json()
        # aprovar com contradição aberta: 409
        r = await http.post(f"{PREFIXO}/conhecimento/{item['id']}/aprovar", headers=auth)
        assert r.status_code == 409
        # versão inexistente: 409; a escolha fecha a contradição e aprova
        r = await http.post(
            f"{PREFIXO}/conhecimento/{item['id']}/resolver", headers=auth, json={"versao": 7}
        )
        assert r.status_code == 409
        r = await http.post(
            f"{PREFIXO}/conhecimento/{item['id']}/resolver", headers=auth, json={"versao": 0}
        )
        item = r.json()
        assert "30 dias" in item["conteudo"] and item["contraditorio"] is False
        assert item["no_prompt"] is True and item["em_disputa"] == []
        assert any("7 dias" in a["conteudo"] for a in item["anteriores"])

        # busca
        achados = (
            await http.get(f"{PREFIXO}/conhecimento", headers=auth, params={"busca": "troca"})
        ).json()
        assert len(achados) == 1
        # editar trava (e aprova): depois, uma resposta nova só conta
        r = await http.patch(
            f"{PREFIXO}/conhecimento/{item['id']}",
            headers=auth,
            json={"conteudo": "A troca é em até 14 dias."},
        )
        assert r.status_code == 200 and r.json()["editado"] is True
        assert r.json()["contraditorio"] is False and r.json()["no_prompt"] is True
        await _registrar(mundo, uid, [("4.1", "UFUNC1", "Troca em 3 dias úteis.", agora)])
        await _processar(mundo, uid, _extrator_faq("Prazo de troca?", "Troca em 3 dias úteis."))
        item = (await lista())[0]
        assert "14 dias" in item["conteudo"] and not item["contraditorio"]
        # apagar: some e não volta sozinho
        assert (
            await http.delete(f"{PREFIXO}/conhecimento/{item['id']}", headers=auth)
        ).status_code == 204
        await _registrar(mundo, uid, [("5.1", "UFUNC2", "7 dias.", agora)])
        await _processar(mundo, uid, _extrator_faq("Prazo de troca?", "7 dias."))
        assert await lista() == []


async def test_conhecimento_isolado_entre_contas_e_apagar_cliente_limpa_rastros(
    mundo: Mundo,
) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth_a, uid_a = await _conta(mundo, http, "iso-a")
        auth_b, uid_b = await _conta(mundo, http, "iso-b")
        await _slack(http, auth_a, ["C111AAAA"])
        await _slack(http, auth_b, ["C111AAAA"])
        agora = datetime.now(UTC)
        await _registrar(
            mundo,
            uid_a,
            [
                ("1.1", "UCLI1", "Troca em quantos dias?", agora),
                ("1.2", "UCLI2", "E a entrega?", agora),
            ],
        )
        await _registrar(mundo, uid_b, [("1.1", "UCLI1", "Outra empresa", agora)])
        await _processar(
            mundo, uid_a, _extrator_faq("Troca em quantos dias", "7 dias", fato="Quer trocar")
        )
        await _processar(mundo, uid_b, _extrator_faq("Entrega no sábado", "Sim"))
        itens_a = (await http.get(f"{PREFIXO}/conhecimento", headers=auth_a)).json()
        itens_b = (await http.get(f"{PREFIXO}/conhecimento", headers=auth_b)).json()
        assert [i["titulo"] for i in itens_a] == ["Troca em quantos dias"]
        assert [i["titulo"] for i in itens_b] == ["Entrega no sábado"]
        assert (
            await http.patch(
                f"{PREFIXO}/conhecimento/{itens_a[0]['id']}", headers=auth_b, json={"titulo": "x"}
            )
        ).status_code == 404
        assert (
            await http.delete(f"{PREFIXO}/conhecimento/{itens_a[0]['id']}", headers=auth_b)
        ).status_code == 404
        assert (
            await http.get(f"{PREFIXO}/conhecimento", headers=auth_b, params={"busca": "troca"})
        ).json() == []
        # o conhecimento só perde as origens do cliente apagado, e nunca as de outra conta
        contatos = (await http.get(f"{PREFIXO}/clientes", headers=auth_a)).json()
        com_fato = next(c for c in contatos if c["total_fatos"])
        r = await http.delete(f"{PREFIXO}/clientes/{com_fato['id']}", headers=auth_a)
        assert r.status_code == 200
        assert len((await http.get(f"{PREFIXO}/conhecimento", headers=auth_b)).json()) == 1


# ------------------------------------------------------------------ retenção


async def test_retencao_apaga_texto_cru_e_mantem_a_ficha(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "ret")
        await _slack(http, auth, ["C111AAAA"])
        assert (await http.get(f"{PREFIXO}/preferencias", headers=auth)).json()[
            "retencao_dias"
        ] == 90
        agora = datetime.now(UTC)
        await _registrar(
            mundo,
            uid,
            [("1.1", "UCLI1", "mensagem velha", agora), ("1.2", "UCLI1", "mensagem nova", agora)],
        )
        await _processar(mundo, uid, _extrator_faq("Velha", "texto", fato="Pediu algo"))
        async with mundo.fabrica() as sessao:
            await sessao.execute(
                update(MensagemEmpresa)
                .where(MensagemEmpresa.id_externo == "C111AAAA:1.1")
                .values(recebida_em=agora - timedelta(days=100))
            )
            await sessao.execute(
                update(MensagemEmpresa)
                .where(MensagemEmpresa.id_externo == "C111AAAA:1.2")
                .values(recebida_em=agora - timedelta(days=40))
            )
            await sessao.commit()
        async with mundo.fabrica() as sessao:  # padrão de 90 dias
            assert await lgpd.apagar_mensagens_vencidas(sessao) >= 1
            await sessao.commit()
        por_id = {m.id_externo: m for m in await _mensagens(mundo, uid)}
        assert (
            por_id["C111AAAA:1.1"].texto is None and por_id["C111AAAA:1.2"].texto == "mensagem nova"
        )
        r = await http.put(f"{PREFIXO}/preferencias", headers=auth, json={"retencao_dias": 30})
        assert r.json()["retencao_dias"] == 30
        assert (
            await http.put(f"{PREFIXO}/preferencias", headers=auth, json={"retencao_dias": 0})
        ).status_code == 422
        async with mundo.fabrica() as sessao:
            assert await lgpd.apagar_mensagens_vencidas(sessao) >= 1
            assert await lgpd.apagar_mensagens_vencidas(sessao) == 0  # já apagadas
            await sessao.commit()
        msgs = await _mensagens(mundo, uid)
        assert len(msgs) == 2 and all(m.texto is None and m.texto_apagado_em for m in msgs)
        # a linha fica (idempotência do webhook) e a ficha continua com o link de origem
        contato = (await http.get(f"{PREFIXO}/clientes", headers=auth)).json()[0]
        ficha = (await http.get(f"{PREFIXO}/clientes/{contato['id']}", headers=auth)).json()
        assert ficha["total_fatos"] == 1 and ficha["fatos"][0]["origem_link"]


# ------------------------------------------------------------------ autorização das ferramentas


async def test_ferramentas_exigem_autorizacao_de_bot_ou_grupo(mundo: Mundo) -> None:
    from app.canais_empresa.ferramentas import (
        ConsultarCliente,
        ConsultarConhecimento,
        consultar_cliente,
        consultar_conhecimento,
    )

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "aut2")
        auth_b, uid_b = await _conta(mundo, http, "aut2-b")
        await _slack(http, auth, ["C111AAAA"], funcionarios=["UFUNC1"])
        await _registrar(
            mundo,
            uid,
            [
                ("1.1", "UCLI1", "oi", datetime.now(UTC)),
                ("1.2", "UFUNC1", "7 dias.", datetime.now(UTC) + timedelta(seconds=1)),
            ],
        )
        await _processar(
            mundo, uid, _extrator_faq("Prazo de troca", "7 dias", fato="Prefere entrega à tarde")
        )
        [pendente] = (await http.get(f"{PREFIXO}/conhecimento", headers=auth)).json()
        async with mundo.fabrica() as sessao:
            await sessao.execute(
                update(ContatoEmpresa)
                .where(ContatoEmpresa.usuario_id == uid)
                .values(nome="Maria Souza")
            )
            await sessao.commit()
        bot = await _bot(http, auth, "Lume")
        colega = await _bot(http, auth, "Nina")
        terceiro = await _bot(http, auth, "Atlas")
        bot_b = await _bot(http, auth_b, "Intruso")

        def ctx(usuario: UUID, agente: str, grupo: str | None = None) -> ContextoFerramenta:
            return ContextoFerramenta(
                usuario_id=usuario,
                agente_id=UUID(agente),
                conversa_id=uuid4(),
                canal_id=UUID(grupo) if grupo else None,
            )

        pedido = ConsultarCliente(cliente="Maria")
        busca = ConsultarConhecimento(consulta="prazo troca")
        # sem autorização: nada
        for chamada in (
            consultar_cliente(pedido, ctx(uid, bot["id"])),
            consultar_conhecimento(busca, ctx(uid, bot["id"])),
        ):
            with pytest.raises(ErroFerramenta, match="autorização"):
                await chamada
        # autoriza só o conhecimento: a ficha continua fechada
        r = await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "agente", "alvo_id": bot["id"], "escopos": ["conhecimento"]},
        )
        assert r.status_code == 200 and r.json()["escopos"] == ["conhecimento"]
        # item novo, ainda não aprovado: o bot autorizado não enxerga
        assert "nada" in await consultar_conhecimento(busca, ctx(uid, bot["id"]))
        r = await http.post(f"{PREFIXO}/conhecimento/{pendente['id']}/aprovar", headers=auth)
        assert r.status_code == 200
        assert "7 dias" in await consultar_conhecimento(busca, ctx(uid, bot["id"]))
        with pytest.raises(ErroFerramenta):
            await consultar_cliente(pedido, ctx(uid, bot["id"]))
        # autoriza a ficha: a resposta vem cercada como dado externo, com a origem
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={
                "alvo_tipo": "agente",
                "alvo_id": bot["id"],
                "escopos": ["clientes", "conhecimento"],
            },
        )
        ficha = await consultar_cliente(pedido, ctx(uid, bot["id"]))
        assert "<dado_externo" in ficha and "Prefere entrega à tarde" in ficha
        assert "origem: https://acme.slack.com/archives/C111AAAA" in ficha
        assert "Nenhum cliente" in await consultar_cliente(
            ConsultarCliente(cliente="Zé"), ctx(uid, bot["id"])
        )
        # a ficha de uma conta nunca aparece para o bot (autorizado) de outra
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth_b,
            json={
                "alvo_tipo": "agente",
                "alvo_id": bot_b["id"],
                "escopos": ["clientes", "conhecimento"],
            },
        )
        assert "Nenhum cliente" in await consultar_cliente(pedido, ctx(uid_b, bot_b["id"]))
        assert "nada" in await consultar_conhecimento(busca, ctx(uid_b, bot_b["id"]))
        # bot de outra conta usando o id de um bot meu: sem autorização
        with pytest.raises(ErroFerramenta):
            await consultar_cliente(pedido, ctx(uid_b, bot["id"]))
        # grupo autorizado vale só dentro do grupo
        g = await http.post(
            "/v1/grupos",
            headers=auth,
            json={"nome": "Atendimento", "membros": [colega["id"], terceiro["id"]]},
        )
        assert g.status_code == 201, g.text
        grupo = g.json()["id"]
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "grupo", "alvo_id": grupo, "escopos": ["clientes"]},
        )
        assert "Prefere entrega" in await consultar_cliente(pedido, ctx(uid, colega["id"], grupo))
        with pytest.raises(ErroFerramenta):
            await consultar_cliente(
                pedido, ctx(uid, colega["id"])
            )  # 1:1, sem a própria autorização
        # tirar a autorização fecha de novo
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "grupo", "alvo_id": grupo, "escopos": []},
        )
        with pytest.raises(ErroFerramenta):
            await consultar_cliente(pedido, ctx(uid, colega["id"], grupo))
        lista = (await http.get(f"{PREFIXO}/autorizacoes", headers=auth)).json()
        assert [a["alvo_id"] for a in lista] == [bot["id"]]


# ------------------------------------------------------------------ sugestões de melhoria


def _gerador(propostas: list[SugestaoProposta]):
    async def gerar(
        bot: BotParaAnalise, itens: list[ConhecimentoEmpresa]
    ) -> list[SugestaoProposta]:
        return list(propostas)

    return gerar


async def _item_de_conhecimento(m: Mundo, uid: UUID) -> None:
    async with m.fabrica() as sessao:
        sessao.add(
            ConhecimentoEmpresa(
                usuario_id=uid, categoria="politica", chave=f"politica:troca:{uuid4()}",
                titulo="Prazo de troca", conteudo="A troca é em até 7 dias.", ocorrencias=4,
                origens=[{"papel": "funcionario", "contato_id": str(uuid4())}],
                estado="aprovado",
            )
        )  # fmt: skip
        await sessao.commit()


async def _instrucoes(m: Mundo, bot_id: str) -> str:
    async with m.fabrica() as sessao:
        return (await sessao.get(Agente, UUID(bot_id))).instrucoes


async def test_sugestoes_aplicar_editar_descartar_e_desfazer(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "sug")
        auth_b, _ = await _conta(mundo, http, "sug-b")
        bot = await _bot(http, auth, "Lume")
        livre = await _bot(http, auth, "Sem acesso")
        await _item_de_conhecimento(mundo, uid)
        # só bot autorizado entra na análise
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "agente", "alvo_id": bot["id"], "escopos": ["conhecimento"]},
        )
        proposta = SugestaoProposta(
            "instrucoes", "Prazo de troca", "Apareceu 4x", "O prazo de troca é 7 dias.", None, (0,)
        )
        redis = Redis.from_url(mundo.url_redis)
        try:
            assert (
                await sugestoes.gerar_sugestoes(
                    mundo.fabrica, redis, uid, gerador=_gerador([proposta])
                )
                == 1
            )
            # repetir a rodada não duplica a sugestão pendente
            assert (
                await sugestoes.gerar_sugestoes(
                    mundo.fabrica, redis, uid, gerador=_gerador([proposta])
                )
                == 0
            )
        finally:
            await redis.aclose()
        lista = (
            await http.get(f"{PREFIXO}/sugestoes", headers=auth, params={"status": "pendente"})
        ).json()
        assert len(lista) == 1 and lista[0]["agente_id"] == bot["id"]
        assert await _instrucoes(mundo, bot["id"]) == ""  # nada mudou antes do Aplicar
        assert await _instrucoes(mundo, livre["id"]) == ""

        # o cartão "Precisa de você": Aplicar · Descartar, ligado ao bot
        atencao = (await http.get("/v1/atencao", headers=auth)).json()
        cartao = next(p for p in atencao if p["id"] == lista[0]["aprovacao_id"])
        assert cartao["titulo"] == "Sugestão de melhoria" and cartao["agente_id"] == bot["id"]
        assert [o["rotulo"] for o in cartao["opcoes"]] == ["Aplicar", "Descartar"]
        assert "7 dias" in cartao["resumo"]
        agente = next(
            a for a in (await http.get("/v1/agentes", headers=auth)).json() if a["id"] == bot["id"]
        )
        assert agente["estado"] == "precisa_de_voce"

        # outra conta não vê nem decide
        assert (await http.get(f"{PREFIXO}/sugestoes", headers=auth_b)).json() == []
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{lista[0]['id']}/aplicar", headers=auth_b)
        ).status_code == 404
        r = await http.post(
            f"/v1/aprovacoes/{cartao['id']}/decidir", headers=auth_b, json={"decisao": "permitir"}
        )
        assert r.status_code == 404
        assert await _instrucoes(mundo, bot["id"]) == ""

        # Editar o texto e depois Aplicar (aqui pelo cartão, com "sempre permitir" ignorado)
        r = await http.patch(
            f"{PREFIXO}/sugestoes/{lista[0]['id']}",
            headers=auth,
            json={"texto": "O prazo de troca é 7 dias corridos. CPF 529.982.247-25"},
        )
        assert r.status_code == 200 and "529.982" not in r.json()["texto"]
        r = await http.post(
            f"/v1/aprovacoes/{cartao['id']}/decidir",
            headers=auth,
            json={"decisao": "sempre_permitir"},
        )
        assert r.status_code == 422, r.text  # instruções só aceitam "uma vez" (decisoes.py)
        r = await http.post(
            f"/v1/aprovacoes/{cartao['id']}/decidir",
            headers=auth,
            json={"decisao": "permitir_uma_vez"},
        )
        assert r.status_code == 204, r.text
        depois = await _instrucoes(mundo, bot["id"])
        assert "7 dias corridos" in depois
        async with mundo.fabrica() as sessao:
            assert (
                await sessao.scalars(select(RegraPermissao).where(RegraPermissao.usuario_id == uid))
            ).all() == []
            s = await sessao.get(SugestaoMelhoria, UUID(lista[0]["id"]))
            assert s.status == "aplicada" and s.versao_anterior == {"instrucoes": ""}
            assert (await sessao.get(Aprovacao, UUID(cartao["id"]))).status.value == "permitida"
        assert await _instrucoes(mundo, livre["id"]) == ""
        assert (await http.get("/v1/atencao", headers=auth)).json() == []
        # aplicar de novo: 409
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{lista[0]['id']}/aplicar", headers=auth)
        ).status_code == 409

        # desfazer volta à versão anterior
        r = await http.post(f"{PREFIXO}/sugestoes/{lista[0]['id']}/desfazer", headers=auth)
        assert r.status_code == 200 and r.json()["status"] == "desfeita"
        assert await _instrucoes(mundo, bot["id"]) == ""
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{lista[0]['id']}/desfazer", headers=auth)
        ).status_code == 409

        # nova sugestão: descartar não muda nada; o cartão fecha como negado
        nova = SugestaoProposta(
            "instrucoes", "Entrega", "3x", "A entrega leva 3 dias úteis.", None, ()
        )
        redis = Redis.from_url(mundo.url_redis)
        try:
            assert (
                await sugestoes.gerar_sugestoes(mundo.fabrica, redis, uid, gerador=_gerador([nova]))
                == 1
            )
        finally:
            await redis.aclose()
        pend = (
            await http.get(f"{PREFIXO}/sugestoes", headers=auth, params={"status": "pendente"})
        ).json()[0]
        r = await http.post(
            f"/v1/aprovacoes/{pend['aprovacao_id']}/decidir",
            headers=auth,
            json={"decisao": "negar"},
        )
        assert r.status_code == 204
        assert await _instrucoes(mundo, bot["id"]) == ""
        async with mundo.fabrica() as sessao:
            assert (await sessao.get(SugestaoMelhoria, UUID(pend["id"]))).status == "descartada"

        # mais uma, aplicada pela rota; se o bot mudou depois, desfazer recusa e preserva a mudança
        outra = SugestaoProposta(
            "instrucoes", "Horário", "2x", "Atendemos das 9h às 18h.", None, ()
        )
        redis = Redis.from_url(mundo.url_redis)
        try:
            await sugestoes.gerar_sugestoes(mundo.fabrica, redis, uid, gerador=_gerador([outra]))
        finally:
            await redis.aclose()
        p3 = (
            await http.get(f"{PREFIXO}/sugestoes", headers=auth, params={"status": "pendente"})
        ).json()[0]
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{p3['id']}/aplicar", headers=auth)
        ).status_code == 200
        async with mundo.fabrica() as sessao:
            bot_db = await sessao.get(Agente, UUID(bot["id"]))
            bot_db.instrucoes += "\n\nMudança do usuário."
            await sessao.commit()
        r = await http.post(f"{PREFIXO}/sugestoes/{p3['id']}/desfazer", headers=auth)
        assert r.status_code == 409 and "mudaram" in r.json()["detail"]
        assert "Mudança do usuário." in await _instrucoes(mundo, bot["id"])
        # eventos para o app
        eventos = [d for n, d in await _eventos(mundo, uid) if n == "conhecimento.atualizado"]
        assert {"sugestoes", "aplicacao"} <= {e["motivo"] for e in eventos}


async def test_sugestao_de_habilidade_cria_e_desfaz(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "hab")
        bot = await _bot(http, auth, "Lume")
        await _item_de_conhecimento(mundo, uid)
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "agente", "alvo_id": bot["id"], "escopos": ["conhecimento"]},
        )
        proposta = SugestaoProposta(
            "habilidade",
            "Responder sobre troca",
            "4x",
            "1. Confirme o pedido.\n2. Informe o prazo de 7 dias.",
            "Troca de produtos",
            (),
        )
        redis = Redis.from_url(mundo.url_redis)
        try:
            assert (
                await sugestoes.gerar_sugestoes(
                    mundo.fabrica, redis, uid, gerador=_gerador([proposta])
                )
                == 1
            )
        finally:
            await redis.aclose()
        s = (await http.get(f"{PREFIXO}/sugestoes", headers=auth)).json()[0]
        async with mundo.fabrica() as sessao:
            assert (
                await sessao.scalars(select(Habilidade).where(Habilidade.usuario_id == uid))
            ).all() == []
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{s['id']}/aplicar", headers=auth)
        ).status_code == 200
        async with mundo.fabrica() as sessao:
            hab = (
                await sessao.scalars(select(Habilidade).where(Habilidade.usuario_id == uid))
            ).one()
            assert hab.nome == "Troca de produtos" and "prazo de 7 dias" in hab.conteudo
            assert hab.origem == "aprendizado"
        assert (
            await http.post(f"{PREFIXO}/sugestoes/{s['id']}/desfazer", headers=auth)
        ).status_code == 200
        async with mundo.fabrica() as sessao:
            assert (
                await sessao.scalars(select(Habilidade).where(Habilidade.usuario_id == uid))
            ).all() == []


async def test_analise_periodica_so_para_quem_tem_bot_autorizado_e_intervalo_vencido(
    mundo: Mundo,
) -> None:
    from workers.canais_empresa import usuarios_para_analisar

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "per")
        bot = await _bot(http, auth, "Lume")
        await _item_de_conhecimento(mundo, uid)
        async with mundo.fabrica() as sessao:
            assert uid not in await usuarios_para_analisar(sessao)  # ninguém autorizado
        await http.put(
            f"{PREFIXO}/autorizacoes",
            headers=auth,
            json={"alvo_tipo": "agente", "alvo_id": bot["id"], "escopos": ["conhecimento"]},
        )
        async with mundo.fabrica() as sessao:
            assert uid in await usuarios_para_analisar(sessao)
        redis = Redis.from_url(mundo.url_redis)
        try:
            await sugestoes.gerar_sugestoes(mundo.fabrica, redis, uid, gerador=_gerador([]))
        finally:
            await redis.aclose()
        async with mundo.fabrica() as sessao:  # acabou de rodar: só daqui a 7 dias
            assert uid not in await usuarios_para_analisar(sessao)
            # passados 8 dias, sem conhecimento novo continua sem rodar (nada a analisar)
            assert uid not in await usuarios_para_analisar(
                sessao, datetime.now(UTC) + timedelta(days=8)
            )
        await _item_de_conhecimento(mundo, uid)
        async with mundo.fabrica() as sessao:
            assert uid in await usuarios_para_analisar(
                sessao, datetime.now(UTC) + timedelta(days=8)
            )
        await http.put(
            f"{PREFIXO}/preferencias", headers=auth, json={"sugestoes_intervalo_dias": 0}
        )
        async with mundo.fabrica() as sessao:  # 0 = desligado
            assert uid not in await usuarios_para_analisar(
                sessao, datetime.now(UTC) + timedelta(days=30)
            )


# ------------------------------------------------------------------ job do worker, ponta a ponta


async def test_job_do_worker_resume_com_o_modelo_falso(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workers.canais_empresa import processar_canais_empresa

    def responder(req: httpx.Request) -> httpx.Response:
        funcionario = b"UFUNC1" in req.content
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user": {
                    "team_id": "T1",
                    "is_restricted": not funcionario,
                    "profile": {"real_name": "Equipe" if funcionario else "Cliente"},
                },
            },
        )

    monkeypatch.setattr(
        clientes,
        "fabrica_http",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(responder)),
    )

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as http:
        auth, uid = await _conta(mundo, http, "job")
        conexao_id, segredo = await _slack(http, auth, ["C111AAAA"], funcionarios=["UFUNC1"])
        async with mundo.fabrica() as sessao:
            conexao = await sessao.get(ConexaoCanalEmpresa, UUID(conexao_id))
            conexao.config = {**conexao.config, "team_id": "T1"}
            await sessao.commit()
        base_ts = int(time.time()) - 600
        for i, (quem, texto) in enumerate(
            [
                ("UCLI1", "Qual o prazo de troca?"),
                ("UFUNC1", "Você tem 7 dias para trocar, sem custo."),
                ("UCLI1", "Preciso do pedido até dia 20"),
                ("UFUNC1", "Prometo enviar amanhã cedo."),
            ]
        ):
            r = await _post_slack(
                http,
                conexao_id,
                segredo,
                _evento_slack("C111AAAA", quem, texto, f"{base_ts + i}.000100"),
            )
            assert r.status_code == 200
        redis = Redis.from_url(mundo.url_redis)
        try:
            ctx = {"sessoes": mundo.fabrica, "redis_eventos": redis}
            assert await processar_canais_empresa(ctx, str(uid)) == 4
            assert await processar_canais_empresa(ctx, str(uid)) == 0
        finally:
            await redis.aclose()
        clientes_ = (await http.get(f"{PREFIXO}/clientes", headers=auth)).json()
        assert len(clientes_) == 1  # o funcionário não vira cliente
        ficha = (await http.get(f"{PREFIXO}/clientes/{clientes_[0]['id']}", headers=auth)).json()
        assert {f["tipo"] for f in ficha["fatos"]} >= {"prazo", "promessa"}
        assert all(
            f["origem_link"].startswith("https://acme.slack.com/archives/C111AAAA/p")
            for f in ficha["fatos"]
        )
        faq = (
            await http.get(f"{PREFIXO}/conhecimento", headers=auth, params={"categoria": "faq"})
        ).json()
        assert faq and "7 dias" in faq[0]["conteudo"]
        funcionarios = (
            await http.get(f"{PREFIXO}/clientes", headers=auth, params={"papel": "funcionario"})
        ).json()
        assert len(funcionarios) == 1
