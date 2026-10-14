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
