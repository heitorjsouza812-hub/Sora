"""Conectores MCP (fase 3): servidores MCP remotos que o usuário conecta, entregues aos
agentes pelo ``langchain-mcp-adapters`` (decisão de 2026-10-14).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``remote-mcp.ts``,
``mcp-connector.ts``, ``mcp-transport.ts``, ``connector-safety.ts``,
``lazy-tool-catalog.ts`` e ``normalizeAgentToolName(s)`` em ``pi-runtime.ts``.

- ``nomes.py``: nomes de ferramenta aceitos por todos os provedores, sem colisão;
- ``servidores.py``: validação do servidor (só https público, com SSRF), conexão segura,
  embrulho das ferramentas (cerca, prazo, erro sem segredo) e o catálogo preguiçoso.

Catálogos hospedados (Composio, Pipedream, Zapier…) entram pelo mesmo caminho, porque todos
oferecem um endpoint MCP.
"""
