"""Canais de equipe: um chat compartilhado onde o usuário fala com vários agentes ao mesmo tempo.

Ideia vista no OpenBot (github.com/nightly-labs/openbot, PolyForm Noncommercial). **Nenhum código
foi copiado**; esta é uma implementação própria da Sora — veja ``docs/referencias/openbot.md``.
(Não confundir com ``app/canais``, que liga Telegram e outros apps de mensagem.)

Na Sora, um canal tem:

- **propósito** e **instruções** (o que esse grupo faz);
- **membros**: os agentes que podem receber trabalho ali;
- um **líder** (coordenador), que decide quem responde quando a mensagem não diz;
- **histórico compartilhado**: todo mundo vê todas as mensagens; cada agente recebe um pacote de
  contexto com limite de tamanho, e não o histórico inteiro;
- **tarefas**: cada pedido vira uma tarefa com **um responsável**. O responsável pode
  **delegar** partes (tarefas filhas) a outros membros ou **transferir** a tarefa inteira;
- **controles**: Parar, Retomar, Reatribuir, Cancelar, Arquivar e Restaurar.

Módulos:

- :mod:`app.canais_equipe.modelos` — tipos e estados;
- :mod:`app.canais_equipe.roteamento` — quem responde, sem gastar modelo quando dá;
- :mod:`app.canais_equipe.servico` — regras de tarefas, delegação e controles;
- :mod:`app.canais_equipe.contexto` — o pacote que cada agente lê;
- :mod:`app.canais_equipe.ferramentas` — as ferramentas dos agentes dentro de um canal.
"""
