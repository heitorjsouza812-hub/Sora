# OpenBot → Sora

O [OpenBot](https://github.com/nightly-labs/openbot) é um app de desktop (Electron + SolidJS, backend em TypeScript) que coordena vários agentes de IA. Em 2026-11-01 a equipe olhou o projeto para trazer à Sora o que fazia sentido: monitor de contexto, filas, mensagens entre agentes, canais compartilhados e navegador persistente.

## Licença: por que nada foi copiado

O OpenBot usa a **PolyForm Noncommercial 1.0.0**. Ela só permite uso **sem fins comerciais**; uso comercial exige comprar uma licença (licenses@openbot.run). A Sora quer ser produto comercial, então:

- **nenhuma linha de código, texto de prompt ou arquivo do OpenBot entrou no repositório**;
- olhamos só a documentação de arquitetura deles (`docs/architecture/*.md`, `README.md`) para entender **o que** cada recurso faz. Ideias, conceitos e comportamentos não são protegidos por direito autoral; o texto e o código, sim;
- cada peça foi escrita do zero em Python, no estilo da Sora (nomes em PT-BR, armazém plugável + versão em memória para testes), com regras e números escolhidos por nós;
- conferido em 2026-11-01: nenhum trecho de 60 caracteres dos arquivos novos aparece nos fontes `.ts`/`.md` do OpenBot (só nomes padrão de tipos MIME).

Isso é diferente do [Rakazo](rakazo.md), que é Apache 2.0 e permite adaptar código com aviso.

> Se um dia a equipe quiser usar código do OpenBot de verdade, precisa da licença comercial antes.

## Estado na etapa 4 (passo 6)

As peças abaixo deixaram de ser só fundação. No ramo `etapa4-pecas`, fila, canais, correio, contexto e navegador persistente estão ligados ao worker e ao app. Os armazéns usam PostgreSQL, os eventos chegam pelo stream global, e a recuperação consulta batimento antes de mexer num turno que outro worker ainda executa. A etapa continua aguardando o veredito final do Aferidor; este texto descreve o que está implementado e provado pelos donos, não uma aprovação final.

## O que entrou na Sora

| Peça na Sora | Ideia vista no OpenBot | O que faz na Sora |
|---|---|---|
| `app/contexto/` | Medidor de contexto por agente e compactação antes de a janela encher | Mede o uso (do provedor ou estimado por caracteres), níveis ok/atenção/compactar/cheio (70/80/95%), decide compactar **antes** do turno, calcula quantas mensagens resumir para cair a 50% (as 8 últimas ficam inteiras) e liga na compactação que já existia (`app/memoria/compactacao.py`). "Compactar agora" é recusado com turno rodando, mensagem na fila ou outra compactação em andamento. |
| `app/filas/` | Fila FIFO por agente com pausa, retomada, cancelamento e recuperação após queda | Pistas (chat principal + tarefas paralelas, limite 2, máx. 8), FIFO dentro da pista, pausar/retomar, cancelar o que não começou, mover, editar com trava por tela, chave de idempotência, cancelar pedidos de um remetente. Depois de queda: `iniciando` volta para a fila e `rodando` vira `interrompido` (o usuário decide repetir). |
| `app/correio/` + `enviar_para_agente` | Mensagens entre agentes com respostas, reações, imagens e arquivos | `enviar_para_agente` ganhou `responde_a`, `anexos` e `espera_resposta`. Reações com lista curta de emojis (não iniciam turno nem contam salto). Transferência gerenciada: confere acesso, tipo e tamanho, copia para a pasta do destinatário com SHA-256 e cria um anexo novo. Respostas de uma pergunta feita a vários colegas entram juntas num turno só. |
| `app/canais_equipe/` | Canais compartilhados com um responsável por tarefa, delegação explícita, histórico compartilhado e Parar/Retomar/Reatribuir/Arquivar/Restaurar | Roteamento sem modelo quando dá (destinatário, `@menção`, `@todos`, "continua", resposta a uma tarefa, canal de um membro) e com o **líder** quando não dá (resposta em esquema, conferida; nunca vira "manda para todos"). Delegação com limite de 8 por pedido, 2 tarefas rodando por canal, sem devolver para quem passou. Revisão por tarefa recusa resultado de turno velho. Pacote de contexto com limite, que esconde a resposta dos colegas ao mesmo pedido até o agente dar a dele. |
| `app/navegador/perfis.py`, `abas.py`, `persistente.py` | Navegador persistente que os agentes abrem, inspecionam e controlam | Perfis compartilhado / só do agente / nomeado; partição pelo id (nunca pelo nome); logins cifrados com a chave mestra. Abas sobrevivem ao turno, só o agente ou o usuário fecha, o usuário pode **assumir** a aba (login, captcha), aba ociosa descarrega em 30 min, captura de tela e console redigido, restauração depois de reiniciar descartando partição inválida. Todo pedido de rede passa pela proteção SSRF que já existia. |
| `app/eventos/equipe.py` | — | Eventos para a interface (`contexto.atualizado`, `fila.atualizada`, `canal.mensagem`, `canal.tarefa`, `canal.atualizado`, `reacao`, `navegador.aba`). Estão ligados ao stream global `GET /v1/eventos` e alimentam as telas da etapa 4. |
| `app/api/equipe.py` + `app/api/navegador.py` | — | Rotas reais de canais, tarefas, fila, contexto, reações, abas e perfis. Os `NotImplementedError` foram removidos; cada rota filtra pelo dono e usa os armazéns SQL. |

### Ferramentas novas dos agentes

`reagir`, `canal_historico`, `canal_delegar`, `canal_transferir`, `canal_resultado`, `navegador_abas`, `navegador_fechar_aba`, `navegador_capturar`, `navegador_console` e `navegador_pedir_ajuda` estão no catálogo ativo do worker. As ferramentas de canal rodam em tarefas persistidas; as de navegador usam o perfil do agente e recusam uma aba assumida pelo usuário. Ações que podem mudar o mundo passam pelo revisor; leitura continua livre.

### Banco: migração `0005_pecas_inspiradas_no_openbot`

Colunas novas em `agentes` (`fila_pausada`, `limite_tarefas`, `perfil_navegador`, `perfil_navegador_id`); tabelas `fila_mensagens`, `reacoes`, `transferencias_arquivo`, `canais_equipe`, `membros_canal`, `mensagens_canal`, `tarefas_canal`, `perfis_navegador`, `estados_navegador` (cifrado) e `abas_navegador`. A restrição única de `reacoes` usa `NULLS NOT DISTINCT` (PostgreSQL 15+).

## O que ficou de fora, e por quê

- **App Electron, celular, Live Activity, WebRTC entre computadores, servidor de equipe**: a Sora já tem app próprio (React + Tauri) e servidor próprio.
- **Provedores via CLI (Codex, Claude Code, Grok, ACP)**: a Sora usa as chaves de API do usuário pelo LangChain.
- **Ramificar conversa ("Branch from here") e fios laterais com abas**: dá para fazer depois em cima das pistas da fila.
- **Integrações Slack/Discord**: o modelo é `app/canais` (Telegram); os outros seguem o mesmo formato.
- **Controle do computador (Computer Use)**: fora do escopo do servidor.

## O que foi ligado no worker

- **Contexto:** medição depois das chamadas de modelo, compactação automática antes de encher e job para "Compactar agora". O botão recusa quando há turno, fila ou compactação em andamento.
- **Fila:** `responder_direto` só enfileira; `executar_item_fila` reserva, roda o turno real e chama o próximo. Pausar, retomar, Repetir e recuperação após queda usam o mesmo caminho. Um worker novo não interrompe trabalho com batimento vivo.
- **Canais e correio:** mensagens, tarefas, delegação, reações e anexos ficam no PostgreSQL. Parar e Cancelar mandam interrupção pelo Redis ao worker dono do turno. As travas cobrem a cadeia inteira de tarefas.
- **Navegador persistente:** `MotorPlaywright`, `GerenteAbas` e o navegador por árvore sobem com o worker. Perfis e logins são cifrados; abas são sincronizadas pelo banco entre workers; domínio novo vira cartão; rotina só vê aba efêmera. O app mostra perfis, rastro, captura e Assumir/Devolver.

## O que segue de fora ou pendente

- A fase 2 do Aferidor ainda precisa validar a ponta atual do ramo com integração, dois workers, reinício, e2e e o Teste de pronto completo.
- O Chromium de produção continua fora do servidor principal: contêiner `navegador`, redes `internal: true`, saída pelo `proxy-egresso` e conexão por `NAVEGADOR_CDP_URL`. A prova da Fase A existe em `infra/scripts/provar-isolamento-navegador.sh`, mas o fluxo completo da etapa 4 ainda precisa ser repetido nesse desenho.
- O login "último que grava vence" ainda é possível quando dois workers mantêm o mesmo perfil aberto. As aprovações de domínio vêm sempre do banco, o que reduz o risco, mas não elimina essa disputa de cookies.
- Abrir um perfil cria uma aba assumida no worker; **espelhar essa aba ao vivo** para o usuário digitar senha ou resolver captcha não entrou.
- A árvore ainda não lê o conteúdo de iframes. A barreira de redirect por CDP cobre documentos, inclusive iframe, mas não `fetch`/XHR.
- A lista pública de sufixos vem de `publicsuffixlist`, fixada no `uv.lock`; precisa de atualização periódica.
- Ramificação de conversa, fios laterais, Slack/Discord, WebRTC entre computadores e controle do sistema operacional continuam fora do escopo desta etapa.
