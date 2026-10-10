# Sora — front-end

**Sora** é uma plataforma de **agentes de IA criados por conversa**. Você descreve o que precisa
("crie uma campanha para lançar minha cafeteria…") e a Sora entende o pedido, monta um **plano**,
cria uma **equipe de agentes** especializados, coordena o trabalho entre eles e entrega o resultado
para você **revisar e aprovar** — nada é publicado sem aprovação.

> Sua ideia. Seus agentes. Tudo em uma conversa.

Este diretório é o **front-end** do produto. Ainda **não há back-end**: o planejamento, os agentes e o
trabalho são **simulados no navegador** e salvos no `localStorage`.

Contexto completo do produto, decisões, histórico do time e pendências:
**[`CLAUDE.md` → §7 Estado do app](../CLAUDE.md#7-estado-do-app-front-end)** (o mesmo conteúdo está em `AGENTS.md`).

## Como rodar

Requisitos: Node.js 20+ e npm.

```bash
cd app
npm install
npm run dev        # http://localhost:5173
```

## Scripts

| Comando | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento (Vite, com HMR) |
| `npm run build` | Checagem de tipos (`tsc -b`) + build de produção em `dist/` |
| `npm run preview` | Serve o build de produção localmente |
| `npm run lint` / `npx oxlint` | Lint (oxlint) |

## Stack

Vite · React 19 · TypeScript · react-router-dom · CSS puro com tokens (`src/styles/tokens.css`).
Efeitos: `border-beam` (BorderBeam no campo de mensagem) e `voice-glow` (VoiceBeam do microfone).
Fontes locais: Inter variável (`@fontsource-variable/inter`) e Playfair Display (`@fontsource/playfair-display`).

## Estrutura

```
app/
├─ index.html            meta tags, Open Graph, manifest e ícones
├─ public/               favicon.svg, ícones PWA, og.png, manifest.webmanifest, imagens de exemplo
├─ qa/                   ferramentas de QA (Playwright) — veja abaixo
└─ src/
   ├─ App.tsx            rotas
   ├─ main.tsx           entrada (fontes + estilos globais)
   ├─ screens/           telas: Home, SoraChat, AgentChat, Projetos, Agentes, CriarAgente,
   │                     Revisao, Configuracoes, Plugins, Mobile (/celular), OrbLab (/lab/orb)…
   ├─ components/
   │  ├─ mascot/         o mascote em canvas (SoraOrb, SoraThinking) — motor em orbEngine.ts
   │  ├─ layout/         AppShell, barra lateral
   │  ├─ builder/        construtor de agente + "Editar agente" (modal) + menu "…" do agente
   │  ├─ work/           painel "Trabalho" (passos ao vivo, chamadas de ferramenta)
   │  ├─ gestao/         renomear/apagar chats, projetos e agentes
   │  ├─ projetos/       tela Projetos
   │  ├─ review/         revisão e aprovação
   │  ├─ settings/       Configurações (modelos de IA)
   │  ├─ overlay/        Modal, BottomSheet, Popover acessíveis
   │  ├─ base/           componentes base (botões, campos…)
   │  └─ ui/             composer (BorderBeam/VoiceBeam), cards de entrega, ícones…
   ├─ data/              planejador simulado (planejador.ts), dados de exemplo e plugins
   ├─ state/             store de projetos/agentes (projetos.ts) e de modelos (modelos.ts)
   └─ styles/            tokens de design
```

## Rotas

| Rota | Tela |
|---|---|
| `/` | Novo chat — a Sora grande e "Em que posso te ajudar hoje?" |
| `/projeto/:id` | Chat da Sora (conversa ou projeto, com plano, equipe e painel Trabalho) |
| `/projetos` | Lista de projetos + "Novo projeto" |
| `/agentes` · `/agentes/novo` · `/agentes/:id/editar` | Galeria e construtor de agentes |
| `/chat/:agente` | Chat direto com um agente |
| `/revisao/:projetoId` | Revisão das entregas (aprovar ou pedir ajuste) |
| `/configuracoes` · `/plugins` | Configurações (modelos de IA) e plugins |
| `/celular` · `/lab/orb` · `/lab/ui` | **Só em desenvolvimento**: versão celular, laboratório do mascote e catálogo de componentes |

## QA

Com o servidor de desenvolvimento rodando (`npm run dev`):

```bash
node qa/e2e.mjs                  # teste ponta a ponta de todos os fluxos
node qa/shoot.mjs                # screenshots de todas as rotas (1440 px e 390 px) em qa/shots/
node qa/shoot.mjs --flow         # fluxo completo: digita um pedido e captura a cada 3 s
node qa/shoot.mjs --agentes      # abre Agentes e o construtor
```

O console de cada execução fica em `qa/shots/console.json`. Antes de entregar algo:
`npm run build && npx oxlint && node qa/e2e.mjs`.
