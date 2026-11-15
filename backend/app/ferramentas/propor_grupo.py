"""Ferramenta da Sora para propor um grupo sem criar bots antes do aceite."""

from pydantic import BaseModel, ConfigDict, Field

from app.api.grupos import PropostaGrupoCriacao, criar_proposta
from app.core.banco import fabrica_sessoes
from app.eventos.tipos import MensagemDelta, MensagemFim, MensagemInicio
from app.ferramentas.ambiente import emitir, redis_dos_eventos
from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import Mensagem


class ProporGrupo(BaseModel):
    """Prepara uma proposta editável de grupo para um pedido grande."""

    model_config = ConfigDict(extra="forbid")

    pedido: str = Field(min_length=1, max_length=20_000)
    grupo_existente: str | None = Field(
        default=None,
        max_length=200,
        description="Nome exato do grupo existente ao qual delegar; null para propor grupo novo.",
    )


async def propor_grupo(args: ProporGrupo, contexto: ContextoFerramenta) -> str:
    if args.grupo_existente is not None:
        from sqlalchemy import select

        from app.api.equipe import MensagemCanalEntrada, enviar_ao_canal
        from app.ferramentas.base import ErroFerramenta
        from app.modelos.tabelas import CanalEquipe

        async with fabrica_sessoes()() as sessao:
            grupos = list(
                (
                    await sessao.scalars(
                        select(CanalEquipe).where(
                            CanalEquipe.usuario_id == contexto.usuario_id,
                            CanalEquipe.nome == args.grupo_existente,
                            CanalEquipe.arquivado_em.is_(None),
                        )
                    )
                ).all()
            )
            if len(grupos) != 1:
                raise ErroFerramenta(
                    "Não encontrei um único grupo ativo com esse nome. Confira o nome."
                )
            await enviar_ao_canal(
                grupos[0].id,
                MensagemCanalEntrada(texto=args.pedido),
                contexto.usuario_id,
                sessao,
                redis_dos_eventos(),
            )
        return "Pedido enviado ao grupo existente. O resultado chegará no grupo."
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
