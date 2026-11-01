"""Correio entre agentes: respostas, reações, imagens e transferência gerenciada de arquivos.

Ideia vista no OpenBot (github.com/nightly-labs/openbot, PolyForm Noncommercial). **Nenhum código
foi copiado**; esta é uma implementação própria da Sora — veja ``docs/referencias/openbot.md``.

- ``app/ferramentas/enviar_para_agente.py`` continua sendo a ferramenta de envio; agora aceita
  ``responde_a``, ``anexos`` e ``espera_resposta``;
- :mod:`app.correio.transferencias` confere quem pode passar cada arquivo, os limites e o tipo,
  e faz a cópia gerenciada (com hash) para a pasta do destinatário;
- :mod:`app.correio.reacoes` guarda as reações (do usuário e dos agentes) em mensagens;
- :mod:`app.correio.entrega` monta o que o agente de destino lê: quem mandou, a mensagem
  respondida, as imagens (para modelos com visão) e os arquivos, tudo cercado como dado.
"""
