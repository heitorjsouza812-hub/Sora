# Sora — leia isto primeiro

> Este arquivo é lido pelo Claude no início de cada sessão. Antes de mexer em qualquer coisa:
> 1. leia a **Introdução** para entender o produto;
> 2. leia os **Logs da equipe** para saber quem fez o quê e onde cada um parou;
> 3. siga o **Mascote**, a **Interface** e as **Funções** como fonte da verdade do design.
>
> Ao terminar uma sessão de trabalho, **atualize o log do integrante** que pediu o trabalho (veja "Como registrar").

---

## 1. Introdução

**Sora** é uma plataforma de **agentes de IA criados por conversa**. O usuário descreve o que precisa em linguagem natural ("crie uma campanha para lançar minha cafeteria…") e a Sora:

1. entende o pedido;
2. monta um **plano** dividido em tarefas;
3. cria uma **equipe de agentes** especializados para executar cada tarefa;
4. coordena os agentes, que passam o trabalho de um para o outro;
5. entrega o resultado para o usuário **revisar e aprovar** — nada é publicado sem aprovação.

Os agentes usam **plugins** (Figma, Canva, Notion, Higgsfield, ChatGPT, Gemini, Google Drive, Instagram… mais de 1.000) para trabalhar de verdade nas ferramentas do usuário. Funciona no computador e no celular, por texto ou por voz.

- **Slogan:** "Sua ideia. Seus agentes. Tudo em uma conversa."
- **Promessas:** sem programar · agentes que trabalham juntos · você no controle.
- **Idioma:** todo o produto, textos e comunicação em **PT-BR**.
- **Nome:** o nome antigo era "Mini" — **não usar mais**. Sempre "Sora".

### Estado atual do repositório

O **app** está em `app/` (veja **§7 Estado do app**) e o **backend** em `backend/` + `infra/` (README na raiz). Desde as etapas 5 e 6 (2026-11-14 e 2026-11-15) o produto é **a Sora como chefe de equipe de bots e grupos**: o usuário conversa com a Sora, ela cria bots (cartão de rascunho) e propõe grupos de 2 a 5 bots (cartão de proposta); ações que mexem no mundo viram cartão **"Precisa de você"**. Não existem mais "projetos", "plano" nem "Aprovar e publicar" na interface. O app fala com o backend real por REST + SSE (login, modelos de IA, conversas, bots, grupos, Trabalho, memória, rotinas, voz, navegador, computador, Clientes). Não há modo demonstração (o modelo falso `SORA_MODELO_FALSO=1` serve só para as suítes automáticas e para desenvolver). Os testes ao vivo usam **modelo real (Groq)**, com a chave em `backend/.env` (`SORA_QA_GROQ_CHAVE`, nunca copiada para documento). Os vídeos de apresentação continuam como referência visual:

| Arquivo | O que é |
|---|---|
| `mini-video/mini.html` | Comercial de 30 s (canvas) → `sora-comercial-30s.mp4` |
| `mini-video/sora-demo.html` | Demo de 75 s mostrando a interface completa → `sora-demo-75s.mp4` |
| `mini-video/plugins.js` | Ícones dos plugins (Simple Icons, CC0) |
| `mini-video/voice-level.js` | Níveis da fala usados no efeito VoiceBeam |
| `mini-video/assets/` | Logos de plugins e imagens da campanha de exemplo |

Cada HTML expõe `renderFrame(t)` determinístico (render feito com Playwright + ffmpeg). **O `sora-demo.html` é a referência visual principal**: cores, textos, telas e estados dos agentes vêm de lá.

> A demo é um **exemplo** (campanha da cafeteria com Atlas, Luna e Nina). No app real os agentes são criados a partir do pedido do usuário.

Stack do app: **Vite + React 19 + TypeScript + react-router-dom, CSS puro com tokens** (decidido em 2026-10-10). Efeitos: `border-beam` e `voice-glow`.

---

## 2. Logs da equipe

Cada integrante tem um bloco. O bloco diz **o que a pessoa já fez**, **onde parou** e **qual é o próximo passo**. O histórico fica abaixo, da entrada mais recente para a mais antiga.

### Como registrar (regra para o Claude)

- No início da sessão, pergunte (se não estiver claro) **qual integrante** está trabalhando.
- Ao final, atualize **"Onde parou"** e **"Próximo passo"** desse integrante e adicione uma linha no histórico dele.
- Use data absoluta (AAAA-MM-DD), nunca "ontem" ou "semana passada".
- Seja curto: o que foi feito, quais arquivos mudaram, o que ficou pendente ou quebrado.
- Não apague entradas antigas de ninguém.

Modelo de entrada:

```md
- **AAAA-MM-DD** — O que fez. Arquivos: `caminho/arquivo`. Pendente: …
```

---

### 👤 Heitor

- **Papel:** _(preencher — ex.: produto / design / front-end)_
- **Onde parou (2026-11-20):** Onda 1 do comparativo com o OpenBot na `main` (`d7dc113`, enviada direto em 2026-11-20, sem PR e sem esperar o CI, a pedido do Heitor): senha nova por link no e-mail e trocar senha, exportar meus dados, relatar problema, chaves extras por conexão e modelos reserva, atualização automática do desktop (desligada até haver chave de assinatura). Migrações 0018 e 0019. Detalhes em `log/2026-11-20.md`.
- **Próximo passo:** conferir o resultado do CI desse envio na `main`. No servidor: `alembic upgrade head` (0017 a 0019), `REDIS_SENHA` e `EMAIL_PROVEDOR`/`EMAIL_REMETENTE` no `.env`. Para ligar a atualização do desktop: gerar as chaves (`app/docs/atualizacao-desktop.md`). Depois, Onda 2 (`docs/referencias/openbot-comparativo.md`).

**Histórico**
- **2026-11-20 (tarde)** — Onda 1 do comparativo, na `main` (`d7dc113`, enviada direto, sem PR): "Esqueci minha senha" com link de uso único (30 min, `app/emails` com SMTP/Resend/console, job `enviar_link_de_senha_nova`), trocar senha em Configurações → Conta (os outros aparelhos saem), "Baixar meus dados" (.zip com tudo, sem segredos), "Relatar problema" (diagnóstico mascarado, Retirar, `python -m app.cli relatos listar`), chaves extras por conexão e modelos reserva da conta (avisados na linha do tempo), atualização do desktop (`src-tauri/src/atualizacao.rs`, fluxo `desktop-versao.yml`). Migrações 0018 (`relatos`) e 0019 (`chaves_provedor`, `modelos_reserva`). Arquivos: `backend/app/{emails,core/{contas,exportacao,reservas},api/{auth,conta,relatos,reservas,provedores}}`, `backend/app/orquestrador/modelos.py`, `backend/app/llm/troca.py`, `app/src/{screens/{Entrar,RedefinirSenha},components/{settings,relatos},diagnostico,desktop/atualizacao.ts}`, `app/src-tauri/**`, `log/2026-11-20.md`. Pendente: e-mail real em produção, chaves do atualizador, reservas por bot.
- **2026-11-20** — Comparativo OpenBot 0.75.0 × Sora: lista por área do que eles têm e a Sora não, o que não trazer e três ondas de prioridade. Achados de base: sem recuperação de senha nem e-mail, sem exportar dados (LGPD), desktop sem atualização automática. Arquivos: `docs/referencias/openbot-comparativo.md`, `docs/referencias/openbot.md`, `log/2026-11-20.md`. Nenhum código alterado.
- **2026-11-20** — CI: os dois jobs do backend instalam o Playwright e o Chromium (a integração do PR #2 reprovava em `test_navegador_worker.py` e os testes do navegador de verdade eram pulados nos unitários). Arquivos: `.github/workflows/ci.yml`, `log/2026-11-20.md`.
- **2026-11-19** — Revisão geral (Claude Code) no ramo `fix/revisao-geral`: apagar conta derivado das FKs (antes falhava para quem tinha rotina, grupo, navegador ou canais), `rodar_limitado` no sandbox e no computador virtual, bloqueio de alt+F11/alt+F8/ctrl+shift+K, títulos de macro/DevTools e LOLBAS no PC (com teste de paridade Rust↔Python), `contaminacao.py` (modo total vira automático depois de ler conteúdo de fora), argon2 em thread, despacho da fila após cancelamento, reemissão de token (decisão 6, migração 0017), revogação do token de acesso ao sair/apagar conta, limpeza de sessões vencidas, Sentry/log, `LimiteDeCorpo` + Caddy 25 MB, Redis com senha, `/health/pronto`, `WORKER_MAX_JOBS`, sandbox com internet atrás do proxy, CI (`.github/workflows/ci.yml`), `.claude/settings.local.json` fora do git, `api/canais_empresa` em pacote e funções puras da cadeia em `app/orquestrador`. Arquivos: `backend/**`, `app/src-tauri/src/pc/regras.rs`, `infra/**`, `.github/**`, `log/2026-11-19.md`. Pendente: CSP com domínio real, push e CI no GitHub. **Tarde:** conferência do PC e do navegador: aba nova aberta pelo site vira a do bot, iframes lidos e clicáveis, clique na beirada rola antes, navegação lenta confirmada, janelas de outros monitores para o PC (`docs/computador-por-bot.md`, "Revisão de 2026-11-19"). Falta: ação de mouse/teclado ao vivo no PC (com o app de desktop). **Noite:** README com prints reais e diagramas; PR #1 juntado na `main`; CI acusou o catálogo de conectores citado no prompt sem existir (regressão de `2c643d1`) e um teste instável do app, corrigidos no ramo `fix/ci-mcp-e-teste-instavel` (PR #2). `main` protegida com os 4 jobs do CI obrigatórios e auto-merge ligado.
- **2026-11-16** — Seletor no compositor (provedor com ícone próprio, nome limpo, raciocínio, permissão Perguntar/Automático/Acesso total com bloqueios absolutos), tela Novo bot com exemplos, Enviar vira Parar enquanto trabalha, modelos ativos por padrão com principais e "Adicionar modelo" (`b9f16e1`, `d871433`, `bb53fda`, `337f8ea`, `32ed37c`, migrações 0015/0016). Controle do PC: "Permitir" retoma o turno, abrir programa pelo nome, tabela no Excel de 26 s para 12 s, bot não afirma que fez sem conferir, Sora minimiza ao usar o PC (`6a0063b`…`d78105d`); chat do bot sem "Pronto!" genérico (`97bda39`). Docs: `docs/seletor-modelo-permissao.md`, `docs/computador-por-bot.md`, `log/2026-11-16.md`. Pendente: pausa pelo mouse físico (Heitor), Excel com modelo depois do ajuste de Enter (cota Groq).
- **2026-11-16** — Âncora-10: seletor e permissão (`337f8ea`), catálogo ativo, destaques e POST de modelo por ID. Migrações aplicadas e QA HTTP Groq real. Arquivos: `backend/**`, `docs/seletor-modelo-permissao.md`, `log/2026-11-16.md`. Sem push; sem edição de `app/**`.
- **2026-11-15 (noite)** — Etapas 5 e 6 enviadas ao GitHub (`e2f4371`; a chave de exemplo da Stripe de um teste foi partida no histórico para passar no bloqueio de segredos). Novo bot direto (`6b52828`), chave Tavily no `.env` local, teste real do desktop pelo Faro (`d9ff590`, `eba9a71`), tarja da captura só na parte visível (`343faf1`) e Ilha tarjada só na pílula (`55025ef`). Arquivos: `app/src/screens/NovoBot.tsx`, `backend/app/api/bots.py`, `app/src-tauri/src/pc/**`, `app/qa/pc-tarja.mjs`, `docs/computador-por-bot.md`, `log/2026-11-15.md`. Pendente: pausa pelo mouse físico (só o Heitor testa), criação de bot e busca com a IA (cota da Groq), Gerenciador de Tarefas (pede UAC), clique no aviso do sistema (precisa do instalador).
- **2026-11-15** — Novo bot direto por descrição, menu com duas opções, tela limpa e primeira mensagem no chat. Arquivos: `backend/app/bot_por_descricao.py`, `backend/app/api/{bots,agentes}.py`, `app/src/screens/NovoBot.tsx`, API/estado/menu/rotas, testes, `app/qa/novobot-live.mjs`. Pendente: pesquisa externa com cota Groq. Sem push.
- **2026-11-15** — **Etapas 5 e 6 concluídas no ramo `etapa5-interface`** (103 commits sobre a `main` `b46518b`; ainda sem push). Etapa 5: Sora persistente como chefe de equipe, bots e grupos (2 a 5 bots), criação por conversa (cartão de rascunho e proposta de grupo), central "Precisa de você" com Permitir uma vez / Sempre permitir / Recusar, Ilha só fora do app. Etapa 6: visual novo (`docs/design/etapa6-visual.md`), conversa com Parar, fontes, editar/refazer/avaliar, imagem e visão, voz contínua, busca e memória; painel Trabalho com tela ao vivo do navegador e do computador; navegador próprio e computador virtual por bot (`docs/computador-por-bot.md`); controle do PC do usuário no desktop com proteções (C3); canais da empresa só leitura com aprendizado e tela Clientes (`docs/canais-da-empresa.md`); rotas antigas removidas e textos sem "agente/projeto/publicar". Time no Maestri com Claude, Codex e Grok; validação final do Prumo-4 e correções da Âncora-8 e do Vitral-10. Teste com modelo real (Groq). Arquivos: `backend/**`, `app/src/**`, `app/src-tauri/**`, `app/qa/**`, `docs/**`, `log/2026-11-15.md`, `log/etapa5-interface.md`, `log/etapa6-acabamento.md`. Pendente: teste real do Tauri (controle do PC, login desktop, Ilha), Slack/Meta reais, instalador assinado com o domínio real da API no CSP, PWA e tema claro (a decidir), MÉDIA/BAIXA abertas em `prumo4.md` e `ancora8.md`.
- **2026-11-14** — Âncora-3: backend dos itens 1/9/11 da etapa 6 (parar, fontes, editar/refazer/avaliar); migração `0011` aplicada no banco da etapa 5. Arquivos: `backend/app/{api/conversas.py,agentes/middleware/conversa.py,modelos/*}`, `backend/workers/{conversa,cadeia}.py`, testes e contrato `.maestri/contrato-etapa5.md`. Próximo passo: integração no app e validação com modelo real; relatório `.maestri/relatorios/ancora3.md`.
- **2026-11-04** — **Etapa 4 concluída: peças ligadas no worker + telas no app** (ramo `etapa4-pecas`). Time no Maestri: Leme (navegador), Tear (fila, canais, correio), Âncora (contexto, memória, revisor, habilidades), Relógio (rotinas, Telegram, conectores, sandbox, voz), Vitral E4 (app), Pena (docs); validação do Prumo (Aferidor) em três rodadas. Teste com modelo real (Groq) ao vivo no Chrome achou 12 defeitos que o modelo falso escondia, todos corrigidos; varredura tirou do app o conteúdo de demonstração. Verde: unitários 1097/0, integrações do navegador, equipe, Âncora, rotinas e fase B, app build/oxlint/184 testes, e2e, ilha, etapa4 com Chromium real e visual. Arquivos: `backend/**`, `app/src/**`, `app/qa/**`, `log/etapa4-pecas.md`, `log/2026-11-02.md`, `docs/referencias/*`. Pendente: Ilha só fora do app e nova interface (OpenBot/Grok); decisões do grupo sobre Plugins e "Aprovar e publicar".
- **2026-11-02** — **Etapa 3 concluída: motor de ponta a ponta + app ligado** (ramo `etapa3-motor` juntado na `main`). Fase A (Cerca): revisão de domínio novo em perfil logado (inclusive clique e redirect, barreira CDP), rotinas com perfil efêmero, Chromium em contêiner `internal` com `proxy-egresso` que recusa IP privado depois do DNS, produção recusa subir sem `NAVEGADOR_CDP_URL` (prova: `infra/scripts/provar-isolamento-navegador.sh`). Fase B (Trilho, Balcão, Molde, Compasso, Prumo, Elo): rotas de conversas/cadeias/eventos/entregas/perguntas/aprovações/agentes/anexos/uso, modo Cadeia no worker (até 3 etapas em paralelo, verificação, orçamento, troca de modelo como passo, erro seguro, cancelamento, batimento do worker, triagem com prazo de 15 s), ferramentas da fase 1, migração 0006. Fase C (Vitral): app por REST + SSE, cartões de pergunta e aprovação, sem planejador/relógio simulados. Revisão final (Lapidário, Cinzel): corrida da resposta antes da pausa, vagas SSE liberadas na desconexão e aviso de limite, cores, contas de QA, sobras de simulação. Validado por Aferidor (duas rodadas) e Faro; no fim: backend 1130 passed / 2 skipped com integração, ruff, build, oxlint, npm test 130, e2e e ilha. Arquivos: `backend/**`, `app/src/**`, `app/qa/**`, `infra/**`, `log/etapa3-motor.md`, `log/2026-11-02.md`. Pendente: teste com chave real, CSP do Tauri, instalador assinado, passo 6 (etapa 4).
- **2026-11-01** — **Navegador por árvore, adaptado do agent-desktop** (github.com/vercel-labs/agent-desktop, Apache 2.0; sem cópia literal, reescrito em Python + JS para o Chromium da Sora). O agente observa a aba como árvore com refs `@sXXXXXXX:eN`, age numa ref e confere: ref reencontrada e conferida antes de agir (elemento removido não cai no vizinho), checagens com espera (visível, estável, habilitado, quem está por cima), 17 ações com verificação depois, resposta com `entrega`/`repetir`, senha nunca exposta, esperas, lote, rastro e cursor na cor do agente. 7 ferramentas novas, prompt `navegador_arvore.v1`, 32 testes com Chromium real, 969 passando. Arquivos: `backend/app/navegador/arvore/**`, `backend/app/navegador/persistente.py`, `backend/app/ferramentas/{registro,rotulos}.py`, `backend/app/revisor/politica.py`, `backend/prompts/navegador_arvore.v1.md`, `backend/tests/unitarios/test_navegador_arvore.py`, `docs/referencias/agent-desktop*.{md,txt}`, `log/2026-11-01.md`. Pendente: ligar no worker, rastro no painel Trabalho, iframes.
- **2026-11-01** — **Revisão das peças do OpenBot** (commit `890dff8`). Corrigido: filha que falha agora acorda a tarefa-mãe (antes ela ficava em `aguardando_filhas` para sempre); filha que termina durante o turno da mãe dá mais um turno à mãe (antes o resultado se perdia); `canal_transferir` não devolve para quem passou (antes dava pingue-pongue sem fim); emojis com/sem U+FE0F; aspas escapadas nos atributos `<mensagem_de_colega>`/`<canal>`; `cancelar_de` grava `terminado_em`. 5 testes novos, 937 passando. Arquivos: `backend/app/canais_equipe/{servico,contexto}.py`, `backend/app/correio/{entrega,reacoes}.py`, `backend/app/filas/__init__.py`, `backend/tests/unitarios/test_pecas_openbot.py`. Pendente: rever a política do navegador agora que os perfis guardam login (ver `log/2026-11-01.md`).
- **2026-11-01** — **Peças inspiradas no OpenBot** (github.com/nightly-labs/openbot). A licença deles é PolyForm Noncommercial, então **nada foi copiado**: tudo reescrito em Python a partir da documentação de arquitetura. Monitor de contexto com compactação antes do turno, fila FIFO por agente (pausa, pistas paralelas, edição, recuperação após queda), mensagens entre agentes com respostas, reações, imagens e transferência de arquivos com hash, canais de equipe (líder, responsável por tarefa, delegação, Parar/Retomar/Reatribuir/Cancelar/Arquivar/Restaurar) e navegador persistente (perfis com login cifrado, abas que sobrevivem ao turno, assumir aba, captura e console). Migração 0005, 932 testes. Arquivos: `backend/app/{contexto,filas,correio,canais_equipe}/**`, `backend/app/navegador/{perfis,abas,persistente}.py`, `backend/app/api/equipe.py`, `docs/referencias/openbot.md`, `log/2026-11-01.md`. Pendente: repositórios no banco, ligar no worker, telas no app.
- **2026-10-17** — **Peças do Rakazo portadas para o backend** (github.com/elie222/rakazo, Apache 2.0), fases 1, 2 e 3: saltos entre agentes, catálogo preguiçoso de ferramentas, política de aprovação + juiz do revisor, compactação e busca no histórico, memória, agenda, pendências, habilidades, conectores MCP, Telegram, voz, navegador por texto, `executar_comando`, gráficos, DuckDuckGo (dev). Migração 0004, testes `test_rakazo_fase{1,2,3}.py`. Arquivos: `backend/app/**`, `docs/referencias/rakazo.md`, `log/2026-10-17.md`. Pendente: ligar no worker, `Vetorizador` da memória, sandboxes fora do servidor principal.
- **2026-10-17** — **Etapa 2 concluída: app ligado ao backend.** Login real (cliente HTTP com token em memória e renovação, sessão, Entrar/Criar conta, gate, onboarding, Sair também no celular), Configurações → Modelos de IA nas rotas `/v1/provedores|modelos|preferencias` (APP-001 fechado: nenhuma chave no navegador), renovação no Credential Manager no desktop, CLI de convite. Time: Tecelã/Âncora (Codex), Lince (Hermes, validador). Validado: fluxo real 1440/390, e2e, ilha, Tauri real, 119 testes do app, 912 do backend. Arquivos: `app/src/api/**`, `app/src/state/{sessao,modelos}.ts`, `app/src/components/sessao/**`, `app/src-tauri/**`, `backend/app/cli.py`. Pendente: domínio real da API no CSP do Tauri antes do instalador final.
- **2026-10-15** — **Backend: fundação da fase 1 pronta e revisada.** Repositório movido para `C:\dev\sora`. Plano 2.2: **sem modo demonstração** (o backend tem o modelo falso `SORA_MODELO_FALSO` só para desenvolver, barrado em produção). Time no Maestri (Alicerce, Bússola, Trama; Vigia como validador) fez o esqueleto de `backend/` e `infra/` e a fundação: contas e login (argon2id, JWT, renovação com detecção de reuso, desktop), cifra AES-GCM das chaves, migrações 0001–0003, eventos Redis Stream + SSE, busca e `ler_pagina` com proteção SSRF, seletor de modelos, Sistema 1 e estados da cadeia. O time do Clausecurity fez uma revisão de segurança em loop, validada com o Docker real (`log/2026-10-15.md`). 795 testes. README na raiz.
- **2026-10-14** — **Decisão: agentes em LangChain.** Plano passou para a versão 2.1: `create_agent` sobre o LangGraph, ferramentas como `@tool`, `ChatLiteLLM` para os modelos, checkpointer no PostgreSQL e as peças de engenharia como middleware (especificação §6.1). Na fase 3, os conectores MCP entram pelo `langchain-mcp-adapters`. Fila, estados da cadeia, seletor e eventos continuam nossos. Arquivos: `docs/plano-de-implementacao/*`, `CLAUDE.md`, `AGENTS.md`, `log/`. Nenhum código alterado.
- **2026-10-11** — **Plano de implementação versão 2** em `docs/plano-de-implementacao/`: o plano do backend (vindo do zip "sora-plano-de-implementacao") revisado para combinar com o app: SearXNG e Qdrant fora da fase 1 (busca por API Tavily/Brave; pgvector), login do desktop com token no cofre do sistema, seção 3 "Contrato com o app" (projetos, especialistas visíveis, passos, entregas e versões, Ilha, anexos, modo demonstração), agente individual básico e Designer na fase 1, créditos → "Uso do mês". Lista completa no README da pasta. Nenhum código alterado.
- **2026-10-11** — **Sora desktop (Tauri) + CHATS em pastas.** Time no Maestri: Tear (Codex) fez `app/src-tauri` e `src/desktop/ponte.ts`; Farol (Claude Opus) fez a janela da ilha, as animações e o filtro de agentes; Sentinela (Hermes) os testes (parou no limite de uso da OpenAI); o orquestrador fez as pastas em CHATS, o seletor Equipe/Agente independente e a validação no desktop (ilha no topo da tela, cliques atravessando, console limpo). Instaladores: `app/src-tauri/target/release/bundle/nsis/Sora_0.1.0_x64-setup.exe` e `.../msi/Sora_0.1.0_x64_pt-BR.msi`. Pendente: assinar o instalador; agentes externos reais (back-end).
- **2026-10-11** — **Ilha da Sora** (adaptação do Coucou) feita por um time no Maestri: Farol (Claude Code Opus, núcleo), Tear (Codex GPT-5.6, peças/Configurações/atalhos), Sentinela (Hermes OpenAI, testes e QA). Build, lint, 27 testes, `qa/e2e.mjs` e `qa/ilha.mjs` passando. Arquivos: `app/src/components/ilha/**`, `app/docs/ilha-da-sora.md`, `AppShell.tsx`, `Configuracoes.tsx`, `components/comandos/*`, `app/qa/ilha.mjs`. Pendente: agentes externos reais (precisa back-end).
- **2026-10-11** — Revisão do `app/` contra a especificação do backend: build, lint, testes e E2E passando; lista do que adicionar e consertar para ligar no backend. Nenhum código alterado. Arquivos: `log/2026-10-11.md`, `log/ONDE-PARAMOS.md`, `log/README.md`, `CLAUDE.md`, `AGENTS.md`. Pendente: tudo da lista; `npm run test:visual` no PC.
- **2026-10-10** — Front-end do app construído com um time de agentes de IA no Maestri (detalhes em §7.6). Mudanças de produto pedidas no caminho: barra lateral vazia ao abrir, Sora grande na tela do 1º prompt, agentes criados pelo pedido e listados em CHATS, telas Projetos e Agentes, construtor de agente no estilo GPT builder, painel Trabalho, apagar/renomear, Configurações com APIs dos modelos. Arquivos: `app/**`, `CLAUDE.md`, `AGENTS.md`. Pendente: back-end, plugins reais, microfone real testado em celular.
- **2026-10-10** — Criou o `CLAUDE.md` com introdução, logs, mascote, interface e funções. Arquivos: `CLAUDE.md`.
- **2026-10-03** — Produziu o comercial de 30 s e a demo de 75 s da Sora em canvas; renomeou o produto de "Mini" para "Sora". Arquivos: `mini-video/*`. Pendente: os scripts de render (Playwright + ffmpeg + trilha) ficaram fora do projeto e podem precisar ser refeitos.

---

### 👤 Integrante 2 — _(nome)_

- **Papel:** _(preencher)_
- **Onde parou:** _(ainda não começou)_
- **Próximo passo:** _(preencher)_

**Histórico**
- _(vazio)_

---

### 👤 Integrante 3 — _(nome)_

- **Papel:** _(preencher)_
- **Onde parou:** _(ainda não começou)_
- **Próximo passo:** _(preencher)_

**Histórico**
- _(vazio)_

> Para adicionar alguém, copie um bloco "Integrante" acima e preencha.

---

## 3. O mascote dirige a interface

O mascote **é** a Sora. Ele não é um enfeite: a interface inteira é organizada em volta dele. Toda tela nova deve responder à pergunta **"onde está a Sora e o que ela está fazendo agora?"**

### 3.1 Aparência (não mudar sem combinar com a equipe)

- Feito **só de pontos de luz** sobre fundo escuro — nada de contorno sólido.
- Duas "cascas" de pontos em 3D: um **capuz** em cima (com listras diagonais) e uma **tigela** embaixo.
- Uma **abertura escura à esquerda**, onde ficam **dois olhos ovais** brilhantes.
- A Sora é **branca-azulada** (`#E2ECFF`). Ela pisca de vez em quando e tem um brilho suave no "chão".
- Os **agentes** usam o **mesmo corpo**, menor e colorido. Cada agente tem uma cor fixa:

| Agente | Cor | Função no exemplo | Como os pontos se mexem quando trabalha |
|---|---|---|---|
| **Sora** | branco `#E2ECFF` | Agente principal, coordena | gira, pulsa ao criar/concluir |
| **Atlas** | azul `#56A8FF` | Pesquisa e referências | vibração fina e rápida |
| **Luna** | violeta `#AC80FF` | Criação visual | torção em espiral |
| **Nina** | verde `#46E8A8` | Textos e planejamento | ondas na superfície |

> Atlas, Luna e Nina são os agentes **de exemplo** (campanha da cafeteria). No app, a Sora cria agentes conforme o pedido; cada agente novo recebe nome, função, cor própria e um tipo de movimento.

### 3.2 Estados do mascote → o que a interface faz

| Estado | O mascote | A interface |
|---|---|---|
| **Chegando** (primeira abertura da sessão, ~1,6 s) | pontos espalhados se juntam e formam o corpo; os olhos abrem | tela do 1º prompt, só a Sora no centro; barra lateral vazia |
| **Ocioso** | "respira" e gira devagar, pisca | tela inicial: "Em que posso te ajudar hoje?" |
| **Ouvindo** (usuário digitando ou falando) | a superfície ondula, os olhos olham para o campo de texto | BorderBeam correndo na borda do campo; no celular, VoiceBeam reagindo à voz |
| **Entendeu / enviou** | pulso de luz | a Sora encolhe e vai para a barra lateral como avatar; abre o chat |
| **Planejando** | pulso curto a cada agente criado | aparece o card "Plano" e os agentes surgem um por um no painel "Equipe" |
| **Coordenando** | gira devagar na barra lateral | status "Coordenando N agentes"; cada agente mostra o próprio status |
| **Agente concluiu** | pulso curto | check verde no agente, cards de entrega aparecem |
| **Pronto** | calma, olhos abertos | botão "Revisar" + aviso "Nada é publicado sem a sua aprovação." |

Regras:
- **Ao abrir o app** (decisão de 2026-10-10): a barra lateral começa **vazia** (sem chats nem agentes) e a Sora aparece **grande no centro da tela do 1º prompt**. Só depois do primeiro envio a conversa e os agentes passam a existir na barra lateral.
- Depois do 1º envio a Sora está sempre visível: avatar no cabeçalho do chat, nas mensagens e no topo do celular.
- O **movimento** do mascote é o indicador de carregamento. Nada de spinners genéricos. O **thinking orb** (estado `thinking`: faixas de luz em hélice, brilho respirando, olhos semicerrados olhando para cima) é o "pensando" do app inteiro.
- A cor de um agente aparece em **tudo** que é dele: avatar, status, barra de progresso, nome nas mensagens.

---

## 4. Interface

Visual escuro, limpo, com o brilho vindo dos pontos e dos beams. Tudo tirado do `sora-demo.html`.

### 4.1 Tokens

| Token | Valor |
|---|---|
| Fundo | `#050608` |
| Painel | `#0F1115` · painel 2 `#14161B` |
| Linha/borda | `rgba(255,255,255,0.08)` |
| Texto principal | `#F2F5FB` · secundário `#8B93A3` · apagado `#6B7280` |
| Sucesso / concluído | `#7EF2C4` |
| Fonte | **Inter** (300–700); títulos de peças criativas podem usar Playfair Display |
| Botão principal | fundo claro `#EEF2FA`, texto escuro `#0B0D12`, cantos bem arredondados |

**Efeitos:**
- **BorderBeam** — luz colorida (rosa → magenta → violeta → azul → ciano) correndo pela borda do campo de mensagem enquanto o usuário digita.
- **VoiceBeam** — brilho na borda de baixo que sobe e desce com o volume da voz.
- **Shimmer** — texto brilhando enquanto algo é gerado ("Pesquisando na web…").

### 4.2 Telas

> As telas abaixo vieram da demo. **As mudanças feitas no app estão em §7.3** e valem mais que este texto quando houver conflito.

**Barra lateral (sempre visível no desktop; menu ☰ no celular)**
- Logo "Sora", **Novo chat**, **Projetos**, **Agentes**, **Plugins**.
- Seção **CHATS**: começa vazia. Recebe cada conversa e, recuados abaixo dela, os agentes criados nela (avatar animado na cor do agente, nome, status colorido). Cada item tem menu "…" com **Renomear** e **Apagar**.
- Rodapé: conta/empresa e plano, **engrenagem → Configurações** e menu da conta.

**Novo chat (tela inicial)**
- Sora grande no centro, título "Em que posso te ajudar hoje?".
- Campo "Peça qualquer coisa à Sora…" com botão de microfone, "Ferramentas" e enviar.
- Sugestões rápidas: *Criar campanha · Pesquisar mercado · Planejar posts · Resumir e-mails*.

**Chat da Sora**
- Mensagem do usuário à direita; resposta da Sora à esquerda.
- Card **Plano**: tarefas em sequência (ex.: Pesquisar referências → Criar peças → Organizar calendário), cada uma com o agente responsável, status e %.
- Painel à direita **"Equipe da campanha"**: lista dos agentes com status; no fim, "Todas as tarefas concluídas".
- Ao terminar: cards de entrega (Pesquisa · 4 referências, Peças · 3 peças, Calendário · 12 posts) + botão **Revisar**.

**Chat de um agente** (Atlas, Luna, Nina…)
- Mostra o trabalho do agente ao vivo (buscas, links, peças sendo geradas, legendas sendo escritas, calendário).
- Faixa no topo indicando o que recebeu de outro agente ("Atlas enviou 4 referências").
- Painel à direita: avatar grande, função, status, barra de **Progresso**, lista de **Ferramentas** com estado *Conectado / Em uso / Usado*.
- Campo "Mensagem para Atlas…" — o usuário pode falar direto com qualquer agente.

**Plugins**
- "Conecte suas ferramentas favoritas." / "Mais de 1.000 plugins para os seus agentes usarem."
- Lista **EM DESTAQUE** com botão **Conectar** → vira "● Conectado".
- Ao lado, grade com todos os plugins.

**Celular**
- Mesma conta, mesmos agentes, mesma campanha.
- Topo com a Sora pequena; lista da equipe; botão de microfone grande.
- Fala → "Ouvindo…" (VoiceBeam) → "Sora está ajustando…" → "Pronto. Veja a nova versão." com comparação **Versão anterior / Nova versão**.

---

## 5. Funções e como funcionam

### 5.1 Fluxo principal

```
Usuário descreve o pedido (texto ou voz)
        ↓
Sora interpreta → monta o PLANO (lista de tarefas em ordem)
        ↓
Para cada tarefa → cria um AGENTE (nome, função, cor, ferramentas)
        ↓
Agentes trabalham; quando um termina, ENTREGA o resultado ao próximo
        ↓
Sora junta as entregas → mostra o resumo → usuário REVISA
        ↓
Usuário aprova (publica) ou pede ajuste (Sora repassa ao agente certo → nova versão)
```

### 5.2 Lista de funções

| Função | Como funciona |
|---|---|
| **Conversa com a Sora** | Chat com texto ou voz. A Sora é o ponto de entrada de tudo. |
| **Planejamento automático** | A Sora divide o pedido em tarefas com ordem e dependências. |
| **Criação de agentes** | Cada tarefa ganha um agente especializado. O usuário não configura nada; pode renomear ou ajustar depois. |
| **Coordenação** | A Sora acompanha os agentes e passa as entregas de um para o outro (ex.: referências do Atlas → Luna). |
| **Status ao vivo** | Cada agente tem estado: *Aguardando* → *Trabalhando* (verbo próprio: Pesquisando, Criando, Escrevendo) → *Concluído*, com % de progresso. |
| **Chat direto com agente** | O usuário pode abrir o chat de qualquer agente e dar instruções só para ele. |
| **Plugins** | Conectar ferramentas externas uma vez; os agentes usam conforme a tarefa. Mostra quais ferramentas cada agente usa. |
| **Entregas** | Resultados em cards: pesquisa (links), peças (imagens), textos, calendário etc. |
| **Revisão e aprovação** | Nada é publicado ou enviado sem o usuário aprovar. |
| **Ajustes e versões** | Pedido de ajuste ("deixe os textos mais descontraídos") gera nova versão; dá para comparar com a anterior. |
| **Multi-dispositivo** | Mesma conta e mesmos projetos no computador e no celular. |
| **Voz** | Microfone no campo de mensagem; mascote e VoiceBeam reagem à fala. |

### 5.3 Modelo de dados (ponto de partida)

```
Usuario     { id, nome, empresa, plano }
Projeto     { id, usuarioId, titulo, status }           // ex.: "Campanha da cafeteria"
Mensagem    { id, projetoId, autor (usuario|sora|agenteId), texto, anexos, criadoEm }
Plano       { id, projetoId, tarefas[] }
Tarefa      { id, planoId, titulo, ordem, dependeDe[], agenteId, status, progresso }
Agente      { id, projetoId, nome, funcao, cor, tipoMovimento, ferramentas[], status }
Entrega     { id, tarefaId, agenteId, tipo (links|imagem|texto|calendario), conteudo, versao }
Plugin      { id, nome, categoria, conectado }
```

Status de agente/tarefa: `aguardando` · `trabalhando` · `concluido` · `erro`.

---

## 6. Regras de trabalho para o Claude

- Escreva em **PT-BR** (código pode ter nomes em português, como nos HTMLs atuais).
- **Leia os logs antes** de propor qualquer coisa e **atualize o log ao terminar**.
- Não altere a aparência do mascote nem as cores dos agentes sem pedido explícito.
- Ao criar telas novas, reaproveite os tokens e textos da seção 4; em caso de dúvida, consulte `mini-video/sora-demo.html`.
- Não apague os vídeos nem os HTMLs de referência.
- Ao terminar uma sessão, registre em **`log/`** (diário `log/AAAA-MM-DD.md` + atualizar `log/ONDE-PARAMOS.md`).
- Ao mudar algo de produto, atualize a **§7** e copie o `CLAUDE.md` para o `AGENTS.md` (o Codex lê o `AGENTS.md`).

---

## 7. Estado do app (front-end)

### 7.1 Como rodar

```bash
cd app
npm install
npm run dev          # http://localhost:5173 (outra porta: PORT=5174 npm run dev)
npm run build        # checagem de tipos + build
npx oxlint           # lint (restam só avisos antigos de clientes/comum.tsx e qa/contraste.mjs)
npm test             # vitest (83 arquivos, 453 testes)
npm run test:visual  # Playwright, telas em 1440 e 390 px (22 testes)
npm run desktop      # app de DESKTOP (Tauri) em modo dev — usa o dev server da porta 5173
npm run desktop:build  # instaladores em src-tauri/target/release/bundle/{nsis,msi}/
```

**Portas padrão:** Vite **5173**, API **8000**. Uma worktree paralela usa outras sem editar arquivos: `PORT` e `SORA_BACKEND_URL` no Vite; `SORA_QA_BASE` e `SORA_QA_API` nos scripts de QA e no Playwright. O `tauri.conf.json` não lê variável de ambiente: `devUrl` e `devCsp` ficam em 5173/8000 (quem usar outra porta troca à mão, sem commitar).

Tudo vem do **backend por REST + SSE** (`src/api/eventos.ts`, `src/state/aplicarEvento.ts`). O app precisa da API e do worker (`backend/README.md`). Para desenvolver sem gastar cota: `SORA_MODELO_FALSO=1` e `uv run python -m workers`. Para o teste real, a conta de QA cadastra o provedor Groq em `/v1/provedores` lendo `SORA_QA_GROQ_CHAVE` do `backend/.env` (arquivo ignorado pelo git). Limite grátis: ao bater 429, esperar e tentar de novo. `sora.modelos.v1` guarda só escolhas não secretas; chave de API nunca fica no `localStorage`.

**Desktop (Tauri v2):** precisa do Rust (MSVC). Duas janelas: `main` (o app; fechar esconde na bandeja) e `ilha` (`index.html?janela=ilha`, transparente, sem borda, sempre no topo, topo central da tela, cliques atravessam fora da pílula). Bandeja, atalho global Ctrl+Shift+S, instância única. A ponte JS↔Rust é `src/desktop/ponte.ts` (no navegador vira no-op); o controle do PC está em `src-tauri/src/pc/` e `src/desktop/{PontePc,computadorPc}`. Specs: `app/docs/sora-desktop.md`, `app/docs/ilha-da-sora.md`, `docs/computador-por-bot.md`. Para inspecionar as WebViews: iniciar o exe com `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333`.

### 7.2 Estrutura (`app/src`)

| Pasta / arquivo | O que tem |
|---|---|
| `components/mascot/` | **Mascote**: `SoraOrb`, `SoraThinking`, `orbEngine.ts`. Estados: `arriving · idle · listening · thinking · coordinating · working · done`. Não mudar. |
| `components/layout/` | `AppShell`, `Sidebar` (260 px), painel lateral e barra superior de 52 px. |
| `screens/` | `SoraChat` (início e conversa com a Sora), `AgentChat` (bot 1:1), `Agentes` (galeria de bots), `NovoBot` (criação direta por descrição), `CriarAgente` (editar bot), `Grupos`, `Clientes`, `Configuracoes`, `Entrar`, `Mobile` (/celular), `OrbLab`, `Catalogo` (/lab/ui, só em dev). `Plugins.tsx` fica no código, mas a rota redireciona para `/`. |
| `components/ui/` | Compositor único (BorderBeam, voz dentro do campo), mensagens, fontes em chips, código e tabela sob demanda, "Ir para o fim", "Pensando" com orb. |
| `components/builder/` | Cartão de rascunho de bot (seções em linhas) e formulário do bot. |
| `components/grupos/` | Novo grupo (2 a 5 bots), chat do grupo, membros com estado e Parar, gerir grupo, menções com teclado, tarefas. |
| `components/pendencias/` | Cartão e central **Precisa de você** (Permitir uma vez · Sempre permitir · Recusar), proposta de grupo, instruções propostas, cartão de domínio do navegador. |
| `components/work/` | Painel **Trabalho**: "Você pediu", chamadas de ferramenta, rastro, abas **Navegador** e **Computador** com tela ao vivo, Assumir/Devolver. |
| `components/clientes/`, `settings/` | Tela Clientes (fichas, conhecimento da empresa, sugestões); Configurações (Conta, Modelos de IA, Memória, Rotinas, Habilidades, Conectores, Telegram, Navegador, Canais da empresa, Ilha). |
| `components/ilha/` | **Ilha da Sora**: pílula com a Sora e os bots trabalhando, aprovação, filtro. `IlhaDesktop.tsx` é a janela. |
| `components/comandos/` | Paleta **Ctrl/⌘+K** (comandos e busca nas mensagens) e atalhos. |
| `components/{equipe,memoria,rotinas,anexos,uso,erros,sessao,overlay,gestao}/` | Fila, contexto, memória, rotinas, anexos, "Uso do mês", erros, login, diálogos e menus. |
| `state/` | `aplicarEvento.ts` (redutor idempotente dos eventos SSE), `projetos.ts` (conversas), `sora.ts`, `bots.ts`, `grupos.ts`, `atencao.ts` ("Precisa de você"), `equipe.ts`, `telas.ts`, `clientes.ts`, `pecas.ts`, `modelos.ts`, `sessao.ts`, `uso.ts`. |
| `api/` | Cliente HTTP (`cliente.ts`, token só em memória), `eventos.ts` (SSE com `Last-Event-ID`), `bots.ts`, `grupos.ts`, `telas.ts`, `canaisEmpresa.ts`, `anexos.ts`, `voz.ts`. |
| `desktop/` | Ponte Tauri, aviso do sistema e "(N) Sora" no título fora de foco, controle do PC. |
| `../src-tauri/` | Casca Tauri v2: janelas, bandeja, atalho, ponte do PC (Rust). |

**Rotas:** `/` (Sora) · `/bots` · `/bots/novo` · `/bots/:agente` · `/bots/:id/editar` · `/grupos` · `/grupos/:grupoId` · `/clientes` · `/configuracoes` · `/celular` · `/lab/orb` · `/lab/ui` (dev). Redirecionam: `/plugins`, `/projetos`, `/projeto/:id`, `/revisao/:id`, `/chat/sora` e `/agentes/novo` para `/`; `/agentes` para `/bots`; `/canais/*` para `/grupos`.

### 7.3 Decisões de produto

**2026-11-20 — Onda 1 (base de produção, `docs/referencias/openbot-comparativo.md`):**
- **Senha nova:** "Esqueci minha senha" em Entrar manda um link de uso único (30 min, token no `#` do endereço) para `/redefinir-senha`; a resposta é a mesma exista a conta ou não, e quem envia o e-mail é o worker. Salvar a senha nova encerra todas as sessões. Sem `EMAIL_PROVEDOR`, a rota responde 503. Configurações → Conta → **Trocar senha** confere a atual e tira os outros aparelhos.
- **Seus dados:** Configurações → Conta → **Baixar meus dados** (senha) gera um .zip com tudo o que é da conta (mesma regra de tabelas do apagar conta), sem senha, chaves, hashes nem vetores; 3 por hora.
- **Relatar problema:** Ctrl+K ou Configurações → Conta. Texto + diagnóstico opcional (versão, tela, últimos 20 erros), que a pessoa vê antes de enviar; tudo mascarado no app e de novo no servidor; dá para retirar. O time lê com `python -m app.cli relatos listar`.
- **Chaves extras e modelos reserva:** cada conexão aceita até 4 chaves extras; no limite da chave, o **mesmo modelo** segue com a próxima. Até 3 modelos reserva por conta, usados só quando o modelo fixo escolhido falha. Toda troca aparece na linha do tempo (nada silencioso). Reserva por bot fica para depois.
- **Atualização do desktop:** procura versão nova ao abrir e a cada 6 h, instala só com assinatura válida. Desligada enquanto `plugins.updater.pubkey` estiver vazio (`app/docs/atualizacao-desktop.md`).

**2026-11-16 — seletor de modelo e permissão:** escolhas persistentes por conversa/bot/grupo; modelo explícito sem troca silenciosa; modos Perguntar/Automático/Total conservam bloqueios. Provedor novo vem com todos os modelos ativos; migração 0016 ativa os existentes uma vez. Chat com destaques e adição por ID. Contrato: `docs/seletor-modelo-permissao.md`.


**2026-11-15 — criação direta pelo menu:** "Criar novo" oferece somente "Novo bot" e "Novo grupo", também no celular. "Novo bot" abre `/bots/novo`, sem histórico e com campo vazio a cada clique. Enviar cria diretamente pelo modelo do usuário (fallback por regras), abre `/bots/:agente` e envia o pedido original pela mensagem otimista normal. Durante a criação aparece "Criando seu bot…" com thinking orb; erro mantém o texto. Pedir um bot na conversa da Sora continua exigindo o cartão de rascunho. A Sora continua acessível pela marca no topo.


**Decisões do Heitor, etapa 5 (2026-11-02, 2026-11-04 e 2026-11-08; `log/etapa5-interface.md`):**
1. A **Sora é sempre a chefe de equipe** dos grupos.
2. **"Projetos" some e vira grupo.** Pedido grande à Sora → ela propõe um grupo, reaproveita bots que já existem; bot novo só depois do "sim".
3. **Plugins escondidos** até o grupo decidir (a rota volta para `/`).
4. **Ilha só fora do app:** no desktop aparece só com a janela principal fora de foco ou minimizada; dentro do app e no navegador não aparece.
5. **Bots sem limite por usuário; grupo com 2 a 5 bots**, além da Sora. `@todos` vai só para os bots; a Sora coordena.
6. **Depois da etapa 5:** consertar a renovação da sessão (três F5 seguidos com respostas perdidas derrubam o login; exige migração). Resolvido em 2026-11-19 (`fix/revisao-geral`, migração 0017): de 30 s a 5 min o token anterior ganha par novo, até 3 vezes.
7. **Criar bot conversando:** cartão de rascunho (nome, função, cor, instruções, ferramentas em chips, rotina "Todo dia / Dias úteis / Toda semana + hora"), que o usuário ajusta e confirma. Sem termo técnico.
8. **Aprovação sem "publicar":** ação que mexe no mundo vira "Precisa de você". Resultado chega como mensagem com arquivos. "Sempre permitir" só aparece quando o servidor manda (nunca para ações perigosas).

**Decisões do Heitor, etapa 6 (2026-11-14 e 2026-11-15; `log/etapa6-acabamento.md`):**
9. **Meta:** acabamento igual ou melhor que o Grok Bot, só como referência de experiência (nada de texto, código, ícone ou marca de terceiros).
10. **Visual novo** (`docs/design/etapa6-visual.md`): barra lateral de 260 px com só o mascote e o nome no topo, **Criar novo** (menu Nova conversa / Novo bot / Novo grupo), **Buscar** (Ctrl+K), **Clientes**, **BOTS** e **GRUPOS**; estado do bot só quando trabalha ou precisa de você (sem "Livre"); e-mail só em Configurações → Conta; título do início "Em que posso te ajudar hoje?", sem linha de apoio; coluna de leitura de 760 px; contraste mínimo 4,5:1.
11. **Conversa:** Parar, fontes em chips, editar a pergunta, refazer a resposta, 👍/👎 guardado, imagem e arquivo na resposta, visão de imagem anexada, voz (ditado no campo; conversa por voz contínua só no bot), busca nas mensagens, memória editável e chip "Guardei isto" com Desfazer. Sem botão que não faz nada.
12. **Painel Trabalho** com tela ao vivo do **navegador** e do **computador** do bot (≥ 1 imagem por segundo, Assumir clicando na imagem).
13. **Navegador próprio por bot** (perfil só dele é o padrão de bot novo) e **computador virtual por bot** (contêiner isolado, em paralelo, mesmas regras do sandbox).
14. **Controle do PC do usuário** (só app de desktop): ponte local com árvore de acessibilidade do Windows, captura, mouse e teclado; **um bot por vez**; desligado por padrão e ligado por bot em Configurações; borda acesa, **Parar** sempre visível, mexer no mouse pausa; primeira ação em cada programa vira cartão; nunca digita senha; bloqueia terminais, gerenciadores de senha e a própria Sora; não controla o servidor.
15. **Canais da empresa só leitura** (WhatsApp Business pela API oficial e Slack pelo app oficial; nada de WhatsApp pessoal): ficha por cliente, base de conhecimento sem dado pessoal, sugestões de melhoria aprovadas pelo usuário. **Responder e resumo do dia foram removidos:** a Sora nunca envia nada por esses canais. LGPD: máscara de CPF/cartão/senha, retenção configurável, "apagar tudo deste cliente".
16. **Aviso fora de foco:** notificação do sistema e "(N) Sora" no título quando um bot precisa de você; o clique leva ao cartão exato.
17. **Teste com modelo real (Groq)** no ambiente de QA; o modelo falso fica só nas suítes automáticas.
18. **Regra de modelo para o time:** tarefa simples → modelo leve; segurança, arquitetura e bug difícil → modelo forte.
19. Vocabulário: nada de "agente", "projeto", "canal" ou "publicar" visível ao usuário (bot, grupo, tarefa). O slogan "Seus agentes" da tela Entrar é o oficial.
20. **Aba Criar do construtor** continua indisponível: o app avisa e leva ao formulário. O usuário cria bots pela conversa com a Sora.

**Decisões anteriores que continuam valendo:** a Sora não pode ser apagada; apagar e renomear pedem confirmação; chaves de API nunca no navegador; capacidades de modelo fora do catálogo são marcadas pelo dono do provedor; mascote e cores dos agentes intocados; **Ilha** inspirada no Coucou (github.com/Louis-CFM/coucou), com atalho Ctrl/⌘+Shift+S, filtro Todos/Trabalhando/Concluídos e "olho" por bot.

### 7.4 Ferramentas de QA (`app/qa/`)

Todas leem `SORA_QA_BASE` (Vite, padrão `http://localhost:5173`) e, quando falam com a API direto, `SORA_QA_API` (padrão `http://localhost:8000`); conta de QA própria (`SORA_QA_EMAIL`).

- `node qa/e2e.mjs` → ponta a ponta de bots, grupos, cartões e conversa (SSE real), com `SORA_MODELO_FALSO=1`.
- `node qa/ilha.mjs` → Ilha da Sora (fotos em `qa/shots/ilha/`); `qa/ilha-tauri.mjs` e `qa/pc-tauri.mjs` → janela da Ilha e controle do PC no **Tauri real**, por CDP (WebView2 com porta de depuração).
- `node qa/contraste.mjs` → mede o contraste de todos os textos nas rotas (522 textos, 0 falhas); reescreve `qa/contraste.md`.
- `npm run test:visual` → baselines em 1440 e 390 px; limpa conversas, bots, grupos e perfis do navegador antes de cada teste.
- `node qa/design.mjs`, `clientes-shots.mjs`, `trabalho-telas.mjs`, `vitral10.mjs`, `conversa-acabamento.mjs`, `conversa-fontes.mjs`, `digitacao.mjs`, `etapa4.mjs` → fotos e conferências específicas.
- `node qa/shoot.mjs [rotas]` → fotos rápidas em 1440 e 390 px.
- `node qa/e2e-erro-provedor.mjs` → erro do provedor com servidor HTTP local que falha.
- Modelo falso: `[pergunta]`, `[aprovacao]` e `[orcamento]` no pedido disparam cartões e orçamento (só com `SORA_MODELO_FALSO=1`).
- Desktop: `cd src-tauri && cargo clippy -- -D warnings && cargo test` (35 testes); `npm run desktop:build`.
- Relatos do "Relatar problema": `cd backend && uv run python -m app.cli relatos listar --dias 7`.
- Backend: `cd backend && uv run ruff check && uv run pytest tests/unitarios` (2176 passam); integração com Docker (Postgres e Redis), arquivo por arquivo com `SORA_MODELO_FALSO=1` (28 de 28 verdes).

### 7.5 Pendências / próximos passos

- **Onda 1 (2026-11-20):** ligar o e-mail em produção (`EMAIL_PROVEDOR=smtp` ou `resend` e `EMAIL_REMETENTE`), aplicar as migrações 0018 e 0019, gerar as chaves do atualizador do desktop e decidir se o repositório fica público (o `latest.json` vem de `releases/latest`). Modelos reserva por bot e a Onda 2 do comparativo seguem abertos.
- **Junção na `main`:** feita e enviada ao GitHub em 2026-11-15 (`e2f4371`).
- **Teste real do Tauri:** feito em 2026-11-15 (login, Ilha, "(1) Sora", Bloco de Notas, Parar, senha e cmd recusados, tarja). Faltam a pausa pelo mouse físico (manual), o Gerenciador de Tarefas (UAC) e o clique no aviso do sistema (instalador).
- **Slack e WhatsApp Business reais:** só testados com assinaturas simuladas.
- **Instalador assinado** e **domínio real da API** no CSP de produção do `tauri.conf.json` (hoje `https://api.seu-dominio.com.br`).
- **A decidir:** PWA e tema claro.
- **Abertos MÉDIA/BAIXA** (`.maestri/relatorios/prumo4.md` e `ancora8.md`): qualidade da proposta de grupo com modelo pequeno (M4); resposta repetida de modelo pequeno (M5); streaming só aparece de verdade fora do Groq (M7); busca com provedor real (Tavily/Brave) e `@todos`/"Guardei isto" com modelo grande não vistos ao vivo; "Resumo está escrevendo…" enquanto o cartão espera; texto anterior cru no cartão de instruções (hoje só a diferença); visão com modelo de imagem.
- **Plugins** (escondidos). A renovação da sessão (decisão 6) foi resolvida em 2026-11-19.
- Microfone num celular de verdade, via https. Sincronização entre computador e celular.

### 7.6 Como o app foi feito (time de IA no Maestri)

O front-end da primeira versão foi construído em 2026-10-10 por um time no Maestri, coordenado por um Claude Code orquestrador, em rodadas: construir → validar com screenshots → corrigir.

| Agente | Modelo | Fez |
|---|---|---|
| Prisma | Claude Code (Opus) | mascote, thinking orb, store, integração geral |
| Forja | Codex (GPT-5.6) | telas da rodada 1–2, overlays, Configurações |
| Brisa | Claude Code | diálogos Renomear/Apagar |
| Vigia | Hermes (OpenAI) | validação: ferramentas de QA, auditoria, E2E |

As etapas 5 e 6 (2026-11-14 e 2026-11-15) usaram um time maior, com Claude, Codex e Grok: Âncora, Motor, Rumo, Ponte e Farol no backend; Leme, Mosaico, Brisa, Vitral, Prisma e Lince no app; Vela no desktop; Cerca na segurança; Prumo e Lince como validadores. Relatórios em `.maestri/relatorios/` (pasta ignorada pelo git). Os papéis ficam salvos no Maestri (workspace "Sora"); o histórico está nos commits. O Hermes deve usar **só modelos da OpenAI**; use raciocínio *medium* no Codex para não estourar a cota.
