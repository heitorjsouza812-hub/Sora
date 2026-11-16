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


# ---------- modo de permissão da conversa (Âncora-9) ----------
#
# O seletor do campo de mensagem tem três modos (``app/preferencias_conversa.py``):
#
# - ``perguntar``: como sempre (regra "sempre permitir", juiz e cartão);
# - ``automatico``: aprova sozinho só o que é de **risco baixo** (``risco_baixo``);
# - ``total``: aprova sozinho tudo o que a política deixa o usuário aprovar num cartão.
#
# Em nenhum modo passam sozinhos os **bloqueios absolutos** (``bloqueio_absoluto``), as
# ferramentas de cartão fixo (criar bot, mudar instruções, esquecer memória, apagar habilidade,
# adicionar servidor MCP) e nada de rotina sem supervisão. Quem aplica: ``revisor/execucao.py``
# (cartões do revisor) e ``computador/pc_usuario.py`` (cartão por programa do PC, só no total).

MODOS_PERMISSAO = ("perguntar", "automatico", "total")

FERRAMENTAS_NUNCA_SOZINHAS = frozenset(
    {
        "propor_instrucoes",  # o bot mudar as próprias instruções
        "criar_habilidade",  # ... ou as próprias habilidades
        "atualizar_habilidade",
        "apagar_habilidade",
    }
)
"""O bot mudar a si mesmo nunca é aprovado por modo."""

TIPOS_NUNCA_SOZINHOS = frozenset({"sugestao_melhoria", "pc_bloqueio"})
"""Aplicar sugestão de melhoria dos bots e liberar programa bloqueado do PC: sempre o usuário."""

ACOES_LEVES_DO_COMPUTADOR = frozenset(
    {"clicar", "clique_duplo", "clicar_direito", "rolar", "tecla", "digitar", "arrastar"}
)
"""Ações do computador virtual sem abrir programa (``abrir`` pode trazer rede nova). ``digitar``
com cara de senha é bloqueio absoluto antes de chegar aqui."""

_PAGAMENTO_NOME = re.compile(
    r"(^|[_\-.])(pay|payment|payments|pagar|pagamento|pagamentos|comprar|compra|compras|"
    r"purchase|buy|checkout|charge|cobrar|cobranca|invoice|fatura|subscribe|subscription|"
    r"assinatura|pix|boleto|transfer|transferir|transferencia|refund|reembolso)([_\-.]|$)",
    re.IGNORECASE,
)
_PAGAMENTO_TEXTO = re.compile(
    r"\b(comprar|compre|finalizar (a )?compra|finalizar pedido|fechar pedido|pagar|pagamento|"
    r"checkout|buy now|buy|place order|purchase|pay now|confirmar pagamento|"
    r"adicionar ao carrinho|add to cart|carrinho|cart|assinar plano|subscribe|pix|boleto|"
    r"cart[aã]o de cr[eé]dito|credit card)\b",
    re.IGNORECASE,
)
_PAGAMENTO_URL = re.compile(
    r"/(checkout|pagamento|payment|pay|cart|carrinho|billing)(/|$|\?)", re.IGNORECASE
)
_CANAL_DA_EMPRESA = re.compile(r"(slack|whatsapp|canal_empresa|canais_empresa)", re.IGNORECASE)
_CHAVE_DE_SENHA = re.compile(r"(senha|password|passwd|pwd|ispassword|is_password)", re.IGNORECASE)


def _textos(valor: Any, profundidade: int = 0) -> list[str]:
    """Todos os textos dos argumentos (até 4 níveis), para procurar pagamento."""
    if profundidade > 4:
        return []
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return [t for item in valor.values() for t in _textos(item, profundidade + 1)]
    if isinstance(valor, list | tuple):
        return [t for item in valor for t in _textos(item, profundidade + 1)]
    return []


def _acoes(argumentos: dict[str, Any]) -> list[dict[str, Any]]:
    """Ações de mouse e teclado (``computador_agir``, ``navegador_lote``…) ou o próprio corpo."""
    for chave in ("acoes", "passos", "lote"):
        lista = argumentos.get(chave)
        if isinstance(lista, list):
            return [a for a in lista if isinstance(a, dict)]
    return [argumentos]


def _campo_de_senha(valor: Any, profundidade: int = 0) -> bool:
    """Uma chave de senha com valor (``senha``, ``password``, ``IsPassword: true``…)."""
    if profundidade > 4:
        return False
    if isinstance(valor, dict):
        for chave, item in valor.items():
            if _CHAVE_DE_SENHA.search(str(chave)) and item not in (None, False, "", 0):
                return True
            if _campo_de_senha(item, profundidade + 1):
                return True
    if isinstance(valor, list | tuple):
        return any(_campo_de_senha(item, profundidade + 1) for item in valor)
    return False


def _mexe_em_senha(argumentos: dict[str, Any]) -> bool:
    from app.computador.interface import parece_senha

    if _campo_de_senha(argumentos):
        return True
    for acao in _acoes(argumentos):
        tipo = str(acao.get("tipo") or acao.get("acao") or "")
        texto = acao.get("texto") or acao.get("valor") or acao.get("text")
        if tipo in {"digitar", "preencher", "type", "fill"} and isinstance(texto, str):
            if parece_senha(texto):
                return True
    return False


def _programa_bloqueado(acao: dict[str, Any], argumentos: dict[str, Any]) -> bool:
    from app.computador.pc_usuario import PROGRAMAS_BLOQUEADOS

    condicao = acao.get("condicao") if isinstance(acao.get("condicao"), dict) else {}
    candidatos = [acao.get("programa"), condicao.get("programa"), argumentos.get("programa")]
    candidatos += [a.get("programa") for a in _acoes(argumentos)]
    return any(isinstance(p, str) and p.strip().lower() in PROGRAMAS_BLOQUEADOS for p in candidatos)


def bloqueio_absoluto(acao: Any) -> str | None:
    """Motivo pelo qual a ação **nunca** é aprovada sozinha, em nenhum modo; ``None`` = nenhum.

    Senha (texto que parece senha ou campo de senha), programa bloqueado do PC, envio pelos
    canais da empresa (só leitura), o bot mudar as próprias instruções ou habilidades, sugestão de
    melhoria e pagamento ou compra.
    """
    if not isinstance(acao, dict):
        return "ação ilegível"
    ferramenta = str(acao.get("ferramenta") or "")
    real = nome_real(acao)
    argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
    if acao.get("tipo") in TIPOS_NUNCA_SOZINHOS:
        return "sugestão de melhoria ou programa bloqueado: só você decide"
    if ferramenta in FERRAMENTAS_NUNCA_SOZINHAS or real in FERRAMENTAS_NUNCA_SOZINHAS:
        return "o bot mudar as próprias instruções ou habilidades"
    if _mexe_em_senha(argumentos):
        return "digitar senha ou mexer em campo de senha"
    if _programa_bloqueado(acao, argumentos):
        return "programa bloqueado para bots"
    if (_CANAL_DA_EMPRESA.search(real) or _CANAL_DA_EMPRESA.search(ferramenta)) and not (
        real.startswith("consultar_")
    ):
        return "envio pelos canais da empresa (só leitura)"
    textos = _textos(argumentos)
    if (
        _PAGAMENTO_NOME.search(real)
        or any(_PAGAMENTO_TEXTO.search(t) for t in textos)
        or any(_PAGAMENTO_URL.search(t) for t in textos)
    ):
        return "pagamento ou compra"
    return None


def risco_baixo(acao: Any, *, perfil_tem_login: bool = True) -> bool:
    """Ações que hoje viram cartão mas são de risco baixo (o modo ``automatico`` aprova sozinho):

    - leitura (nome de leitura, inclusive por conector ou catálogo);
    - navegador num perfil **sem login salvo** (clicar, digitar, tecla, lote);
    - computador **virtual** do bot sem abrir programa (clicar, digitar sem senha, tecla, rolar,
      arrastar).

    ``perfil_tem_login`` vem do perfil do bot; na dúvida é ``True`` (falha fechada). Bloqueio
    absoluto e envio externo nunca são risco baixo.
    """
    from app.revisor.politica import parece_somente_leitura

    if not isinstance(acao, dict) or bloqueio_absoluto(acao) is not None:
        return False
    if acao.get("tipo") in TIPOS_SO_UMA_VEZ or e_envio(acao):
        return False
    ferramenta = str(acao.get("ferramenta") or "")
    real = nome_real(acao)
    argumentos = acao.get("argumentos") if isinstance(acao.get("argumentos"), dict) else {}
    if parece_somente_leitura(real.split("__")[-1]):
        return True
    if ferramenta.startswith("navegador_") or real.startswith("navegador_"):
        return not perfil_tem_login
    if ferramenta == "computador_agir":
        if (argumentos.get("alvo") or "virtual") != "virtual":
            return False
        tipos = {str(a.get("tipo") or "") for a in _acoes(argumentos)}
        return bool(tipos) and tipos <= ACOES_LEVES_DO_COMPUTADOR
    return False


def aprova_sozinho(
    modo: str, acao: Any, *, sem_supervisao: bool = False, perfil_tem_login: bool = True
) -> bool:
    """O modo da conversa dispensa o cartão desta ação?

    ``perguntar`` nunca; rotina sem supervisão nunca; bloqueio absoluto e cartão fixo nunca;
    ``total`` sim; ``automatico`` só com ``risco_baixo``.
    """
    from app.revisor.politica import Politica, politica_da_ferramenta

    if sem_supervisao or modo not in {"automatico", "total"}:
        return False
    if not isinstance(acao, dict) or bloqueio_absoluto(acao) is not None:
        return False
    ferramenta = str(acao.get("ferramenta") or "")
    if ferramenta and politica_da_ferramenta(ferramenta) is Politica.CARTAO_FIXO:
        return False
    if modo == "total":
        return True
    return risco_baixo(acao, perfil_tem_login=perfil_tem_login)


def texto_aprovado_automaticamente(modo: str, resumo: str) -> str:
    """Passo do painel Trabalho: "Aprovado automaticamente (modo X)"."""
    rotulo = {"automatico": "automático", "total": "total"}.get(modo, modo)
    return f"Aprovado automaticamente (modo {rotulo}): {resumo}"[:300]
