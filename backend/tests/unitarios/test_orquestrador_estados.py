"""Máquina de estados e limites da cadeia (especificação §6), em tabelas."""

from itertools import product
from uuid import uuid4

import pytest

from app.orquestrador.cadeia import (
    EtapaResumo,
    LimitesCadeia,
    chave_de_cancelamento,
    decidir_avanco,
    etapas_prontas,
    passou_dos_limites,
    pode_iniciar_etapa,
    pode_nova_rodada,
    progresso_da_etapa,
    tentativas_atuais,
    todas_concluidas,
)
from app.orquestrador.estados import (
    FINAIS_CADEIA,
    TRANSICOES_CADEIA,
    TRANSICOES_ETAPA,
    StatusAgenteApp,
    StatusCadeia,
    StatusEtapa,
    TransicaoInvalida,
    mudar_cadeia,
    mudar_etapa,
    pode_mudar_cadeia,
    pode_mudar_etapa,
    status_do_agente,
)

C, E = StatusCadeia, StatusEtapa

# ---------- transições da cadeia ----------

PERMITIDAS_CADEIA = {
    (C.PLANEJANDO, C.EXECUTANDO),
    (C.PLANEJANDO, C.AGUARDANDO_USUARIO),
    (C.PLANEJANDO, C.FALHOU),
    (C.PLANEJANDO, C.CANCELADA),
    (C.EXECUTANDO, C.VERIFICANDO),
    (C.EXECUTANDO, C.AGUARDANDO_USUARIO),
    (C.EXECUTANDO, C.FALHOU),
    (C.EXECUTANDO, C.CANCELADA),
    (C.VERIFICANDO, C.CONCLUIDA),
    (C.VERIFICANDO, C.EXECUTANDO),
    (C.VERIFICANDO, C.AGUARDANDO_USUARIO),
    (C.VERIFICANDO, C.FALHOU),
    (C.VERIFICANDO, C.CANCELADA),
    (C.AGUARDANDO_USUARIO, C.PLANEJANDO),
    (C.AGUARDANDO_USUARIO, C.EXECUTANDO),
    (C.AGUARDANDO_USUARIO, C.VERIFICANDO),
    (C.AGUARDANDO_USUARIO, C.FALHOU),
    (C.AGUARDANDO_USUARIO, C.CANCELADA),
}


@pytest.mark.parametrize(("de", "para"), list(product(C, C)), ids=lambda s: str(s))
def test_tabela_completa_da_cadeia(de: StatusCadeia, para: StatusCadeia) -> None:
    esperado = (de, para) in PERMITIDAS_CADEIA
    assert pode_mudar_cadeia(de, para) is esperado
    if esperado:
        assert mudar_cadeia(de, para) == para
    else:
        with pytest.raises(TransicaoInvalida):
            mudar_cadeia(de, para)


def test_toda_cadeia_tem_regra() -> None:
    assert set(TRANSICOES_CADEIA) == set(C)


def test_so_o_verificador_leva_a_concluida() -> None:
    origens = {de for de, para in PERMITIDAS_CADEIA if para == C.CONCLUIDA}
    assert origens == {C.VERIFICANDO}


@pytest.mark.parametrize("final", sorted(FINAIS_CADEIA))
def test_estado_final_da_cadeia_nao_sai(final: StatusCadeia) -> None:
    assert TRANSICOES_CADEIA[final] == frozenset()


@pytest.mark.parametrize("de", [s for s in C if s not in FINAIS_CADEIA])
def test_cancelar_vale_de_qualquer_estado_em_andamento(de: StatusCadeia) -> None:
    assert pode_mudar_cadeia(de, C.CANCELADA)


def test_aceita_texto_do_banco() -> None:
    assert pode_mudar_cadeia("verificando", "concluida")  # type: ignore[arg-type]
    assert pode_mudar_etapa("pendente", "executando")  # type: ignore[arg-type]


# ---------- transições da etapa ----------

PERMITIDAS_ETAPA = {
    (E.PENDENTE, E.EXECUTANDO),
    (E.PENDENTE, E.CANCELADA),
    (E.EXECUTANDO, E.PENDENTE),
    (E.EXECUTANDO, E.AGUARDANDO_USUARIO),
    (E.EXECUTANDO, E.AGUARDANDO_APROVACAO),
    (E.EXECUTANDO, E.CONCLUIDA),
    (E.EXECUTANDO, E.FALHOU),
    (E.EXECUTANDO, E.CANCELADA),
    (E.AGUARDANDO_USUARIO, E.EXECUTANDO),
    (E.AGUARDANDO_USUARIO, E.FALHOU),
    (E.AGUARDANDO_USUARIO, E.CANCELADA),
    (E.AGUARDANDO_APROVACAO, E.EXECUTANDO),
    (E.AGUARDANDO_APROVACAO, E.FALHOU),
    (E.AGUARDANDO_APROVACAO, E.CANCELADA),
    (E.CONCLUIDA, E.REPROVADA),
}


@pytest.mark.parametrize(("de", "para"), list(product(E, E)), ids=lambda s: str(s))
def test_tabela_completa_da_etapa(de: StatusEtapa, para: StatusEtapa) -> None:
    esperado = (de, para) in PERMITIDAS_ETAPA
    assert pode_mudar_etapa(de, para) is esperado
    if esperado:
        assert mudar_etapa(de, para) == para
    else:
        with pytest.raises(TransicaoInvalida):
            mudar_etapa(de, para)


def test_toda_etapa_tem_regra() -> None:
    assert set(TRANSICOES_ETAPA) == set(E)


@pytest.mark.parametrize(
    ("etapa", "agente"),
    [
        (E.PENDENTE, StatusAgenteApp.AGUARDANDO),
        (E.EXECUTANDO, StatusAgenteApp.TRABALHANDO),
        (E.AGUARDANDO_USUARIO, StatusAgenteApp.TRABALHANDO),
        (E.AGUARDANDO_APROVACAO, StatusAgenteApp.TRABALHANDO),
        (E.CONCLUIDA, StatusAgenteApp.CONCLUIDO),
        (E.REPROVADA, StatusAgenteApp.AGUARDANDO),
        (E.FALHOU, StatusAgenteApp.ERRO),
        (E.CANCELADA, StatusAgenteApp.AGUARDANDO),
    ],
)
def test_status_do_agente_no_app(etapa: StatusEtapa, agente: StatusAgenteApp) -> None:
    assert status_do_agente(etapa) == agente


# ---------- etapas prontas e avanço ----------


def etapa(
    ordem: int,
    status: StatusEtapa = E.PENDENTE,
    depende_de: tuple[int, ...] = (),
    especialista: str = "pesquisador",
    tentativa: int = 1,
) -> EtapaResumo:
    return EtapaResumo(uuid4(), ordem, depende_de, status, especialista, tentativa)


def ordens(etapas: list[EtapaResumo] | tuple[EtapaResumo, ...]) -> list[int]:
    return [e.ordem for e in etapas]


@pytest.mark.parametrize(
    ("plano", "prontas"),
    [
        # independentes rodam juntas, até 3
        ([etapa(1), etapa(2), etapa(3), etapa(4)], [1, 2, 3]),
        # dependência ainda pendente
        ([etapa(1), etapa(2, depende_de=(1,))], [1]),
        # dependência concluída libera
        ([etapa(1, E.CONCLUIDA), etapa(2, depende_de=(1,))], [2]),
        # dependência executando não libera
        ([etapa(1, E.EXECUTANDO), etapa(2, depende_de=(1,))], []),
        # duas dependências: só com as duas concluídas
        ([etapa(1, E.CONCLUIDA), etapa(2), etapa(3, depende_de=(1, 2))], [2]),
        # vagas: 2 rodando → só 1 nova
        ([etapa(1, E.EXECUTANDO), etapa(2, E.AGUARDANDO_APROVACAO), etapa(3), etapa(4)], [3]),
        # 3 ocupando vaga (inclui pausa por pergunta) → nenhuma
        (
            [
                etapa(1, E.EXECUTANDO),
                etapa(2, E.AGUARDANDO_USUARIO),
                etapa(3, E.EXECUTANDO),
                etapa(4),
            ],
            [],
        ),
        # o verificador nunca entra aqui
        ([etapa(1, E.CONCLUIDA), etapa(2, depende_de=(1,), especialista="verificador")], []),
        # dependência que não existe nunca fica pronta
        ([etapa(1, depende_de=(9,))], []),
        # nova tentativa (reprovada → pendente, tentativa 2) volta a ficar pronta
        ([etapa(1, E.REPROVADA), etapa(1, E.PENDENTE, tentativa=2)], [1]),
    ],
)
def test_etapas_prontas(plano: list[EtapaResumo], prontas: list[int]) -> None:
    assert ordens(etapas_prontas(plano)) == prontas


def test_tentativa_mais_nova_vale() -> None:
    plano = [etapa(1, E.REPROVADA, tentativa=1), etapa(1, E.EXECUTANDO, tentativa=2)]
    assert tentativas_atuais(plano)[1].tentativa == 2


@pytest.mark.parametrize(
    ("plano", "esperado"),
    [
        ([etapa(1, E.CONCLUIDA), etapa(2, E.CONCLUIDA)], True),
        ([etapa(1, E.CONCLUIDA), etapa(2, E.EXECUTANDO)], False),
        ([etapa(1, E.CONCLUIDA), etapa(2, especialista="verificador")], True),
        ([etapa(1, E.REPROVADA), etapa(1, E.PENDENTE, tentativa=2)], False),
        ([etapa(1, especialista="verificador")], False),
    ],
)
def test_todas_concluidas(plano: list[EtapaResumo], esperado: bool) -> None:
    assert todas_concluidas(plano) is esperado


VER = "verificador"


@pytest.mark.parametrize(
    ("plano", "passos", "acao", "esperadas"),
    [
        ("começo", 0, "executar", [1, 2]),
        ("rodando", 2, "aguardar", []),
        ("libera_3", 2, "executar", [3]),
        ("tudo_pronto", 3, "verificar", []),
        ("falhou", 2, "falhar", [2]),
        ("cancelada", 2, "falhar", [2]),
        ("sem_passos", 10, "limite", []),
        ("um_passo", 9, "executar", [1]),
        ("travada", 0, "falhar", []),
    ],
)
def test_decidir_avanco(plano: str, passos: int, acao: str, esperadas: list[int]) -> None:
    planos = {
        "começo": [etapa(1), etapa(2), etapa(3, depende_de=(1, 2)), etapa(4, especialista=VER)],
        "rodando": [
            etapa(1, E.EXECUTANDO),
            etapa(2, E.EXECUTANDO),
            etapa(3, depende_de=(1, 2)),
            etapa(4, especialista=VER),
        ],
        "libera_3": [
            etapa(1, E.CONCLUIDA),
            etapa(2, E.CONCLUIDA),
            etapa(3, depende_de=(1, 2)),
            etapa(4, especialista=VER),
        ],
        "tudo_pronto": [
            etapa(1, E.CONCLUIDA),
            etapa(2, E.CONCLUIDA),
            etapa(3, E.CONCLUIDA),
            etapa(4, especialista=VER),
        ],
        "falhou": [etapa(1, E.CONCLUIDA), etapa(2, E.FALHOU), etapa(3, especialista=VER)],
        "cancelada": [etapa(1, E.CONCLUIDA), etapa(2, E.CANCELADA), etapa(3, especialista=VER)],
        "sem_passos": [etapa(1), etapa(2, especialista=VER)],
        "um_passo": [etapa(1), etapa(2), etapa(3, especialista=VER)],
        "travada": [etapa(1, depende_de=(2,)), etapa(2, depende_de=(1,))],
    }
    decisao = decidir_avanco(planos[plano], passos_feitos=passos)
    assert decisao.acao == acao
    assert ordens(decisao.etapas) == esperadas
    if acao in ("falhar", "limite"):
        assert decisao.motivo


def test_decidir_avanco_respeita_limites_customizados() -> None:
    plano = [etapa(1), etapa(2), etapa(3)]
    decisao = decidir_avanco(plano, passos_feitos=0, limites=LimitesCadeia(paralelo=1))
    assert ordens(decisao.etapas) == [1]


# ---------- limites ----------


@pytest.mark.parametrize(
    ("rodada", "passos", "passou"),
    [(0, 0, False), (3, 10, False), (4, 0, True), (0, 11, True), (4, 11, True)],
)
def test_passou_dos_limites(rodada: int, passos: int, passou: bool) -> None:
    assert passou_dos_limites(rodada, passos, LimitesCadeia()) is passou


@pytest.mark.parametrize(("passos", "pode"), [(0, True), (9, True), (10, False), (11, False)])
def test_pode_iniciar_etapa(passos: int, pode: bool) -> None:
    assert pode_iniciar_etapa(passos, LimitesCadeia()) is pode


@pytest.mark.parametrize(("rodada", "pode"), [(0, True), (2, True), (3, False)])
def test_pode_nova_rodada(rodada: int, pode: bool) -> None:
    assert pode_nova_rodada(rodada, LimitesCadeia()) is pode


def test_limites_padrao_da_especificacao() -> None:
    limites = LimitesCadeia()
    assert (limites.rodadas, limites.passos, limites.paralelo) == (3, 10, 3)
    assert (limites.tokens, limites.especialistas) == (200_000, 5)


# ---------- progresso ----------


@pytest.mark.parametrize(
    ("feitas", "limite", "entregou", "anterior", "esperado"),
    [
        (0, 10, False, 0, 10),
        (5, 10, False, 0, 47),
        (10, 10, False, 0, 85),
        (50, 10, False, 0, 85),  # passou do limite: fica em 85
        (3, 10, True, 0, 100),
        (1, 10, False, 60, 60),  # nunca volta para trás
        (0, 0, False, 0, 10),
        (-1, 10, False, 0, 10),
    ],
)
def test_progresso_da_etapa(
    feitas: int, limite: int, entregou: bool, anterior: int, esperado: int
) -> None:
    assert progresso_da_etapa(feitas, limite, entregou, anterior) == esperado


def test_progresso_cresce_sem_voltar() -> None:
    valores, anterior = [], 0
    for feitas in range(12):
        anterior = progresso_da_etapa(feitas, 10, False, anterior)
        valores.append(anterior)
    assert valores == sorted(valores)
    assert valores[0] == 10 and valores[-1] == 85


def test_chave_de_cancelamento() -> None:
    cadeia = uuid4()
    assert chave_de_cancelamento(cadeia) == f"cancelar:{cadeia}"
