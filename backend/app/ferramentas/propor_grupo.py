"""Ferramenta da Sora para propor um grupo sem criar bots antes do aceite."""

from pydantic import BaseModel, Field

from app.api.grupos import PropostaGrupoCriacao, criar_proposta
from app.core.banco import fabrica_sessoes
from app.eventos.tipos import MensagemDelta, MensagemFim, MensagemInicio
from app.ferramentas.ambiente import emitir, redis_dos_eventos
from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import Mensagem


class ProporGrupo(BaseModel):
    """Prepara uma proposta editável de grupo para um pedido grande."""

    pedido: str = Field(min_length=1, max_length=20_000)


async def propor_grupo(args: ProporGrupo, contexto: ContextoFerramenta) -> str:
    async with fabrica_sessoes()() as sessao:
        proposta = await criar_proposta(
            PropostaGrupoCriacao(pedido=args.pedido),
            contexto.usuario_id,
            sessao,
            redis_dos_eventos(),
        )
        texto = f"Preparei a proposta do grupo {proposta.nome}. Confira os bots antes de montar."
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
    return f"Proposta de grupo {proposta.nome} preparada; aguarde a decisão do usuário."
