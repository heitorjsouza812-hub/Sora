#!/bin/sh
# Abre um programa da lista fechada (o bot nunca passa linha de comando).
set -eu
case "${1:-}" in
    navegador) setsid chromium about:blank >/dev/null 2>&1 & ;;
    terminal) setsid xterm -fa 'DejaVu Sans Mono' -fs 11 -geometry 110x32 >/dev/null 2>&1 & ;;
    *) echo "programa desconhecido" >&2; exit 2 ;;
esac
