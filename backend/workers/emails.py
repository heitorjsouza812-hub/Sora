"""Jobs de e-mail da conta (especificação §8.2).

O e-mail sai do worker, não da API: a rota "Esqueci minha senha" responde 202 na hora, exista a
conta ou não, e é aqui que se descobre se há conta, se cria o token e se envia o link. Nada de
e-mail nem de token no log.
"""

from __future__ import annotations

import logging
from typing import Any

registro = logging.getLogger(__name__)


async def enviar_link_de_senha_nova(ctx: dict[str, Any], email: str) -> bool:
    """Cria o link de uso único e envia. ``False`` quando não há conta ou o e-mail está desligado.

    Se o envio falhar, a exceção faz o ARQ tentar de novo; cada tentativa cria um token novo e
    invalida o anterior, então só o último link enviado vale."""
    from app.core import contas
    from app.core.config import obter_configuracao
    from app.emails import mensagem_redefinicao

    enviador = ctx.get("email")
    if enviador is None:
        registro.warning("pedido de senha nova ignorado: o envio de e-mail está desligado")
        return False
    async with ctx["sessoes"]() as sessao:
        criado = await contas.criar_link_de_senha_nova(sessao, email)
        if criado is None:
            return False
        usuario, token = criado
        await sessao.commit()
        destino, nome = usuario.email, usuario.nome
    link = contas.link_de_senha_nova(obter_configuracao().app_url, token)
    minutos = int(contas.VALIDADE_REDEFINICAO.total_seconds() // 60)
    await enviador.enviar(mensagem_redefinicao(destino, nome, link, minutos))
    registro.info("link de senha nova enviado")
    return True
