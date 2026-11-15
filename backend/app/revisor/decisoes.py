"""Regra única de "Sempre permitir" (Vela-8, achados Cerca M3 e Prumo A2/B1).

Um cartão de aprovação só aceita "Sempre permitir" quando a regra que ele gravaria fica **presa
a uma coisa concreta**: a ferramenta exata de um conector, o programa exato do PC, o computador
virtual do bot. Nunca vira permissão permanente:

- mudar as próprias instruções (``propor_instrucoes``) e as demais ferramentas de cartão fixo;
- envio externo (e-mail, mensagem, post): o cartão é Enviar/Descartar;
- domínio novo em perfil logado, sugestão de melhoria, retomar o PC, alerta de programa
  bloqueado;
- ``computador_agir`` no PC do usuário (o cartão por programa é que libera; "sempre" no PC
  inteiro seria liberar tudo);
- ferramenta genérica (``executar_comando``, ``chamar_conector``, ações do navegador…) sem
  condição: uma regra vazia casaria com qualquer chamada futura;
- cartão sem bot (a regra valeria para todos os bots da conta).

Quem usa: ``api/aprovacoes.py`` (recusa ``sempre_permitir`` com 422 e grava só a condição daqui),
``atencao.py`` (só oferece a opção quando ela vale) e, pelo app, os dois cartões (chat e central),
que leem a opção que o servidor manda.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

TIPOS_SO_UMA_VEZ = frozenset(
    {"aprovar_dominio", "rascunho_envio", "sugestao_melhoria", "pc_retomar", "pc_bloqueio"}
)
"""Tipos de cartão que nunca viram regra permanente."""

FERRAMENTA_PROGRAMA = "computador_pc_programa"
"""Mesmo nome de ``app/computador/pc_usuario_cartoes.py`` (sem importar o computador aqui)."""

_META_FERRAMENTAS = frozenset(
    {"chamar_conector", "conectores_executar_ferramenta", "navegador_executar_ferramenta"}
)

_ENVIO = re.compile(
    r"(^|[_\-.])(send|post|reply|publish|tweet|enviar|responder|postar|publicar|mandar)"
    r"([_\-.]|$)",
    re.IGNORECASE,
)
"""Ação que manda algo para fora (e-mail, mensagem, post): o cartão é Enviar/Descartar."""

SO_UMA_VEZ = "Este pedido só aceita Permitir uma vez ou Recusar."


def nome_real(acao: dict[str, Any]) -> str:
    """Nome da ferramenta de verdade (conector executado pelo catálogo leva o nome no ``id``)."""
    ferramenta = str(acao.get("ferramenta") or "")
    if ferramenta not in _META_FERRAMENTAS:
        return ferramenta
    argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
    for chave in ("id", "ferramenta", "nome"):
        if isinstance(argumentos.get(chave), str):
            return argumentos[chave]
    return ferramenta


def e_envio(acao: dict[str, Any]) -> bool:
    """O cartão é de envio externo (Enviar/Descartar)."""
    if acao.get("tipo") == "rascunho_envio":
        return True
    if acao.get("tipo") == "aprovar_dominio" or acao.get("ferramenta") == "propor_instrucoes":
        return False
    return bool(_ENVIO.search(nome_real(acao)))


def _generica(ferramenta: str) -> bool:
    """Ferramenta que faz "qualquer coisa" conforme os argumentos (regra vazia libera tudo)."""
    from app.revisor.politica import REVISADAS

    return (
        ferramenta in REVISADAS
        or ferramenta in _META_FERRAMENTAS
        or ferramenta.startswith("navegador_")
    )


def condicao_da_regra(acao: Any) -> dict[str, Any] | None:
    """Condição que "Sempre permitir" gravaria para este cartão; ``None`` = só "uma vez"."""
    from app.revisor.politica import Politica, politica_da_ferramenta

    if not isinstance(acao, dict):
        return None
    if acao.get("tipo") in TIPOS_SO_UMA_VEZ:
        return None
    ferramenta = acao.get("ferramenta")
    if not isinstance(ferramenta, str) or not ferramenta.strip():
        return None
    if politica_da_ferramenta(ferramenta) is Politica.CARTAO_FIXO or e_envio(acao):
        return None
    bruta = acao.get("condicao")
    condicao = dict(bruta) if isinstance(bruta, dict) else {}
    argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
    if ferramenta == FERRAMENTA_PROGRAMA:
        programa = condicao.get("programa")
        if (
            not isinstance(programa, str)
            or not programa.strip()
            or programa.strip().lower() == "explorer.exe"
        ):
            return None
        return {"programa": programa.strip().lower()}
    if ferramenta == "computador_agir":
        # só o computador virtual do bot; o PC do usuário é liberado programa a programa
        alvo = argumentos.get("alvo") or "virtual"
        return {"alvo": "virtual"} if alvo == "virtual" else None
    if not condicao and _generica(ferramenta):
        return None
    return condicao


def aceita_sempre(acao: Any, agente_id: UUID | None) -> bool:
    """O cartão pode oferecer "Sempre permitir" (regra presa ao bot e a uma condição)."""
    return agente_id is not None and condicao_da_regra(acao) is not None
