# Backend da Sora

Esqueleto assíncrono em Python 3.12 para a API, filas, persistência e eventos da Sora,
conforme `docs/plano-de-implementacao/02-especificacao-do-backend.md`.

## Desenvolvimento

```powershell
uv sync --python 3.12
uv run uvicorn app.main:app --reload
uv run ruff check .
uv run pytest
```

A API expõe `GET /health`. Copie `../infra/.env.exemplo` para um `.env` local e
preencha os segredos antes de ligar serviços reais. O Docker Compose está documentado,
mas não foi executado nesta máquina por ausência do Docker.

## Peças adaptadas do Rakazo

Em 2026-10-17 entraram no backend peças portadas do [Rakazo](https://github.com/elie222/rakazo)
(Apache 2.0) para as fases 1, 2 e 3: limite de saltos entre agentes, catálogo preguiçoso de
ferramentas, política de aprovação, compactação e busca no histórico, memória, agenda,
pendências, habilidades, conectores MCP, Telegram, voz, navegador por texto,
`executar_comando`, gráficos e busca DuckDuckGo (só dev). Mapa, licença e pendências:
[`docs/referencias/rakazo.md`](../docs/referencias/rakazo.md).

O navegador por texto usa o Playwright, que é opcional:

```powershell
uv sync --python 3.12 --group navegador
uv run playwright install chromium
```
