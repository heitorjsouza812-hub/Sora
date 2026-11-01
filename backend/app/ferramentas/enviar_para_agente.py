"""Ferramenta ``enviar_para_agente`` (especificação §4, fase 2): manda uma atualização,
pergunta ou resultado para outro agente do usuário.

Descrição e regras adaptadas do Rakazo (github.com/elie222/rakazo, Apache-2.0):
``message_bot`` em ``adapters/src/builtin-tools.ts`` e ``core/src/bot-messages.ts``.

A entrega é assíncrona e não encerra o turno. Cada envio carrega o salto da corrente
(``app/orquestrador/saltos.py``): mensagem do usuário zera; passou de 6 trocas seguidas entre
agentes, a entrega é recusada.

Extensão própria da Sora (2026-11-01, ideia vista no OpenBot; ver ``docs/referencias/openbot.md``):
a mensagem pode **responder** a outra (``responde_a``), levar **anexos** (imagens e arquivos,
conferidos em ``app/correio/transferencias.py``) e dizer se **espera resposta**. Sem esses
campos o comportamento é o de antes.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.orquestrador.saltos import MAX_CARACTERES_MENSAGEM, conferir_envio

DESCRICAO = (
    "Manda uma atualização, pergunta ou resultado útil para outro agente do usuário. Você "
    "precisa chamar esta ferramenta para entregar: escrever '[para Atlas] …' na resposta não "
    "envia nada. A entrega é assíncrona e não encerra o seu turno; siga com o trabalho que não "
    "depende da resposta, não fique checando e não mande só 'ok'."
)


class EnviarParaAgente(BaseModel):
    """Manda uma mensagem para outro agente do usuário."""

    agente_id: UUID = Field(description="Id do agente de destino (da lista de colegas).")
    texto: str = Field(min_length=1, max_length=MAX_CARACTERES_MENSAGEM)
    prioridade: bool = Field(default=False, description="Interrompe o que o agente está fazendo.")
    responde_a: UUID | None = Field(
        default=None, description="Id da mensagem que você está respondendo, se houver."
    )
    anexos: list[UUID] = Field(
        default_factory=list,
        max_length=10,
        description="Ids de anexos (imagens ou arquivos) que você recebeu ou criou e quer passar.",
    )
    espera_resposta: bool = Field(
        default=True,
        description="False para avisos que não pedem resposta (o colega não precisa responder).",
    )


@dataclass(frozen=True, slots=True)
class EnvioPreparado:
    de_agente_id: UUID
    para_agente_id: UUID
    texto: str
    prioridade: bool
    salto: int
    chave_entrega: str
    """Evita entregar duas vezes se o job repetir (``mensagens`` com o mesmo nonce)."""
    responde_a: UUID | None = None
    anexos: tuple[UUID, ...] = ()
    espera_resposta: bool = True


def preparar_envio(
    args: EnviarParaAgente,
    contexto: ContextoFerramenta,
    *,
    salto_de_origem: int | None,
    colegas: set[UUID],
    chamada_id: str,
) -> EnvioPreparado:
    """Confere destino e limite de saltos e devolve o envio para o worker gravar e enfileirar."""
    if args.agente_id == contexto.agente_id:
        raise ErroFerramenta("Você não pode mandar mensagem para si mesmo.")
    if args.agente_id not in colegas:
        raise ErroFerramenta("Esse agente não está na sua lista de colegas.")
    texto = args.texto.strip()
    if not texto:
        raise ErroFerramenta("A mensagem está vazia.")
    if len(set(args.anexos)) != len(args.anexos):
        raise ErroFerramenta("O mesmo anexo apareceu duas vezes.")
    salto = conferir_envio(salto_de_origem)
    return EnvioPreparado(
        de_agente_id=contexto.agente_id,
        para_agente_id=args.agente_id,
        texto=texto,
        prioridade=args.prioridade,
        salto=salto,
        chave_entrega=f"agente:{contexto.agente_id}:{chamada_id}",
        responde_a=args.responde_a,
        anexos=tuple(args.anexos),
        espera_resposta=args.espera_resposta,
    )


def diretorio_de_colegas(
    colegas: list[tuple[UUID, str, str]], limite_caracteres: int = 8_000
) -> str:
    """Lista de colegas para o prompt: ``(id, nome, função)``, cortada no limite de caracteres."""
    linhas: list[str] = []
    total = 0
    for agente_id, nome, funcao in colegas:
        linha = f"- {nome} ({funcao.strip() or 'sem função'}): {agente_id}"
        if total + len(linha) > limite_caracteres:
            linhas.append(f"- … e mais {len(colegas) - len(linhas)} agentes")
            break
        linhas.append(linha)
        total += len(linha)
    if not linhas:
        return ""
    return "Seus colegas (use o id em enviar_para_agente):\n" + "\n".join(linhas)
