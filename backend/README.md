# Backend da Sora

Backend assíncrono em Python 3.12 para a API, filas, persistência e eventos da Sora,
conforme `docs/plano-de-implementacao/02-especificacao-do-backend.md`.

## Rodar localmente

Os comandos abaixo partem de `C:\dev\sora`. O Compose sobe somente PostgreSQL e Redis; a API
roda no host para recarregar o código rapidamente. O override `infra/docker-compose.dev.yml`
publica as duas portas apenas em `127.0.0.1` e não deve ser usado em produção.

1. Crie o arquivo local exigido pelo Compose e defina a senha do PostgreSQL. O arquivo é
   ignorado pelo Git. O PostgreSQL exige essa senha; o Redis local atual não exige senha.

   ```powershell
   Copy-Item infra/.env.exemplo infra/.env
   # Edite infra/.env e preencha POSTGRES_PASSWORD com a mesma senha abaixo.
   $env:POSTGRES_PASSWORD = "SUA_SENHA_LOCAL"
   ```

2. Instale as dependências e suba a infraestrutura:

   ```powershell
   docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis
   Set-Location backend
   uv sync --python 3.12
   ```

3. Configure a sessão do PowerShell. Os valores abaixo são somente para desenvolvimento local;
   gere uma `CHAVE_MESTRA` base64 de 32 bytes e um `JWT_SEGREDO` próprios.

   ```powershell
   $env:DATABASE_URL = "postgresql://sora:SUA_SENHA_LOCAL@127.0.0.1:5432/sora"
   $env:REDIS_URL = "redis://127.0.0.1:6379/0"
   $env:CHAVE_MESTRA = "BASE64_DE_32_BYTES"
   $env:JWT_SEGREDO = "segredo-local"
   $env:AMBIENTE = "desenvolvimento"
   $env:SORA_MODELO_FALSO = "1"
   ```

4. Aplique as migrações, crie um convite e inicie a API na porta usada pelo proxy do Vite:

   ```powershell
   uv run alembic upgrade head
   uv run python -m app.cli convite criar --codigo DESENVOLVIMENTO --usos 10
   uv run uvicorn app.main:app --reload --port 8000
   ```

   Sem `--codigo`, o CLI gera um código aleatório. `--usos` vale `1` por padrão.

Em shells POSIX, o servidor equivalente é:

```bash
AMBIENTE=desenvolvimento SORA_MODELO_FALSO=1 uv run uvicorn app.main:app --port 8000
```

O Vite encaminha `/v1` de `http://localhost:5173` para essa API. Em desenvolvimento, o cookie
`sora_renovacao` é `HttpOnly` e `SameSite=Lax`, mas não `Secure`, portanto funciona sobre HTTP.
O CORS local permite `http://localhost:5173`, `http://tauri.localhost` e `tauri://localhost`,
incluindo o cabeçalho `X-Sora-Cliente` usado pelo desktop. Em produção, o cookie continua
obrigatoriamente `Secure` e localhost continua proibido.

## Verificações

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

A API expõe `GET /health`.

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
