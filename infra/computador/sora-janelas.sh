#!/bin/sh
# Lista as janelas visíveis (id x y largura altura título) e a janela ativa.
wmctrl -lG 2>/dev/null || true
echo "---"
xdotool getactivewindow 2>/dev/null || true
