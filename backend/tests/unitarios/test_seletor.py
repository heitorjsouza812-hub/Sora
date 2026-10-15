"""Seletor de modelo (§5): carga da config e tabelas de casos de ``escolher_modelos``."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.modelos.enumeracoes import Nivel, Prioridade, TipoProvedor
from app.seletor.catalogo import carregar_catalogo
from app.seletor.flags import ModoLaya, carregar_flags
from app.seletor.politica import carregar_politica
from app.seletor.seletor import ResultadoSelecao, TipoAviso, escolher_modelos, tem_modelo_de_imagem
from app.seletor.tipos import (
    Capacidade,
    ContextoSeletor,
    ModeloCandidato,
    PapelModelo,
    ProvedorSeletor,
)

AGORA = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
POLITICA = carregar_politica()
FER, JSON, IMG = Capacidade.FERRAMENTAS, Capacidade.JSON, Capacidade.IMAGEM


def prov(tipo: TipoProvedor = TipoProvedor.GROQ, **extra) -> ProvedorSeletor:
    return ProvedorSeletor(id=uuid4(), tipo=tipo, **extra)


def modelo(
    nome: str,
    provedor: ProvedorSeletor,
    nivel: Nivel | str = Nivel.N2,
    *,
    caps: tuple[Capacidade, ...] = (FER, JSON),
    preco: str = "1",
    tps: int | None = 100,
    contexto: int = 100_000,
    **extra,
) -> ModeloCandidato:
    return ModeloCandidato(
        modelo=nome,
        provedor=provedor,
        nivel=nivel,
        capacidades=frozenset(caps),
        contexto=contexto,
        preco_entrada=Decimal(preco),
        preco_saida=Decimal(preco),
        velocidade_tps=tps,
        **extra,
    )


def escolher(
    modelos: list[ModeloCandidato],
    papel: PapelModelo,
    dificuldade: int = 2,
    *,
    prioridade: Prioridade = Prioridade.CUSTO,
    privada: bool = False,
    precisa: set[Capacidade] | None = None,
    tokens: int = 1000,
    **kw,
) -> ResultadoSelecao:
    contexto = ContextoSeletor(modelos=modelos, prioridade=prioridade, conversa_privada=privada)
    return escolher_modelos(
        contexto, papel, dificuldade, precisa or set(), tokens, politica=POLITICA, agora=AGORA, **kw
    )


def nomes(resultado: ResultadoSelecao) -> list[str]:
    return [m.modelo for m in resultado.modelos]


def tipos(resultado: ResultadoSelecao) -> set[TipoAviso]:
    return {a.tipo for a in resultado.avisos}


# ------------------------------------------------------------------ configuração


def test_politica_catalogo_e_flags_do_repositorio_carregam() -> None:
    assert set(POLITICA.papeis) == set(PapelModelo)
    assert POLITICA.limites.falhas_para_pausar_provedor == 3
    assert carregar_catalogo().buscar("groq/openai/gpt-oss-20b")
    flags = carregar_flags()
    assert flags.laya.ativo is False
    assert flags.laya.modo is ModoLaya.DESLIGADO


def test_catalogo_classifica_modelo_desconhecido_como_n2_do_usuario() -> None:
    desconhecido = carregar_catalogo().classificar("groq/modelo-que-nao-existe")
    assert desconhecido.nivel is Nivel.N2
    assert desconhecido.capacidades == []
    assert desconhecido.origem == "usuario"


def test_catalogo_cruza_modelo_do_openrouter_pelo_nome_sem_prefixo() -> None:
    achado = carregar_catalogo().classificar("openrouter/anthropic/claude-sonnet-5-5")
    assert achado.origem == "catalogo"
    assert achado.nivel is Nivel.N2


def test_politica_sem_papel_e_recusada(tmp_path: Path) -> None:
    caminho = tmp_path / "politica.yaml"
    caminho.write_text(
        "papeis: {sora: {nivel: N2}}\n"
        "dificuldade_para_nivel: {1: N1}\n"
        "prioridade_padrao: custo\n"
        "limites: {confianca_minima_s1: 0.7, cadeia: {rodadas: 1, passos: 1, tokens: 1},"
        " especialistas_por_cadeia: 5, agentes_individuais_por_usuario: 5,"
        " lembrete_apos_chamadas_sem_falar: 6, falhas_para_pausar_provedor: 3,"
        " pausa_provedor_minutos: 5}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sem os papéis"):
        carregar_politica(caminho)


# ------------------------------------------------------------------ nível e subida


@pytest.mark.parametrize(
    ("papel", "dificuldade", "esperado"),
    [
        (PapelModelo.PESQUISADOR, 2, "n2"),
        (PapelModelo.PLANEJADOR, 2, "n3"),  # planejador é sempre N3
        (PapelModelo.SISTEMA1, 3, "n1"),
        (PapelModelo.RESPOSTA_DIRETA, 1, "n1"),
        (PapelModelo.RESPOSTA_DIRETA, 2, "n2"),  # sobe com a dificuldade
        (PapelModelo.RESPOSTA_DIRETA, 3, "n3"),
    ],
)
def test_nivel_pela_politica(papel: PapelModelo, dificuldade: int, esperado: str) -> None:
    p = prov()
    todos = [modelo(f"m/{n}", p, n.upper()) for n in ("n1", "n2", "n3")]
    resultado = escolher(todos, papel, dificuldade)
    assert nomes(resultado)[0] == f"m/{esperado}"
    assert not tipos(resultado)


def test_sem_modelo_no_nivel_sobe_para_o_de_cima_e_avisa() -> None:
    p = prov()
    modelos = [modelo("m/n1", p, Nivel.N1), modelo("m/n3", p, Nivel.N3)]
    resultado = escolher(modelos, PapelModelo.PESQUISADOR)
    assert nomes(resultado) == ["m/n3"]
    assert tipos(resultado) == {TipoAviso.NIVEL_SUBIU}


def test_sem_nivel_igual_ou_acima_usa_o_mais_forte_e_avisa() -> None:
    p = prov()
    modelos = [modelo("m/a", p, Nivel.N1), modelo("m/b", p, Nivel.N2)]
    resultado = escolher(modelos, PapelModelo.PLANEJADOR)
    assert nomes(resultado)[0] == "m/b"
    assert tipos(resultado) == {TipoAviso.USOU_O_MAIS_FORTE}


# ------------------------------------------------------------------ filtros


def test_filtra_capacidade_contexto_e_inativos() -> None:
    p = prov()
    ok = modelo("m/ok", p)
    sem_ferramentas = modelo("m/sem", p, caps=(JSON,))
    pequeno = modelo("m/pequeno", p, contexto=500)
    inativo = modelo("m/inativo", p, ativo=False)
    resultado = escolher([sem_ferramentas, pequeno, inativo, ok], PapelModelo.PESQUISADOR)
    assert nomes(resultado) == ["m/ok"]


def test_capacidade_extra_pedida_pela_triagem_entra_no_filtro() -> None:
    p = prov()
    com_visao = modelo("m/visao", p, caps=(FER, JSON, Capacidade.VISAO))
    resultado = escolher(
        [modelo("m/texto", p), com_visao], PapelModelo.PESQUISADOR, precisa={Capacidade.VISAO}
    )
    assert nomes(resultado) == ["m/visao"]


def test_provedor_em_pausa_sai_e_volta_quando_a_pausa_acaba() -> None:
    pausado = prov(pausado_ate=AGORA + timedelta(minutes=5))
    livre = prov(TipoProvedor.OPENAI)
    modelos = [modelo("m/pausado", pausado, preco="0.1"), modelo("m/livre", livre, preco="5")]
    assert nomes(escolher(modelos, PapelModelo.PESQUISADOR)) == ["m/livre"]
    vencido = prov(pausado_ate=AGORA - timedelta(seconds=1))
    resultado = escolher([modelo("m/vencido", vencido)], PapelModelo.PESQUISADOR)
    assert nomes(resultado) == ["m/vencido"]


def test_provedor_acima_do_teto_sai_mas_abaixo_do_teto_fica() -> None:
    estourou = prov(teto_mensal_usd=Decimal(10), gasto_mes_usd=Decimal(10))
    folga = prov(TipoProvedor.OPENAI, teto_mensal_usd=Decimal(10), gasto_mes_usd=Decimal("9.99"))
    sem_teto = prov(TipoProvedor.GOOGLE, gasto_mes_usd=Decimal(9999))
    modelos = [
        modelo("m/estourou", estourou, preco="0.1"),
        modelo("m/folga", folga, preco="1"),
        modelo("m/sem-teto", sem_teto, preco="2"),
    ]
    assert nomes(escolher(modelos, PapelModelo.PESQUISADOR)) == ["m/folga", "m/sem-teto"]


def test_nada_serve_devolve_lista_vazia_com_aviso() -> None:
    resultado = escolher([], PapelModelo.PESQUISADOR)
    assert resultado.modelos == []
    assert tipos(resultado) == {TipoAviso.SEM_MODELO}


def test_conversa_privada_so_com_ollama() -> None:
    nuvem, local = prov(TipoProvedor.OPENAI), prov(TipoProvedor.OLLAMA)
    modelos = [modelo("openai/m", nuvem, preco="0.1"), modelo("ollama/m", local, preco="9")]
    assert nomes(escolher(modelos, PapelModelo.PESQUISADOR, privada=True)) == ["ollama/m"]
    sem_local = escolher(modelos[:1], PapelModelo.PESQUISADOR, privada=True)
    assert sem_local.modelos == []
    assert tipos(sem_local) == {TipoAviso.SEM_MODELO}
    assert "privada" in sem_local.avisos[0].detalhe


# ------------------------------------------------------------------ ordem e reserva


@pytest.mark.parametrize(
    ("prioridade", "esperado"),
    [
        (Prioridade.CUSTO, ["m/barato", "m/medio", "m/rapido", "m/caro"]),
        (Prioridade.VELOCIDADE, ["m/rapido", "m/medio", "m/barato", "m/caro"]),
        (Prioridade.QUALIDADE, ["m/caro", "m/rapido", "m/medio", "m/barato"]),
    ],
)
def test_prioridade_do_usuario_ordena_o_grupo_do_nivel(
    prioridade: Prioridade, esperado: list[str]
) -> None:
    p = prov()
    modelos = [
        modelo("m/barato", p, preco="1", tps=50),
        modelo("m/medio", p, preco="3", tps=100),
        modelo("m/rapido", p, preco="4", tps=500),
        modelo("m/caro", p, preco="9", tps=20),
    ]
    resultado = escolher(modelos, PapelModelo.PESQUISADOR, prioridade=prioridade)
    assert nomes(resultado) == esperado


def test_sistema1_sempre_pelo_mais_rapido_mesmo_com_prioridade_de_custo() -> None:
    p = prov()
    modelos = [
        modelo("m/barato", p, Nivel.N1, preco="0.1", tps=50),
        modelo("m/rapido", p, Nivel.N1, preco="2", tps=900),
    ]
    resultado = escolher(modelos, PapelModelo.SISTEMA1, 1, prioridade=Prioridade.CUSTO)
    assert nomes(resultado) == ["m/rapido", "m/barato"]


def test_preco_desconhecido_vai_para_o_fim_na_ordem_de_custo() -> None:
    p = prov()
    sem_preco = ModeloCandidato(
        modelo="m/sem-preco",
        provedor=p,
        nivel=Nivel.N2,
        capacidades=frozenset({FER}),
        contexto=100_000,
    )
    resultado = escolher([sem_preco, modelo("m/caro", p, preco="50")], PapelModelo.PESQUISADOR)
    assert nomes(resultado) == ["m/caro", "m/sem-preco"]


def test_reserva_fica_no_grupo_do_nivel_e_nao_sobe_para_mais_caro() -> None:
    p = prov()
    modelos = [
        modelo("m/n2a", p, preco="1"),
        modelo("m/n2b", p, preco="2"),
        modelo("m/n3", p, Nivel.N3, preco="20"),
    ]
    assert nomes(escolher(modelos, PapelModelo.PESQUISADOR)) == ["m/n2a", "m/n2b"]


# ------------------------------------------------------------------ escolhas do usuário


def test_somente_se_escolhido_nunca_entra_sozinho() -> None:
    p = prov(TipoProvedor.ANTHROPIC)
    fable = modelo("anthropic/claude-fable-5-1", p, Nivel.N3, somente_se_escolhido=True)
    opus = modelo("anthropic/claude-opus-5-5", p, Nivel.N3, preco="5")
    assert nomes(escolher([fable, opus], PapelModelo.PLANEJADOR, 3)) == [opus.modelo]
    assert nomes(escolher([fable], PapelModelo.PLANEJADOR, 3)) == []
    escolhido = escolher([fable, opus], PapelModelo.PLANEJADOR, 3, preferido=fable.modelo)
    assert nomes(escolhido) == [fable.modelo, opus.modelo]


def test_modelo_preferido_do_agente_vai_na_frente_e_apaga_aviso_de_nivel() -> None:
    p = prov()
    n3 = modelo("m/n3", p, Nivel.N3, preco="9")
    n1 = modelo("m/n1", p, Nivel.N1)
    resultado = escolher([n1, n3], PapelModelo.PESQUISADOR, preferido="m/n1")
    assert nomes(resultado) == ["m/n1", "m/n3"]
    assert TipoAviso.NIVEL_SUBIU not in tipos(resultado)


def test_preferido_sem_capacidade_e_ignorado() -> None:
    p = prov()
    fraco = modelo("m/fraco", p, caps=(JSON,))
    resultado = escolher([fraco, modelo("m/bom", p)], PapelModelo.PESQUISADOR, preferido="m/fraco")
    assert nomes(resultado) == ["m/bom"]


# ------------------------------------------------------------------ verificador e memória


def test_verificador_prefere_outro_provedor() -> None:
    a, b = prov(TipoProvedor.GROQ), prov(TipoProvedor.OPENAI)
    executor = modelo("groq/x", a, preco="1")
    modelos = [executor, modelo("groq/y", a, preco="0.5"), modelo("openai/z", b, preco="9")]
    resultado = escolher(modelos, PapelModelo.VERIFICADOR, executor=executor)
    assert nomes(resultado)[0] == "openai/z"
    assert not tipos(resultado)


def test_verificador_sem_outro_provedor_usa_outro_modelo_e_avisa() -> None:
    a = prov()
    executor = modelo("groq/x", a, preco="1")
    modelos = [executor, modelo("groq/y", a, preco="5")]
    resultado = escolher(modelos, PapelModelo.VERIFICADOR, executor=executor)
    assert nomes(resultado) == ["groq/y", "groq/x"]
    assert tipos(resultado) == {TipoAviso.VERIFICADOR_NO_MESMO_PROVEDOR}


def test_verificador_com_um_modelo_so_roda_nele_e_avisa() -> None:
    executor = modelo("groq/x", prov())
    resultado = escolher([executor], PapelModelo.VERIFICADOR, executor=executor)
    assert nomes(resultado) == ["groq/x"]
    assert tipos(resultado) == {TipoAviso.VERIFICADOR_NO_MESMO_MODELO}


def test_memoria_verificacao_difere_da_sintese() -> None:
    a, b = prov(TipoProvedor.GROQ), prov(TipoProvedor.OPENAI)
    sintese = modelo("groq/x", a, Nivel.N1, preco="0.1")
    modelos = [sintese, modelo("openai/y", b, Nivel.N1, preco="3")]
    resultado = escolher(modelos, PapelModelo.MEMORIA_VERIFICACAO, 1, papel_irmao=sintese)
    assert nomes(resultado)[0] == "openai/y"


# ------------------------------------------------------------------ revisor e imagem


def test_revisor_usa_o_modelo_especial_da_politica_mesmo_fora_da_escada() -> None:
    p = prov()
    safeguard = modelo("groq/openai/gpt-oss-safeguard-20b", p, "especial", caps=(JSON,))
    n2 = modelo("m/n2", p, Nivel.N2, preco="0.01")
    assert nomes(escolher([n2, safeguard], PapelModelo.REVISOR))[0] == safeguard.modelo
    assert nomes(escolher([n2], PapelModelo.REVISOR)) == ["m/n2"]


def test_papel_imagem_nao_tem_nivel_e_designer_depende_de_modelo_de_imagem() -> None:
    p = prov(TipoProvedor.OPENAI)
    imagem = modelo("openai/img", p, "especial", caps=(IMG,))
    texto = modelo("openai/texto", p)
    sem_imagem = ContextoSeletor(modelos=[texto])
    assert not tem_modelo_de_imagem(sem_imagem, politica=POLITICA, agora=AGORA)
    com_imagem = ContextoSeletor(modelos=[texto, imagem])
    assert tem_modelo_de_imagem(com_imagem, politica=POLITICA, agora=AGORA)
    assert nomes(escolher([texto, imagem], PapelModelo.IMAGEM)) == ["openai/img"]


def test_ids_de_provedor_sao_uuid() -> None:
    assert isinstance(prov().id, UUID)


def test_verificador_sobe_de_nivel_para_achar_outro_provedor() -> None:
    """Antes: só o N2 do executor existia no nível e o aviso dizia 'só há um modelo'."""
    a, b = prov(TipoProvedor.OPENAI), prov(TipoProvedor.ANTHROPIC)
    executor = modelo("openai/terra", a, Nivel.N2, preco="2")
    opus = modelo("anthropic/opus", b, Nivel.N3, preco="20")
    resultado = escolher([executor, opus], PapelModelo.VERIFICADOR, executor=executor)
    assert nomes(resultado) == ["anthropic/opus", "openai/terra"]
    assert tipos(resultado) == {TipoAviso.NIVEL_SUBIU}


def test_verificador_prefere_outro_provedor_no_nivel_a_outro_modelo_acima() -> None:
    a, b = prov(TipoProvedor.OPENAI), prov(TipoProvedor.ANTHROPIC)
    executor = modelo("openai/terra", a, Nivel.N2)
    modelos = [executor, modelo("anthropic/sonnet", b, Nivel.N2), modelo("openai/sol", a, Nivel.N3)]
    resultado = escolher(modelos, PapelModelo.VERIFICADOR, executor=executor)
    assert nomes(resultado)[0] == "anthropic/sonnet"
    assert not tipos(resultado)


def test_verificador_mesmo_provedor_acha_outro_modelo_no_nivel_de_cima() -> None:
    a = prov(TipoProvedor.OPENAI)
    executor = modelo("openai/terra", a, Nivel.N2)
    resultado = escolher(
        [executor, modelo("openai/sol", a, Nivel.N3)], PapelModelo.VERIFICADOR, executor=executor
    )
    assert nomes(resultado)[0] == "openai/sol"
    assert tipos(resultado) == {TipoAviso.NIVEL_SUBIU, TipoAviso.VERIFICADOR_NO_MESMO_PROVEDOR}
