"""Modelo falso (§8.5): respostas prontas válidas e trava de produção."""

import json
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from app.core.config import Configuracao, obter_configuracao
from app.llm.fabrica import criar_chat_model
from app.llm.falso import (
    PAPEIS_COM_RESPOSTA_PRONTA,
    ModeloFalsoEmProducao,
    criar_modelo_falso,
    modelo_falso_ativo,
    verificar_modelo_falso_permitido,
)
from app.llm.provedores import ConfigProvedor
from app.modelos.enumeracoes import TipoProvedor
from app.orquestrador.planejador import Plano
from app.sistema1.esquemas import ModoTriagem, SaidaSistema1
from app.sistema1.saida_json import validar_saida


@pytest.mark.parametrize("ambiente", ["producao", "produção", "Production", " PROD "])
def test_producao_com_modelo_falso_ligado_levanta_erro(ambiente: str) -> None:
    with pytest.raises(ModeloFalsoEmProducao):
        verificar_modelo_falso_permitido(ambiente, True)


@pytest.mark.parametrize(
    ("ambiente", "ligado"),
    [("desenvolvimento", True), ("teste", True), ("producao", False), ("desenvolvimento", False)],
)
def test_demais_combinacoes_passam(ambiente: str, ligado: bool) -> None:
    verificar_modelo_falso_permitido(ambiente, ligado)


@pytest.fixture(autouse=True)
def _config_limpa():
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


def test_variavel_de_ambiente_liga_o_modelo_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    assert not modelo_falso_ativo()
    for valor in ("1", "true", "sim"):
        monkeypatch.setenv("SORA_MODELO_FALSO", valor)
        obter_configuracao.cache_clear()
        assert modelo_falso_ativo()
    monkeypatch.setenv("SORA_MODELO_FALSO", "0")
    obter_configuracao.cache_clear()
    assert not modelo_falso_ativo()


def test_fonte_unica_a_fabrica_enxerga_o_ligado_vindo_so_do_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Antes a fábrica lia só ``os.environ``; o ``.env`` ligava a API mas não a fábrica."""
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    env = tmp_path / ".env"
    env.write_text("SORA_MODELO_FALSO=sim" + chr(10), encoding="utf-8")
    monkeypatch.setattr("app.core.config.obter_configuracao", lambda: Configuracao(_env_file=env))
    assert modelo_falso_ativo()


def test_fabrica_recusa_o_modelo_falso_em_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    """Antes devolvia o modelo REAL em silêncio quando o worker subia sem a trava."""
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("JWT_SEGREDO", "x" * 40 + "-aleatorio-9f2c")
    obter_configuracao.cache_clear()
    with pytest.raises(ModeloFalsoEmProducao):
        criar_chat_model("groq/x", ConfigProvedor(tipo=TipoProvedor.GROQ), papel="redator")


async def test_triagem_cadeia_valida_no_esquema_do_sistema1() -> None:
    modelo = criar_modelo_falso("sistema1")
    resposta = await modelo.ainvoke([HumanMessage("Pedido: crie uma campanha para minha loja")])
    saida = validar_saida(str(resposta.content))
    assert saida.modo is ModoTriagem.CADEIA
    assert saida.especialistas


async def test_triagem_saudacao_vira_resposta_direta() -> None:
    modelo = criar_modelo_falso("sistema1")
    resposta = await modelo.ainvoke([HumanMessage("Pedido: oi, tudo bem?")])
    saida = SaidaSistema1.model_validate_json(str(resposta.content))
    assert saida.modo is ModoTriagem.DIRETO
    assert saida.dificuldade == 1
    assert saida.resposta_direta


async def test_plano_do_modelo_falso_e_aceito_pelo_esquema_do_plano() -> None:
    resposta = await criar_modelo_falso("planejador").ainvoke([HumanMessage("planeje")])
    plano = Plano.model_validate_json(str(resposta.content))
    assert [e.ordem for e in plano.etapas] == [1, 2, 3]


async def test_pesquisador_busca_e_depois_entrega_links() -> None:
    modelo = criar_modelo_falso("pesquisador")
    primeira = await modelo.ainvoke([HumanMessage("x")])
    segunda = await modelo.ainvoke([HumanMessage("x")])
    assert primeira.tool_calls[0]["name"] == "buscar_web"
    assert segunda.tool_calls[0]["name"] == "entregar"
    assert segunda.tool_calls[0]["args"]["tipo"] == "links"


async def test_verificador_aprova_e_as_respostas_se_repetem_em_ciclo() -> None:
    modelo = criar_modelo_falso("verificador")
    for _ in range(3):
        resposta = await modelo.ainvoke([HumanMessage("x")])
        assert resposta.tool_calls[0]["name"] == "veredito"
        assert resposta.tool_calls[0]["args"]["aprovado"] is True


async def test_revisor_bloqueia_por_padrao() -> None:
    resposta = await criar_modelo_falso("revisor").ainvoke([HumanMessage("x")])
    assert json.loads(str(resposta.content))["decisao"] == "BLOQUEAR"


async def test_resposta_traz_uso_de_tokens_e_ids_de_chamada_novos() -> None:
    modelo = criar_modelo_falso("redator")
    a = await modelo.ainvoke([HumanMessage("escreva")])
    b = await modelo.ainvoke([HumanMessage("escreva")])
    assert a.usage_metadata and a.usage_metadata["input_tokens"] > 0
    assert a.tool_calls[0]["id"] != b.tool_calls[0]["id"]


async def test_stream_preserva_as_chamadas_de_ferramenta() -> None:
    modelo = criar_modelo_falso("redator")
    junto = None
    async for pedaco in modelo.astream([HumanMessage("escreva")]):
        junto = pedaco if junto is None else junto + pedaco
    assert junto is not None
    assert junto.tool_calls[0]["name"] == "entregar"


@pytest.mark.parametrize("papel", PAPEIS_COM_RESPOSTA_PRONTA)
async def test_todo_papel_responde(papel: str) -> None:
    modelo = criar_modelo_falso(papel).bind_tools([])
    resposta = await modelo.ainvoke([HumanMessage("Pedido: oi")])
    assert resposta.content or resposta.tool_calls
