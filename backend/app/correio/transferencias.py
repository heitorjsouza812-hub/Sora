"""Transferência gerenciada de arquivos entre agentes.

Quando um agente passa um arquivo para outro, a Sora **não** entrega um caminho: ela confere se
o remetente tem acesso àquele anexo, se o tipo e o tamanho são aceitos, copia o arquivo para a
pasta do destinatário conferindo o hash e só então registra a entrega. Assim:

- um agente não consegue "inventar" um id e pegar arquivo de outra conta ou de outro projeto;
- o destinatário fica com a própria cópia: se o remetente apagar o dele, nada quebra;
- o hash (SHA-256) prova que o que chegou é o que saiu.

Limites da Sora: até ``MAX_ARQUIVOS`` por mensagem, ``MAX_BYTES_ARQUIVO`` por arquivo e
``MAX_BYTES_MENSAGEM`` somando todos. Imagens (``image/png``, ``jpeg``, ``webp``, ``gif``) vão
também como imagem para modelos com visão; o resto chega como arquivo para ``ler_anexo``.
ZIP é aceito, mas nunca aberto pela Sora: o agente recebe o arquivo como está.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from app.ferramentas.arquivos import CaminhoInseguro, dentro_da_pasta, validar_nome_arquivo
from app.ferramentas.base import ErroFerramenta

MAX_ARQUIVOS = 10
MAX_BYTES_ARQUIVO = 50 * 1024 * 1024
MAX_BYTES_MENSAGEM = 150 * 1024 * 1024
BLOCO_HASH = 1024 * 1024

TIPOS_IMAGEM = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
TIPOS_ACEITOS = TIPOS_IMAGEM | frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "audio/mpeg",
        "video/mp4",
        "video/quicktime",
    }
)


class StatusTransferencia(StrEnum):
    PENDENTE = "pendente"
    ENTREGUE = "entregue"
    FALHOU = "falhou"


@dataclass(frozen=True, slots=True)
class AnexoInfo:
    """O que o banco sabe de um anexo (tabela ``anexos``)."""

    id: UUID
    usuario_id: UUID
    nome: str
    tipo: str
    tamanho: int
    caminho: str
    """Relativo à raiz do volume de arquivos."""


@dataclass(frozen=True, slots=True)
class Transferencia:
    id: UUID
    usuario_id: UUID
    anexo_id: UUID
    de_agente_id: UUID
    para_agente_id: UUID
    nome: str
    tipo: str
    tamanho: int
    imagem: bool
    status: StatusTransferencia = StatusTransferencia.PENDENTE
    sha256: str | None = None
    caminho_destino: str | None = None
    """Relativo à raiz; preenchido quando a cópia termina."""
    novo_anexo_id: UUID | None = None
    erro: str | None = None
    criada_em: datetime = field(default_factory=lambda: datetime.now(UTC))


def tipo_base(tipo: str) -> str:
    return tipo.split(";", 1)[0].strip().lower()


def preparar(
    anexos_pedidos: Sequence[UUID],
    *,
    conhecidos: dict[UUID, AnexoInfo],
    acessiveis: set[UUID],
    usuario_id: UUID,
    de_agente_id: UUID,
    para_agente_id: UUID,
) -> list[Transferencia]:
    """Confere tudo antes de copiar. Erro aqui volta para o modelo e nada é gravado.

    ``acessiveis`` são os anexos que o remetente pode ver: os que ele criou, os que recebeu
    por transferência e os que o usuário mandou nas conversas dele. Quem calcula é o worker.
    """
    if not anexos_pedidos:
        return []
    if len(anexos_pedidos) > MAX_ARQUIVOS:
        raise ErroFerramenta(f"No máximo {MAX_ARQUIVOS} arquivos por mensagem.")
    if len(set(anexos_pedidos)) != len(anexos_pedidos):
        raise ErroFerramenta("O mesmo anexo apareceu duas vezes.")
    if de_agente_id == para_agente_id:
        raise ErroFerramenta("Você não precisa mandar arquivo para si mesmo.")
    transferencias: list[Transferencia] = []
    total = 0
    for anexo_id in anexos_pedidos:
        anexo = conhecidos.get(anexo_id)
        # Mesmo texto para "não existe" e "não é seu": não confirma que o id existe.
        if anexo is None or anexo.usuario_id != usuario_id or anexo_id not in acessiveis:
            raise ErroFerramenta(f"Você não tem o anexo {anexo_id}.")
        tipo = tipo_base(anexo.tipo)
        if tipo not in TIPOS_ACEITOS:
            raise ErroFerramenta(f"O tipo de '{anexo.nome}' ({tipo}) não pode ser passado.")
        if anexo.tamanho > MAX_BYTES_ARQUIVO:
            raise ErroFerramenta(
                f"'{anexo.nome}' passa de {MAX_BYTES_ARQUIVO // (1024 * 1024)} MB."
            )
        total += anexo.tamanho
        try:
            nome = validar_nome_arquivo(anexo.nome)
        except CaminhoInseguro as erro:
            raise ErroFerramenta(f"Nome de arquivo recusado: {erro}") from erro
        transferencias.append(
            Transferencia(
                id=uuid4(),
                usuario_id=usuario_id,
                anexo_id=anexo_id,
                de_agente_id=de_agente_id,
                para_agente_id=para_agente_id,
                nome=nome,
                tipo=tipo,
                tamanho=anexo.tamanho,
                imagem=tipo in TIPOS_IMAGEM,
            )
        )
    if total > MAX_BYTES_MENSAGEM:
        raise ErroFerramenta(f"Os arquivos somam mais de {MAX_BYTES_MENSAGEM // (1024 * 1024)} MB.")
    return transferencias


def hash_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(BLOCO_HASH):
            resumo.update(bloco)
    return resumo.hexdigest()


def pasta_recebidos(raiz: Path, usuario_id: UUID, agente_id: UUID) -> Path:
    return raiz / "usuarios" / str(usuario_id) / "agentes" / str(agente_id) / "recebidos"


def copiar(raiz: Path, transferencia: Transferencia, origem: AnexoInfo) -> Transferencia:
    """Copia o arquivo para a pasta do destinatário e confere o hash.

    Síncrono (o worker chama em ``asyncio.to_thread``). Nunca levanta: devolve a transferência
    com ``status`` ``entregue`` ou ``falhou`` e o erro em texto curto, sem caminho do servidor.
    """
    if transferencia.status is not StatusTransferencia.PENDENTE:
        return transferencia
    try:
        caminho_origem = dentro_da_pasta(raiz, raiz / origem.caminho)
        if not caminho_origem.is_file():
            raise FileNotFoundError
        if caminho_origem.stat().st_size != origem.tamanho:
            return replace(
                transferencia,
                status=StatusTransferencia.FALHOU,
                erro="O arquivo mudou de tamanho desde o envio.",
            )
        hash_origem = hash_arquivo(caminho_origem)
        pasta = pasta_recebidos(raiz, transferencia.usuario_id, transferencia.para_agente_id)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = dentro_da_pasta(raiz, pasta / f"{transferencia.id}-{transferencia.nome}")
        temporario = destino.with_name(destino.name + ".parcial")
        shutil.copyfile(caminho_origem, temporario)
        if hash_arquivo(temporario) != hash_origem:
            temporario.unlink(missing_ok=True)
            return replace(
                transferencia,
                status=StatusTransferencia.FALHOU,
                erro="A cópia não bateu com o original.",
            )
        temporario.replace(destino)
    except (CaminhoInseguro, FileNotFoundError):
        return replace(
            transferencia,
            status=StatusTransferencia.FALHOU,
            erro="O arquivo original não está mais disponível.",
        )
    except OSError:
        return replace(
            transferencia, status=StatusTransferencia.FALHOU, erro="Não consegui copiar o arquivo."
        )
    return replace(
        transferencia,
        status=StatusTransferencia.ENTREGUE,
        sha256=hash_origem,
        caminho_destino=str(destino.relative_to(raiz.resolve())),
        novo_anexo_id=uuid4(),
    )


def acessiveis_do_agente(
    *,
    criados_por_ele: Iterable[UUID],
    recebidos: Iterable[Transferencia],
    do_usuario_nas_conversas_dele: Iterable[UUID],
    agente_id: UUID,
) -> set[UUID]:
    """Junta os três jeitos de um agente ter acesso a um anexo."""
    entregues = {
        t.novo_anexo_id
        for t in recebidos
        if t.para_agente_id == agente_id
        and t.status is StatusTransferencia.ENTREGUE
        and t.novo_anexo_id is not None
    }
    return set(criados_por_ele) | entregues | set(do_usuario_nas_conversas_dele)
