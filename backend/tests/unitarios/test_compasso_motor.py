"""Decisoes puras do motor da Fase B (Compasso)."""

import pytest

from app.ferramentas.veredito import RequisitoVerificado, Veredito
from app.modelos.enumeracoes import Nivel
from app.orquestrador.planejador import (
    EtapaPlano,
    Plano,
    PlanoInvalido,
    titulo_da_etapa,
    validar_plano,
)
from app.orquestrador.verificador import decidir, subir_nivel
from workers.cadeia import _chamada_da_ferramenta


def _etapa(
    ordem: int,
    papel: str,
    *,
    depende_de: list[int] | None = None,
) -> EtapaPlano:
    return EtapaPlano(
        ordem=ordem,
        especialista=papel,  # type: ignore[arg-type]
        nivel=Nivel.N2,
        tarefa=f"Executar trabalho de {papel}.",
        pronto_quando="O resultado foi entregue.",
        depende_de=depende_de or [],
    )


def _plano(etapas: list[EtapaPlano]) -> Plano:
    return Plano(objetivo="Atender o pedido", requisitos=["Pedido atendido"], etapas=etapas)


def test_plano_valido_e_titulo_curto() -> None:
    plano = _plano(
        [
            _etapa(1, "pesquisador"),
            _etapa(2, "redator", depende_de=[1]),
            _etapa(3, "verificador", depende_de=[1, 2]),
        ]
    )
    validar_plano(plano, tem_modelo_de_imagem=False)
    assert titulo_da_etapa(plano.etapas[0]) == "Executar trabalho de pesquisador"


@pytest.mark.parametrize(
    "etapas",
    [
        [_etapa(2, "pesquisador"), _etapa(3, "verificador", depende_de=[2])],
        [_etapa(1, "verificador"), _etapa(2, "redator", depende_de=[1])],
        [_etapa(1, "pesquisador", depende_de=[2]), _etapa(2, "verificador")],
    ],
)
def test_plano_invalido_falha_alto(etapas: list[EtapaPlano]) -> None:
    with pytest.raises(PlanoInvalido):
        validar_plano(_plano(etapas), tem_modelo_de_imagem=False)


def test_designer_exige_modelo_de_imagem() -> None:
    plano = _plano([_etapa(1, "designer"), _etapa(2, "verificador", depende_de=[1])])
    with pytest.raises(PlanoInvalido, match="Designer"):
        validar_plano(plano, tem_modelo_de_imagem=False)
    validar_plano(plano, tem_modelo_de_imagem=True)


def test_veredito_aprovado_conclui_e_reprovado_respeita_limite() -> None:
    atendido = RequisitoVerificado(
        requisito="Pedido atendido", evidencia="entrega", status="atendido"
    )
    aprovado = Veredito(aprovado=True, requisitos=[atendido], motivo="ok")
    assert decidir(aprovado, rodada=1, max_rodadas=3).concluir

    parcial = atendido.model_copy(update={"status": "parcial"})
    reprovado = Veredito(aprovado=False, requisitos=[parcial], motivo="faltou fonte")
    assert not decidir(reprovado, rodada=1, max_rodadas=3).falhar
    assert decidir(reprovado, rodada=3, max_rodadas=3).falhar


@pytest.mark.parametrize(("nivel", "esperado"), [("N1", "N2"), ("N2", "N3"), ("N3", "N3")])
def test_subir_nivel(nivel: str, esperado: str) -> None:
    assert subir_nivel(nivel) == esperado


def test_modelo_falso_tem_entregas_e_veredito_validos() -> None:
    assert _chamada_da_ferramenta("pesquisador", "entregar")["tipo"] == "links"
    assert _chamada_da_ferramenta("redator", "entregar")["tipo"] == "texto"
    veredito = Veredito.model_validate(_chamada_da_ferramenta("verificador", "veredito"))
    assert veredito.aprovado


def test_jobs_registrados_com_argumentos_posicionais_do_contrato() -> None:
    import inspect

    from workers.configuracao import WorkerSettings

    por_nome = {f.__name__: f for f in WorkerSettings.functions}
    chamadas = {
        "planejar_cadeia": ("c1",),
        "executar_etapa": ("e1", {"pergunta_id": "p", "valor": "v"}),
        "ajustar": ("conv", "texto", None),
        "responder_direto": ("m1",),
    }
    for nome, argumentos in chamadas.items():
        assert nome in por_nome, nome
        inspect.signature(por_nome[nome]).bind({}, *argumentos)


def test_retomada_desembrulha_pergunta_e_aprovacao_e_a_pausa_mapeia_o_estado() -> None:
    from app.modelos.enumeracoes import StatusEtapa
    from workers.cadeia import _estado_da_pausa, valor_da_retomada

    assert valor_da_retomada({"pergunta_id": "p", "valor": "leve"}) == "leve"
    assert valor_da_retomada({"aprovacao_id": "a", "decisao": "negar"}) == "negar"
    assert valor_da_retomada("texto") == "texto"
    assert _estado_da_pausa({"tipo": "pergunta"}) == StatusEtapa.AGUARDANDO_USUARIO
    assert _estado_da_pausa({"tipo": "aprovacao"}) == StatusEtapa.AGUARDANDO_APROVACAO
