"""Rótulos dos passos do painel Trabalho (especificação §4, regra do evento
``passo``; §3.3, Painel Trabalho).

O backend monta o rótulo a partir do nome e dos argumentos da ferramenta
("Buscando: cafeterias no bairro", "Lendo: g1.globo.com", "Gerando 3
imagens"), sem segredos. O modelo não precisa narrar nada.
"""

from __future__ import annotations

from typing import Any

NOME_EXIBIDO: dict[str, str] = {
    "buscar_web": "Busca na web",
    "ler_pagina": "Ler página",
    "ler_anexo": "Ler anexo",
    "escrever_arquivo": "Escrever arquivo",
    "gerar_imagem": "Gerar imagem",
    "entregar": "Entrega",
    "veredito": "Verificação",
}
"""Nome técnico (``acao``) → nome mostrado (``ferramenta``) no evento ``passo``."""


def rotulo_do_passo(acao: str, argumentos: dict[str, Any]) -> str:
    """Rótulo legível do passo ("Buscando: …")."""
    raise NotImplementedError


def parametros_sem_segredos(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Cópia dos argumentos sem nada que pareça chave, token ou senha."""
    raise NotImplementedError


def resumir_resultado(acao: str, resultado: Any) -> dict[str, Any]:
    """Resultado resumido para o passo: ``{resumo, links[{titulo, dominio}], itens[]}``."""
    raise NotImplementedError
