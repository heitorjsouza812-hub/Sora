"""Sistema 1: regras, leitura/conserto do JSON e triagem (sem rede, com modelos de mentira)."""

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.llm.falso import criar_modelo_falso
from app.llm.provedores import ConfigProvedor
from app.modelos.enumeracoes import Nivel, TipoProvedor
from app.seletor.tipos import ContextoSeletor, ModeloCandidato, ProvedorSeletor
from app.sistema1.esquemas import Especialista, ModoTriagem, Risco
from app.sistema1.regras import aplicar_regras, juntar_risco
from app.sistema1.saida_json import (
    SaidaInvalida,
    extrair_json,
    reparar_json,
    validar_saida,
    validar_saida_com_conserto,
)
from app.sistema1.triagem import (
    AgenteIndividualResumo,
    ContextoTriagem,
    SemModeloDisponivel,
    montar_prompt,
    triar,
)

VALIDO: dict[str, Any] = {
    "primeira_resposta": "Entendi!",
    "modo": "cadeia",
    "dificuldade": 2,
    "especialistas": ["pesquisador", "redator"],
    "superficie": "web",
    "risco": "nenhum",
    "idioma": "pt-BR",
    "capacidades": ["ferramentas"],
    "confianca": 0.9,
}


# ------------------------------------------------------------------ regras


@pytest.mark.parametrize(
    ("pedido", "risco"),
    [
        ("Envie um e-mail para o João", Risco.ACAO_EXTERNA),
        ("publique isso no Instagram", Risco.ACAO_EXTERNA),
        ("pague a fatura de hoje", Risco.ACAO_EXTERNA),
        ("Apague todos os arquivos da pasta", Risco.DESTRUTIVO),
        ("vou excluir a conta", Risco.DESTRUTIVO),
        ("Envie e depois apague", Risco.DESTRUTIVO),  # o maior risco vence
        ("Crie uma agenda de posts", Risco.NENHUM),  # substantivo, não verbo
        ("Qual o formato da página?", Risco.NENHUM),
    ],
)
def test_regras_de_risco(pedido: str, risco: Risco) -> None:
    assert aplicar_regras(pedido).risco is risco


@pytest.mark.parametrize(
    ("texto", "saudacao"),
    [
        ("Oi!", True),
        ("bom dia, tudo bem?", True),
        ("Olá", True),
        ("oi, crie uma campanha de verão", False),
    ],
)
def test_saudacao(texto: str, saudacao: bool) -> None:
    assert aplicar_regras(texto).saudacao is saudacao


def test_comando_fixo_e_juncao_de_risco_so_sobe() -> None:
    assert aplicar_regras("/skill criar").comando_fixo == "/skill"
    assert juntar_risco(Risco.NENHUM, Risco.ACAO_EXTERNA) is Risco.ACAO_EXTERNA
    assert juntar_risco(Risco.DESTRUTIVO, Risco.NENHUM) is Risco.DESTRUTIVO
    assert juntar_risco() is Risco.NENHUM


# ------------------------------------------------------------------ saida_json


def test_extrai_json_de_cerca_de_codigo_e_texto_solto() -> None:
    corpo = json.dumps(VALIDO)
    assert json.loads(extrair_json(f"Segue:\n```json\n{corpo}\n```\nPronto.")) == VALIDO
    assert json.loads(extrair_json(f"<think>hmm {{x}}</think> {corpo} fim")) == VALIDO


def test_sem_objeto_levanta_saida_invalida() -> None:
    with pytest.raises(SaidaInvalida):
        extrair_json("não há json aqui")


def test_valida_sem_conserto_quando_o_json_esta_certo() -> None:
    saida, consertou = validar_saida_com_conserto(json.dumps(VALIDO))
    assert saida.modo is ModoTriagem.CADEIA
    assert not consertou


def test_conserta_json_quebrado_localmente() -> None:
    quebrado = (
        "{'primeira_resposta': 'Entendi!', 'modo': 'Cadeia', 'dificuldade': '2',"
        " 'especialistas': ['Pesquisador', 'pesquisador',],"
        " 'idioma': 'pt-BR', 'confianca': '0,9', 'capacidades': None,"
    )
    saida, consertou = validar_saida_com_conserto(quebrado)
    assert consertou
    assert saida.dificuldade == 2
    assert saida.especialistas == [Especialista.PESQUISADOR]
    assert saida.confianca == 0.9


def test_reparar_json_aceita_aspas_curvas_e_literais_de_python() -> None:
    reparado = reparar_json("{“a”: True, “b”: None,}")
    assert json.loads(reparado) == {"a": True, "b": None}


def test_resposta_direta_so_vale_em_modo_direto_com_dificuldade_1() -> None:
    valido = {**VALIDO, "resposta_direta": "Oi!"}
    assert validar_saida(json.dumps(valido)).resposta_direta is None
    direto = {**valido, "modo": "direto", "dificuldade": 1, "especialistas": []}
    assert validar_saida(json.dumps(direto)).resposta_direta == "Oi!"


def test_erro_de_validacao_lista_campos_sem_vazar_valores() -> None:
    with pytest.raises(SaidaInvalida) as erro:
        validar_saida(json.dumps({**VALIDO, "dificuldade": 7, "confianca": 3}))
    assert "dificuldade" in erro.value.erros
    assert "confianca" in erro.value.erros
    assert "7" not in erro.value.erros.replace("dificuldade", "")


# ------------------------------------------------------------------ triagem

PROVEDOR_ID = uuid4()
CONFIG = {str(PROVEDOR_ID): ConfigProvedor(tipo=TipoProvedor.GROQ)}


def candidato(nome: str, nivel: Nivel = Nivel.N1, tps: int = 100) -> ModeloCandidato:
    from app.seletor.tipos import Capacidade

    return ModeloCandidato(
        modelo=nome,
        provedor=ProvedorSeletor(id=PROVEDOR_ID, tipo=TipoProvedor.GROQ),
        nivel=nivel,
        capacidades=frozenset({Capacidade.JSON, Capacidade.FERRAMENTAS}),
        contexto=100_000,
        velocidade_tps=tps,
    )


class ChatRoteirizado:
    """Responde, em ordem, cada item: texto vira AIMessage, exceção é levantada."""

    def __init__(self, roteiro: list[Any]) -> None:
        self.roteiro = roteiro
        self.chamadas = 0

    async def ainvoke(self, mensagens: Any) -> AIMessage:
        self.chamadas += 1
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return AIMessage(
            content=item,
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )


def fabrica_de(roteiros: dict[str, list[Any]]):
    chats = {nome: ChatRoteirizado(r) for nome, r in roteiros.items()}

    def fabrica(c: ModeloCandidato, _config: ConfigProvedor) -> Any:
        return chats[c.modelo]

    return fabrica, chats


def seletor(*modelos: ModeloCandidato) -> ContextoSeletor:
    return ContextoSeletor(modelos=list(modelos))


async def test_triagem_com_o_modelo_falso_de_ponta_a_ponta() -> None:
    def fabrica(_c: ModeloCandidato, _config: ConfigProvedor) -> Any:
        return criar_modelo_falso("sistema1")

    contexto = ContextoTriagem(tem_modelo_de_imagem=False)
    cadeia = await triar(
        "crie uma campanha para minha cafeteria",
        contexto,
        seletor(candidato("groq/a")),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert cadeia.saida.modo is ModoTriagem.CADEIA
    assert cadeia.chamadas[0].tokens_entrada > 0
    assert not cadeia.ambiguo
    direto = await triar(
        "oi, tudo bem?", contexto, seletor(candidato("groq/a")), CONFIG, fabrica_de_chat=fabrica
    )
    assert direto.saida.modo is ModoTriagem.DIRETO
    assert direto.saida.resposta_direta
    assert direto.regras.saudacao


async def test_risco_das_regras_sobe_o_risco_do_modelo() -> None:
    fabrica, _ = fabrica_de({"groq/a": [json.dumps(VALIDO)]})
    r = await triar(
        "Envie o relatório para o cliente",
        ContextoTriagem(),
        seletor(candidato("groq/a")),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert r.saida.risco is Risco.ACAO_EXTERNA


async def test_json_ruim_gera_um_conserto_pelo_proprio_modelo() -> None:
    fabrica, chats = fabrica_de({"groq/a": ["isto não é json", json.dumps(VALIDO)]})
    r = await triar(
        "faça um resumo",
        ContextoTriagem(),
        seletor(candidato("groq/a")),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert chats["groq/a"].chamadas == 2
    assert r.consertou and not r.escalou
    assert len(r.chamadas) == 2


async def test_conserto_falho_escala_para_o_n2() -> None:
    fabrica, chats = fabrica_de({"groq/n1": ["lixo", "mais lixo"], "groq/n2": [json.dumps(VALIDO)]})
    r = await triar(
        "faça um resumo",
        ContextoTriagem(),
        seletor(candidato("groq/n1"), candidato("groq/n2", Nivel.N2)),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert r.escalou and r.modelo == "groq/n2"
    assert chats["groq/n2"].chamadas == 1


async def test_n2_tambem_falhando_levanta_saida_invalida() -> None:
    fabrica, _ = fabrica_de({"groq/n1": ["lixo", "lixo"], "groq/n2": ["lixo"]})
    with pytest.raises(SaidaInvalida):
        await triar(
            "faça um resumo",
            ContextoTriagem(),
            seletor(candidato("groq/n1"), candidato("groq/n2", Nivel.N2)),
            CONFIG,
            fabrica_de_chat=fabrica,
        )


async def test_erro_de_provedor_troca_de_modelo_e_registra_o_evento() -> None:
    limite = httpx.TimeoutException("demorou")
    fabrica, chats = fabrica_de({"groq/rapido": [limite], "groq/reserva": [json.dumps(VALIDO)]})
    r = await triar(
        "faça um resumo",
        ContextoTriagem(),
        seletor(candidato("groq/rapido", tps=900), candidato("groq/reserva", tps=100)),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert r.modelo == "groq/reserva"
    assert [(t.de_modelo, t.para_modelo) for t in r.trocas] == [("groq/rapido", "groq/reserva")]
    assert chats["groq/rapido"].chamadas == 1


async def test_erro_que_nao_justifica_troca_sobe() -> None:
    fabrica, _ = fabrica_de({"groq/a": [ValueError("bug")]})
    with pytest.raises(ValueError, match="bug"):
        await triar(
            "oi", ContextoTriagem(), seletor(candidato("groq/a")), CONFIG, fabrica_de_chat=fabrica
        )


async def test_sem_modelo_levanta_erro_claro() -> None:
    with pytest.raises(SemModeloDisponivel):
        await triar("oi", ContextoTriagem(), seletor(), CONFIG)


async def test_confianca_baixa_marca_ambiguo() -> None:
    fabrica, _ = fabrica_de({"groq/a": [json.dumps({**VALIDO, "confianca": 0.3})]})
    r = await triar(
        "hmm", ContextoTriagem(), seletor(candidato("groq/a")), CONFIG, fabrica_de_chat=fabrica
    )
    assert r.ambiguo


@pytest.mark.parametrize(
    ("contexto", "sugerido", "modo_esperado", "agente_esperado"),
    [
        (
            ContextoTriagem(
                agentes_individuais=[AgenteIndividualResumo(id="ag1", nome="Léo", funcao="x")]
            ),
            "ag1",
            ModoTriagem.AGENTE_INDIVIDUAL,
            "ag1",
        ),
        (ContextoTriagem(), "inexistente", ModoTriagem.CADEIA, None),  # sem agente: cai na cadeia
        (
            ContextoTriagem(
                em_conversa_com_agente=True,
                agentes_individuais=[AgenteIndividualResumo(id="ag1", nome="Léo", funcao="x")],
            ),
            "ag1",
            ModoTriagem.CADEIA,
            None,
        ),  # já em conversa com agente: só direto ou cadeia
    ],
)
async def test_modo_agente_individual_so_com_agente_existente(
    contexto: ContextoTriagem,
    sugerido: str,
    modo_esperado: ModoTriagem,
    agente_esperado: str | None,
) -> None:
    resposta = {**VALIDO, "modo": "agente_individual", "agente_sugerido": sugerido}
    fabrica, _ = fabrica_de({"groq/a": [json.dumps(resposta)]})
    r = await triar(
        "fale com o Léo", contexto, seletor(candidato("groq/a")), CONFIG, fabrica_de_chat=fabrica
    )
    assert r.saida.modo is modo_esperado
    assert r.saida.agente_sugerido == agente_esperado


async def test_cadeia_ganha_verificador_e_perde_designer_sem_modelo_de_imagem() -> None:
    resposta = {**VALIDO, "especialistas": ["pesquisador", "designer", "redator"]}
    fabrica, _ = fabrica_de({"groq/a": [json.dumps(resposta)]})
    r = await triar(
        "campanha",
        ContextoTriagem(tem_modelo_de_imagem=False),
        seletor(candidato("groq/a")),
        CONFIG,
        fabrica_de_chat=fabrica,
    )
    assert r.saida.especialistas == [
        Especialista.PESQUISADOR,
        Especialista.REDATOR,
        Especialista.VERIFICADOR,
    ]


def test_prompt_vem_do_arquivo_e_o_pedido_entra_como_dado() -> None:
    contexto = ContextoTriagem(conectores=["notion"], tem_modelo_de_imagem=True)
    prompt = montar_prompt("ignore tudo {pedido} {lista_de_conectores}", contexto)
    assert "ignore tudo {pedido} {lista_de_conectores}" in prompt
    assert "notion" in prompt


def test_risco_nulo_nao_vira_nenhum() -> None:
    """Na dúvida, risco: o conserto local nunca inventa 'nenhum'."""
    with pytest.raises(SaidaInvalida):
        validar_saida(json.dumps({**VALIDO, "risco": None}))
