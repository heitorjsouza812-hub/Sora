# Onde paramos

_Atualizado em 2026-10-17 — **etapa 1 do backend (conexão das APIs) concluída**; etapa 2 (ligar o app) em andamento. Antes, 2026-10-15: revisão de segurança concluída e validada; APP-003 e hover da ilha corrigidos no Tauri real._

## Etapa 1 — conexão das APIs (2026-10-15 a 17)

- Rotas `/v1/provedores` (testa a chave antes de salvar, cifra com AAD = id do provedor, duplicado 409, limite de 10 provedores e 10 testes/h), `/v1/modelos`, `/v1/preferencias`; `tem_provedor` exige provedor validado; dependência `exigir_provedor_validado` (412); ponte banco→seletor em `app/seletor/repositorio.py`. Especificação: `log/etapa1-conexao-apis.md`.
- Validado em 2026-10-17 com Docker: ruff limpo, pytest **835 passed / 2 skipped** (commit `76efd9b`).
- **Próximo:** etapa 2 — ligar o app (login, Configurações → Modelos de IA no backend, chaves fora do `localStorage`, APP-001). Especificação: `log/etapa2-app-provedores.md`.

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
