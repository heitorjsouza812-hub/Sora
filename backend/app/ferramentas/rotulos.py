"""Rótulos dos passos do painel Trabalho (especificação §4, regra do evento
``passo``; §3.3, Painel Trabalho).

O backend monta o rótulo a partir do nome e dos argumentos da ferramenta
("Buscando: cafeterias no bairro", "Lendo: g1.globo.com", "Gerando 3
imagens"), sem segredos. O modelo não precisa narrar nada.

``rotulo_do_passo`` foi adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0):
``describeToolActivity`` em ``pi-runtime.ts``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.busca.provedor import dominio
from app.core.redacao import limpar_texto_sensivel, ocultar_argumentos_sensiveis

LIMITE_DETALHE = 90
"""Caracteres do detalhe no rótulo (o resto vira ``…``)."""

NOME_EXIBIDO: dict[str, str] = {
    "buscar_web": "Busca na web",
    "ler_pagina": "Ler página",
    "ler_anexo": "Ler anexo",
    "escrever_arquivo": "Escrever arquivo",
    "gerar_imagem": "Gerar imagem",
    "entregar": "Entrega",
    "veredito": "Verificação",
    "buscar_memoria": "Memória",
    "lembrar": "Memória",
    "esquecer_memoria": "Memória",
    "buscar_historico": "Histórico",
    "ler_historico": "Histórico",
    "enviar_para_agente": "Mensagem a agente",
    "chamar_conector": "Conector",
    "executar_comando": "Terminal",
    "gerar_grafico": "Gráfico",
    "agendar": "Agenda",
    "ler_habilidade": "Habilidade",
}
"""Nome técnico (``acao``) → nome mostrado (``ferramenta``) no evento ``passo``."""


def _detalhe(valor: Any) -> str:
    texto = " ".join(limpar_texto_sensivel(str(valor if valor is not None else "")).split())
    return texto if len(texto) <= LIMITE_DETALHE else f"{texto[:LIMITE_DETALHE]}…"


def _site(valor: Any) -> str:
    host = dominio(str(valor or ""))
    return _detalhe(host) if host else "[url inválida]"


def _plural(n: Any, um: str, varios: str) -> str:
    try:
        quantidade = int(n)
    except (TypeError, ValueError):
        quantidade = 1
    return f"{quantidade} {um if quantidade == 1 else varios}"


_ROTULOS: dict[str, Callable[[dict[str, Any]], str]] = {
    "buscar_web": lambda a: f"Buscando: {_detalhe(a.get('consulta'))}",
    "ler_pagina": lambda a: f"Lendo: {_site(a.get('url'))}",
    "ler_anexo": lambda _: "Lendo o anexo",
    "escrever_arquivo": lambda a: f"Escrevendo {_detalhe(a.get('nome'))}",
    "gerar_imagem": lambda a: f"Gerando {_plural(a.get('quantidade', 1), 'imagem', 'imagens')}",
    "entregar": lambda a: f"Entregando: {_detalhe(a.get('titulo'))}",
    "veredito": lambda _: "Conferindo os requisitos",
    "falar": lambda _: "Respondendo",
    "perguntar": lambda _: "Perguntando ao usuário",
    "disparar_especialista": lambda a: f"Chamando especialista: {_detalhe(a.get('papel'))}",
    "ver_especialista": lambda _: "Olhando o especialista",
    "mensagem_especialista": lambda _: "Corrigindo a rota do especialista",
    "parar_especialista": lambda _: "Parando o especialista",
    "criar_agente": lambda a: f"Criando agente: {_detalhe(a.get('nome'))}",
    "buscar_memoria": lambda a: f"Lembrando: {_detalhe(a.get('consulta'))}",
    "lembrar": lambda _: "Guardando na memória",
    "esquecer_memoria": lambda _: "Apagando uma memória",
    "buscar_historico": lambda a: f"Procurando na conversa: {_detalhe(a.get('consulta'))}",
    "ler_historico": lambda _: "Relendo a conversa",
    "enviar_para_agente": lambda _: "Mandando mensagem a outro agente",
    "catalogo_tarefas": lambda _: "Conferindo o que sei fazer",
    "propor_instrucoes": lambda _: "Propondo novas instruções",
    "agendar": lambda a: f"Agendando: {_detalhe(a.get('titulo'))}",
    "listar_agendamentos": lambda _: "Olhando a agenda",
    "cancelar_agendamento": lambda _: "Cancelando um agendamento",
    "adicionar_pendencia": lambda a: f"Anotando: {_detalhe(a.get('titulo'))}",
    "listar_pendencias": lambda _: "Olhando as pendências",
    "atualizar_pendencia": lambda _: "Atualizando uma pendência",
    "concluir_pendencia": lambda _: "Concluindo uma pendência",
    "remover_pendencia": lambda _: "Removendo uma pendência",
    "ler_habilidade": lambda a: f"Lendo a habilidade: {_detalhe(a.get('nome'))}",
    "criar_habilidade": lambda a: f"Criando a habilidade: {_detalhe(a.get('nome'))}",
    "atualizar_habilidade": lambda a: f"Atualizando a habilidade: {_detalhe(a.get('nome'))}",
    "apagar_habilidade": lambda a: f"Apagando a habilidade: {_detalhe(a.get('nome'))}",
    "adicionar_servidor_mcp": lambda a: f"Conectando servidor MCP: {_detalhe(a.get('nome'))}",
    "executar_comando": lambda a: f"Rodando: {_detalhe(a.get('comando'))}",
    "gerar_grafico": lambda a: f"Desenhando gráfico: {_detalhe(a.get('titulo') or a.get('tipo'))}",
    "navegador_abrir": lambda a: f"Abrindo: {_site(a.get('url'))}",
    "navegador_ler": lambda _: "Lendo a página",
    "navegador_agir": lambda _: "Usando a página",
}

_CONECTOR = re.compile(r"^mcp__(.+?)__(.+)$")


def rotulo_do_passo(acao: str, argumentos: dict[str, Any]) -> str:
    """Rótulo legível do passo ("Buscando: …")."""
    argumentos = argumentos if isinstance(argumentos, dict) else {}
    montar = _ROTULOS.get(acao)
    if montar is not None:
        return montar(argumentos)
    conector = _CONECTOR.match(acao)
    if conector:
        return f"Usando {_detalhe(conector.group(1))}: {_detalhe(conector.group(2))}"
    if acao == "chamar_conector":
        servidor = _detalhe(argumentos.get("servidor"))
        return f"Usando {servidor}: {_detalhe(argumentos.get('ferramenta'))}"
    return f"Usando {_detalhe(acao)}"


def parametros_sem_segredos(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Cópia dos argumentos sem nada que pareça chave, token ou senha."""
    return ocultar_argumentos_sensiveis(argumentos if isinstance(argumentos, dict) else {})


def resumir_resultado(acao: str, resultado: Any) -> dict[str, Any]:
    """Resultado resumido para o passo: ``{resumo, links[{titulo, dominio}], itens[]}``."""
    raise NotImplementedError
