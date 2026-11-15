"""Previa de texto durante a chamada; mensagens persistidas continuam autoritativas."""

from typing import ClassVar
from uuid import UUID, uuid4

from app.eventos.tipos import EventoBase


class TokenMensagem(EventoBase):
    evento: ClassVar[str] = "mensagem.token"
    fluxo_id: UUID
    agente_id: UUID
    canal_id: UUID | None = None
    texto: str
    fim: bool = False


class FluxoTexto:
    def __init__(self, contexto):
        self.contexto = contexto
        self.id = uuid4()
        self.enviado = ""

    async def publicar(self, texto: str, *, fim: bool = False):
        from app.eventos.streams import publicar_evento
        from app.ferramentas.infra import obter_redis

        if texto == self.enviado and not fim:
            return
        await publicar_evento(
            obter_redis(),
            TokenMensagem(
                fluxo_id=self.id,
                agente_id=self.contexto.agente_id,
                canal_id=self.contexto.canal_id,
                texto=texto,
                fim=fim,
            ),
            self.contexto.conversa_id,
            self.contexto.usuario_id,
        )
        if self.contexto.canal_id is not None:
            import json

            from app.eventos.streams import RETENCAO_SEGUNDOS, canal_usuario, id_minimo_retido

            evento = TokenMensagem(
                fluxo_id=self.id,
                agente_id=self.contexto.agente_id,
                canal_id=self.contexto.canal_id,
                texto=texto,
                fim=fim,
            )
            canal = canal_usuario(self.contexto.usuario_id)
            pipe = obter_redis().pipeline(transaction=False)
            pipe.xadd(
                canal,
                {"event": evento.evento, "data": json.dumps(evento.model_dump(mode="json"))},
                minid=id_minimo_retido(),
                approximate=False,
            )
            pipe.expire(canal, RETENCAO_SEGUNDOS)
            await pipe.execute()
        self.enviado = texto
