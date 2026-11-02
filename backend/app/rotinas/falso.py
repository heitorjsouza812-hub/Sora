"""Roteiro do modelo falso (``SORA_MODELO_FALSO=1``) para o papel ``rotina``.

Só para desenvolvimento e testes. O que o pedido da rotina contém decide o roteiro:

- ``[sem-novidades]``: responde ``SEM_RESPOSTA`` (a rotina fica em silêncio);
- ``[usar:listar]``: chama ``listar_agendamentos`` (ferramenta segura) e relata o resultado;
- ``[tentar:agendar]``: tenta ``agendar`` (proibida sem supervisão) e relata o que voltou;
- ``[lembrar:texto]``: chama ``buscar_memoria`` com o texto;
- qualquer outro: um resumo curto.
"""

from __future__ import annotations

import re
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

_LEMBRAR = re.compile(r"\[lembrar:([^\]]+)\]")


def _chamada(nome: str, argumentos: dict) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": nome, "args": argumentos, "id": f"call_{uuid4().hex[:12]}"}]
    )


def resposta_da_rotina(mensagens: list[BaseMessage]) -> AIMessage:
    pedido = "\n".join(str(m.content) for m in mensagens if isinstance(m, HumanMessage))
    resultados = [m for m in mensagens if isinstance(m, ToolMessage)]
    if "[sem-novidades]" in pedido:
        return AIMessage(content="SEM_RESPOSTA")
    if "[usar:listar]" in pedido:
        if not resultados:
            return _chamada("listar_agendamentos", {})
        return AIMessage(content=f"Agendamentos vistos: {resultados[-1].content}")
    if "[tentar:agendar]" in pedido:
        if not resultados:
            return _chamada(
                "agendar", {"titulo": "intruso", "pedido": "x", "daqui_minutos": 5}
            )
        return AIMessage(content=f"Retorno do agendar: {resultados[-1].content}")
    achado = _LEMBRAR.search(pedido)
    if achado:
        if not resultados:
            return _chamada("buscar_memoria", {"consulta": achado.group(1)})
        return AIMessage(content=f"Memória: {resultados[-1].content}")
    return AIMessage(content="Resumo da rotina: tudo certo (modelo falso).")
