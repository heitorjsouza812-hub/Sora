"""Fila FIFO de mensagens por agente, com pausa, retomada, cancelamento e recuperação após queda.

Ideia vista no OpenBot (github.com/nightly-labs/openbot, PolyForm Noncommercial): cada agente
tem a própria fila; o que chega enquanto ele trabalha espera a vez, e o usuário pode pausar,
cancelar ou editar o que ainda não começou. **Nenhum código foi copiado**; esta é uma
implementação própria da Sora — veja ``docs/referencias/openbot.md``.

Regras da Sora:

- cada item entra com um ``seq`` crescente por agente e sai na mesma ordem (FIFO);
- um agente tem **pistas**: a ``principal`` (o chat dele, um turno por vez) e as pistas de
  tarefa (``tarefa:<id>``), que rodam em paralelo até ``limite_tarefas`` (padrão 2, máximo 8).
  Dentro de cada pista, só um item roda por vez;
- **pausar** a fila segura tudo o que ainda não começou; o que já roda termina normalmente;
- item em **edição** segura a pista dele (para não sair um texto que o usuário está mudando);
- **cancelar** só vale para o que ainda não começou; para parar um turno em andamento o worker
  usa ``interromper`` (fica ``cancelado`` com motivo);
- **chave** deixa o enfileiramento idempotente: repetir o mesmo envio não duplica;
- **depois de uma queda**: ``iniciando`` volta para a fila (nada chegou ao modelo ainda) e
  ``rodando`` vira ``interrompido`` — o usuário decide se repete, porque o modelo pode ter
  feito parte do trabalho (efeito externo não tem garantia de "uma vez só").
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

LIMITE_TAREFAS_PADRAO = 2
LIMITE_TAREFAS_MAXIMO = 8
MAX_ITENS_NA_FILA = 200
"""Por agente; acima disso a fila recusa para não esconder um laço entre agentes."""

PISTA_PRINCIPAL = "principal"


class StatusItem(StrEnum):
    NA_FILA = "na_fila"
    INICIANDO = "iniciando"
    RODANDO = "rodando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"
    INTERROMPIDO = "interrompido"


ABERTOS = frozenset({StatusItem.NA_FILA, StatusItem.INICIANDO, StatusItem.RODANDO})
ATIVOS = frozenset({StatusItem.INICIANDO, StatusItem.RODANDO})


class OrigemItem(StrEnum):
    USUARIO = "usuario"
    AGENTE = "agente"
    CANAL = "canal"
    ROTINA = "rotina"
    MENSAGEIRO = "mensageiro"
    """Telegram e outros apps de mensagem (``app/canais``)."""


class MotivoEspera(StrEnum):
    """Por que o próximo item ainda não saiu (aparece na interface ao lado do item)."""

    FILA_PAUSADA = "fila_pausada"
    AGENTE_OCUPADO = "agente_ocupado"
    LIMITE_DE_TAREFAS = "limite_de_tarefas"
    EM_EDICAO = "em_edicao"


class ErroFila(Exception):
    """Operação recusada; o texto vai para o usuário."""


@dataclass(frozen=True, slots=True)
class ItemFila:
    id: UUID
    usuario_id: UUID
    agente_id: UUID
    seq: int
    pista: str
    origem: OrigemItem
    texto: str
    anexos: tuple[UUID, ...] = ()
    de_agente_id: UUID | None = None
    responde_a: UUID | None = None
    salto: int = 0
    chave: str | None = None
    status: StatusItem = StatusItem.NA_FILA
    em_edicao_por: str | None = None
    motivo: str | None = None
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    iniciado_em: datetime | None = None
    terminado_em: datetime | None = None


@dataclass(slots=True)
class EstadoFila:
    agente_id: UUID
    pausada: bool = False
    limite_tarefas: int = LIMITE_TAREFAS_PADRAO


def pista_de_tarefa(tarefa_id: UUID) -> str:
    return f"tarefa:{tarefa_id}"


def validar_limite(limite: int) -> int:
    if not 1 <= limite <= LIMITE_TAREFAS_MAXIMO:
        raise ErroFila(f"O limite de tarefas paralelas vai de 1 a {LIMITE_TAREFAS_MAXIMO}.")
    return limite


class ArmazemFila(Protocol):
    """Persistência da fila. No servidor, a tabela ``fila_mensagens`` (migração 0005)."""

    async def estado(self, agente_id: UUID) -> EstadoFila: ...
    async def salvar_estado(self, estado: EstadoFila) -> None: ...
    async def itens(self, agente_id: UUID) -> list[ItemFila]: ...
    async def por_chave(self, agente_id: UUID, chave: str) -> ItemFila | None: ...
    async def proximo_seq(self, agente_id: UUID) -> int: ...
    async def gravar(self, item: ItemFila) -> None: ...
    async def todos_abertos(self) -> list[ItemFila]: ...


class ArmazemFilaEmMemoria:
    """Para testes e para rodar sem banco."""

    def __init__(self) -> None:
        self._estados: dict[UUID, EstadoFila] = {}
        self._itens: dict[UUID, ItemFila] = {}
        self._seq: dict[UUID, itertools.count[int]] = {}

    async def estado(self, agente_id: UUID) -> EstadoFila:
        return self._estados.setdefault(agente_id, EstadoFila(agente_id))

    async def salvar_estado(self, estado: EstadoFila) -> None:
        self._estados[estado.agente_id] = estado

    async def itens(self, agente_id: UUID) -> list[ItemFila]:
        return sorted((i for i in self._itens.values() if i.agente_id == agente_id), key=_ordem)

    async def por_chave(self, agente_id: UUID, chave: str) -> ItemFila | None:
        for item in self._itens.values():
            if item.agente_id == agente_id and item.chave == chave:
                return item
        return None

    async def proximo_seq(self, agente_id: UUID) -> int:
        return next(self._seq.setdefault(agente_id, itertools.count(1)))

    async def gravar(self, item: ItemFila) -> None:
        self._itens[item.id] = item

    async def todos_abertos(self) -> list[ItemFila]:
        return sorted((i for i in self._itens.values() if i.status in ABERTOS), key=_ordem)


def _ordem(item: ItemFila) -> tuple[str, int]:
    return (str(item.agente_id), item.seq)


@dataclass(frozen=True, slots=True)
class Liberacao:
    """Resultado de :meth:`FilaAgente.proximos`: o que pode começar e o que espera, e por quê."""

    iniciar: list[ItemFila]
    esperando: dict[UUID, MotivoEspera]


class FilaAgente:
    def __init__(self, armazem: ArmazemFila) -> None:
        self._armazem = armazem

    # ---------- entrada ----------

    async def enfileirar(
        self,
        *,
        usuario_id: UUID,
        agente_id: UUID,
        texto: str,
        origem: OrigemItem,
        pista: str = PISTA_PRINCIPAL,
        anexos: Iterable[UUID] = (),
        de_agente_id: UUID | None = None,
        responde_a: UUID | None = None,
        salto: int = 0,
        chave: str | None = None,
    ) -> ItemFila:
        if chave:
            existente = await self._armazem.por_chave(agente_id, chave)
            if existente is not None:
                return existente
        texto = texto.strip()
        anexos = tuple(dict.fromkeys(anexos))
        if not texto and not anexos:
            raise ErroFila("A mensagem está vazia.")
        abertos = [i for i in await self._armazem.itens(agente_id) if i.status in ABERTOS]
        if len(abertos) >= MAX_ITENS_NA_FILA:
            raise ErroFila("A fila deste agente está cheia. Espere ou cancele alguns itens.")
        item = ItemFila(
            id=uuid4(),
            usuario_id=usuario_id,
            agente_id=agente_id,
            seq=await self._armazem.proximo_seq(agente_id),
            pista=pista,
            origem=origem,
            texto=texto,
            anexos=anexos,
            de_agente_id=de_agente_id,
            responde_a=responde_a,
            salto=salto,
            chave=chave,
        )
        await self._armazem.gravar(item)
        return item

    # ---------- despacho ----------

    async def proximos(self, agente_id: UUID) -> Liberacao:
        """Quais itens podem começar agora (no máximo um por pista), sem mudar nada."""
        estado = await self._armazem.estado(agente_id)
        itens = await self._armazem.itens(agente_id)
        pistas_ocupadas = {i.pista for i in itens if i.status in ATIVOS}
        tarefas_ativas = sum(1 for p in pistas_ocupadas if p != PISTA_PRINCIPAL)
        iniciar: list[ItemFila] = []
        esperando: dict[UUID, MotivoEspera] = {}
        pistas_vistas: set[str] = set()
        for item in (i for i in itens if i.status is StatusItem.NA_FILA):
            if item.pista in pistas_vistas:
                continue  # FIFO dentro da pista: só a cabeça é candidata
            pistas_vistas.add(item.pista)
            if estado.pausada:
                esperando[item.id] = MotivoEspera.FILA_PAUSADA
            elif item.em_edicao_por:
                esperando[item.id] = MotivoEspera.EM_EDICAO
            elif item.pista in pistas_ocupadas:
                esperando[item.id] = MotivoEspera.AGENTE_OCUPADO
            elif item.pista != PISTA_PRINCIPAL and tarefas_ativas >= estado.limite_tarefas:
                esperando[item.id] = MotivoEspera.LIMITE_DE_TAREFAS
            else:
                iniciar.append(item)
                if item.pista != PISTA_PRINCIPAL:
                    tarefas_ativas += 1
        return Liberacao(iniciar, esperando)

    async def iniciar(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        """O worker reservou o item (antes de chamar o modelo)."""
        item = await self._buscar(item_id, agente_id)
        if item.status is not StatusItem.NA_FILA:
            raise ErroFila("Este item já saiu da fila.")
        liberacao = await self.proximos(agente_id)
        if item.id not in {i.id for i in liberacao.iniciar}:
            raise ErroFila("Ainda não é a vez deste item.")
        return await self._mudar(item, status=StatusItem.INICIANDO, iniciado_em=_agora())

    async def rodando(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        """O modelo aceitou o pedido: daqui em diante pode haver efeito externo."""
        item = await self._buscar(item_id, agente_id)
        if item.status is not StatusItem.INICIANDO:
            raise ErroFila("O item precisa estar iniciando.")
        return await self._mudar(item, status=StatusItem.RODANDO)

    async def concluir(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.status not in ATIVOS:
            return item  # repetição do job: nada a fazer
        return await self._mudar(item, status=StatusItem.CONCLUIDO, terminado_em=_agora())

    async def falhar(self, item_id: UUID, agente_id: UUID, motivo: str) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.status not in ATIVOS:
            return item
        return await self._mudar(
            item, status=StatusItem.FALHOU, motivo=motivo[:500], terminado_em=_agora()
        )

    # ---------- controles do usuário ----------

    async def pausar(self, agente_id: UUID) -> EstadoFila:
        estado = await self._armazem.estado(agente_id)
        estado.pausada = True
        await self._armazem.salvar_estado(estado)
        return estado

    async def retomar(self, agente_id: UUID) -> EstadoFila:
        estado = await self._armazem.estado(agente_id)
        estado.pausada = False
        await self._armazem.salvar_estado(estado)
        return estado

    async def definir_limite(self, agente_id: UUID, limite: int) -> EstadoFila:
        estado = await self._armazem.estado(agente_id)
        estado.limite_tarefas = validar_limite(limite)
        await self._armazem.salvar_estado(estado)
        return estado

    async def cancelar(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.status is StatusItem.CANCELADO:
            return item
        if item.status is not StatusItem.NA_FILA:
            raise ErroFila("Só dá para cancelar o que ainda não começou. Use Parar.")
        return await self._mudar(
            item,
            status=StatusItem.CANCELADO,
            motivo="cancelado_pelo_usuario",
            terminado_em=_agora(),
            em_edicao_por=None,
        )

    async def interromper(self, agente_id: UUID, pista: str, motivo: str) -> ItemFila | None:
        """Parar o turno em andamento numa pista. O worker cancela a chamada do modelo."""
        for item in await self._armazem.itens(agente_id):
            if item.pista == pista and item.status in ATIVOS:
                return await self._mudar(
                    item, status=StatusItem.CANCELADO, motivo=motivo, terminado_em=_agora()
                )
        return None

    async def cancelar_de(self, agente_id: UUID, de_agente_id: UUID) -> int:
        """Cancela os pedidos ainda na fila que um agente mandou para outro (ao interromper)."""
        total = 0
        for item in await self._armazem.itens(agente_id):
            if item.de_agente_id == de_agente_id and item.status is StatusItem.NA_FILA:
                await self._mudar(
                    item, status=StatusItem.CANCELADO, motivo="interrompido_pelo_remetente"
                )
                total += 1
        return total

    async def mover(
        self, item_id: UUID, agente_id: UUID, *, antes_de: UUID | None
    ) -> list[ItemFila]:
        """Reordena um item que ainda espera (``antes_de=None`` manda para o fim da pista)."""
        item = await self._buscar(item_id, agente_id)
        if item.status is not StatusItem.NA_FILA:
            raise ErroFila("Só dá para mover o que ainda está na fila.")
        pista = [
            i
            for i in await self._armazem.itens(agente_id)
            if i.pista == item.pista and i.status is StatusItem.NA_FILA and i.id != item.id
        ]
        if antes_de is None:
            nova = [*pista, item]
        else:
            posicao = next((n for n, i in enumerate(pista) if i.id == antes_de), None)
            if posicao is None:
                raise ErroFila("O item de referência não está esperando nesta pista.")
            nova = [*pista[:posicao], item, *pista[posicao:]]
        seqs = sorted(i.seq for i in nova)
        resultado = []
        for seq, atual in zip(seqs, nova, strict=True):
            resultado.append(await self._mudar(atual, seq=seq) if atual.seq != seq else atual)
        return resultado

    async def comecar_edicao(self, item_id: UUID, agente_id: UUID, editor: str) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.status is not StatusItem.NA_FILA:
            raise ErroFila("Este item já começou e não pode mais ser editado.")
        if item.em_edicao_por not in (None, editor):
            raise ErroFila("Outra tela está editando este item.")
        return await self._mudar(item, em_edicao_por=editor)

    async def salvar_edicao(
        self, item_id: UUID, agente_id: UUID, editor: str, texto: str
    ) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.em_edicao_por != editor:
            raise ErroFila("Esta edição não está mais aberta.")
        texto = texto.strip()
        if not texto and not item.anexos:
            raise ErroFila("A mensagem está vazia.")
        return await self._mudar(item, texto=texto, em_edicao_por=None)

    async def descartar_edicao(self, item_id: UUID, agente_id: UUID, editor: str) -> ItemFila:
        item = await self._buscar(item_id, agente_id)
        if item.em_edicao_por != editor:
            return item
        return await self._mudar(item, em_edicao_por=None)

    # ---------- queda do worker ----------

    async def recuperar_apos_queda(self) -> list[ItemFila]:
        """Chamado uma vez quando o worker sobe. Devolve os itens que pedem atenção do usuário."""
        atencao = []
        for item in await self._armazem.todos_abertos():
            if item.status is StatusItem.INICIANDO:
                await self._mudar(item, status=StatusItem.NA_FILA, iniciado_em=None)
            elif item.status is StatusItem.RODANDO:
                atencao.append(
                    await self._mudar(
                        item,
                        status=StatusItem.INTERROMPIDO,
                        motivo="servidor_reiniciou",
                        terminado_em=_agora(),
                    )
                )
        return atencao

    async def repetir(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        """O usuário escolheu repetir um item interrompido ou que falhou: entra no fim da fila."""
        item = await self._buscar(item_id, agente_id)
        if item.status not in (StatusItem.INTERROMPIDO, StatusItem.FALHOU):
            raise ErroFila("Só dá para repetir o que falhou ou foi interrompido.")
        return await self.enfileirar(
            usuario_id=item.usuario_id,
            agente_id=agente_id,
            texto=item.texto,
            origem=item.origem,
            pista=item.pista,
            anexos=item.anexos,
            de_agente_id=item.de_agente_id,
            responde_a=item.responde_a,
            salto=item.salto,
        )

    # ---------- leitura ----------

    async def visao(self, agente_id: UUID) -> tuple[EstadoFila, list[ItemFila]]:
        """Fila para a interface: abertos e interrompidos (os terminados ficam no histórico)."""
        estado = await self._armazem.estado(agente_id)
        itens = [
            i
            for i in await self._armazem.itens(agente_id)
            if i.status in ABERTOS or i.status is StatusItem.INTERROMPIDO
        ]
        return estado, itens

    async def ocupado(self, agente_id: UUID, pista: str = PISTA_PRINCIPAL) -> bool:
        return any(
            i.pista == pista and i.status in ATIVOS for i in await self._armazem.itens(agente_id)
        )

    async def na_fila(self, agente_id: UUID, pista: str = PISTA_PRINCIPAL) -> int:
        return sum(
            1
            for i in await self._armazem.itens(agente_id)
            if i.pista == pista and i.status is StatusItem.NA_FILA
        )

    # ---------- interno ----------

    async def _buscar(self, item_id: UUID, agente_id: UUID) -> ItemFila:
        for item in await self._armazem.itens(agente_id):
            if item.id == item_id:
                return item
        raise ErroFila("Item não encontrado na fila deste agente.")

    async def _mudar(self, item: ItemFila, **mudancas: object) -> ItemFila:
        novo = replace(item, **mudancas)  # type: ignore[arg-type]
        await self._armazem.gravar(novo)
        return novo


def _agora() -> datetime:
    return datetime.now(UTC)
