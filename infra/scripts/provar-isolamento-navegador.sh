#!/bin/sh
set -eu

docker compose --profile teste-navegador up -d --build proxy-egresso alvo-privado navegador
docker compose exec -T navegador sh -c "cd /opt/sora && python provar-isolamento-navegador.py"

# O proxy (rede isolada) não pode falar com o CDP: nem a ponte (9223) nem o Chromium cru (9222).
docker compose exec -T proxy-egresso python - < scripts/provar-cdp-fechado.py
