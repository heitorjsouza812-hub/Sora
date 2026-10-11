# Ilha da Sora — especificação (2026-10-11)

Adaptação do **Coucou** (https://github.com/Louis-CFM/coucou; clone de referência em
`C:\Users\heito\AppData\Local\Temp\claude\C--Users-heito\288ef481-f464-4ccc-abab-b7d76bd383bf\scratchpad\coucou`,
veja `design/captures/*.png`, `windows/src/island/` e `windows/src/style.css`).

No Coucou, o mascote Mochi vive no "notch" e mostra as sessões de agentes de IA que estão rodando.
**Na Sora:** uma *ilha* fixa no topo do app. A **Sora branca** (`#E2ECFF`, o `<SoraOrb>` de sempre) é a
personagem principal; os **"bonecos" são os agentes que estão rodando** (mesmo corpo de pontos, menor e na
cor de cada agente). Uma **aba de projetos** escolhe qual projeto está sendo mostrado.

Regras do projeto valem: PT-BR, tokens de `src/styles/tokens.css`, **não mudar a aparência do mascote**,
nada de spinners (o movimento do orb é o carregamento), front-end apenas (sem servidor), acessível
(teclado, `aria-*`, alvos de 44 px no celular, `prefers-reduced-motion`).

## Contrato de dados — `src/components/ilha/ilhaEstado.ts` (PRONTO, não renomear exports)

- `useIlha(): VisaoIlha` — projetos (rodando primeiro), projeto mostrado, `agentes: AgenteIlha[]`
  (os bonecos, com `orb`, `rotulo`, `progresso`, `passoAtual`), `sora` (orb/rotulo/pulso do projeto
  mostrado), `ticker` (últimos 6 passos), `trabalhando`, `rodando`, `alerta` (equipe pronta → revisar).
- `useIlhaPrefs()` / `definirIlhaPrefs(patch)` — `{ visivel, som, esconderOciosa, projetoId }`
  (`projetoId: null` = automático), salvo em `localStorage['sora.ilha.v1']`.
- `visaoIlha(e, agora, projetoId)` — função pura para testes.

Pode acrescentar exports novos; não quebre os existentes.

## Estados da ilha (como o FSM do Coucou)

| Estado | Quando | Aparência |
|---|---|---|
| **oculta** | `prefs.visivel=false`, ou nenhum projeto existe (a barra lateral começa vazia, §7.3-1), ou na rota `/` sem projeto | nada |
| **espiando** | `esconderOciosa` e nada rodando | faixa fina (≈120×6 px) no topo; mouse em cima → compacta |
| **compacta** | padrão | pílula preta centralizada no topo (≈ 280–420×40 px, cantos 20 px): Sora pequena (24 px) à esquerda + texto curto (`sora.rotulo` ou "N trabalhando") + bonecos (orbs 18 px nas cores dos agentes, até 5 + "+N") à direita. Um pulso quando um agente conclui. |
| **expandida** | hover > 250 ms, clique, Enter/Espaço com foco, ou atalho | painel ≈ 720×300 px (no celular: largura total − 16 px de margem, altura automática). Esc, clique fora ou mouse saindo (desktop, após 400 ms) fecham. |
| **alerta** | `alerta` novo (equipe pronta) | abre sozinha na **vista Aprovação** (com som se `prefs.som`), uma vez por projeto/versão |

## Vistas da ilha expandida

Cabeçalho (como o Coucou: ícones à esquerda, status à direita):
`[Início] [Projeto ▾ <título>] [Abrir chat]  ····  "N trabalhando"  [🔊 som]  [⧉ destacar]  [✕]`

1. **Início (Visão geral)** — card esquerdo: Sora branca grande (≈96 px, `state=sora.orb`,
   `pulseKey=sora.pulso`), nome do projeto, rótulo da Sora e o **ticker** (passos com ícone por tipo:
   prompt, pensamento, ferramenta `acao`, handoff "Atlas → Luna", entrega; o executando com shimmer).
   Card direito: **pílulas dos bonecos** — orb do agente (28 px, `state=agente.orb`, `movimento`) + nome
   na cor do agente + rótulo curto + barra de progresso fina na cor. Clique na pílula → vista Agente.
   Sem agentes ("conversa"): só a Sora + "Sem agentes rodando neste projeto".
2. **Aba Projeto (seletor)** — lista de `projetos`: título, fase (rotuloFase de `layout/useSoraStatus`),
   mini-bolinhas nas `cores`, "N trabalhando", progresso; primeiro item "Automático — projeto aberto".
   Busca quando houver > 6. Escolher chama `definirIlhaPrefs({ projetoId })` e volta ao Início.
   Navegável por setas (listbox acessível).
3. **Agente (detalhe)** — como a captura `docs/media/claude-code.png` do Coucou: coluna esquerda com orb
   grande na cor do agente, nome, função, status e a **lista de passos** (✓ concluído / orb mini girando
   executando); à direita o **passo atual** (ferramenta `acao`, parâmetros em JSON legível, resultado
   resumo/links/itens) ou o último concluído; barra de progresso; botões **Abrir chat do agente**
   (`/chat/:id`) e um campo **"Mensagem para <nome>…"** que chama `enviarParaAgente`. Botão Voltar.
4. **Aprovação** (o "Allow/Deny" do Coucou adaptado à regra "nada é publicado sem a sua aprovação"):
   Sora com pulso, "A equipe terminou **<título>**", lista de `alerta.entregas`, botões
   **Pedir ajuste (N)** → `/revisao/:id`, **Revisar (R)** → `/revisao/:id`, **Aprovar e publicar (Y)**
   → `aprovarProjeto(id)` + toast. Atalhos só valem com a ilha aberta e foco fora de campos de texto.

## Extras do Coucou adaptados

- **Sons** (`som.ts`): WebAudio, sem arquivos — `tocar('abrir'|'concluiu'|'pronto'|'aprovado')`,
  volume baixo, respeita `prefs.som`. Disparos: agente concluiu, equipe pronta, aprovado.
- **Destacar** (`useJanelaDestacada.ts`): "Mochi no desktop" → Document Picture-in-Picture
  (`window.documentPictureInPicture.requestWindow({ width: 420, height: 320 })`, copiar as folhas de
  estilo para a janela) e renderizar a ilha expandida nela via `createPortal`. Sem suporte → botão escondido.
  Fechar a janela volta a ilha para o app.
- **Olhar**: a Sora da ilha compacta olha para o mouse (`lookAt`, −1..1) quando ele está perto do topo.
- **Cutucar**: 5 cliques rápidos na Sora → `pulseKey` + rótulo "Ei! 😵‍💫" por 1,5 s (easter egg, como o "dizzy").
- **Atalhos**: `Ctrl/⌘+Shift+S` abre/fecha a ilha; comandos na paleta (Ctrl+K): "Abrir a Ilha da Sora",
  "Ilha: escolher projeto", "Ilha: som ligado/desligado".
- **Configurações → aba "Ilha"**: mostrar ilha, sons, recolher quando nada estiver rodando, projeto
  (Automático/lista), botão "Testar som".

## Arquivos e donos

| Arquivo | Dono |
|---|---|
| `components/ilha/ilhaEstado.ts` | orquestrador (pronto) |
| `components/ilha/Ilha.tsx`, `VisaoGeral.tsx`, `Aprovacao.tsx`, `ilha.css`, `index.ts`; montagem no `layout/AppShell.tsx` e no `screens/Home.tsx` se a Home não usa o AppShell | **Farol** (Claude Code) |
| `components/ilha/SeletorProjeto.tsx`, `DetalheAgente.tsx`, `Ticker.tsx`, `som.ts`, `useJanelaDestacada.ts`, `ilha-partes.css`; aba "Ilha" em `screens/Configuracoes.tsx`; comandos em `components/comandos/` | **Tear** (Codex) |
| testes `src/components/ilha/__tests__/*.test.ts(x)`, `qa/ilha.mjs` (E2E + screenshots) | **Sentinela** (Hermes) |

Interfaces entre Farol e Tear (props):
- `<SeletorProjeto onEscolhido={() => void} />` — lê `useIlha()`/`useIlhaPrefs()` sozinho.
- `<DetalheAgente agenteId={string} onVoltar={() => void} />`
- `<Ticker passos={PassoTrabalho[]} compacto?={boolean} />`
- `tocar(nome)` e `useJanelaDestacada(): { suportado; aberta; abrir(): Promise<void>; fechar(); container: HTMLElement | null }`

## Pronto quando

`npm run build`, `npx oxlint`, `npm test` e `node qa/e2e.mjs` passam; `node qa/ilha.mjs` passa; console sem
erros; screenshots 1440 e 390 px aprovados pelo validador.
