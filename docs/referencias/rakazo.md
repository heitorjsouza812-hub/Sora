# Rakazo → Sora

O [Rakazo](https://github.com/elie222/rakazo) é um agente open source (TypeScript, Apache 2.0) que se apresenta como alternativa ao Grok Bot, o mesmo espaço da Sora. Em 2026-10-17 a equipe decidiu trazer para a Sora tudo o que dava para aproveitar dele. Como a Sora é Python/LangChain, nada foi copiado como código: cada peça foi **portada** para Python, com nomes em PT-BR, encaixada nos módulos que já existiam e coberta por testes.

## Licença

O Rakazo é Apache 2.0, que permite copiar, adaptar e usar comercialmente. As condições são manter o aviso de licença e indicar o que mudou. Por isso:

- a licença deles está em [`rakazo-LICENSE.txt`](rakazo-LICENSE.txt);
- todo arquivo derivado diz no topo `Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): <arquivo de origem>`;
- esta página lista o que foi portado e o que mudou.

## O que foi portado

### Fase 1: coordenação, aprovação e contexto

| Peça na Sora | Origem no Rakazo | O que faz |
|---|---|---|
| `app/orquestrador/saltos.py` | `core/src/bot-messages.ts` | Limite de 6 trocas seguidas entre agentes sem o usuário (`SORA_MAX_SALTOS`). A mensagem do usuário zera a corrente. Coluna `mensagens.salto`. |
| `app/ferramentas/catalogo_preguicoso.py` | `adapters/src/lazy-tool-catalog.ts` | Até 20 ferramentas vão direto; acima disso o agente recebe `conectores_buscar_ferramentas`, `conectores_carregar_ferramenta` e `conectores_executar_ferramenta`. Valida os argumentos antes de chamar o servidor. |
| `app/revisor/politica.py` (+ `exige_revisao` em `acoes.py`) | `core/src/action-approval.ts` | Cada ferramenta é `livre`, `cartao_fixo` ou `revisor`. Conector com nome de leitura (`list_`, `buscar_`…) é livre; o resto vai para o revisor. Lista do que pode rodar em rotina sem supervisão. |
| `app/revisor/juiz.py` + `prompts/juiz_rapido.v1.md` | `adapters/src/auto-review.ts` | Executa o revisor de ações com dados redigidos e truncados, prazo curto e **falha fechada** (erro ou prazo estourado = BLOQUEAR = cartão para o usuário). |
| `app/memoria/compactacao.py` + `prompts/compactacao_historico.v1.md` | `adapters/src/history-compaction.ts` | Janela de 50 mensagens + resumo cumulativo em lotes de 50, com cursor em `conversas.compactado_ate`. Nunca cria buraco no histórico. |
| `app/ferramentas/historico.py` | `db/src/history-retrieval.ts` | `buscar_historico` (literal, todas as palavras, 5 por página, com `proxima_busca`) e `ler_historico` (em volta, anteriores, seguintes, paginação de mensagens longas). |
| `app/ferramentas/catalogo_tarefas.py` | `task_catalog` | Inventário real (ferramentas, habilidades, agenda, pendências) para o agente não inventar capacidade. |
| `app/ferramentas/propor_instrucoes.py` | `propose_instructions_update` | O agente propõe mudar as **próprias** instruções; o usuário aprova no cartão com a diferença. Protege a personalidade. |
| `app/agentes/instrucoes.py` | `userTurnInstructions` (`executor.ts`) | Cláusulas de uso que só entram para as ferramentas oferecidas: agente × especialista, "escrever [para Atlas] não envia nada", cursores opacos, dado externo, aviso de progresso. |
| `app/core/redacao.py` | `connector-safety.ts`, `redactSecrets`, `sanitizeSensitiveText` | Tira segredos conhecidos e padrões (`sk-…`, `Bearer`, JWT, `api_key=`) de erros, payloads, passos e logs. |
| `app/ferramentas/rotulos.py` (`rotulo_do_passo`) | `describeToolActivity` | Rótulo do painel Trabalho ("Buscando: …", "Lendo: g1.globo.com"), sem segredo. |
| `app/agentes/prompts.py` (`carregar_prompt`, `preencher`, `cercar`) | `escapePromptData` | Os três stubs foram implementados porque as peças acima dependem deles. |

### Fase 2: memória, rotinas, pendências e habilidades

| Peça na Sora | Origem no Rakazo | O que faz |
|---|---|---|
| `app/memoria/servico.py` | `packages/memory`, `memory-tools.ts`, `memory-context.ts` | `lembrar`, `buscar_memoria`, `esquecer_memoria` sobre a tabela `memorias` (busca no pgvector quando houver `Vetorizador`; senão, por palavras). Recusa senha e chave. No máximo 5 memórias no prompt, cercadas. |
| `app/ferramentas/enviar_para_agente.py` | `message_bot` | Ferramenta da fase 2 da especificação, com o limite de saltos e o diretório de colegas. |
| `app/rotinas/agenda.py` | `schedule_create`, `core/src/cron.ts` | `agendar` (cron de 5 campos no fuso do usuário, "a cada N", data exata ou "daqui N minutos"), `listar_agendamentos`, `cancelar_agendamento`. Tabela `rotinas`. |
| `app/rotinas/silencio.py` | `silent-reply.ts` | `SEM_RESPOSTA`: a rotina termina sem mensagem quando não há nada a relatar. |
| `app/pendencias/` | `scratchpad-tools.ts`, `scratchpad-context.ts` | Trabalho aberto que sobrevive ao turno (até 4 KB no prompt). Tabela `pendencias`. |
| `app/habilidades/` | `core/src/agent-skill.ts`, `teach-playbook.ts`, `skill-tools.ts` | Receitas SKILL.md (formato das Agent Skills), `/Nome` para forçar, `@Nome` em rotinas, formato de playbook ensinado. Tabela `habilidades`. |
| `app/orquestrador/travados.py` | `core/src/stuck-work.ts` | Lembra depois de 4 h e cancela depois de 24 h etapas esperando o usuário; retoma uma vez etapas cujo worker morreu. |

### Fase 3: conectores, canais, voz, navegador, computador

| Peça na Sora | Origem no Rakazo | O que faz |
|---|---|---|
| `app/conectores/` | `remote-mcp.ts`, `mcp-transport.ts`, `normalizeAgentToolName(s)` | Servidores MCP do usuário pelo `langchain-mcp-adapters`: só https público (proteção SSRF do `ler_pagina` no cliente httpx), cabeçalhos cifrados em `conectores`, nomes `mcp__servidor__ferramenta`, resultado cercado, prazo, erro sem segredo e catálogo preguiçoso. Composio, Pipedream e Zapier entram por aqui (todos têm endpoint MCP). |
| `app/canais/telegram.py` + `app/api/canais.py` | `messaging-platforms.ts`, `messaging-delivery.ts` | Bot do Telegram por webhook (segredo conferido em tempo constante), vínculo com código de uso único (`/start CODIGO`), resposta cortada em 4.096 caracteres. Tabela `canais_vinculados`. |
| `app/voz/` | `openai-voice.ts`, `elevenlabs-voice.ts`, `cartesia-voice.ts`, `fish-audio-voice.ts`, `speech-text.ts` | Falar e transcrever com a chave do usuário; texto de agente → frases que a voz lê bem. |
| `app/navegador/` | `page-browser-session.ts`, `browser-tools.ts` | `navegador_abrir`, `navegador_ler`, `navegador_agir`: a página como texto + até 80 elementos com refs; senha mascarada; ref antiga recusada; todo pedido de rede passa pelo SSRF. Playwright opcional (`uv sync --group navegador`). |
| `app/computador/` | `docker-sandbox.ts`, `sandbox-faults.ts` | `executar_comando` num contêiner descartável: sem rede por padrão, sem os arquivos do usuário, usuário sem privilégio, só leitura, memória/CPU/processos/tempo limitados. `SANDBOX_PROVEDOR=docker`. |
| `app/ferramentas/gerar_grafico.py` | `plot-tool.ts` | Barra, linha, área, dispersão, histograma e pizza em PNG, nas cores da Sora (matplotlib sem pyplot, seguro em threads). |
| `app/busca/duckduckgo.py` | `keyless-http-web.ts` | Busca sem chave. Só em desenvolvimento, como o SearXNG (a página HTML não é API e limita quem busca muito). |

### Banco: migração `0004_pecas_do_rakazo`

Colunas `conversas.resumo_compactado`, `conversas.compactado_ate`, `mensagens.salto`; tabelas `rotinas`, `pendencias`, `habilidades`, `conectores`, `canais_vinculados`.

### Configuração nova

`TELEGRAM_TOKEN_BOT`, `TELEGRAM_SEGREDO_WEBHOOK`, `SANDBOX_PROVEDOR` (`nenhum` | `docker`), `SANDBOX_IMAGEM`, `SORA_MAX_SALTOS` e `BUSCA_PROVEDOR=duckduckgo` (só desenvolvimento). Jobs novos em `workers/fila.py`: `executar_rotina`, `compactar_historico`, `responder_canal`, `reconciliar_travados`.

## O que já existia na Sora (não foi duplicado)

- Troca de provedor em 429/5xx/prazo com lista de reservas: `app/llm/troca.py` (`ModelFallbackMiddleware`) já faz o que os "backup models" do Rakazo fazem.
- Proteção SSRF, cerca `<dado_externo>`, detector de loop, limites de passos, Sistema 1, busca plugável, eventos SSE, cifra das chaves e aprovações por cartão.

## O que ficou de fora, e por quê

- **Desktop gráfico por bot** (Linux com Chrome, controle por screenshot, takeover da tela): é a maior e mais cara parte do Rakazo e o modo por texto do navegador cobre a maior parte do uso. O `executar_comando` usa contêiner descartável em vez de máquina persistente.
- **Apps Electron/Expo e interface React**: a Sora já tem o próprio app (Vite + React + Tauri).
- **OAuth de assinatura** (usar a assinatura do Claude/ChatGPT no lugar da API): depende dos termos de cada empresa; a Sora segue com as chaves de API que o usuário conecta.
- **Stripe/cobrança**: a Sora mostra "Uso do mês" com as chaves do próprio usuário.
- **Lark, iMessage, push e SMTP**: o Telegram ficou como modelo; outros canais seguem o mesmo formato de `app/canais`.

## Antes de ligar em produção

- `executar_comando` com Docker: o worker que fala com o Docker tem poder de root na máquina. Rode as sandboxes num host separado ou com Docker rootless, e nunca monte o socket do Docker do servidor principal no contêiner do worker.
- Embeddings da memória: o `Vetorizador` (768 dimensões) ainda precisa ser escolhido e a escrita do vetor no pgvector precisa ser testada com o banco real.
- Os testes de banco desta leva compilam o SQL no dialeto do PostgreSQL; rodar `tests/integracao` com Docker antes de ligar memória, pendências e canais.
