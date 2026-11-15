#!/bin/sh
# Sobe a tela virtual, o gerenciador de janelas e o navegador; marca /tmp/sora-pronto quando a
# janela do navegador aparece (ou depois de 20 s, para o bot ver a tela mesmo assim).
set -eu
mkdir -p "$HOME/arquivos" "$HOME/.config" "$HOME/.cache"
rm -f /tmp/sora-pronto /tmp/.X1-lock
mkdir -p -m 1777 /tmp/.X11-unix
Xvfb :1 -screen 0 "${SORA_TELA:-1280x800x24}" -nolisten tcp -nolisten local -noreset &
XVFB=$!
i=0
until xdpyinfo -display :1 >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -gt 100 ] && { echo "a tela virtual não subiu" >&2; exit 1; }
    sleep 0.1
done
openbox >/dev/null 2>&1 &
sleep 0.3
/usr/local/bin/sora-abrir navegador
i=0
until [ -n "$(wmctrl -l 2>/dev/null)" ] || [ "$i" -gt 200 ]; do
    i=$((i + 1))
    sleep 0.1
done
touch /tmp/sora-pronto
wait "$XVFB"
