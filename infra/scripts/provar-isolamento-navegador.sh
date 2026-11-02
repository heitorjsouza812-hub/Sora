#!/bin/sh
set -eu

docker compose --profile teste-navegador up -d --build proxy-egresso alvo-privado navegador
docker compose exec -T navegador sh -c "cd /opt/sora && python provar-isolamento-navegador.py"
