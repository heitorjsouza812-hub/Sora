"""Rotas dos canais da empresa (Ponte): conexões com Slack e WhatsApp Business (só leitura),
webhooks, clientes e fichas, autorizações, base de conhecimento e sugestões de melhoria.

A Sora nunca envia nada por esses canais. Os webhooks não usam login: a origem é conferida pela
assinatura (``X-Slack-Signature``; ``X-Hub-Signature-256`` e o handshake do GET na Meta). Detalhes
e campos em ``docs/canais-da-empresa.md``.

Era um arquivo só (1.092 linhas, rotas misturadas com regra de negócio); agora uma seção por
módulo, todas no mesmo ``roteador`` de ``comum``. O FastAPI casa as rotas na ordem em que foram
declaradas: dentro de cada módulo a ordem é a de antes, e cada módulo tem um prefixo próprio
(``/conexoes``, ``/clientes``, ``/conhecimento``…), então a ordem entre eles não muda nada.
"""

from app.api.canais_empresa import (  # noqa: F401 - registram as rotas
    clientes,
    conexoes,
    conhecimento,
    preferencias,
    sugestoes,
    webhooks,
)
from app.api.canais_empresa.comum import (
    LIMITE_CORPO_WEBHOOK,
    roteador,
    roteador_webhooks,
)
from app.api.canais_empresa.webhooks import _corpo_limitado

__all__ = ["LIMITE_CORPO_WEBHOOK", "_corpo_limitado", "roteador", "roteador_webhooks"]
