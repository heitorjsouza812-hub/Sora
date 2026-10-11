# Sora para desktop (Tauri) + ilha mais bonita — especificação (2026-10-11)

O Heitor autorizou ("faça o tauri") transformar o app em programa instalável para ver **como ficaria
rodando no PC**. Referência: a versão Windows do Coucou (`scratchpad/coucou/windows/src-tauri`,
principalmente `island.rs` — janela transparente no topo, click-through por retângulo com polling do cursor).

Regras de sempre: PT-BR, não mudar a aparência do mascote nem as cores dos agentes, sem spinners, os
agentes continuam os **simulados da Sora** (nada de monitorar Claude Code/Codex reais nesta rodada,
nada de servidor HTTP, nada de SDK de IA). O app web (`npm run dev`) tem que continuar funcionando igual.

## 1. Casca Tauri v2 — `app/src-tauri/` (dono: **Tear**)

- `npm i -D @tauri-apps/cli@^2` e `npm i @tauri-apps/api@^2` (+ plugins JS que precisar);
  scripts `"tauri": "tauri"`, `"desktop": "tauri dev"`, `"desktop:build": "tauri build"`.
- `tauri.conf.json`: productName **"Sora"**, identifier `com.sora.app`, `devUrl http://localhost:5173`,
  `beforeDevCommand "npm run dev"`, `frontendDist ../dist`, `beforeBuildCommand "npm run build"`.
  Bundle `nsis` + `msi`, `installMode currentUser`, idioma PortugueseBR. Ícones gerados de uma imagem da
  Sora (renderize o `<SoraOrb>` em PNG 1024 px com Playwright sobre fundo `#0B0F1A` arredondado, depois
  `npx tauri icon`).
- Janelas:
  - **main**: "Sora", 1280×820, mín. 960×640, centralizada, decorada. **Fechar → esconde** (fica na bandeja).
  - **ilha**: `url "index.html?janela=ilha"`, 800×460 lógicos (= `ILHA_JANELA` em `src/desktop/ponte.ts`),
    `transparent`, `decorations false`, `shadow false`, `alwaysOnTop`, `skipTaskbar`, `focus false`,
    `resizable false`, posicionada no **topo central do monitor principal** (y = 0) no setup e quando
    a tela muda. `additionalBrowserArgs` com `--autoplay-policy=no-user-gesture-required` (sons).
- **Click-through**: thread que lê `app.cursor_position()` ~30×/s; comando `ilha_retangulo {x,y,w,h}`
  guarda o retângulo; fora dele (+ margem 8 px) `set_ignore_cursor_events(true)`. Emite `ilha-mouse
  {dentro,x,y}` (coordenadas lógicas relativas à janela) para a janela "ilha" quando muda.
  Pausar quando a janela estiver escondida (0 % de CPU parada, como o Coucou).
- **Bandeja** (tray): ícone da Sora; menu "Abrir a Sora", "Mostrar/ocultar a ilha", "Sair".
  Clique esquerdo → abre o app.
- **Atalho global** `Ctrl+Shift+S` (`tauri-plugin-global-shortcut`) → evento `ilha-alternar` para a janela ilha.
- `tauri-plugin-single-instance`: abrir de novo só traz a janela principal.
- Comandos: `ilha_retangulo`, `ilha_visivel(visivel)`, `mostrar_app`, `navegar(caminho)` (emite
  `sora-navegar` para "main" e mostra/foca a janela main).
- `capabilities/default.json` com o mínimo para as duas janelas (core:event, core:window, os comandos).
- CSP: sem rede externa (as fontes já são locais).
- **Implementar `src/desktop/ponte.ts`** (o stub já tem as assinaturas; não renomear).
- **Sincronização entre janelas**: o store (`sora.projetos.v1`) e as prefs da ilha (`sora.ilha.v1`) usam
  `localStorage` + evento `storage`. Verifique se o evento `storage` cruza as duas WebViews do Tauri. Se
  **não** cruzar, faça a ponte reemitir (ex. evento Tauri `sora-armazenamento {chave}` depois de gravar e,
  ao receber, despachar um `StorageEvent` sintético na janela) — sem mudar a API dos stores.

## 2. Ilha no desktop + mais bonita + filtro de agentes (dono: **Farol**)

- `main.tsx`: se `janelaAtual === 'ilha'` renderizar só `<IlhaDesktop/>` (sem router de telas, sem
  AppShell), com `html, body, #root { background: transparent }`.
- `components/ilha/IlhaDesktop.tsx` (+ CSS): reutiliza `Ilha` em modo `desktop` — a pílula **colada no topo
  da tela** como um notch (cantos de cima retos, de baixo arredondados), centralizada na janela de 800 px.
  Mede o retângulo visível (ResizeObserver) e chama `informarRetanguloIlha`. Hover/saída/olhar usam
  `aoMouseIlha` (com click-through o DOM nem sempre recebe `mouseleave`). `aoAlternarIlha` abre/fecha.
  "Abrir chat", "Revisar", "Pedir ajuste" → `abrirNoApp(caminho)`. Aprovar funciona direto (store compartilhado).
  O painel expandido cabe em 800×460 (rolagem interna se o detalhe passar disso).
- Na janela **main** do desktop: a ilha interna fica escondida (a de verdade está no topo da tela), a menos
  que `prefs.ilhaNoApp`. `aoNavegar` → `navigate(caminho)` (um componente pequeno dentro do Router).
  `definirIlhaVisivel(prefs.visivel)` quando a preferência mudar.
- **Mais bonita, com animação** (respeitando `prefs-reduced-motion`, sem mudar o mascote):
  - transição compacta ⇄ expandida com mola (largura/altura/raio animados, conteúdo com fade+slide escalonado);
  - bonecos entram com escala/fade em cascata e saem suavemente; o que conclui dá um "pop" e um anel na cor dele;
  - borda/halo da pílula com um brilho que corre nas cores dos agentes trabalhando (pode usar `border-beam`,
    que já está nas dependências) e some quando nada roda;
  - barras de progresso com transição e brilho; contador "N trabalhando" com troca animada dos números;
  - no estado alerta, a pílula "respira" suavemente até ser vista.
- **Escolher quais agentes ver** (contrato pronto em `ilhaEstado.ts`: `prefs.filtro`, `prefs.ocultos`,
  `filtrarAgentes`, `alternarAgenteOculto`):
  - na Visão geral, um seletor segmentado **Todos · Trabalhando · Concluídos** (com contagem em cada um);
  - em cada pílula de boneco, um botão "olho" (Esconder/Mostrar <nome>) — os escondidos ficam numa linha
    "N escondidos · mostrar" que reexibe;
  - a pílula compacta e o contador respeitam o filtro; a Sora branca sempre aparece.
- Configurações → aba Ilha: acrescentar "Mostrar também dentro do app" (`ilhaNoApp`, só aparece no desktop)
  e o filtro padrão. (Arquivo do Tear na rodada anterior — combine com ele, ele está ocupado com o Rust.)

## 3. Validação (dono: **Sentinela**)

- Testes vitest para `filtrarAgentes`/`alternarAgenteOculto`/prefs novas (padrões e migração de prefs antigas
  sem os campos novos).
- `npm run build`, `npx oxlint`, `npm test`, `node qa/e2e.mjs`, `node qa/ilha.mjs` (atualizar para o filtro).
- `cd src-tauri && cargo check` e `cargo clippy` sem erros; `npm run desktop:build` gera o instalador
  (anote o caminho do `.exe`/`.msi`).
- Rodar o app de desktop (`npx tauri dev` ou o exe de release) e capturar a tela inteira (PowerShell
  `System.Drawing` CopyFromScreen) com a ilha compacta e expandida → `qa/shots/desktop/`. Verificar: janela da
  ilha transparente (sem retângulo branco/preto em volta), cliques atravessam fora da pílula, app principal
  abre ao clicar "Abrir chat".

## Pronto quando

Tudo do §3 passa, o instalador é gerado, as capturas da área de trabalho mostram a ilha no topo da tela
sobre outras janelas, e o app web segue igual.
