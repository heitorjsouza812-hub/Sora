# Onde paramos

_Atualizado em 2026-10-11 — revisão do front-end contra a especificação do backend (nenhum código alterado). Antes: 2026-10-10, ~23h20, trabalho pausado a pedido do Heitor._

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
