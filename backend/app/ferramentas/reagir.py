"""Ferramenta de reacao persistida, sem iniciar outro turno."""

from sqlalchemy import select

from app.core.banco import fabrica_sessoes
from app.correio.reacoes import ReagirMensagem, reagir_como_agente
from app.correio.sql import ArmazemReacoesSQL
from app.eventos.equipe import ReacaoEvento, publicar_evento_equipe
from app.ferramentas import ambiente
from app.ferramentas.base import ContextoFerramenta
from app.modelos.tabelas import Mensagem, MensagemCanalTabela


async def reagir(args: ReagirMensagem, contexto: ContextoFerramenta) -> str:
    async with fabrica_sessoes()() as sessao:
        if contexto.canal_id is not None:
            visiveis = set(
                (
                    await sessao.scalars(
                        select(MensagemCanalTabela.id).where(
                            MensagemCanalTabela.canal_id == contexto.canal_id
                        )
                    )
                ).all()
            )
        else:
            visiveis = set(
                (
                    await sessao.scalars(
                        select(Mensagem.id).where(Mensagem.conversa_id == contexto.conversa_id)
                    )
                ).all()
            )
        armazem = ArmazemReacoesSQL(sessao, contexto.usuario_id)
        existentes = await armazem.da_mensagem(args.mensagem_id)
        texto = await reagir_como_agente(armazem, args, contexto, mensagens_visiveis=visiveis)
        await sessao.commit()
        ligada = not any(
            r.autor == "agente" and r.agente_id == contexto.agente_id and r.emoji == args.emoji
            for r in existentes
        )
    await publicar_evento_equipe(
        ambiente.redis_dos_eventos(),
        ReacaoEvento(
            mensagem_id=args.mensagem_id,
            emoji=args.emoji,
            autor="agente",
            agente_id=contexto.agente_id,
            ligada=ligada,
        ),
        contexto.usuario_id,
    )
    return texto


__all__ = ["ReagirMensagem", "reagir"]
