"""``escolher_modelos``: o seletor de modelo (especificação §5, "Seletor de modelo").

Passos: (1) papel + dificuldade → nível pela política; (2) filtra modelos ativos com as
capacidades exigidas e contexto maior que o prompt; (3) tira provedores acima do teto ou em
pausa; (4) ordena pela prioridade do usuário; (5) devolve a lista (o 1º é usado, o resto é
reserva).

Regras: sem modelo no nível pedido sobe para o de cima, e se não houver usa o mais forte
disponível (e avisa); Sistema 1 usa o N1 mais rápido; verificador e verificação de memória
preferem outro provedor, senão outro modelo (e avisam se só houver um); conversa privada só com
Ollama; ``somente_se_escolhido`` nunca entra sozinho.

Ordem de reserva: o grupo do nível escolhido, na ordem da prioridade. O seletor não empurra a
reserva para um nível mais caro: se o grupo todo falhar, quem chamou decide (a spec manda
trocar "para o próximo da lista").

É função pura (sem banco, sem relógio global): tudo entra por ``ContextoSeletor``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import Nivel, Prioridade, TipoProvedor
from app.seletor.politica import Politica, PoliticaPapel, obter_politica
from app.seletor.tipos import (
    Capacidade,
    ContextoSeletor,
    ModeloCandidato,
    PapelModelo,
)

_ESCADA: tuple[Nivel, ...] = (Nivel.N1, Nivel.N2, Nivel.N3)
_PESO_DE_QUALIDADE: dict[str, int] = {Nivel.N3.value: 3, Nivel.N2.value: 2, Nivel.N1.value: 1}


class TipoAviso(StrEnum):
    """Coisas que o seletor marca para a linha do tempo (§5)."""

    NIVEL_SUBIU = "nivel_subiu"
    USOU_O_MAIS_FORTE = "usou_o_mais_forte"
    VERIFICADOR_NO_MESMO_MODELO = "verificador_no_mesmo_modelo"
    VERIFICADOR_NO_MESMO_PROVEDOR = "verificador_no_mesmo_provedor"
    SEM_MODELO = "sem_modelo"


class AvisoSeletor(BaseModel):
    tipo: TipoAviso
    detalhe: str = ""


class ResultadoSelecao(BaseModel):
    """Lista ordenada de modelos (o 1º é usado) mais os avisos para a linha do tempo.

    Lista vazia = nada serve (ex.: nenhuma API conectada, ou conversa privada sem Ollama).
    """

    modelos: list[ModeloCandidato] = Field(default_factory=list)
    avisos: list[AvisoSeletor] = Field(default_factory=list)


def niveis_a_partir_de(nivel: Nivel) -> list[Nivel]:
    """N1 → [N1, N2, N3]; N2 → [N2, N3]; N3 → [N3]."""
    return list(_ESCADA[_ESCADA.index(nivel) :])


def _custo_somado(modelo: ModeloCandidato) -> Decimal | None:
    if modelo.preco_entrada is None and modelo.preco_saida is None:
        return None
    return (modelo.preco_entrada or Decimal(0)) + (modelo.preco_saida or Decimal(0))


def _chave_de_custo(m: ModeloCandidato) -> tuple[object, ...]:
    """Mais barato primeiro; preço desconhecido vai para o fim; desempate pela velocidade."""
    custo = _custo_somado(m)
    return (custo is None, custo or Decimal(0), -(m.velocidade_tps or 0), m.modelo)


def _chave_de_velocidade(m: ModeloCandidato) -> tuple[object, ...]:
    """Mais rápido primeiro; velocidade desconhecida vai para o fim; desempate pelo custo."""
    custo = _custo_somado(m)
    return (
        m.velocidade_tps is None,
        -(m.velocidade_tps or 0),
        custo is None,
        custo or Decimal(0),
        m.modelo,
    )


def _chave_de_qualidade(m: ModeloCandidato) -> tuple[object, ...]:
    """Nível mais alto primeiro; dentro do nível, o mais caro (proxy de qualidade)."""
    return (
        -_PESO_DE_QUALIDADE.get(str(m.nivel), 0),
        -(_custo_somado(m) or Decimal(0)),
        -(m.velocidade_tps or 0),
        m.modelo,
    )


def ordenar(
    modelos: Sequence[ModeloCandidato],
    prioridade: Prioridade,
    preferir: Prioridade | None,
    preferir_modelo: str | None = None,
) -> list[ModeloCandidato]:
    """Ordena por custo, velocidade ou qualidade. ``preferir`` do papel vence a do usuário
    (ex.: Sistema 1 sempre por velocidade); ``preferir_modelo`` põe esse modelo na frente.
    """
    criterio = preferir or prioridade
    chave = {
        Prioridade.CUSTO: _chave_de_custo,
        Prioridade.VELOCIDADE: _chave_de_velocidade,
        Prioridade.QUALIDADE: _chave_de_qualidade,
    }[criterio]
    ordenados = sorted(modelos, key=chave)
    if preferir_modelo:
        ordenados = [m for m in ordenados if m.modelo == preferir_modelo] + [
            m for m in ordenados if m.modelo != preferir_modelo
        ]
    return ordenados


def _nivel_do_papel(regra: PoliticaPapel, dificuldade: int, politica: Politica) -> Nivel | None:
    """Nível do papel. ``resposta_direta`` sobe com a dificuldade (``subir_se_dificuldade``)."""
    if regra.nivel is None:
        return None
    if regra.subir_se_dificuldade is not None and dificuldade >= regra.subir_se_dificuldade:
        return politica.dificuldade_para_nivel.get(dificuldade, regra.nivel)
    return regra.nivel


def _afastar_da_referencia(
    modelos: list[ModeloCandidato], referencia: ModeloCandidato
) -> list[ModeloCandidato]:
    """Verificador e verificação de memória: outro provedor, senão outro modelo, senão o mesmo."""
    outro_provedor = [m for m in modelos if m.provedor.id != referencia.provedor.id]
    outro_modelo = [
        m
        for m in modelos
        if m.provedor.id == referencia.provedor.id and m.modelo != referencia.modelo
    ]
    mesmo = [
        m
        for m in modelos
        if m.provedor.id == referencia.provedor.id and m.modelo == referencia.modelo
    ]
    return outro_provedor + outro_modelo + mesmo


def escolher_modelos(
    contexto: ContextoSeletor,
    papel: PapelModelo,
    dificuldade: int,
    precisa: set[Capacidade],
    tokens_prompt: int,
    *,
    politica: Politica | None = None,
    agora: datetime | None = None,
    executor: ModeloCandidato | None = None,
    papel_irmao: ModeloCandidato | None = None,
    preferido: str | None = None,
) -> ResultadoSelecao:
    """Escolhe e ordena os modelos para uma chamada.

    ``executor`` é o modelo que fez o trabalho que o verificador vai conferir (papel
    ``verificador``); ``papel_irmao`` é o modelo da síntese de memória (papel
    ``memoria_verificacao``, ``diferente_de``). ``preferido`` é o modelo que o usuário escolheu
    para o agente (``modelo_padrao``): vai na frente desde que tenha as capacidades, caiba o
    prompt e o provedor esteja disponível, e é o único jeito de usar um modelo
    ``somente_se_escolhido``. ``politica`` e ``agora`` existem para teste.
    """
    politica = politica or obter_politica()
    agora = agora or datetime.now(UTC)
    regra = politica.papeis[papel]
    exigidas = set(regra.capacidades) | precisa
    avisos: list[AvisoSeletor] = []

    elegiveis = [
        m
        for m in contexto.modelos_ativos()
        if exigidas <= set(m.capacidades)
        and m.contexto > tokens_prompt
        and not m.provedor.em_pausa(agora)
        and not m.provedor.passou_do_teto()
        and (not contexto.conversa_privada or m.provedor.tipo is TipoProvedor.OLLAMA)
    ]
    prioridade = contexto.prioridade

    nivel = _nivel_do_papel(regra, dificuldade, politica)
    sem_escolha_explicita = [m for m in elegiveis if not m.somente_se_escolhido]

    if nivel is None:
        # Papel sem nível (imagem): vale qualquer modelo com a capacidade exigida.
        lista = ordenar(sem_escolha_explicita, prioridade, regra.preferir, regra.preferir_modelo)
    else:
        na_escada = [m for m in sem_escolha_explicita if str(m.nivel) in _PESO_DE_QUALIDADE]
        lista = []
        for candidato in niveis_a_partir_de(nivel):
            do_nivel = [m for m in na_escada if m.nivel == candidato]
            if not do_nivel:
                continue
            if candidato != nivel:
                avisos.append(
                    AvisoSeletor(
                        tipo=TipoAviso.NIVEL_SUBIU,
                        detalhe=f"Sem modelo {nivel.value}; usando {candidato.value}.",
                    )
                )
            lista = ordenar(do_nivel, prioridade, regra.preferir, regra.preferir_modelo)
            break
        else:
            if na_escada:
                lista = ordenar(na_escada, Prioridade.QUALIDADE, None)
                avisos.append(
                    AvisoSeletor(
                        tipo=TipoAviso.USOU_O_MAIS_FORTE,
                        detalhe=f"Sem modelo {nivel.value} ou acima; usando o mais forte que há.",
                    )
                )
        # O modelo preferido do papel pode estar fora da escada (ex.: revisor, nível especial).
        if regra.preferir_modelo:
            especial = [
                m
                for m in sem_escolha_explicita
                if m.modelo == regra.preferir_modelo and m not in lista
            ]
            lista = especial + lista

    if preferido:
        escolhido = next((m for m in elegiveis if m.modelo == preferido), None)
        if escolhido is not None:
            lista = [escolhido] + [m for m in lista if m is not escolhido]
            # A escolha do usuário vence o nível: os avisos de nível deixam de valer.
            avisos = [a for a in avisos if a.tipo is not TipoAviso.NIVEL_SUBIU]

    referencia = executor if regra.diferente_do_executor else None
    if regra.diferente_de is not None:
        referencia = papel_irmao
    if referencia is not None and lista:
        lista = _afastar_da_referencia(lista, referencia)
        primeiro = lista[0]
        if primeiro.provedor.id == referencia.provedor.id:
            igual = primeiro.modelo == referencia.modelo
            avisos.append(
                AvisoSeletor(
                    tipo=(
                        TipoAviso.VERIFICADOR_NO_MESMO_MODELO
                        if igual
                        else TipoAviso.VERIFICADOR_NO_MESMO_PROVEDOR
                    ),
                    detalhe=(
                        "Só há um modelo disponível; a verificação roda nele."
                        if igual
                        else "Só há modelos do mesmo provedor; a verificação usa outro modelo."
                    ),
                )
            )

    if not lista:
        detalhe = (
            "Conversa privada sem modelo local (Ollama) disponível."
            if contexto.conversa_privada
            else "Nenhum modelo conectado serve para este papel."
        )
        avisos.append(AvisoSeletor(tipo=TipoAviso.SEM_MODELO, detalhe=detalhe))
    return ResultadoSelecao(modelos=lista, avisos=avisos)


def tem_modelo_de_imagem(
    contexto: ContextoSeletor,
    *,
    politica: Politica | None = None,
    agora: datetime | None = None,
) -> bool:
    """True se há um modelo ativo com a capacidade ``imagem`` (o Designer só entra então, §5)."""
    resultado = escolher_modelos(
        contexto,
        PapelModelo.IMAGEM,
        dificuldade=1,
        precisa=set(),
        tokens_prompt=0,
        politica=politica,
        agora=agora,
    )
    return bool(resultado.modelos)
