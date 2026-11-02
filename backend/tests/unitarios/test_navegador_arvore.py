"""Navegador por árvore de acessibilidade (``app/navegador/arvore``), adaptado do agent-desktop
(docs/referencias/agent-desktop.md).

A primeira parte testa as regras em Python puro. A segunda abre um Chromium de verdade e só roda
onde o Playwright e o navegador estão instalados (senão pula).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.ferramentas.registro import esquemas_das_proximas_fases
from app.ferramentas.rotulos import rotulo_do_passo
from app.navegador.arvore import (
    ESQUEMAS,
    Codigo,
    CursorAgente,
    Entrega,
    ErroNavegador,
    NavegadorArvore,
    Politica,
    Repetir,
    Resposta,
    para_modelo,
)
from app.navegador.arvore.acionabilidade import Exigencia, Status, avaliar, prazo_para
from app.navegador.arvore.ferramentas import NavegadorAcao, NavegadorLote
from app.navegador.arvore.identidade import Candidato, escolher
from app.navegador.arvore.motor import Seletor, normalizar_tecla
from app.navegador.arvore.rastro import Rastro, redigir_argumentos
from app.navegador.arvore.refs import ArmazemLeituras, EntradaRef, IdNativo, ler_ref
from app.navegador.arvore.resposta import Disposicao, repetir_de
from app.revisor.politica import SEGURAS_SEM_SUPERVISAO, politica_da_ferramenta
from app.revisor.politica import Politica as PoliticaRevisor

# ---------- envelope ----------


def test_so_o_que_nao_chegou_pode_ser_repetido() -> None:
    assert repetir_de(Entrega.NAO_ENTREGUE) is Repetir.SEGURO
    for entrega in (Entrega.INCERTA, Entrega.ENTREGUE_SEM_CONFIRMAR, Entrega.ENTREGUE_CONFIRMADA):
        assert repetir_de(entrega) is Repetir.INSEGURO
    assert repetir_de(Entrega.DESCONHECIDA) is Repetir.DESCONHECIDO
    assert Disposicao(Entrega.INCERTA).para_json() == {"entrega": "incerta", "repetir": "inseguro"}


def test_recuperacao_so_aparece_quando_repetir_e_seguro() -> None:
    seguro = ErroNavegador(Codigo.REF_VELHA, "sumiu").para_json()
    assert seguro["recuperacao"] == {"estrategia": "nova_leitura_e_repetir"}
    assert seguro["entrega"] == {"entrega": "nao_entregue", "repetir": "seguro"}
    inseguro = ErroNavegador(Codigo.PRAZO_ESGOTADO, "x", entrega=Entrega.INCERTA).para_json()
    assert "recuperacao" not in inseguro
    assert "sugestao" in inseguro
    prazo = ErroNavegador(Codigo.PRAZO_ESGOTADO, "x").para_json()
    assert prazo["recuperacao"]["esperar_ms"] == 1_000


def test_resposta_para_modelo_mostra_entrega_e_codigo() -> None:
    texto = para_modelo(Resposta.falha("agir", ErroNavegador(Codigo.ALVO_AMBIGUO, "dois")))
    assert texto.startswith("ERRO ALVO_AMBIGUO: dois")
    assert "repetir: seguro" in texto


# ---------- refs ----------


def test_ref_precisa_ser_qualificada() -> None:
    lida = ler_ref("@s4k9x2m1:e7")
    assert (lida.id_leitura, lida.numero, lida.texto) == ("s4k9x2m1", 7, "@s4k9x2m1:e7")
    assert ler_ref("s4k9x2m1:e7").numero == 7
    for ruim in ("@e7", "e7"):
        with pytest.raises(ErroNavegador) as erro:
            ler_ref(ruim)
        assert erro.value.codigo is Codigo.ARGUMENTOS_INVALIDOS
        assert "sem a leitura" in erro.value.mensagem
    with pytest.raises(ErroNavegador):
        ler_ref("@s4k9:e1")


def test_leituras_expiram_e_ref_inexistente_e_velha() -> None:
    armazem = ArmazemLeituras(limite=2)
    primeira = armazem.nova(url="https://a.com", completa=True)
    armazem.registrar(primeira, [EntradaRef(numero=1, papel="button", nome="Ok")])
    assert armazem.resolver(f"@{primeira.id}:e1")[1].nome == "Ok"
    with pytest.raises(ErroNavegador) as erro:
        armazem.resolver(f"@{primeira.id}:e2")
    assert erro.value.codigo is Codigo.REF_VELHA
    armazem.nova(url="", completa=True)
    armazem.nova(url="", completa=True)
    with pytest.raises(ErroNavegador) as erro:
        armazem.obter(primeira.id)
    assert erro.value.codigo is Codigo.LEITURA_NAO_ENCONTRADA


def test_perfurar_troca_so_as_refs_daquela_raiz() -> None:
    armazem = ArmazemLeituras()
    leitura = armazem.nova(url="", completa=True)
    armazem.registrar(
        leitura,
        [EntradaRef(numero=1, papel="group"), EntradaRef(numero=2, papel="group")],
    )
    leitura.perfurar(1, [EntradaRef(numero=3, papel="button", raiz=1)])
    leitura.perfurar(2, [EntradaRef(numero=4, papel="link", raiz=2)])
    leitura.perfurar(1, [EntradaRef(numero=5, papel="button", raiz=1)])
    assert sorted(leitura.refs) == [1, 2, 4, 5]
    assert leitura.proximo_numero == 6


def test_entrada_le_o_json_da_pagina() -> None:
    entrada = EntradaRef.do_json(
        {
            "numero": 3,
            "papel": "textbox",
            "nome": "E-mail",
            "id_nativo": {"tipo": "name", "valor": "email"},
            "limites": [1, 2, 3, 4],
            "acoes": ["editar", "focar"],
            "senha": False,
        }
    )
    assert entrada.id_nativo == IdNativo("name", "email")
    assert entrada.limites == (1.0, 2.0, 3.0, 4.0)
    assert entrada.evidencia()["id_nativo"] == {"tipo": "name", "valor": "email"}


# ---------- identidade ----------


def _c(indice: int, camada: str, papel: str = "button", nome: str | None = "Salvar", **extra: Any):
    return Candidato(indice=indice, camada=camada, papel=papel, nome=nome, **extra)


def test_memoria_basta_o_papel_mesmo_com_texto_novo() -> None:
    entrada = EntradaRef(numero=1, papel="button", nome="Seguir")
    escolha = escolher(entrada, "@sabcdefg:e1", {"memoria": [_c(0, "memoria", nome="Seguindo")]})
    assert escolha.camada == "memoria"


def test_id_diferente_recusa_mesmo_com_nome_igual() -> None:
    entrada = EntradaRef(numero=1, papel="button", nome="Salvar", id_nativo=IdNativo("id", "a"))
    camadas = {"caminho": [_c(0, "caminho", id_nativo={"tipo": "id", "valor": "b"})]}
    with pytest.raises(ErroNavegador) as erro:
        escolher(entrada, "@sabcdefg:e1", camadas)
    assert erro.value.codigo is Codigo.REF_VELHA


def test_dois_candidatos_confirmados_e_ambiguo() -> None:
    entrada = EntradaRef(numero=1, papel="button", nome="Apagar")
    camadas = {"busca": [_c(0, "busca", nome="Apagar"), _c(1, "busca", nome="apagar ")]}
    with pytest.raises(ErroNavegador) as erro:
        escolher(entrada, "@sabcdefg:e1", camadas)
    assert erro.value.codigo is Codigo.ALVO_AMBIGUO
    assert len(erro.value.detalhes["candidatos"]) == 2


def test_elemento_removido_so_volta_pelo_id() -> None:
    entrada = EntradaRef(numero=1, papel="button", nome="Apagar")
    camadas = {"caminho": [_c(0, "caminho", nome="Apagar")]}
    assert escolher(entrada, "@sabcdefg:e1", camadas, "desconhecido").camada == "caminho"
    with pytest.raises(ErroNavegador) as erro:
        escolher(entrada, "@sabcdefg:e1", camadas, "removido")
    assert erro.value.detalhes["motivo"] == "elemento_removido"
    com_id = EntradaRef(numero=1, papel="button", nome="Apagar", id_nativo=IdNativo("id", "x"))
    camadas_id = {"id": [_c(0, "id", nome="Apagar", id_nativo={"tipo": "id", "valor": "x"})]}
    assert escolher(com_id, "@sabcdefg:e1", camadas_id, "removido").camada == "id"


def test_sem_identidade_so_resolve_pela_posicao_unica() -> None:
    entrada = EntradaRef(numero=1, papel="generic", nome=None, limites=(10, 10, 50, 20))
    mesma = _c(0, "busca", papel="generic", nome=None, limites=(10.5, 10, 50, 20))
    outra = _c(1, "busca", papel="generic", nome=None, limites=(10, 90, 50, 20))
    assert escolher(entrada, "@sabcdefg:e1", {"busca": [mesma, outra]}).candidato.indice == 0
    with pytest.raises(ErroNavegador):
        escolher(entrada, "@sabcdefg:e1", {"busca": [outra]})


# ---------- acionabilidade ----------


def _evidencia(**extra: Any) -> dict[str, Any]:
    base = {
        "conectado": True,
        "papel": "button",
        "visivel": True,
        "limites": [0, 0, 10, 10],
        "limites_antes": [0, 0, 10, 10],
        "desabilitado": False,
        "editavel": False,
        "acoes": ["clicar", "focar"],
        "na_tela": True,
        "pontos": [{"x": 5, "y": 5, "acerta": True}],
    }
    return {**base, **extra}


def test_avaliar_pronto_e_ponto_do_clique() -> None:
    rel = avaliar(_evidencia(), Exigencia("clicar", ponteiro=True), Politica.FISICA)
    assert rel.pronto and rel.ponto == (5, 5)


def test_avaliar_tapado_diz_quem_tapa() -> None:
    oclusor = {"papel": "dialog", "nome": "Cookies", "limites": [0, 0, 100, 100]}
    ev = _evidencia(pontos=[{"x": 5, "y": 5, "acerta": False, "oclusor": oclusor}])
    rel = avaliar(ev, Exigencia("clicar", ponteiro=True), Politica.FISICA)
    falha = rel.primeira_falha()
    assert falha is not None and falha.nome == "recebe_eventos" and falha.oclusor == oclusor


def test_avaliar_falha_aberto_sem_evidencia_de_ponto() -> None:
    rel = avaliar(_evidencia(pontos=[]), Exigencia("clicar", ponteiro=True), Politica.FISICA)
    assert rel.pronto
    assert any(c.status is Status.DESCONHECIDO for c in rel.checagens)


def test_avaliar_falhas_definitivas() -> None:
    rel = avaliar(_evidencia(), Exigencia("editar", edicao=True), Politica.FISICA)
    assert rel.falha_definitiva is not None and rel.falha_definitiva.nome == "suporta_acao"
    so_fisica = Exigencia(None, ponteiro=True, so_fisica=True)
    rel = avaliar(_evidencia(), so_fisica, Politica.SEMANTICA)
    assert rel.falha_definitiva is not None and rel.falha_definitiva.nome == "politica"


def test_desabilitado_e_instavel_sao_passageiros() -> None:
    ev = _evidencia(desabilitado=True, limites_antes=[0, 5, 10, 10])
    rel = avaliar(ev, Exigencia("clicar", ponteiro=True), Politica.FISICA)
    assert not rel.pronto and rel.falha_definitiva is None


def test_prazo_de_digitar_cresce_com_o_texto() -> None:
    assert prazo_para("clicar", None, None) == 5_000
    assert prazo_para("digitar", "abcd", None) == 5_120
    assert prazo_para("digitar", "abcd", 0) == 0


# ---------- teclas, seletores, rastro, esquemas ----------


def test_teclas() -> None:
    assert normalizar_tecla("ctrl+a") == "Control+a"
    assert normalizar_tecla("enter") == "Enter"
    assert normalizar_tecla("shift+Tab") == "Shift+Tab"
    for ruim in ("ctrl+", "hiper+a", "Sleep"):
        with pytest.raises(ErroNavegador):
            normalizar_tecla(ruim)


def test_seletor() -> None:
    assert Seletor.ler("button:Salvar") == Seletor("button", "Salvar")
    assert Seletor.ler(":Salvo!") == Seletor(None, "Salvo!")
    assert Seletor.ler("Heading") == Seletor("heading", None)
    with pytest.raises(ErroNavegador):
        Seletor.ler(":")


def test_rastro_nunca_guarda_senha() -> None:
    assert redigir_argumentos({"texto": "minhasenha"}, senha=True) == {"texto": "[oculto]"}
    assert "sk-" not in redigir_argumentos({"texto": "chave sk-abcdefghijkl"})["texto"]
    rastro = Rastro()
    rastro.anotar("agir", {"texto": "x"}, ok=True, codigo=None, entrega="entregue", inicio=0.0)
    assert rastro.jsonl().count("\n") == 1


def test_esquemas_recusam_campos_desconhecidos_e_ref_solta() -> None:
    with pytest.raises(ValueError):
        NavegadorAcao(ref="@e1", acao="clicar")
    with pytest.raises(ValueError):
        NavegadorAcao(ref="@sabcdefg:e1", acao="clicar", extra=1)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        NavegadorLote(passos=[{"comando": "lote", "args": {}}])  # type: ignore[list-item]


def test_ferramentas_registradas_com_politica_e_rotulo() -> None:
    proximas = esquemas_das_proximas_fases()
    for nome in ESQUEMAS:
        assert nome in proximas
        assert rotulo_do_passo(nome, {"acao": "digitar", "texto": "segredo"})
    for nome in ("navegador_observar", "navegador_procurar", "navegador_elemento",
                 "navegador_esperar"):  # fmt: skip
        assert politica_da_ferramenta(nome) is PoliticaRevisor.LIVRE
        assert nome in SEGURAS_SEM_SUPERVISAO
    for nome in ("navegador_acao", "navegador_tecla", "navegador_lote"):
        assert politica_da_ferramenta(nome) is PoliticaRevisor.REVISOR
    assert "segredo" not in rotulo_do_passo(
        "navegador_acao", {"acao": "digitar", "texto": "segredo"}
    )


# ---------- Chromium de verdade ----------

FORMULARIO = (Path(__file__).parent / "paginas" / "navegador_arvore.html").read_text(
    encoding="utf-8"
)


def _chromium() -> str | None:
    caminho = os.environ.get("SORA_CHROMIUM") or "/opt/pw-browsers/chromium"
    return caminho if Path(caminho).exists() else None


@pytest.fixture
async def pagina() -> AsyncIterator[Any]:
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            navegador = await p.chromium.launch(executable_path=_chromium())
        except Exception as erro:
            pytest.skip(f"Chromium indisponível: {type(erro).__name__}")
        pagina = await navegador.new_page()
        await pagina.set_content(FORMULARIO)
        try:
            yield pagina
        finally:
            await navegador.close()


def _refs(arvore: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[str]]:
    achadas: dict[tuple[str, str | None], list[str]] = {}

    def andar(nos: list[dict[str, Any]]) -> None:
        for no in nos:
            if no.get("ref"):
                achadas.setdefault((no["papel"], no.get("nome")), []).append(no["ref"])
            andar(no.get("filhos") or [])

    andar(arvore)
    return achadas


async def _observar(nav: NavegadorArvore, **opcoes: Any) -> dict[tuple[str, str | None], list[str]]:
    resposta = await nav.observar(**opcoes)
    assert resposta.ok, resposta.para_json()
    return _refs(resposta.dados["arvore"])


async def test_observar_le_papeis_nomes_estados_e_esconde_senha(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    resposta = await nav.observar()
    texto = para_modelo(resposta)
    assert resposta.dados["completa"] and resposta.dados["rolagem"]["tem_mais_abaixo"]
    assert 'navigation "Principal"' in texto and 'heading "Cadastro"' in texto
    assert 'textbox "Senha"' in texto and "[senha]" in texto
    assert 'button "Enviar"' in texto and "desabilitado" in texto
    assert 'button "Na sombra"' in texto  # shadow DOM aberto
    assert "Escondido" not in texto  # <details> fechado
    refs = _refs(resposta.dados["arvore"])
    assert all(r.startswith(f"@{resposta.dados['leitura']}:e") for v in refs.values() for r in v)
    # sem -i aparece o texto solto da página
    completo = para_modelo(await nav.observar(somente_interativos=False))
    assert 'texto: "A"' in completo or "texto:" in completo


async def test_formulario_de_ponta_a_ponta(pagina: Any) -> None:
    nav = NavegadorArvore(pagina, cursor=CursorAgente("#46E8A8", "Nina"))
    refs = await _observar(nav)
    nome = refs[("textbox", "Nome")][0]

    r = await nav.agir(nome, "definir_valor", texto="Ana")
    assert r.ok and r.dados["entrega"]["entrega"] == "entregue_confirmada"
    r = await nav.agir(nome, "digitar", texto=" Silva")
    assert r.dados["estado_depois"]["valor"] == "Ana Silva"

    senha = refs[("textbox", "Senha")][0]
    r = await nav.agir(senha, "definir_valor", texto="segredo-123")
    assert r.ok and r.dados["verificacao"]["motivo"] == "campo_secreto"
    assert "segredo-123" not in r.texto()
    lido = await nav.elemento(senha, "valor")
    assert lido.dados["valor"] is None and lido.dados["senha"] is True
    assert "segredo-123" not in nav.rastro.jsonl()

    enviar = refs[("button", "Enviar")][0]
    r = await nav.agir(enviar, "clicar", prazo_ms=300)
    assert r.erro is not None and r.erro.codigo is Codigo.PRAZO_ESGOTADO
    assert r.erro.disposicao.repetir is Repetir.SEGURO

    termos = refs[("checkbox", "Aceito os termos")][0]
    r = await nav.agir(termos, "marcar")
    assert r.dados["entrega"]["entrega"] == "entregue_confirmada"
    r = await nav.agir(termos, "marcar")
    assert r.dados["ja_satisfeito"] and r.dados["entrega"]["repetir"] == "seguro"

    r = await nav.agir(refs[("combobox", "Plano")][0], "selecionar", opcao="Pro")
    assert r.dados["estado_depois"]["valor"] == "Pro"
    r = await nav.agir(refs[("combobox", "Plano")][0], "selecionar", opcao="Ouro")
    assert r.erro is not None and r.erro.detalhes["opcoes"] == ["Grátis", "Pro"]

    r = await nav.agir(refs[("button", "Mais opções")][0], "expandir")
    assert "expandido" in r.dados["estado_depois"]["estados"]

    r = await nav.agir(enviar, "clicar", esperar_por=":Enviado!")
    assert r.ok and r.dados["espera"]["contagem"] == 1
    assert await pagina.evaluate("!!document.querySelector('[data-sora-cursor]')")


async def test_ref_de_elemento_removido_nao_cai_no_vizinho(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    refs = await _observar(nav)
    apagar_b = refs[("button", "Apagar")][1]
    await pagina.evaluate(
        "lista.innerHTML = '<li><button>Apagar</button> X</li><li><button>Apagar</button> Y</li>'"
    )
    r = await nav.agir(apagar_b, "clicar", prazo_ms=200)
    assert r.erro is not None and r.erro.codigo is Codigo.REF_VELHA
    assert r.erro.detalhes["motivo"] == "elemento_removido"
    # recriado com o mesmo id do desenvolvedor: volta
    await pagina.evaluate("const b = document.getElementById('nome'); b.replaceWith(b.cloneNode())")
    assert (await nav.elemento(refs[("textbox", "Nome")][0], "papel")).ok


async def test_mesma_ref_depois_de_recarregar_e_dois_iguais_e_ambiguo(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    refs = await _observar(nav)
    apagar_a = refs[("button", "Apagar")][0]
    # mesmo documento, objeto removido: nem o caminho salva (cairia no vizinho)
    await pagina.set_content(FORMULARIO)
    r = await nav.elemento(apagar_a, "titulo")
    assert r.erro is not None and r.erro.detalhes["motivo"] == "elemento_removido"
    # página recarregada (window novo): sem memória, o caminho e o nome conferem
    await pagina.evaluate("window.__soraArvore = undefined")
    assert (await nav.elemento(apagar_a, "titulo")).ok
    await pagina.evaluate(
        "lista.innerHTML = '<li><p><button>Apagar</button></p></li><li><p><button>Apagar</button>"
        "</p></li>'"
    )
    await pagina.evaluate("window.__soraArvore = undefined")
    r = await nav.elemento(apagar_a, "titulo")
    assert r.erro is not None and r.erro.codigo is Codigo.ALVO_AMBIGUO


async def test_clique_tapado_diz_quem_tapa_e_nao_clica(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    refs = await _observar(nav)
    await pagina.evaluate("capa.style.display = 'block'")
    r = await nav.agir(refs[("button", "Apagar")][0], "clicar", prazo_ms=300)
    assert r.erro is not None and r.erro.codigo is Codigo.ACAO_FALHOU
    assert r.erro.disposicao.entrega is Entrega.NAO_ENTREGUE
    assert "Aviso de cookies" in r.texto()
    achado = await nav.procurar(papel="button", nome="aceitar", exato=True)
    assert achado.dados["total"] == 1
    assert (await nav.agir(achado.dados["correspondencias"][0]["ref"], "clicar")).ok
    assert (await nav.agir(refs[("button", "Apagar")][0], "clicar")).ok


async def test_combobox_aria_sombra_e_rolagem(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    refs = await _observar(nav)
    r = await nav.agir(refs[("combobox", "Cidade")][0], "selecionar", opcao="Recife")
    assert r.ok and r.dados["entrega"]["entrega"] == "entregue_confirmada"
    r = await nav.agir(refs[("button", "Na sombra")][0], "clicar", esperar_por=":sombra!")
    assert r.ok
    r = await nav.agir(refs[("button", "Lá embaixo")][0], "clicar", esperar_por=":fim!")
    assert r.ok and r.dados["rolagem_preparatoria"] is True
    for _ in range(5):
        r = await nav.agir(None, "rolar", direcao="cima", quantidade=20)
        assert r.ok
        if r.dados.get("ja_no_limite"):
            break
    assert r.dados["ja_no_limite"] and r.dados["entrega"]["repetir"] == "seguro"
    assert r.dados["posicao"] == [0, 0]


async def test_esqueleto_perfurar_e_leitura_parcial(pagina: Any) -> None:
    nav = NavegadorArvore(pagina)
    esqueleto = await nav.observar(esqueleto=True, profundidade_max=1)
    texto = para_modelo(esqueleto)
    assert "dentro; perfure com raiz=" in texto
    form = next(no for no in esqueleto.dados["arvore"] if no.get("papel") == "form")
    assert form["filhos_cortados"] >= 5 and "filhos" not in form
    regiao = await nav.observar(raiz=form["ref"])
    assert regiao.ok and regiao.dados["raiz"] == form["ref"]
    assert ("textbox", "Nome") in _refs(regiao.dados["arvore"])
    # perfurar de novo troca só as refs daquela região; as outras continuam valendo
    de_novo = await nav.observar(raiz=form["ref"])
    leitura = nav.leituras.obter(esqueleto.dados["leitura"])
    perfuradas = [e for e in leitura.refs.values() if e.raiz is not None]
    assert len(perfuradas) == de_novo.dados["refs"]
    nome_novo = _refs(de_novo.dados["arvore"])[("textbox", "Nome")][0]
    assert (await nav.agir(nome_novo, "definir_valor", texto="Caio")).ok
    nav_ref = next(no["ref"] for no in esqueleto.dados["arvore"] if no.get("papel") == "navigation")
    assert (await nav.elemento(nav_ref, "papel")).dados["valor"] == "navigation"
    parcial = await nav.observar(max_nos=3)
    assert parcial.ok and parcial.dados["parcial"] and not parcial.dados["completa"]
    ref_parcial = next(iter(_refs(parcial.dados["arvore"]).values()))[0]
    r = await nav.observar(raiz=ref_parcial)
    assert r.erro is not None and r.erro.codigo is Codigo.PRAZO_ESGOTADO


async def test_politica_semantica_teclas_lote_esperas_e_dialogo(pagina: Any) -> None:
    nav = NavegadorArvore(pagina, politica=Politica.SEMANTICA)
    refs = await _observar(nav)
    r = await nav.agir(refs[("button", "Apagar")][0], "pairar")
    assert r.erro is not None and r.erro.codigo is Codigo.POLITICA_NEGADA
    r = await nav.agir(refs[("button", "Apagar")][0], "clicar")
    assert r.ok and r.dados["passos"][-1]["mecanismo"] == "semantico"
    assert (await nav.tecla("Enter")).erro.codigo is Codigo.POLITICA_NEGADA  # type: ignore[union-attr]

    nav.politica = Politica.FISICA
    nome = refs[("textbox", "Nome")][0]
    lote = await nav.lote(
        [
            {"comando": "agir", "args": {"ref": nome, "acao": "definir_valor", "texto": "Bia"}},
            {"comando": "elemento", "args": {"ref": nome, "propriedade": "focado"}},
            {"comando": "tecla", "args": {"tecla": "ctrl+a"}},
            {"comando": "esperar", "args": {"ref": "@sabcdefg:e1"}},
            {"comando": "esperar", "args": {"ms": 1}},
        ]
    )
    resultados = lote.dados["resultados"]
    assert [r.get("ok") for r in resultados[:4]] == [True, True, True, False]
    assert resultados[4]["status"] == "nao_iniciado" and lote.dados["falhas"] == 1
    assert resultados[3]["erro"]["codigo"] == "LEITURA_NAO_ENCONTRADA"

    r = await nav.esperar(texto="Nunca aparece", prazo_ms=200)
    assert r.erro is not None and r.erro.detalhes["tipo"] == "espera"
    r = await nav.esperar(ref=nome, predicado="valor", valor="Bia", prazo_ms=1_000)
    assert r.ok
    r = await nav.esperar(ms=1, texto="x")
    assert r.erro is not None and r.erro.codigo is Codigo.ARGUMENTOS_INVALIDOS

    await pagina.evaluate("document.getElementById('fim').onclick = () => alert('Pronto')")
    refs = await _observar(nav)
    r = await nav.agir(refs[("button", "Lá embaixo")][0], "clicar")
    assert r.dados["dialogos_nativos"] == [{"tipo": "alert", "mensagem": "Pronto"}]


async def test_servico_usa_a_aba_do_agente_e_respeita_o_usuario(pagina: Any) -> None:
    from app.ferramentas.base import ContextoFerramenta
    from app.navegador.abas import GerenteAbas
    from app.navegador.arvore import ServicoArvore
    from app.navegador.arvore.ferramentas import NavegadorObservar
    from app.navegador.perfis import EscolhaPerfil, TipoPerfil

    class MotorDeTeste:
        async def abrir_pagina(self, aba: Any) -> None: ...
        async def navegar(self, aba: Any, url: str) -> tuple[str, str]:
            return url, ""

        async def descarregar(self, aba: Any) -> None: ...
        async def fechar(self, aba: Any) -> None: ...
        async def capturar(self, aba: Any) -> bytes:
            return b""

        async def limpar_particao(self, particao_: str) -> None: ...

    gerente = GerenteAbas(MotorDeTeste())
    usuario, agente = uuid4(), uuid4()
    contexto = ContextoFerramenta(usuario_id=usuario, agente_id=agente, conversa_id=uuid4())
    servico = ServicoArvore(gerente, lambda aba: pagina)

    sem_aba = await servico.executar("navegador_observar", NavegadorObservar(), contexto)
    assert sem_aba.erro is not None and sem_aba.erro.codigo is Codigo.ABA_NAO_ENCONTRADA

    aba = await gerente.abrir(
        usuario_id=usuario, agente_id=agente, escolha=EscolhaPerfil(TipoPerfil.COMPARTILHADO)
    )
    texto = await servico.executar_para_modelo("navegador_observar", NavegadorObservar(), contexto)
    assert texto.startswith("Página: Cadastro")
    gerente.assumir(aba.id, usuario)
    r = await servico.executar("navegador_observar", NavegadorObservar(aba_id=aba.id), contexto)
    assert r.erro is not None and r.erro.codigo is Codigo.POLITICA_NEGADA


# ---------- teste real com a Groq (2026-11-02): espera de exemplo e leitura antes do load


def test_seletor_da_acao_ignora_valor_de_exemplo_e_aceita_texto_solto() -> None:
    for exemplo in (None, "", "texto", "Texto", "papel:texto", ":texto", "'texto'", "none", "-"):
        assert Seletor.da_acao(exemplo) is None, exemplo
    assert Seletor.da_acao("Enviado!") == Seletor(None, "Enviado!")
    assert Seletor.da_acao("Total: 3") == Seletor(None, "Total: 3")
    assert Seletor.da_acao("texto:Salvo") == Seletor(None, "Salvo")
    assert Seletor.da_acao("button:Salvar") == Seletor("button", "Salvar")
    assert Seletor.da_acao("botão:texto") == Seletor("button", None)
    assert Seletor.da_acao("dialog") == Seletor("dialog", None)
    assert Seletor.da_acao(":Salvo!") == Seletor(None, "Salvo!")


SITE = "http://sora.test"
PAGINA_A = """<!doctype html><html><head><title>A</title></head><body>
<h1>Página inicial</h1>
<button onclick="document.body.insertAdjacentHTML('beforeend','<p>Pronto agora</p>')">Gerar</button>
<a href="/b">Ir para B</a>
<div style="height:3000px"></div><p>fim</p>
</body></html>"""
PAGINA_B = "<!doctype html><title>B</title><h1>Página B</h1>"
# o <script> lento trava o parser: o link só existe no DOM depois do load
PAGINA_LENTA = """<!doctype html><title>Lenta</title><h1>Domínios</h1>
<script src="/lento.js"></script>
<a href="/b">Example domains</a>"""


@pytest.fixture
async def site(pagina: Any) -> Any:
    import asyncio

    async def servir(route: Any) -> None:
        caminho = route.request.url.removeprefix(SITE)
        if caminho == "/lento.js":
            await asyncio.sleep(1.5)
            await route.fulfill(body="void 0", content_type="application/javascript")
            return
        corpo = {"/a": PAGINA_A, "/b": PAGINA_B, "/lenta": PAGINA_LENTA}.get(caminho)
        if corpo is None:
            await route.fulfill(status=404, body="")
        else:
            await route.fulfill(body=corpo, content_type="text/html; charset=utf-8")

    await pagina.route(f"{SITE}/**", servir)
    await pagina.goto(f"{SITE}/a")
    return pagina


async def test_acao_com_espera_de_exemplo_volta_ok_rapido(site: Any) -> None:
    import time as _time

    nav = NavegadorArvore(site)
    refs = await _observar(nav)
    gerar = refs[("button", "Gerar")][0]
    inicio = _time.monotonic()
    r = await nav.agir(gerar, "clicar", esperar_por="texto")
    assert r.ok, r.para_json()
    assert _time.monotonic() - inicio < 3
    assert "espera_ignorada" in r.dados and r.dados["pagina_mudou"] is True
    inicio = _time.monotonic()
    r = await nav.agir(None, "rolar", direcao="baixo", quantidade=5, esperar_por="papel:texto")
    assert r.ok and _time.monotonic() - inicio < 3, r.para_json()
    # texto solto (sem 'papel:') é texto, não papel
    r = await nav.agir(gerar, "clicar", esperar_por="Pronto agora")
    assert r.ok and r.dados["espera"]["contagem"] >= 1, r.para_json()


async def test_clique_que_navega_confirma_pela_url(site: Any) -> None:
    nav = NavegadorArvore(site)
    refs = await _observar(nav)
    r = await nav.agir(refs[("link", "Ir para B")][0], "clicar")
    assert r.ok and r.dados["navegou"]["para"] == f"{SITE}/b"
    assert r.dados["entrega"]["entrega"] == "entregue_confirmada"
    assert r.dados["confirmado_por"] == "navegou"


async def test_observar_e_procurar_esperam_a_pagina_carregar(site: Any) -> None:
    nav = NavegadorArvore(site)
    await site.goto(f"{SITE}/lenta", wait_until="commit")
    achou = await nav.procurar(texto="example domains")
    assert achou.ok and achou.dados["total"] >= 1, achou.para_json()
    await site.goto(f"{SITE}/lenta", wait_until="commit")
    refs = await _observar(nav)
    assert ("link", "Example domains") in refs


async def test_procurar_ignora_acento_e_maiuscula_e_da_dica_quando_nao_acha(site: Any) -> None:
    nav = NavegadorArvore(site)
    r = await nav.procurar(texto="PAGINA inicial")
    assert r.ok and r.dados["total"] >= 1, r.para_json()
    r = await nav.procurar(texto="example")
    assert r.dados["total"] == 0 and r.dados["url"] == f"{SITE}/a" and "dica" in r.dados
    r = await nav.observar(esqueleto=True)
    assert "Esqueleto: mapa raso" in para_modelo(r)
