"""Ferramenta da Sora que prepara um rascunho de bot.

O bot nunca nasce durante o turno do modelo. A ferramenta persiste o rascunho e a
mensagem antes de publicar o cartão; somente a rota de confirmação cria o bot.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.banco import fabrica_sessoes
from app.eventos.equipe import BotRascunhoEvento, publicar_evento_equipe
from app.eventos.tipos import MensagemDelta, MensagemFim, MensagemInicio
from app.ferramentas.ambiente import emitir, redis_dos_eventos
from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import Mensagem
from app.rascunhos_bot import criar_rascunho, saida_do_rascunho


class CriarAgente(BaseModel):
    """Prepara um rascunho editável de bot para o usuário confirmar."""

    nome: str = Field(min_length=1, max_length=40)
    papel: str = Field(min_length=1, max_length=2_000)


async def _agendar_expiracao(aprovacao_id, expira_em) -> None:
    """Compatibilidade do revisor genérico, que também agenda cartões de ação."""
    from workers.fila import enfileirar

    try:
        await enfileirar(
            "expirar_aprovacao",
            id_job=f"expirar:{aprovacao_id}",
            agendar_para=expira_em,
            aprovacao_id=str(aprovacao_id),
        )
    except Exception:
        logging.getLogger(__name__).warning("não agendei a expiração de %s", aprovacao_id)


async def criar_agente(args: CriarAgente, contexto: ContextoFerramenta) -> str:
    async with fabrica_sessoes()() as sessao:
        rascunho = await criar_rascunho(
            sessao,
            contexto.usuario_id,
            descricao=args.papel,
            conversa_id=contexto.conversa_id,
            nome=args.nome,
            funcao=args.papel,
        )
        nome = rascunho.dados["nome"]
        texto = f"Preparei o rascunho de {nome}. Confira antes de criar o bot."
        mensagem = Mensagem(
            conversa_id=contexto.conversa_id,
            autor=AutorMensagem.SORA,
            agente_id=contexto.agente_id,
            conteudo=texto,
            anexos=[],
            visivel=True,
        )
        sessao.add(mensagem)
        await sessao.flush()
        saida = saida_do_rascunho(rascunho)
        mensagem_id = mensagem.id
        await sessao.commit()

    await emitir(
        contexto,
        MensagemInicio(
            mensagem_id=mensagem_id,
            autor=AutorMensagem.SORA,
            agente_id=contexto.agente_id,
        ),
    )
    await emitir(contexto, MensagemDelta(mensagem_id=mensagem_id, texto=texto))
    await emitir(contexto, MensagemFim(mensagem_id=mensagem_id))
    await publicar_evento_equipe(
        redis_dos_eventos(), BotRascunhoEvento.de(saida), contexto.usuario_id
    )
    return f"Rascunho de {nome} preparado; aguarde a confirmação do usuário."
