"""Leitura e publicação do estado "Precisa de você" da etapa 5."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas.propor_instrucoes import proposta_do_cartao
from app.modelos.enumeracoes import StatusAprovacao
from app.modelos.tabelas import Agente, Aprovacao, Conversa, Pergunta
from app.revisor.decisoes import aceita_sempre, e_envio
from app.revisor.decisoes import nome_real as _nome_real


class OpcaoAtencao(BaseModel):
    rotulo: str
    valor: str


class PedidoAtencao(BaseModel):
    id: UUID
    tipo: Literal["pergunta", "aprovacao", "rascunho_envio"]
    agente_id: UUID | None = None
    grupo_id: UUID | None = None
    titulo: str
    resumo: str
    pergunta: str | None = None
    opcoes: list[OpcaoAtencao] = Field(default_factory=list)
    acao: str | None = None
    anexos: list[UUID] = Field(default_factory=list)
    proposta: dict[str, str] | None = None
    """Só no cartão de ``propor_instrucoes``: ``instrucoes`` novas, ``diferenca`` e ``motivo``."""
    criado_em: datetime

    @model_serializer(mode="wrap")
    def _sem_proposta_vazia(self, proximo: Any) -> dict[str, Any]:
        """``proposta`` só existe no cartão de ``propor_instrucoes``; nos outros o campo some."""
        dados = proximo(self)
        if dados.get("proposta") is None:
            dados.pop("proposta", None)
        return dados


_META_FERRAMENTAS = frozenset(
    {"chamar_conector", "conectores_executar_ferramenta", "navegador_executar_ferramenta"}
)


def _resumo_envio(acao: dict) -> str:
    argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
    internos = (
        argumentos.get("argumentos") if isinstance(argumentos.get("argumentos"), dict) else {}
    )
    dados = {**argumentos, **internos}
    para = next(
        (str(dados[c]) for c in ("para", "to", "destinatario", "canal") if dados.get(c)), ""
    )
    texto = next(
        (
            str(dados[c])
            for c in ("assunto", "subject", "texto", "text", "mensagem", "corpo", "body")
            if dados.get(c)
        ),
        "",
    )
    partes = [f"Para {para}" if para else "", texto[:280]]
    return " · ".join(p for p in partes if p) or "Revise antes de enviar."


_FRASE_DA_ACAO: dict[str, str] = {
    "propor_instrucoes": "mudar as próprias instruções",
    "esquecer_memoria": "apagar uma memória",
    "criar_habilidade": "criar uma habilidade, que vale para todos os seus bots",
    "atualizar_habilidade": "mudar uma habilidade, que vale para todos os seus bots",
    "apagar_habilidade": "apagar uma habilidade",
    "adicionar_servidor_mcp": "adicionar um conector",
    "executar_comando": "executar um comando",
    "navegador_agir": "agir numa página do navegador",
    "navegador_acao": "agir numa página do navegador",
    "navegador_tecla": "digitar numa página do navegador",
    "navegador_lote": "fazer várias ações numa página do navegador",
    "chamar_conector": "usar um conector",
    "conectores_executar_ferramenta": "usar um conector",
}
"""O que o agente quer fazer, em PT-BR, para o resumo do cartão (nunca o nome técnico)."""


def _frase_da_acao(acao: dict) -> str:
    ferramenta = str(acao.get("ferramenta") or "")
    if ferramenta in _FRASE_DA_ACAO:
        frase = _FRASE_DA_ACAO[ferramenta]
        real = _nome_real(acao)
        if ferramenta in _META_FERRAMENTAS and real != ferramenta:
            frase += f" ({real.replace('_', ' ')})"
        return frase
    from app.ferramentas.rotulos import NOME_EXIBIDO

    exibido = NOME_EXIBIDO.get(ferramenta) or ferramenta.replace("_", " ") or "uma ação externa"
    return f"usar {exibido}"


def _texto_acao(aprovacao: Aprovacao, nome: str = "O bot") -> tuple[str, str, str]:
    acao = aprovacao.acao if isinstance(aprovacao.acao, dict) else {}
    envio = e_envio(acao)
    tipo = "rascunho_envio" if envio else "aprovacao"
    ferramenta = str(acao.get("ferramenta") or "ação externa")
    if acao.get("tipo") == "sugestao_melhoria":
        return "aprovacao", "Sugestão de melhoria", str(acao.get("resumo") or "Melhorar um bot.")
    if acao.get("tipo") == "aprovar_dominio":
        titulo = "Revisar acesso a domínio"
        resumo = f"Permitir acesso a {acao.get('dominio', 'um novo domínio')}?"
    elif acao.get("tipo") in {"pc_programa", "pc_retomar"}:  # Vela-3 (C3): texto já pronto
        titulo = str(acao.get("titulo") or "Usar o seu computador")[:120]
        resumo = str(acao.get("resumo") or f"{nome} quer usar o seu computador.")[:400]
    elif tipo == "rascunho_envio":
        titulo = "Revisar envio"
        resumo = str(acao.get("resumo") or _resumo_envio(acao))
    else:
        titulo = "Aprovar ação"
        avaliacao = aprovacao.avaliacao if isinstance(aprovacao.avaliacao, dict) else {}
        argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
        resumo = f"{nome} quer {_frase_da_acao(acao)}."
        if ferramenta == "propor_instrucoes" and argumentos.get("instrucoes"):
            resumo += f" Novas instruções: “{str(argumentos['instrucoes'])[:200]}”"
            if argumentos.get("motivo"):
                resumo += f" Motivo: {str(argumentos['motivo'])[:200]}"
        elif ferramenta in {"criar_habilidade", "atualizar_habilidade", "apagar_habilidade"}:
            # O usuário precisa ver o que vai valer para todos os bots antes de aprovar.
            if argumentos.get("nome"):
                resumo += f" Nome: {str(argumentos['nome'])[:80]}."
            if argumentos.get("descricao"):
                resumo += f" Para que serve: {str(argumentos['descricao'])[:160]}."
            if argumentos.get("corpo"):
                resumo += f" Texto: “{str(argumentos['corpo'])[:400]}”"
        elif avaliacao.get("motivo"):
            resumo += f" {str(avaliacao['motivo'])[:280]}"
    return tipo, titulo, resumo


async def listar_atencao(sessao: AsyncSession, usuario_id: UUID) -> list[PedidoAtencao]:
    agora = datetime.now(UTC)
    saida: list[PedidoAtencao] = []
    aprovacoes = await sessao.scalars(
        select(Aprovacao)
        .where(
            Aprovacao.usuario_id == usuario_id,
            Aprovacao.status == StatusAprovacao.PENDENTE,
            Aprovacao.expira_em > agora,
        )
        .order_by(Aprovacao.criado_em, Aprovacao.id)
    )
    aprovacoes = list(aprovacoes)
    ids = {a.agente_id for a in aprovacoes if a.agente_id is not None}
    nomes = (
        dict((await sessao.execute(select(Agente.id, Agente.nome).where(Agente.id.in_(ids)))).all())
        if ids
        else {}
    )
    for aprovacao in aprovacoes:
        tipo, titulo, resumo = _texto_acao(aprovacao, nomes.get(aprovacao.agente_id, "O bot"))
        sugestao = (
            isinstance(aprovacao.acao, dict) and aprovacao.acao.get("tipo") == "sugestao_melhoria"
        )
        opcoes = (
            [
                OpcaoAtencao(rotulo="Aplicar", valor="permitir"),
                OpcaoAtencao(rotulo="Descartar", valor="negar"),
            ]
            if sugestao
            else [
                OpcaoAtencao(rotulo="Enviar", valor="permitir"),
                OpcaoAtencao(rotulo="Descartar", valor="negar"),
            ]
            if tipo == "rascunho_envio"
            else [
                OpcaoAtencao(rotulo="Permitir uma vez", valor="permitir"),
                # Regra única (``revisor/decisoes.py``): o app só mostra "Sempre permitir"
                # quando o servidor manda esta opção, no chat e na central.
                *(
                    [OpcaoAtencao(rotulo="Sempre permitir", valor="sempre_permitir")]
                    if aceita_sempre(aprovacao.acao, aprovacao.agente_id)
                    else []
                ),
                OpcaoAtencao(rotulo="Recusar", valor="negar"),
            ]
        )
        saida.append(
            PedidoAtencao(
                id=aprovacao.id,
                tipo=tipo,
                agente_id=aprovacao.agente_id,
                grupo_id=aprovacao.grupo_id,
                titulo=titulo,
                resumo=resumo,
                acao=str((aprovacao.acao or {}).get("ferramenta") or tipo),
                proposta=proposta_do_cartao(aprovacao.acao),
                opcoes=opcoes,
                criado_em=aprovacao.criado_em,
            )
        )
    perguntas = await sessao.execute(
        select(Pergunta, Conversa.agente_id)
        .join(Conversa, Conversa.id == Pergunta.conversa_id)
        .where(Conversa.usuario_id == usuario_id, Pergunta.respondida_em.is_(None))
        .order_by(Pergunta.criado_em, Pergunta.id)
    )
    for pergunta, agente_id in perguntas:
        saida.append(
            PedidoAtencao(
                id=pergunta.id,
                tipo="pergunta",
                agente_id=agente_id,
                grupo_id=pergunta.grupo_id,
                titulo="Responder pergunta",
                resumo=pergunta.texto,
                pergunta=pergunta.texto,
                opcoes=[OpcaoAtencao.model_validate(opcao) for opcao in pergunta.opcoes],
                criado_em=pergunta.criado_em,
            )
        )
    return sorted(saida, key=lambda pedido: (pedido.criado_em, str(pedido.id)))


async def publicar_estado_atencao(
    redis,
    sessao: AsyncSession,
    usuario_id: UUID,
    *,
    agente_id: UUID | None,
    grupo_id: UUID | None,
) -> None:
    from app.estado_interface import estados_dos_agentes, estados_dos_grupos
    from app.eventos.equipe import PrecisaDeVoceAtualizado, publicar_evento_equipe

    pedidos = [
        pedido
        for pedido in await listar_atencao(sessao, usuario_id)
        if (agente_id is not None and pedido.agente_id == agente_id)
        or (grupo_id is not None and pedido.grupo_id == grupo_id)
    ]
    if grupo_id is not None:
        estado = (await estados_dos_grupos(sessao, usuario_id, [grupo_id]))[grupo_id]
    elif agente_id is not None:
        estado = (await estados_dos_agentes(sessao, usuario_id, [agente_id]))[agente_id]
    else:
        estado = "livre"
    await publicar_evento_equipe(
        redis,
        PrecisaDeVoceAtualizado(
            agente_id=agente_id,
            grupo_id=grupo_id,
            estado=estado,
            pedidos=pedidos,
        ),
        usuario_id,
    )


async def publicar_estado_atencao_persistido(
    usuario_id: UUID, *, agente_id: UUID | None, grupo_id: UUID | None
) -> None:
    """Adaptador para ferramentas, que rodam fora da sessão e da requisição da API."""
    from app.core.banco import fabrica_sessoes
    from app.ferramentas import ambiente

    async with fabrica_sessoes()() as sessao:
        await publicar_estado_atencao(
            ambiente.redis_dos_eventos(),
            sessao,
            usuario_id,
            agente_id=agente_id,
            grupo_id=grupo_id,
        )


async def encerrar_pendentes(
    sessao: AsyncSession,
    usuario_id: UUID,
    *,
    conversa_id: UUID | None = None,
    agente_id: UUID | None = None,
) -> set[tuple[UUID | None, UUID | None]]:
    """Fecha os pedidos "Precisa de você" que perderam o dono (conversa ou bot apagado).

    Aprovação pendente vira ``expirada`` (ninguém retoma: a conversa ou o bot não existe mais);
    pergunta pendente de bot apagado é dada por encerrada sem resposta. Devolve os pares
    ``(agente_id, grupo_id)`` afetados, para publicar ``precisa_de_voce.atualizado`` depois do
    commit.
    """
    agora = datetime.now(UTC)
    afetados: set[tuple[UUID | None, UUID | None]] = set()
    filtros = []
    if conversa_id is not None:
        filtros.append(Aprovacao.acao["conversa_id"].astext == str(conversa_id))
    if agente_id is not None:
        filtros.append(Aprovacao.agente_id == agente_id)
    if filtros:
        from sqlalchemy import or_

        aprovacoes = await sessao.scalars(
            select(Aprovacao).where(
                Aprovacao.usuario_id == usuario_id,
                Aprovacao.status == StatusAprovacao.PENDENTE,
                or_(*filtros),
            )
        )
        for aprovacao in aprovacoes:
            aprovacao.status = StatusAprovacao.EXPIRADA
            aprovacao.decidida_em = agora
            afetados.add((aprovacao.agente_id, aprovacao.grupo_id))
    if agente_id is not None:
        perguntas = await sessao.scalars(
            select(Pergunta)
            .join(Conversa, Conversa.id == Pergunta.conversa_id)
            .where(
                Conversa.usuario_id == usuario_id,
                Conversa.agente_id == agente_id,
                Pergunta.respondida_em.is_(None),
            )
        )
        for pergunta in perguntas:
            pergunta.respondida_em = agora
            afetados.add((agente_id, pergunta.grupo_id))
    await sessao.flush()
    return afetados


async def publicar_encerrados(
    redis, sessao: AsyncSession, usuario_id: UUID, afetados: set[tuple[UUID | None, UUID | None]]
) -> None:
    for agente_id, grupo_id in afetados:
        if agente_id is not None:
            await publicar_estado_atencao(
                redis, sessao, usuario_id, agente_id=agente_id, grupo_id=None
            )
        if grupo_id is not None:
            await publicar_estado_atencao(
                redis, sessao, usuario_id, agente_id=None, grupo_id=grupo_id
            )
