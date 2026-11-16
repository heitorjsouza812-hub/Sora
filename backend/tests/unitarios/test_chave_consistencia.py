"""Chave: consistência entre as tabelas de ferramentas.

Cada ferramenta do registro precisa ter, ao mesmo tempo: esquema Pydantic com descrição,
executor importável e assíncrono, rótulo em PT-BR, decisão EXPLÍCITA na política do revisor
(nada pode cair no padrão por esquecimento) e nome conhecido pelo app. Quando uma tabela
diverge, o teste diz qual nome ficou de fora.
"""

from __future__ import annotations

import asyncio
import re
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.agentes.ancora import FERRAMENTAS_DA_ANCORA
from app.agentes.ferramentas_do_turno import ESSENCIAIS, GRUPOS_ESCONDIDOS
from app.agentes.montagem import FERRAMENTAS_NAVEGADOR
from app.agentes.montagem import FERRAMENTAS_POR_PAPEL as POR_PAPEL_MONTAGEM
from app.api.agentes import FERRAMENTAS_CONHECIDAS
from app.ferramentas import rotulos
from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL as POR_PAPEL_API
from app.ferramentas.registro import (
    ESQUEMAS,
    FERRAMENTAS_QUE_ENCERRAM,
    MODULO_DA_FERRAMENTA,
    esquemas_das_proximas_fases,
)
from app.revisor.politica import (
    CARTAO_FIXO,
    LIVRES,
    REVISADAS,
    SEGURAS_SEM_SUPERVISAO,
    Politica,
    politica_da_ferramenta,
)

RAIZ = Path(__file__).resolve().parents[3]
TODAS = sorted(ESQUEMAS)

# Nomes antigos que só vivem em ``esquemas_das_proximas_fases`` (o motor atual não os registra).
LEGADO = {"navegador_ler", "navegador_agir"}


def _executor(nome: str):
    modulo = MODULO_DA_FERRAMENTA.get(nome, f"app.ferramentas.{nome}")
    return getattr(import_module(modulo), nome)


def test_inventario_tem_as_ferramentas_esperadas() -> None:
    assert len(ESQUEMAS) >= 64
    assert {"falar", "perguntar", "computador_agir", "executar_comando"} <= set(ESQUEMAS)


@pytest.mark.parametrize("nome", TODAS)
def test_cada_ferramenta_tem_executor_assincrono(nome: str) -> None:
    funcao = _executor(nome)
    assert asyncio.iscoroutinefunction(funcao), f"{nome}: o executor precisa ser async"


@pytest.mark.parametrize("nome", TODAS)
def test_cada_ferramenta_tem_esquema_e_descricao(nome: str) -> None:
    esquema = ESQUEMAS[nome]
    assert issubclass(esquema, BaseModel)
    descricao = (esquema.__doc__ or "").strip()
    assert len(descricao) >= 15, f"{nome}: o modelo lê a docstring do esquema como descrição"
    esquema.model_json_schema()  # esquema precisa virar JSON Schema (o provedor exige)


@pytest.mark.parametrize("nome", TODAS)
def test_cada_ferramenta_tem_rotulo_proprio_em_ptbr(nome: str) -> None:
    assert nome in rotulos._ROTULOS, f"{nome}: sem rótulo no painel Trabalho"
    texto = rotulos.rotulo_do_passo(nome, {})
    assert texto, nome
    assert "_" not in texto, f"{nome}: o rótulo mostra nome técnico: {texto!r}"


@pytest.mark.parametrize("nome", TODAS)
def test_cada_ferramenta_tem_decisao_explicita_na_politica(nome: str) -> None:
    explicitas = LIVRES | CARTAO_FIXO | REVISADAS
    assert nome in explicitas, (
        f"{nome}: sem decisão explícita (livre/cartão/revisor) em app/revisor/politica.py"
    )
    assert sum(nome in lista for lista in (LIVRES, CARTAO_FIXO, REVISADAS)) == 1, nome


def test_ferramentas_com_efeito_nunca_sao_livres() -> None:
    for nome in (
        "executar_comando",
        "computador_agir",
        "navegador_acao",
        "navegador_tecla",
        "navegador_lote",
    ):
        assert politica_da_ferramenta(nome) is Politica.REVISOR, nome
    for nome in (
        "esquecer_memoria",
        "apagar_habilidade",
        "adicionar_servidor_mcp",
        "propor_instrucoes",
        "criar_agente",
    ):
        assert politica_da_ferramenta(nome) is Politica.CARTAO_FIXO, nome


def test_listas_da_politica_so_citam_ferramentas_que_existem() -> None:
    conhecidas = set(ESQUEMAS) | set(esquemas_das_proximas_fases()) | LEGADO
    # meta-ferramentas do catálogo preguiçoso e conector externo, que não são ``@tool`` próprias
    externas = {
        "conectores_buscar_ferramentas",
        "conectores_carregar_ferramenta",
        "conectores_executar_ferramenta",
        "chamar_conector",
    }
    for lista in (LIVRES, CARTAO_FIXO, REVISADAS, SEGURAS_SEM_SUPERVISAO):
        fantasmas = set(lista) - conhecidas - externas
        assert not fantasmas, f"nomes da política sem ferramenta: {sorted(fantasmas)}"


def test_seguras_sem_supervisao_nao_tem_efeito_no_mundo() -> None:
    assert not (SEGURAS_SEM_SUPERVISAO & (CARTAO_FIXO | REVISADAS))
    perigosas = {
        "executar_comando",
        "computador_agir",
        "computador_abrir_programa",
        "navegador_acao",
        "navegador_tecla",
        "navegador_lote",
        "escrever_arquivo",
        "enviar_para_agente",
        "agendar",
        "lembrar",
        "esquecer_memoria",
        "propor_instrucoes",
        "criar_agente",
        "propor_grupo",
        "adicionar_servidor_mcp",
        "disparar_especialista",
    }
    assert not (perigosas & SEGURAS_SEM_SUPERVISAO)


def test_ferramentas_que_encerram_existem() -> None:
    assert FERRAMENTAS_QUE_ENCERRAM <= set(ESQUEMAS)


def test_tabelas_por_papel_so_citam_ferramentas_registradas() -> None:
    for tabela in (POR_PAPEL_MONTAGEM, POR_PAPEL_API):
        for papel, nomes in tabela.items():
            ausentes = set(nomes) - set(ESQUEMAS)
            assert not ausentes, f"{papel}: {sorted(ausentes)} não estão no registro"
    for papel, nomes in FERRAMENTAS_DA_ANCORA.items():
        assert not (set(nomes) - set(ESQUEMAS)), papel
    assert not (set(ESSENCIAIS) - set(ESQUEMAS))
    assert not (set(GRUPOS_ESCONDIDOS) - set(ESQUEMAS))


def test_todo_nome_que_o_bot_recebe_por_papel_e_validavel_no_patch() -> None:
    """O app manda de volta a lista inteira do bot no PATCH: nada que o bot já recebe pode dar
    422 só porque a API não o conhece."""
    esperados = set(POR_PAPEL_API["individual"]) | set(FERRAMENTAS_NAVEGADOR)
    faltam = esperados - FERRAMENTAS_CONHECIDAS
    assert not faltam, sorted(faltam)
    assert {"computador_observar", "computador_agir"} <= FERRAMENTAS_CONHECIDAS
    assert {"consultar_cliente", "consultar_conhecimento"} <= FERRAMENTAS_CONHECIDAS


def test_conhecidas_so_citam_ferramentas_registradas() -> None:
    fantasmas = FERRAMENTAS_CONHECIDAS - set(ESQUEMAS)
    assert not fantasmas, sorted(fantasmas)


def test_ferramentas_perigosas_nao_podem_ser_dadas_ao_bot_pela_api() -> None:
    for nome in ("executar_comando", "adicionar_servidor_mcp", "propor_grupo", "criar_agente"):
        assert nome not in FERRAMENTAS_CONHECIDAS or nome in POR_PAPEL_API["sora"], nome


def test_app_so_usa_nomes_de_ferramenta_que_existem_no_backend() -> None:
    usados: set[str] = set()
    for arquivo in ("src/data/ferramentas.ts", "src/components/settings/ComputadorPC.tsx"):
        texto = (RAIZ / "app" / arquivo).read_text(encoding="utf-8")
        usados |= {
            n
            for n in re.findall(r"'((?:[a-z]+_)+[a-z]+)'", texto)
            if n.startswith(("computador_", "navegador_", "consultar_", "buscar_", "ler_"))
            or n in {"escrever_arquivo", "gerar_imagem"}
        }
    assert usados, "não achei nomes de ferramenta no app (regex quebrada?)"
    divergentes = usados - set(ESQUEMAS)
    assert not divergentes, f"o app usa nomes que o backend não tem: {sorted(divergentes)}"
    assert not (usados - FERRAMENTAS_CONHECIDAS), "o PATCH do bot daria 422"


def test_app_oferece_ao_bot_so_ferramentas_aceitas_pela_api() -> None:
    texto = (RAIZ / "app/src/data/ferramentas.ts").read_text(encoding="utf-8")
    ids = set(re.findall(r"id:\s*'([a-z_]+)'", texto))
    assert ids and ids <= FERRAMENTAS_CONHECIDAS, sorted(ids - FERRAMENTAS_CONHECIDAS)
