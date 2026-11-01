"""Monitor de contexto por agente, com compactação automática antes de a janela encher.

Ideia vista no OpenBot (github.com/nightly-labs/openbot, PolyForm Noncommercial): cada agente
mostra o quanto da janela de contexto já usou, e o sistema compacta a conversa antes de o modelo
recusar o pedido. **Nenhum código foi copiado** (a licença deles não permite uso comercial);
esta é uma implementação própria da Sora — veja ``docs/referencias/openbot.md``.

Como funciona na Sora:

- depois de cada chamada de modelo o worker chama :func:`medir` com o uso informado pelo
  provedor (``tokens_entrada`` da última chamada). Quando o provedor não informa, a Sora estima
  pelos caracteres do histórico (1 token ≈ 4 caracteres) e marca ``estimado=True``;
- o :class:`MonitorContexto` guarda o último estado de cada fio (o chat do agente ou uma tarefa
  de canal) e diz o que fazer: nada, avisar ou compactar;
- a compactação é a mesma de ``app/memoria/compactacao.py`` (resumo cumulativo por lotes). Aqui
  só decidimos **quando** disparar e **quantas mensagens** resumir para voltar abaixo da meta;
- o usuário pode pedir "Compactar agora" mesmo abaixo do limite, mas não enquanto o agente
  estiver no meio de um turno, com mensagem na fila ou já compactando.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

CARACTERES_POR_TOKEN = 4
"""Estimativa grosseira quando o provedor não informa o uso (vale bem para PT-BR e código)."""

JANELA_PADRAO = 32_000
"""Janela usada quando o catálogo não sabe o tamanho do modelo."""

LIMITE_AVISO = 0.70
"""A partir daqui o medidor fica amarelo na interface."""

LIMITE_COMPACTAR = 0.80
"""A partir daqui a Sora compacta sozinha antes do próximo turno."""

LIMITE_CHEIO = 0.95
"""Acima disso o próximo turno não começa sem compactar (o modelo provavelmente recusaria)."""

META_APOS_COMPACTAR = 0.50
"""A compactação resume mensagens até o uso estimado cair para esta fração."""

RESERVA_RESPOSTA = 4_000
"""Tokens guardados para a resposta do modelo; não contam como espaço livre."""

MIN_MENSAGENS_NA_JANELA = 8
"""Mesmo compactando forte, as últimas mensagens ficam inteiras."""


class NivelContexto(StrEnum):
    OK = "ok"
    ATENCAO = "atencao"
    COMPACTAR = "compactar"
    CHEIO = "cheio"


class SituacaoCompactacao(StrEnum):
    PARADA = "parada"
    COMPACTANDO = "compactando"
    FALHOU = "falhou"


@dataclass(frozen=True, slots=True)
class EstadoContexto:
    """Quanto da janela um fio de um agente já usa. Vai para a interface como medidor."""

    agente_id: UUID
    fio: str
    """``"principal"`` para o chat do agente; ``"canal:<tarefa_id>"`` para trabalho de canal."""
    tokens: int
    janela: int
    estimado: bool
    nivel: NivelContexto
    compactacao: SituacaoCompactacao = SituacaoCompactacao.PARADA
    medido_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def fracao(self) -> float:
        util = max(1, self.janela - RESERVA_RESPOSTA)
        return min(1.0, self.tokens / util)

    @property
    def porcentagem(self) -> int:
        return round(self.fracao * 100)

    @property
    def compacta_em(self) -> int:
        """Quantos tokens disparam a compactação automática (para o texto do medidor)."""
        return int(max(1, self.janela - RESERVA_RESPOSTA) * LIMITE_COMPACTAR)


def estimar_tokens(textos: Sequence[str]) -> int:
    """Estimativa por caracteres. Sempre arredonda para cima: errar para mais é o lado seguro."""
    total = sum(len(t) for t in textos)
    return -(-total // CARACTERES_POR_TOKEN)


def nivel_de(fracao: float) -> NivelContexto:
    if fracao >= LIMITE_CHEIO:
        return NivelContexto.CHEIO
    if fracao >= LIMITE_COMPACTAR:
        return NivelContexto.COMPACTAR
    if fracao >= LIMITE_AVISO:
        return NivelContexto.ATENCAO
    return NivelContexto.OK


def medir(
    agente_id: UUID,
    fio: str,
    *,
    janela: int | None,
    tokens_informados: int | None = None,
    textos_do_historico: Sequence[str] = (),
) -> EstadoContexto:
    """Mede pelo uso que o provedor informou; sem ele, estima pelo texto do histórico."""
    janela_real = janela if janela and janela > RESERVA_RESPOSTA else JANELA_PADRAO
    if tokens_informados is not None and tokens_informados >= 0:
        tokens, estimado = tokens_informados, False
    else:
        tokens, estimado = estimar_tokens(textos_do_historico), True
    util = max(1, janela_real - RESERVA_RESPOSTA)
    return EstadoContexto(
        agente_id=agente_id,
        fio=fio,
        tokens=tokens,
        janela=janela_real,
        estimado=estimado,
        nivel=nivel_de(min(1.0, tokens / util)),
    )


Decisao = Literal["seguir", "compactar_antes", "esperar", "recusar"]


@dataclass(frozen=True, slots=True)
class DecisaoCompactacao:
    decisao: Decisao
    motivo: str


def decidir_antes_do_turno(estado: EstadoContexto) -> DecisaoCompactacao:
    """O worker chama antes de começar um turno do agente neste fio."""
    if estado.compactacao is SituacaoCompactacao.COMPACTANDO:
        return DecisaoCompactacao("esperar", "A conversa está sendo compactada.")
    if estado.nivel in (NivelContexto.COMPACTAR, NivelContexto.CHEIO):
        return DecisaoCompactacao(
            "compactar_antes", f"Contexto em {estado.porcentagem}% da janela."
        )
    return DecisaoCompactacao("seguir", "")


def pedir_compactacao_manual(
    estado: EstadoContexto, *, turno_rodando: bool, itens_na_fila: int
) -> DecisaoCompactacao:
    """Botão "Compactar agora": vale abaixo do limite, mas não com trabalho em andamento."""
    if estado.compactacao is SituacaoCompactacao.COMPACTANDO:
        return DecisaoCompactacao("recusar", "Já estou compactando esta conversa.")
    if turno_rodando:
        return DecisaoCompactacao("recusar", "Espere o agente terminar o que está fazendo.")
    if itens_na_fila:
        return DecisaoCompactacao(
            "recusar", "Há mensagens na fila deste agente; compacte depois que elas rodarem."
        )
    return DecisaoCompactacao("compactar_antes", "Pedido do usuário.")


def mensagens_para_liberar(
    tokens_por_mensagem: Sequence[int], janela: int, meta: float = META_APOS_COMPACTAR
) -> int:
    """Quantas mensagens antigas (do começo da lista) resumir para o uso cair até a ``meta``.

    ``tokens_por_mensagem`` vem em ordem cronológica e só cobre o que ainda está fora do resumo.
    As últimas ``MIN_MENSAGENS_NA_JANELA`` nunca entram; o resumo novo é estimado em 10% do que
    ele substitui.
    """
    util = max(1, janela - RESERVA_RESPOSTA)
    alvo = int(util * meta)
    total = sum(tokens_por_mensagem)
    candidatas = max(0, len(tokens_por_mensagem) - MIN_MENSAGENS_NA_JANELA)
    removidos = 0
    for indice in range(candidatas):
        if total - removidos + removidos // 10 <= alvo:
            return indice
        removidos += tokens_por_mensagem[indice]
    return candidatas


class MonitorContexto:
    """Último estado de cada fio, em memória do worker (o banco guarda só o resumo).

    Depois de reiniciar, o medidor volta na primeira medição; até lá a interface não mostra
    número nenhum, em vez de mostrar um número velho.
    """

    def __init__(self) -> None:
        self._estados: dict[tuple[UUID, str], EstadoContexto] = {}

    def registrar(self, estado: EstadoContexto) -> EstadoContexto:
        anterior = self._estados.get((estado.agente_id, estado.fio))
        if anterior is not None and anterior.compactacao is SituacaoCompactacao.COMPACTANDO:
            estado = replace(estado, compactacao=SituacaoCompactacao.COMPACTANDO)
        self._estados[(estado.agente_id, estado.fio)] = estado
        return estado

    def estado(self, agente_id: UUID, fio: str = "principal") -> EstadoContexto | None:
        return self._estados.get((agente_id, fio))

    def do_agente(self, agente_id: UUID) -> list[EstadoContexto]:
        return sorted(
            (e for (a, _), e in self._estados.items() if a == agente_id), key=lambda e: e.fio
        )

    def comecar_compactacao(self, agente_id: UUID, fio: str) -> bool:
        """Marca o fio como compactando. Devolve ``False`` se já estava (evita dois jobs)."""
        atual = self._estados.get((agente_id, fio))
        if atual is None:
            return True
        if atual.compactacao is SituacaoCompactacao.COMPACTANDO:
            return False
        self._estados[(agente_id, fio)] = replace(
            atual, compactacao=SituacaoCompactacao.COMPACTANDO
        )
        return True

    def terminar_compactacao(
        self, agente_id: UUID, fio: str, *, ok: bool, tokens_depois: int | None = None
    ) -> EstadoContexto | None:
        atual = self._estados.get((agente_id, fio))
        if atual is None:
            return None
        if not ok:
            novo = replace(atual, compactacao=SituacaoCompactacao.FALHOU)
        else:
            tokens = atual.tokens if tokens_depois is None else tokens_depois
            util = max(1, atual.janela - RESERVA_RESPOSTA)
            novo = replace(
                atual,
                tokens=tokens,
                estimado=tokens_depois is not None or atual.estimado,
                nivel=nivel_de(min(1.0, tokens / util)),
                compactacao=SituacaoCompactacao.PARADA,
                medido_em=datetime.now(UTC),
            )
        self._estados[(agente_id, fio)] = novo
        return novo

    def esquecer_agente(self, agente_id: UUID) -> None:
        for chave in [c for c in self._estados if c[0] == agente_id]:
            del self._estados[chave]
