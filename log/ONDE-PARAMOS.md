## Onda 1 — `main` (`d7dc113`) (2026-11-20, tarde)

Feita a Onda 1 do comparativo, enviada direto na `main` sem PR: senha nova por link no e-mail e trocar senha, baixar
meus dados (.zip), relatar problema (diagnóstico mascarado, CLI do time), chaves extras por
conexão e modelos reserva da conta (troca sempre avisada), atualização do desktop (desligada até
haver chave de assinatura). Migrações 0018 e 0019. Testes verdes no backend, app e Rust; detalhes
em `log/2026-11-20.md`. **Próximo:** no servidor, migrações 0017 a 0019 e
`EMAIL_PROVEDOR`; chaves do atualizador (`app/docs/atualizacao-desktop.md`).


## Comparativo OpenBot × Sora (2026-11-20)

Análise do OpenBot 0.75.0 contra a `main`: `docs/referencias/openbot-comparativo.md` (lista por
área, o que não trazer, três ondas). Achados de base: sem recuperação de senha e sem e-mail, sem
exportar dados (LGPD), desktop sem atualização automática. Nenhum código alterado. **Próximo:**
Heitor escolher os itens (sugestão: Onda 1 + webhooks nas rotinas + notificação no celular).


## Revisão geral — ramo `fix/revisao-geral` (2026-11-19)

Análise do repositório e correção de tudo o que apareceu: apagar conta (LGPD) quebrava para quem
usou rotinas, grupos, navegador ou canais da empresa; `executar_comando` podia derrubar o worker
com saída sem fim; macro do Office (alt+F11) e interpretadores escapavam do controle do PC;
prompt injection podia usar o modo "total"; F5 seguidos derrubavam o login (decisão 6, migração
0017); token de acesso valia 15 min depois de sair; sem Sentry/log, sem teto de upload, Redis sem
senha, sem CI. Também `api/canais_empresa` virou pacote e as funções puras da cadeia foram para
`app/orquestrador`. Validação: 2130 unitários, 31/32 arquivos de integração (o MCP já falhava na
`main`), clippy + 32 testes Rust. Detalhes em `log/2026-11-19.md`. Juntado na `main` (PR #1); o
CI achou o catálogo de conectores no prompt sem existir e um teste instável do app, corrigidos no
PR #2 (auto-merge: junta quando o CI passa). A `main` agora exige os 4 jobs do CI; em
2026-11-20 os jobs do backend passaram a instalar o Chromium (a integração reprovava sem ele). **Próximo:**
`alembic upgrade head` (0017) e `REDIS_SENHA` no `.env` do servidor.


## Âncora-10 — seletor no backend (2026-11-16)

Preferências de Sora/bot/grupo persistem o modelo, raciocínio e permissão; modelo fixo sem fallback silencioso. Catálogo só de chat com destaques; conexão ativa todos e POST adiciona por ID. Migrações 0015/0016 aplicadas. API 8200 e worker reiniciados por Start-Process; Vite/desktop preservados. QA HTTP Groq: 11 ativos, 4 chats, PATCH/GET e inclusão nova passaram; conversa/provedor QA limpos. Próximo: validar seletor no app e continuar PC com Vela-12. Diário `2026-11-16.md`.


## Heitor — Novo bot direto (2026-11-15)

- Implementado: menu com Novo bot/Novo grupo; `/bots/novo` sem histórico, reset a cada navegação, thinking orb e texto preservado no erro; criação seguida de registro nos dois estados, navegação e envio otimista normal. Rascunho na conversa com a Sora preservado.
- Backend: `POST /v1/bots/criar-por-descricao`, descrição 1–2000 caracteres (vazia após trim recusada), seletor/provedor do usuário, JSON validado, fallback local para falha/429/JSON inválido; nome/cor e materialização reaproveitados sob trava por usuário; navegador e leitura garantidos para pedido de site. Sem registrar descrição ou erro do provedor nos logs da nova rota.
- Validação: ruff check e format check passaram; 1413 unitários passaram / 2 pulados por symlink no Windows; integração nova com PostgreSQL/Redis descartáveis e modelo falso passou. App build e oxlint passaram (7 avisos preexistentes); 384 testes passaram em 73 arquivos. Testes novos cobrem fallback, sugestão, isolamento, nomes/cores, tamanho, menu, reset, criação/envio e erro.
- Chrome real em conta exclusiva `prumo3-novobot-1794780449663@sora.local`: menu → descrição solicitada → bot Ravi criado por fallback → chat abriu com pedido original → chamadas Groq iniciadas. Novo bot abriu limpo em 390 px, inclusive novo clique na própria tela após digitar rascunho. Capturas `app/qa/shots/novobot/{limpa,chat}-{1440,390}.png`; roteiro `app/qa/novobot-live.mjs`.
- Limitação ao vivo: o modelo retornou chamada de ferramenta inválida e depois 429; aguardada a retomada, a conversa informou cota diária esgotada e espera de 2031 segundos. Não foi comprovada navegação efetiva no site nem conclusão da comparação de preços. Geração do perfil por modelo real não comprovada (foi fallback); esse caminho passou com modelo controlado em teste unitário.
- API 8200 e worker reiniciados na mesma chamada, conferidos em execução com modelo real. Vite 5173 preservado. Nenhuma conta/dado do Heitor alterado. Sem push.
- Próximo passo: retestar geração e pesquisa com cota disponível; demais pendências anteriores de Tauri/Slack/WhatsApp permanecem.

# Onde paramos

## Etapas 5 e 6 — interface nova e acabamento (2026-11-14 e 2026-11-15)

- **Estado:** prontas no ramo `etapa5-interface` (`C:\dev\sora-e5`), à espera do "sim" do Heitor para a `main`; sem push. Portas de desenvolvimento no padrão (Vite 5173, API 8000).
- **O que existe:** Sora como chefe de equipe, bots e grupos (2 a 5 bots), criação por conversa (cartão de rascunho e proposta de grupo), central "Precisa de você" (Permitir uma vez · Sempre permitir · Recusar), barra lateral nova (Criar novo, Buscar, Clientes, BOTS, GRUPOS), visual novo (`docs/design/etapa6-visual.md`), conversa com Parar, fontes, editar/refazer/avaliar, imagem e visão, voz, busca e memória; painel Trabalho com tela ao vivo do navegador e do computador; navegador próprio e computador virtual por bot (`docs/computador-por-bot.md`); controle do PC do usuário no desktop com proteções; canais da empresa só leitura com aprendizado e tela Clientes (`docs/canais-da-empresa.md`); Ilha só fora do app e aviso fora de foco.
- **Verde (Prumo-4, Âncora-8):** backend 1409 unitários e 28/28 arquivos de integração; app 382 testes, `test:visual` 22/22, contraste 0 falhas; Clippy e 22 testes Rust. Ao vivo com Groq: conversa, cartões, aprovação, Parar e voz. Detalhes em `log/2026-11-15.md`.
- **Próximo passo:** (1) aprovação da junção; (2) teste real do Tauri (controle do PC, login desktop, Ilha); (3) Slack e WhatsApp Business reais; (4) instalador assinado com o domínio real da API no CSP; (5) decidir PWA e tema claro; (6) MÉDIA/BAIXA abertas em `.maestri/relatorios/prumo4.md` e `ancora8.md` e a renovação da sessão. Planos: `log/etapa5-interface.md`, `log/etapa6-acabamento.md`.

## Etapa 6 — Âncora-3 (2026-11-14)

- Backend: interrupção de conversa, fontes persistidas, edição/refação da última pergunta/resposta e avaliação. Migração `0011` aplicada no PostgreSQL da etapa 5 (46432). Contrato: `.maestri/contrato-etapa5.md`, seção Âncora-3. Relatório: `.maestri/relatorios/ancora3.md`.
- Próximo passo: ligar os controles no app e validar com modelo real; esta rodada usa worker/API reais com modelo controlado nos testes de interrupção. Demais frentes da etapa 6 continuam com seus donos.

## Etapa 4 — peças ligadas ao worker (concluída em 2026-11-04)

- O worker real usa navegador por árvore com perfis e revisão de domínio, fila persistente, canais de equipe e correio, contexto e compactação, memória, pendências, revisor, habilidades, rotinas, conectores MCP, Telegram, sandbox e voz. O app mostra canais, fila, contexto, memória, rotinas, habilidades, conectores, Telegram, pendências, voz, perfis do navegador, cartão de domínio e rastro da aba. Plano: `log/etapa4-pecas.md`. Diário: `log/2026-11-02.md`.
- Segurança: ações do navegador passam pelo revisor; rotinas só recebem ferramentas seguras e perfil efêmero; voz e conectores conferem o IP na conexão; sandbox de produção só liga com host separado; recuperação de fila/canal respeita batimento; uma ocorrência de rotina não roda duas vezes; conteúdo vindo de etapa anterior entra no prompt como dado externo.
- **Teste com modelo real (Groq, 2026-11-02, ao vivo no Chrome):** equipe pesquisa → redação → verificação, navegador por árvore (abrir, procurar, 2 cliques, captura, entrega aprovada pelo verificador), cartões de aprovação e pergunta, pendência, memória, rotina "Rodar agora", canal de equipe com delegação e recuperação depois de reiniciar o worker. Achou 12 defeitos que o modelo falso escondia (limite por minuto do provedor, pedido grande demais, conteúdo entre etapas, catálogo do navegador, limite de chamadas, espera falsa após ação, leitura antes do load, laço da rotina, esquema estrito do líder, verificador sem os passos, letras engolidas, ordem das mensagens), todos corrigidos e retestados; depois a varredura tirou do app o conteúdo de demonstração que ainda parecia real.
- Verde no Aferidor (conferência final, HEAD `a2d78b8`): backend unitários 1097/0, ruff limpo, `test_navegador_worker` 11/11, `test_ancora_pecas` 14/14 (antes: `test_equipe_tear` 13, `test_relogio_rotinas` 6, `fase_b_pronto` 2, `fase_b_robustez` 26); app build, oxlint, npm test 184, `qa/e2e.mjs`, `qa/ilha.mjs`, `qa/digitacao.mjs`, `qa/etapa4.mjs` com Chromium real e `test:visual` (baseline "projeto pronto" atualizada pela mudança do card de links).
- Ficou de fora: transcrição de voz com chave real (precisa da fala do usuário); o grupo decide a tela Plugins (marca plugins como conectados), o botão "Aprovar e publicar" e as ferramentas do agente no `AgenteSaida`.
- **Próximo (pedido do Heitor):** (1) a Ilha da Sora só aparece quando o usuário está fora do app (desktop, sobre outras janelas); dentro do app não aparece nem abre sozinha com cartões; (2) refazer a interface, hoje confusa, no estilo OpenBot/Grok (só referência de experiência; OpenBot é PolyForm Noncommercial). Depois: domínio real da API no CSP do Tauri e instalador assinado. Plugins continuam congelados.

## Etapa 3 — motor de ponta a ponta (concluída em 2026-11-02)

- Conversa → plano → especialistas → etapas → entrega no worker, com pausa/retomada, perguntas, aprovações, orçamento, cancelamento e batimento; app ligado por REST + SSE, sem simulação; decisões de segurança do navegador aplicadas. Plano: `log/etapa3-motor.md`. Diário: `log/2026-11-02.md`.
- Verde: backend 1130 passed / 2 skipped com integração, ruff, build, oxlint, npm test 130, e2e e ilha.
- Seguiu para a etapa 4 (acima).

_Atualizado em 2026-11-01 — **navegador por árvore adaptado do agent-desktop** (refs conferidas, ações com verificação, esperas, lote) e, no mesmo dia, **peças inspiradas no OpenBot escritas do zero no backend** (contexto, filas, correio, canais de equipe, navegador persistente; migração 0005). Antes, 2026-10-17: **etapa 1 do backend (conexão das APIs) concluída** e **peças do Rakazo portadas** (fases 1, 2 e 3), as duas juntadas no mesmo `main`; **etapa 2 (app ligado ao backend, login real, chaves fora do navegador) concluída**. Antes, 2026-10-15: revisão de segurança concluída e validada; APP-003 e hover da ilha corrigidos no Tauri real._

## Navegador por árvore — agent-desktop (2026-11-01)

- agent-desktop (Vercel Labs) é **Apache 2.0**; trouxemos o modelo (observar → agir numa ref → conferir) para o Chromium da Sora, escrito em Python + JS, sem cópia literal. Mapa e licença: [`docs/referencias/agent-desktop.md`](../docs/referencias/agent-desktop.md). Diário: `log/2026-11-01.md`.
- Novo: `backend/app/navegador/arvore/` e as ferramentas `navegador_observar|procurar|elemento|esperar|acao|tecla|lote`; prompt `navegador_arvore.v1`.
- Verde: ruff, format, pytest **969 passed** (32 novos em `test_navegador_arvore.py`, com Chromium real).
- Ligado ao worker na etapa 4; estado atual no topo deste arquivo.

## Peças inspiradas no OpenBot (2026-11-01)

- OpenBot é **PolyForm Noncommercial**: nada foi copiado; tudo foi reescrito em Python a partir da documentação de arquitetura deles. Mapa, licença e o que ficou de fora: [`docs/referencias/openbot.md`](../docs/referencias/openbot.md). Diário: `log/2026-11-01.md`.
- Novo no backend: `app/contexto` (medidor + compactar antes do turno), `app/filas` (FIFO por agente com pausa, pistas paralelas, edição, recuperação após queda), `app/correio` (respostas, reações, arquivos e imagens entre agentes com cópia e hash), `app/canais_equipe` (canal com líder, responsável por tarefa, delegação, Parar/Retomar/Reatribuir/Cancelar/Arquivar/Restaurar), `app/navegador/{perfis,abas,persistente}` (perfis com login cifrado, abas que sobrevivem ao turno, "assumir aba", captura e console). Migração `0005`, rotas em `app/api/equipe.py`, eventos em `app/eventos/equipe.py`.
- Verde: ruff, format, pytest **937 passed** (`tests/unitarios/test_pecas_openbot.py`).
- Revisão no mesmo dia: 3 bugs de canais (filha que falha trava a mãe, resultado perdido, pingue-pongue em transferir) e 3 menores corrigidos. **Decidir:** política do navegador com perfil logado (`log/2026-11-01.md`).
- Ligado ao worker na etapa 4; estado atual no topo deste arquivo.

## Etapa 2 — app ligado ao backend (concluída em 2026-10-17)

- **Login de verdade:** cliente HTTP `app/src/api/cliente.ts` (token só em memória, renovação única no 401, `ErroApi` em PT-BR), sessão `state/sessao.ts`, telas Entrar/Criar conta, gate em todas as rotas, onboarding "Conecte sua primeira API" (com Sair) e aviso na Home, conta + Sair na Sidebar e no menu do celular.
- **Modelos de IA no backend:** `state/modelos.ts` é cache de `/v1/provedores`, `/v1/modelos`, `/v1/preferencias`; nenhuma chave no navegador (migração limpa `sora.modelos.v1`); Groq e compatíveis (xAI/DeepSeek/Mistral); nomes amigáveis dos modelos. **APP-001 fechado.**
- **Desktop:** renovação no Credential Manager (`cofre_ler/gravar/apagar`, só a janela `main`), CSP com a API. Antes do instalador final: trocar `https://api.seu-dominio.com.br` no `tauri.conf.json` pela origem real.
- **Dev:** `uv run python -m app.cli convite criar`, passo a passo em `backend/README.md`, `infra/docker-compose.dev.yml`; QA entra sozinho (`qa/entrar.mjs`).
- **Validado pelo Lince** (`app/qa/lince-rodada{1,3}.md`, `lince-rodada2-tauri.md`): fluxo real 1440 e 390 px, e2e, ilha, Tauri real; app build/oxlint/119 testes; backend ruff/912 testes.
- **Próximo:** worker de ponta a ponta (modo Cadeia, especialistas, SSE no chat — o chat ainda é simulado), ligar as peças do Rakazo no worker.
## Etapa 1 — conexão das APIs (2026-10-15 a 17)

- Rotas `/v1/provedores` (testa a chave antes de salvar, cifra com AAD = id do provedor, duplicado 409, limite de 10 provedores e 10 testes/h), `/v1/modelos`, `/v1/preferencias`; `tem_provedor` exige provedor validado; dependência `exigir_provedor_validado` (412); ponte banco→seletor em `app/seletor/repositorio.py`. Especificação: `log/etapa1-conexao-apis.md`.
- Validado em 2026-10-17 com Docker: ruff limpo, pytest **835 passed / 2 skipped** (commit `76efd9b`).
- **Próximo:** etapa 2 — ligar o app (login, Configurações → Modelos de IA no backend, chaves fora do `localStorage`, APP-001). Especificação: `log/etapa2-app-provedores.md`.

## Peças do Rakazo (2026-10-17)

- Mapa completo, licença (Apache 2.0) e o que ficou de fora: [`docs/referencias/rakazo.md`](../docs/referencias/rakazo.md). Diário: `log/2026-10-17.md`.
- Novo no backend: saltos entre agentes, catálogo preguiçoso de ferramentas, política de aprovação + juiz do revisor, compactação e busca no histórico, memória, agenda/rotinas, pendências, habilidades SKILL.md, conectores MCP, Telegram, voz, navegador por texto, `executar_comando` (Docker), gráficos e busca DuckDuckGo (só dev). Migração `0004_pecas_do_rakazo`.
- Verde: ruff, format e pytest (testes novos em `backend/tests/unitarios/test_rakazo_fase{1,2,3}.py`).
- Próximo: ligar essas peças no worker (ainda esqueleto), escolher o `Vetorizador` da memória, sandboxes num host separado antes de produção e rodar `tests/integracao` com Docker.

## Revisão de segurança (2026-10-15, time do Clausecurity)

- Auditoria + correção em loop de backend, infra e app; tudo validado (detalhes em `log/2026-10-15.md` e na nota Maestri "Segurança — Achados").
- Verde: backend ruff/format, pytest 795 passed / 2 skipped, pip-audit limpo; app build, oxlint, 82 testes, npm audit 0, clippy; stack Docker real (read-only, migrações, Caddy, backup/restauração); Tauri real por CDP.
- Mudança para quem roda o backend: `AMBIENTE` agora é `producao` por padrão (no PC use `AMBIENTE=desenvolvimento`); em produção `CORS_ORIGENS` fica vazio (APP_URL + desktop). Rotação da chave mestra: `CHAVE_MESTRA_VERSAO` + `CHAVES_MESTRAS_ANTIGAS`.
- Pendente para a próxima etapa: APP-001 (chaves de API saem do `localStorage` quando o app for ligado às rotas de provedores) e o worker (ainda esqueleto).

## APP-003 no desktop real (2026-10-15)

- Script reproduzível: `app/qa/desktop-capabilities.mjs` (configuração auxiliar: `app/qa/tauri-capabilities.config.json`).
- OK: `ilha-mouse`, `ilha-alternar`, Ctrl+Shift+S, `sora-navegar`, três negações cruzadas de capabilities e consoles sem erros novos.
- Corrigido: a abertura por hover não incrementa mais `ui.pedido`, portanto continua temporária e fecha 400 ms após o mouse sair. Aberturas externas permanecem fixadas.
- Regressão em `app/src/components/ilha/__tests__/ilhaUi.test.tsx`; build OK, oxlint limpo, 82/82 testes e fumaça Tauri real integralmente verde. Nenhum commit foi criado.

## Agentes em LangChain (2026-10-14)

- Decidido: os agentes do backend são feitos em **LangChain 1.x** (`create_agent`). O plano passou para a **versão 2.1**; o que muda está na seção 6.1 da especificação e no README de `docs/plano-de-implementacao/`.
- Fila ARQ, estados da cadeia no PostgreSQL, seletor, orçamento e eventos SSE continuam sendo código nosso.

## Estado atual

- **Front-end da Sora pronto** em `app/` (Vite + React 19 + TypeScript). Roda com `cd app && npm install && npm run dev` → http://localhost:5173.
- **Sem back-end.** Respostas dos agentes, planejador, "Testar conexão" das APIs e créditos são **simulados no navegador** (dados no `localStorage`).
- **Parte B da lista "Melhorias da Sora"** (itens 28–60, só front-end) está **implementada**, em 3 etapas:
  - Etapa 1: design system (tokens, componentes base) e limpeza (rotas de laboratório só em DEV, README, fontes locais, ícones e manifest).
  - Etapa 2: densidade, painel direito com abas Equipe/Trabalho/Entregas, tela "Projeto aprovado", estados vazios com modelos prontos, contraste WCAG e toque de 44 px.
  - Etapa 3: markdown, texto aparecendo aos poucos com botão Parar, ações por mensagem, anexos, Desfazer, Ctrl+K, créditos, estados de erro e testes unitários (Vitest).

## Onde exatamente paramos

- Todos os agentes foram **parados** e o dev server desligado. O repositório estava limpo e o build passando.
- Os ajustes visuais finais (miniaturas das peças e espaçamento das entregas) foram **concluídos** (commit `4e5ab5f`).
- O **teste visual automático** (Playwright `toHaveScreenshot`, item 56) foi criado e commitado pelo Vigia (`903a401`, `2c79f38`): `npm run test:visual`, com o dev server rodando.
- **Faltou:** o veredito final do Vigia sobre a Parte B inteira (itens 28–60). A validação foi interrompida antes do relatório. Na próxima sessão, rodar: `npm run build`, `npx oxlint`, `npm test`, `node qa/e2e.mjs`, `npm run test:visual` e `node qa/contraste.mjs`, e conferir os itens novos no navegador.

## Plano do backend — versão 2 (2026-10-11, noite)

- `docs/plano-de-implementacao/` tem o plano revisado para combinar com o app (agora versão 2.1, com os agentes em LangChain; o que mudou: README da pasta). Próximo passo quando o Heitor disser "sim": fase 1 do backend + camada `src/api` no app (seção 3 da especificação). **2026-10-14: o modo demonstração saiu do plano (versão 2.2) e o backend começou em `C:\dev\sora`.**

## Sora desktop + CHATS em pastas (2026-10-11, noite)

- App instalável: `cd app && npm run desktop` (dev) ou `npm run desktop:build` → `src-tauri/target/release/bundle/nsis/Sora_0.1.0_x64-setup.exe` / `msi/Sora_0.1.0_x64_pt-BR.msi`. A ilha fica no topo da tela, por cima das outras janelas; cliques fora dela atravessam. Spec: `app/docs/sora-desktop.md`.
- Ilha com animações novas e filtro Todos/Trabalhando/Concluídos + olho por agente.
- CHATS: projeto com equipe = pasta (abre/fecha); agente independente = linha solta. Novo chat: seletor **Equipe | Agente independente**.
- Validado: build, oxlint, 31 testes, `qa/e2e.mjs`, `qa/ilha.mjs`, `cargo clippy -D warnings`, instaladores gerados, e o exe testado de verdade (mouse real: hover abre, clique fora atravessa e fecha, console limpo).
- Pendente: instalador sem assinatura digital (o Windows pode mostrar o aviso do SmartScreen); agentes externos reais (back-end, só com "sim" do Heitor).

## Ilha da Sora (2026-10-11)

- Nova pílula no topo de todas as telas com projeto: Sora branca + os agentes rodando; aba **Projeto ▾** escolhe o projeto; detalhe do agente; **Aprovação** quando a equipe termina; Ctrl/⌘+Shift+S; Configurações → Ilha. Spec: `app/docs/ilha-da-sora.md`. QA: `node qa/ilha.mjs`.
- Próximo (só com "sim" do Heitor): mostrar agentes externos reais (Claude Code/Codex/Hermes via hooks), o que exige um servidor local.

## Revisão de 2026-10-11 (detalhes em `log/2026-10-11.md`)

- Build, lint, 22 testes e E2E passaram; contraste com 4 falhas pequenas; `npm run test:visual` ainda precisa rodar no PC do Heitor.
- O front está bonito e consistente, mas é uma **simulação por relógio**: para ligar no backend é preciso uma camada de API + eventos SSE, mantendo a simulação como **modo demonstração**.
- Faltam: API conectada obrigatória (onboarding), chaves fora do navegador, modelos vindos do backend (incluir Groq), prioridade e teto de gasto, roteamento/custo na linha do tempo, cartões de pergunta e aprovação, limite de 5 agentes, contas/login.
- Decisão pendente: **créditos x chaves próprias** (sugestão: trocar créditos por "Uso" em US$ por provedor).
- A especificação do backend precisa de: evento de passo (painel Trabalho), aparência dos agentes, entregas e versões, projetos e nomes unificados.

## Próximos passos

1. Rodar a validação final da Parte B (comandos acima), corrigir o que aparecer e mandar ao Lupa o resumo item a item (28–60).
2. **Parte A (produto/negócio/back-end, itens 1–27 da lista):** NÃO iniciar sem o "sim" do Heitor. Inclui decidir o back-end, o nome (colide com o Sora da OpenAI), o nicho, a cobrança e mover o projeto para fora do OneDrive.
3. **Plugins:** continuam congelados até o grupo decidir.

## Regras importantes para quem continuar

- Não mudar a aparência do mascote nem as cores dos agentes.
- Tudo em PT-BR.
- Antes de commitar: `npm run build`, `npx oxlint`, `npm test` e `node qa/e2e.mjs` (com o dev server rodando).
- Não reverter `app/package.json`; avisar antes de rodar `npm install` quando houver mais de uma pessoa ou agente trabalhando.
- Chaves de API **nunca** devem ir para o repositório nem ficar só no navegador em produção.

## Backend — fundação da fase 1 (2026-10-14 e 15)
- Repositório em `C:\dev\sora`. Esqueleto do backend e da infra (`8d7b2ed`) validado pelo Vigia.
- Etapa 3 (fundação) **concluída**: Alicerce (segurança, migrações 0001–0003, contas, infra), Trama (eventos/SSE, ler_pagina com SSRF, busca, estados da cadeia, arquivos sem path traversal, checkpointer) e Bússola (modelo falso, seletor, Sistema 1, custo e fábrica de modelos). Vigia: rodadas 1 a 3. Depois, a revisão de segurança do time do Clausecurity (acima).
- **Próximo:** backend de ponta a ponta (conexão das APIs, prompt da Sora, worker com o modo Cadeia, especialistas em LangChain, middlewares, entregas com versões, passos, cartões de pergunta, agente independente, anexos, dados de treino do Laya); depois ligar o app (inclui tratar o erro `recarregar` do contrato em `tests/contrato/retomada/`).

## Vela-4 — C3 (2026-11-14)

- Onde parou: recuperou o WIP da Vela-3 e completou backend, canal autenticado, cartões, ponte Tauri/Windows e Configurações → Computador. Documentação: `docs/computador-por-bot.md` § C3 e contrato § Vela-4. Relatório: `.maestri/relatorios/vela4.md`.
- Próximo passo: teste interativo no desktop (Bloco de Notas, entrada física e campo real de senha), antes de marcar C3 NO AR. Sem push; WIP dos outros integrantes preservado.

## Heitor / Vela-7 — C3 (2026-11-15)

- Onde parou: backend recuperado, revisado e commitado em `1dcf0ad`; 1239 unitários passaram / 2 pulados, integração C3 real passou. App build/lint/347 testes e Rust Clippy/12 testes C3 passaram. Rastro do PC sem título de documento, pausa no primeiro movimento físico e leitura de senha conservadora. Relatório: `.maestri/relatorios/vela7.md`.
- Próximo passo: resolver o erro de login desktop no ambiente local e testar Bloco de Notas, mouse físico e campo real IsPassword. C3 ainda não marcado NO AR; sem push/instalador. Outros donos preservados.
