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

## O que entrou na Sora

| Peça na Sora | Ideia vista no OpenBot | O que faz na Sora |
|---|---|---|
| `app/contexto/` | Medidor de contexto por agente e compactação antes de a janela encher | Mede o uso (do provedor ou estimado por caracteres), níveis ok/atenção/compactar/cheio (70/80/95%), decide compactar **antes** do turno, calcula quantas mensagens resumir para cair a 50% (as 8 últimas ficam inteiras) e liga na compactação que já existia (`app/memoria/compactacao.py`). "Compactar agora" é recusado com turno rodando, mensagem na fila ou outra compactação em andamento. |
| `app/filas/` | Fila FIFO por agente com pausa, retomada, cancelamento e recuperação após queda | Pistas (chat principal + tarefas paralelas, limite 2, máx. 8), FIFO dentro da pista, pausar/retomar, cancelar o que não começou, mover, editar com trava por tela, chave de idempotência, cancelar pedidos de um remetente. Depois de queda: `iniciando` volta para a fila e `rodando` vira `interrompido` (o usuário decide repetir). |
| `app/correio/` + `enviar_para_agente` | Mensagens entre agentes com respostas, reações, imagens e arquivos | `enviar_para_agente` ganhou `responde_a`, `anexos` e `espera_resposta`. Reações com lista curta de emojis (não iniciam turno nem contam salto). Transferência gerenciada: confere acesso, tipo e tamanho, copia para a pasta do destinatário com SHA-256 e cria um anexo novo. Respostas de uma pergunta feita a vários colegas entram juntas num turno só. |
| `app/canais_equipe/` | Canais compartilhados com um responsável por tarefa, delegação explícita, histórico compartilhado e Parar/Retomar/Reatribuir/Arquivar/Restaurar | Roteamento sem modelo quando dá (destinatário, `@menção`, `@todos`, "continua", resposta a uma tarefa, canal de um membro) e com o **líder** quando não dá (resposta em esquema, conferida; nunca vira "manda para todos"). Delegação com limite de 8 por pedido, 2 tarefas rodando por canal, sem devolver para quem passou. Revisão por tarefa recusa resultado de turno velho. Pacote de contexto com limite, que esconde a resposta dos colegas ao mesmo pedido até o agente dar a dele. |
| `app/navegador/perfis.py`, `abas.py`, `persistente.py` | Navegador persistente que os agentes abrem, inspecionam e controlam | Perfis compartilhado / só do agente / nomeado; partição pelo id (nunca pelo nome); logins cifrados com a chave mestra. Abas sobrevivem ao turno, só o agente ou o usuário fecha, o usuário pode **assumir** a aba (login, captcha), aba ociosa descarrega em 30 min, captura de tela e console redigido, restauração depois de reiniciar descartando partição inválida. Todo pedido de rede passa pela proteção SSRF que já existia. |
| `app/eventos/equipe.py` | — | Eventos para a interface (`contexto.atualizado`, `fila.atualizada`, `canal.mensagem`, `canal.tarefa`, `canal.atualizado`, `reacao`, `navegador.aba`). Ficam fora do contrato congelado (`tests/contrato`) até o app ter as telas. |
| `app/api/equipe.py` | — | Rotas do contrato (canais, tarefas, fila, contexto, reações, abas e perfis). Como as outras rotas ainda não ligadas, respondem `NotImplementedError` até o repositório no banco existir. |

### Ferramentas novas dos agentes

`reagir`, `canal_historico`, `canal_delegar`, `canal_transferir`, `canal_resultado`, `navegador_abas`, `navegador_fechar_aba`, `navegador_capturar`, `navegador_console`, `navegador_pedir_ajuda`. Todas estão em `esquemas_das_proximas_fases()` (fora de `ESQUEMAS` até ligar no worker), com política **livre** em `app/revisor/politica.py` (nada sai da Sora) e rótulo no painel Trabalho.

### Banco: migração `0005_pecas_inspiradas_no_openbot`

Colunas novas em `agentes` (`fila_pausada`, `limite_tarefas`, `perfil_navegador`, `perfil_navegador_id`); tabelas `fila_mensagens`, `reacoes`, `transferencias_arquivo`, `canais_equipe`, `membros_canal`, `mensagens_canal`, `tarefas_canal`, `perfis_navegador`, `estados_navegador` (cifrado) e `abas_navegador`. A restrição única de `reacoes` usa `NULLS NOT DISTINCT` (PostgreSQL 15+).

## O que ficou de fora, e por quê

- **App Electron, celular, Live Activity, WebRTC entre computadores, servidor de equipe**: a Sora já tem app próprio (React + Tauri) e servidor próprio.
- **Provedores via CLI (Codex, Claude Code, Grok, ACP)**: a Sora usa as chaves de API do usuário pelo LangChain.
- **Ramificar conversa ("Branch from here") e fios laterais com abas**: dá para fazer depois em cima das pistas da fila.
- **Integrações Slack/Discord**: o modelo é `app/canais` (Telegram); os outros seguem o mesmo formato.
- **Controle do computador (Computer Use)**: fora do escopo do servidor.

## Antes de ligar em produção

- Escrever os repositórios SQLAlchemy dos armazéns (`ArmazemFila`, `ArmazemCanais`, `ArmazemReacoes`) e trocar os `NotImplementedError` de `app/api/equipe.py`.
- No worker: medir o contexto depois de cada chamada, consultar `FilaAgente.proximos` antes de começar turnos, rodar `recuperar_apos_queda` da fila e dos canais ao subir, e o turno curto do líder para `precisa_lider`.
- Rodar `tests/integracao` com Docker para a migração 0005 (PostgreSQL 15+ por causa do `NULLS NOT DISTINCT`).
- Navegador: o worker que abre o Chromium precisa ficar fora do servidor principal, como as sandboxes de `executar_comando`.
- Navegador (Fase A, 2026-11-01): em produção o Chromium roda em contêiner próprio (`navegador`), em redes `internal: true`, e toda saída passa pelo `proxy-egresso`, que resolve o DNS e recusa IP privado, loopback, link-local e metadados depois de resolver. O worker conecta por CDP (`NAVEGADOR_CDP_URL`; sem ele, produção recusa subir o navegador). Prova com Docker real: `sh infra/scripts/provar-isolamento-navegador.sh`.
- Domínio novo em perfil com login passa por revisão (aprovação guardada no perfil, por domínio registrável); rotinas e execuções sem supervisão sempre usam perfil efêmero (`sem_supervisao=True`). Falta: as ferramentas do navegador passarem `sem_supervisao` nas rotinas e tratarem `RevisaoNavegacaoNecessaria` quando forem ligadas no worker.
- Navegador, para quando for ligado ao worker (passo 6), achados do Faro que só valem aí: (a) o despachante das rotinas passa `sem_supervisao=True` no `ContextoFerramenta` e nas chamadas a `GerenteAbas` (a resolução de aba já recusa aba com perfil salvo nesse modo, e fechar a aba efêmera destrói o contexto); (b) o orquestrador captura `RevisaoNavegacaoNecessaria`, pausa a cadeia, avisa por SSE e espera a decisão; (c) `POST /v1/aprovacoes/{id}/decidir` chama `GerenteAbas.aprovar_dominio()` para gravar a aprovação no perfil; (d) iniciar `MotorPlaywright` e `GerenteAbas` no startup do worker e pôr as ferramentas `navegador_*` no catálogo; (e) navegação disparada por clique que cai em domínio barrado volta hoje como erro do Playwright na ação (só `navegar` converte para pedido de revisão).
- Canais de equipe: aplicar a migração 0006 (`tarefas_canal.turno_seq` e `fim_no_turno_do_pai`). A ordem dos turnos vem desses contadores, não do relógio; os repositórios SQL precisam gravar os dois campos.
- Domínios: a lista pública de sufixos vem do pacote `publicsuffixlist` (versão fixada no `uv.lock`, offline). Atualizar o pacote periodicamente.
