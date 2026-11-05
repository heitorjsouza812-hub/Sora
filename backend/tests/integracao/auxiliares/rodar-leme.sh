#!/bin/sh
# Roda os testes do navegador num contêiner Linux. Uso: rodar-leme.sh <args do pytest>
set -e
export UV_PROJECT_ENVIRONMENT=/venv UV_LINK_MODE=copy
pip install -q uv >/dev/null 2>&1
cd /work
[ -x /venv/bin/pytest ] || uv sync --frozen --group dev --group navegador >/dev/null 2>&1
[ -f /tmp/chromium-ok ] || { /venv/bin/playwright install chromium >/dev/null 2>&1; touch /tmp/chromium-ok; }
export SORA_TESTE_PG="postgresql+asyncpg://t:t@leme-pg:5432/t" SORA_TESTE_REDIS="redis://leme-redis:6379/0"
export NAVEGADOR_CDP_URL=
exec /venv/bin/pytest -p no:cacheprovider "$@"
