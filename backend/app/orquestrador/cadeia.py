"""Ciclo de vida de uma cadeia (especificação §6, "Regras de execução").

As decisões são funções puras (sem banco nem Redis), para os jobs chamarem e
os testes de tabela cobrirem: que etapas já podem rodar (``depende_de``, até 3
em paralelo), limites de rodadas e passos, progresso da etapa e o que o
``avancar_cadeia`` deve fazer agora. As funções ``async`` com sessão gravam no
banco e ficam para a parte da cadeia de ponta a ponta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa
from app.orquestrador.estados import EM_ANDAMENTO_ETAPA

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PARALELO_POR_CADEIA = 3
"""Etapas independentes rodando ao mesmo tempo numa cadeia (§6)."""

PAPEL_VERIFICADOR = "verificador"

PROGRESSO_INICIAL = 10
PROGRESSO_MAXIMO_ANTES_DE_ENTREGAR = 85


@dataclass(frozen=True, slots=True)
class LimitesCadeia:
    """Limites da cadeia; os valores vêm de ``config/politica.yaml`` (§5)."""

    rodadas: int = 3
    passos: int = 10
    tokens: int = 200_000
    especialistas: int = 5
    paralelo: int = PARALELO_POR_CADEIA


@dataclass(frozen=True, slots=True)
class EtapaResumo:
    """O mínimo de uma etapa para decidir o avanço da cadeia."""

    etapa_id: UUID
    ordem: int
    depende_de: tuple[int, ...]
    status: StatusEtapa
    especialista: str = ""
    tentativa: int = 1

    @property
    def eh_verificador(self) -> bool:
        return self.especialista == PAPEL_VERIFICADOR


AcaoAvanco = Literal["executar", "aguardar", "verificar", "falhar", "limite"]


@dataclass(frozen=True, slots=True)
class DecisaoAvanco:
    """O que o ``avancar_cadeia`` faz agora.

    - ``executar``: enfileirar ``executar_etapa`` para ``etapas``;
    - ``aguardar``: há etapas rodando, nada a fazer até uma terminar;
    - ``verificar``: todas as etapas de execução terminaram → ``verificar_cadeia``;
    - ``falhar``: uma etapa falhou ou a cadeia travou (``motivo``);
    - ``limite``: bateu no máximo de passos → a Sora entrega o que tem e pergunta.
    """

    acao: AcaoAvanco
    etapas: tuple[EtapaResumo, ...] = field(default_factory=tuple)
    motivo: str = ""


# ---------- funções puras ----------


def tentativas_atuais(etapas: list[EtapaResumo]) -> dict[int, EtapaResumo]:
    """A tentativa mais nova de cada ``ordem`` (as reprovadas ficam para trás)."""
    atuais: dict[int, EtapaResumo] = {}
    for etapa in etapas:
        guardada = atuais.get(etapa.ordem)
        if guardada is None or etapa.tentativa > guardada.tentativa:
            atuais[etapa.ordem] = etapa
    return atuais


def _de_execucao(etapas: list[EtapaResumo]) -> list[EtapaResumo]:
    return [e for e in tentativas_atuais(etapas).values() if not e.eh_verificador]


def em_andamento(etapas: list[EtapaResumo]) -> list[EtapaResumo]:
    """Etapas ocupando vaga de paralelo (executando ou pausadas)."""
    return [e for e in tentativas_atuais(etapas).values() if e.status in EM_ANDAMENTO_ETAPA]


def etapas_prontas(
    etapas: list[EtapaResumo], paralelo: int = PARALELO_POR_CADEIA
) -> list[EtapaResumo]:
    """Etapas pendentes cujas dependências já terminaram, respeitando o limite de paralelo.

    O Verificador nunca entra aqui: ele roda pelo ``verificar_cadeia`` quando
    todas as outras terminam. Dependência que não existe no plano nunca fica
    pronta (o plano é validado antes; aqui só não deixa rodar fora de ordem).
    """
    atuais = tentativas_atuais(etapas)
    vagas = paralelo - len(em_andamento(etapas))
    if vagas <= 0:
        return []
    prontas = [
        e
        for e in sorted(atuais.values(), key=lambda e: e.ordem)
        if e.status == StatusEtapa.PENDENTE
        and not e.eh_verificador
        and all(d in atuais and atuais[d].status == StatusEtapa.CONCLUIDA for d in e.depende_de)
    ]
    return prontas[:vagas]


def todas_concluidas(etapas: list[EtapaResumo]) -> bool:
    """Todas as etapas de execução (sem o Verificador) terminaram com sucesso."""
    execucao = _de_execucao(etapas)
    return bool(execucao) and all(e.status == StatusEtapa.CONCLUIDA for e in execucao)


def etapas_com_falha(etapas: list[EtapaResumo]) -> list[EtapaResumo]:
    """Etapas de execução que falharam ou foram canceladas (na tentativa atual)."""
    ruins = {StatusEtapa.FALHOU, StatusEtapa.CANCELADA}
    return [e for e in _de_execucao(etapas) if e.status in ruins]


def pode_iniciar_etapa(passos_feitos: int, limites: LimitesCadeia) -> bool:
    """Ainda cabe mais uma etapa executada nesta cadeia (máximo de passos)."""
    return passos_feitos < limites.passos


def pode_nova_rodada(rodada: int, limites: LimitesCadeia) -> bool:
    """O Verificador ainda pode rodar mais uma vez (máximo de rodadas)."""
    return rodada < limites.rodadas


def passou_dos_limites(rodada: int, passos: int, limites: LimitesCadeia) -> bool:
    """A cadeia passou do máximo de rodadas ou de passos."""
    return rodada > limites.rodadas or passos > limites.passos


def decidir_avanco(
    etapas: list[EtapaResumo], *, passos_feitos: int, limites: LimitesCadeia | None = None
) -> DecisaoAvanco:
    """O miolo do ``avancar_cadeia``: olha as etapas e diz o próximo passo."""
    limites = limites or LimitesCadeia()
    falhas = etapas_com_falha(etapas)
    if falhas:
        ordens = ", ".join(str(e.ordem) for e in falhas)
        return DecisaoAvanco("falhar", tuple(falhas), f"etapa {ordens} não terminou")
    if todas_concluidas(etapas):
        return DecisaoAvanco("verificar")
    prontas = etapas_prontas(etapas, limites.paralelo)
    if prontas:
        vagas = limites.passos - passos_feitos
        if vagas <= 0:
            return DecisaoAvanco("limite", motivo=f"limite de {limites.passos} passos")
        return DecisaoAvanco("executar", tuple(prontas[:vagas]))
    if em_andamento(etapas):
        return DecisaoAvanco("aguardar")
    return DecisaoAvanco("falhar", motivo="nenhuma etapa pode rodar (dependências travadas)")


def progresso_da_etapa(
    chamadas_feitas: int, limite_chamadas: int, entregou: bool, anterior: int = 0
) -> int:
    """Progresso de 0 a 100: 10 ao começar, até 85 pelas ferramentas, 100 no ``entregar``.

    Nunca volta para trás (§6, "Progresso da etapa").
    """
    if entregou:
        return 100
    if limite_chamadas <= 0:
        calculado = PROGRESSO_INICIAL
    else:
        feitas = min(max(chamadas_feitas, 0), limite_chamadas)
        faixa = PROGRESSO_MAXIMO_ANTES_DE_ENTREGAR - PROGRESSO_INICIAL
        calculado = PROGRESSO_INICIAL + (faixa * feitas) // limite_chamadas
    return max(anterior, min(calculado, PROGRESSO_MAXIMO_ANTES_DE_ENTREGAR))


def chave_de_cancelamento(cadeia_id: UUID) -> str:
    """Chave que os workers conferem antes de cada chamada (§6, "Cancelamento")."""
    return f"cancelar:{cadeia_id}"


# ---------- banco (cadeia de ponta a ponta, próxima parte) ----------


async def criar_cadeia(
    sessao: AsyncSession,
    *,
    usuario_id: UUID,
    conversa_id: UUID,
    pedido_id: UUID,
    orcamento_tokens: int,
    versao: int = 1,
) -> UUID:
    """Cria a cadeia em ``planejando`` e marca a conversa como ``projeto``."""
    raise NotImplementedError


async def mudar_status_cadeia(sessao: AsyncSession, cadeia_id: UUID, para: StatusCadeia) -> None:
    """Troca o estado da cadeia (checando a transição) e emite ``cadeia.atualizada``."""
    raise NotImplementedError


async def pegar_etapa(sessao: AsyncSession, etapa_id: UUID) -> bool:
    """``UPDATE ... WHERE status = 'pendente' RETURNING id``: sem trabalho em dobro.

    Devolve ``False`` se outro worker já pegou a etapa.
    """
    raise NotImplementedError


async def mudar_status_etapa(
    sessao: AsyncSession,
    etapa_id: UUID,
    para: StatusEtapa,
    *,
    erro: str | None = None,
) -> None:
    """Troca o estado da etapa e emite ``etapa.atualizada``."""
    raise NotImplementedError


async def cancelar_cadeia(sessao: AsyncSession, cadeia_id: UUID) -> None:
    """Marca ``cancelada`` e grava ``cancelar:{cadeia_id}`` no Redis."""
    raise NotImplementedError
