# Computador virtual de um bot (docs/computador-por-bot.md): área de trabalho Linux leve com
# tela virtual (Xvfb), gerenciador de janelas (Openbox), navegador (Chromium) e utilitários de
# mouse, teclado e captura. Um contêiner por bot, criado pelo worker sob demanda.
#
# O contêiner roda com a raiz só leitura, sem capacidades, sem montar nada do host e numa rede
# interna própria cuja única saída é o proxy de egresso (recusa IP privado depois do DNS).
# Construir: docker build -t sora-computador:1 infra/computador
FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb openbox chromium chromium-l10n xdotool wmctrl x11-utils xterm imagemagick \
        fonts-dejavu-core fonts-liberation ca-certificates procps \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
    && useradd --create-home --uid 1000 --shell /bin/bash bot

COPY sora-iniciar.sh /usr/local/bin/sora-iniciar
COPY sora-abrir.sh /usr/local/bin/sora-abrir
COPY sora-janelas.sh /usr/local/bin/sora-janelas
COPY chromium-sora.conf /etc/chromium.d/sora
COPY politicas-chromium.json /etc/chromium/policies/managed/sora.json
COPY menu.xml /etc/xdg/openbox/menu.xml
RUN chmod 0755 /usr/local/bin/sora-iniciar /usr/local/bin/sora-abrir /usr/local/bin/sora-janelas \
    && chmod 0644 /etc/chromium.d/sora /etc/chromium/policies/managed/sora.json /etc/xdg/openbox/menu.xml

USER 1000:1000
ENV DISPLAY=:1 HOME=/home/bot SORA_TELA=1280x800x24
WORKDIR /home/bot
CMD ["/usr/local/bin/sora-iniciar"]
