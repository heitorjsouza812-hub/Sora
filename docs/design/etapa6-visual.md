# Etapa 6: especificação visual

Autora: Prisma-2 (design) · 2026-11-14 · ramo `etapa5-interface`, worktree `C:\dev\sora-e5`

Meta do dono: a parte visual tem de ficar **igual ou melhor que o Grok Bot**. O Grok entra só como referência de experiência (limpo, compositor central no estado vazio, conversa arejada). Nenhum texto, ícone, logo ou marca da xAI entra no app.

- Protótipo: [`prototipo-etapa6.html`](prototipo-etapa6.html) (um arquivo, sem rede; abra direto no navegador). Seis abas: Sora vazia, Conversa, Bot + Trabalho, Grupo, Precisa de você, Celular.
- Fotos do app hoje: `app/qa/shots/design/antes-*.png` (71 fotos, 1440×900 e 390×844, tiradas em 2026-11-14 contra `localhost:5383` com o modelo falso).
- Fotos do protótipo: `app/qa/shots/design/depois-*.png`.

Regras que não mudam: aparência do mascote e cores dos agentes (§3 do `CLAUDE.md`), tokens de §4.1, tudo em PT-BR, nada de conteúdo de demonstração, Plugins escondido. Esta especificação não pede rota nova no backend.

---

## 1. Princípios

1. **A Sora é o centro.** Toda tela responde "onde está a Sora e o que ela faz agora". No estado vazio, mascote e compositor ficam juntos no centro. O movimento do mascote é o único indicador de trabalho.
2. **Uma coluna de leitura.** Mensagens, cartões e compositor dividem o mesmo eixo de 760 px. Nada de texto esticado por 1.100 px.
3. **Texto sem caixa.** A resposta do bot é texto na página. Caixa só para o que é do usuário (bolha) e para o que pede decisão (cartão).
4. **Um nome por tela.** O título aparece uma vez. Se a barra lateral já diz onde o usuário está, o cabeçalho não repete.
5. **Cor diz quem.** Cor de bot só no que é do bot (orb, nome, estado, faixa do cartão). Fora isso, branco, cinzas e o brilho dos beams.
6. **Peso por importância.** O que espera decisão tem o maior contraste da tela. Ação secundária aparece no hover ou no foco e some quando não é necessária.
7. **Navegação parece navegação.** Item de menu não tem borda de campo. Campo de texto só é campo de texto.
8. **Movimento com função.** De 120 a 420 ms, sempre ligado a uma mudança de estado. Com `prefers-reduced-motion`, tudo vira troca direta.

---

## 2. Grade e espaçamentos

Base de 4 px. Só os passos `4 · 8 · 12 · 16 · 20 · 24 · 28 · 32 · 40 · 48 · 64` (já existem como `--sp-*`).

| Região | Hoje | Depois |
|---|---|---|
| Barra lateral | 268 px, padding 20/12 | **260 px**, padding 8 px |
| Cabeçalho da tela | 60 px (68 no celular), borda embaixo | **52 px**, sem borda; a borda (`--line`) só aparece quando a conversa rola por baixo |
| Coluna de leitura | não existe: 1.106 px de texto na Sora, 678 px no bot | **760 px** de conteúdo, centralizada, com 24 px de respiro de cada lado (16 px no celular) |
| Compositor | 1.140 px na Sora, cerca de 710 px no bot | largura da coluna (760 px) |
| Painel Trabalho | cartão flutuante de 380 px com raio 16 e margem 16 | **360 px**, de cima a baixo, colado na borda direita, só com `border-left` |
| Telas de lista (Bots, Grupos, Configurações) | largura total | conteúdo com no máximo **1.040 px** (Configurações: 720 px de formulário) |

Quando o painel Trabalho está aberto, a coluna de leitura encolhe até 520 px; abaixo disso o painel vira gaveta por cima.

Ritmo vertical da conversa:

| Entre | Espaço |
|---|---|
| mensagens de autores diferentes | 28 px (24 no celular) |
| cabeçalho do autor (orb + nome) e o texto | 6 px |
| parágrafos, listas, tabela e código dentro da resposta | 14 px |
| texto e fontes | 16 px |
| fontes e ações | 8 px |
| resposta e cartão "Precisa de você" | 16 px |
| última mensagem e compositor | 40 px, com degradê de 32 px por cima do compositor |

Raios: `6` (código em linha, tecla), `10` (linhas da barra lateral, campos), `12` (tabela, código, imagem), `16` (cartões), `20` (bolha do usuário, modal), `24` (compositor), `999` (botões e chips).

---

## 3. Escala tipográfica (Inter)

Pilha: `"Inter", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif`. Sem `font-weight` quebrado (hoje há 450, 580, 640, 650); só **400, 500, 600 e 700**.

| Papel | Tamanho / linha | Peso | Onde |
|---|---|---|---|
| Destaque | 32 / 40, `-0.02em` | 600 | título do estado vazio (24 / 30 no celular) |
| Título de tela | 24 / 32 | 600 | Configurações, cabeçalho de seção |
| Título de bloco | 20 / 28, `-0.01em` | 600 | `h2` do markdown, título de modal |
| Corpo de conversa | **16 / 26** | 400 | resposta do bot |
| Bolha do usuário | **16 / 24** | 400 | hoje cai para 13 px no celular; passa a ser 16 em todo lugar |
| Compositor | 16 / 24 | 400 | hoje 14 px no desktop |
| Nome no cabeçalho | 15 / 20 | 600 | bot, grupo, título e texto dos cartões (15 / 22) |
| Interface | 14 / 20 | 400 ou 500 | linhas da barra lateral, botões (600), tabela |
| Apoio | 13 / 18 | 400 | estado, legenda, chip de fonte, "Resposta interrompida", nome do autor (600) |
| Legenda | **12 / 16** | 500 | piso do sistema: contador, tecla, hora |
| Rótulo de seção | 12 / 16, caixa alta, `0.06em` | 600 | "BOTS", "GRUPOS", "FERRAMENTAS" |
| Código | 13 / 20 | 400 | `ui-monospace, "Cascadia Code", Consolas` |

**Nada abaixo de 12 px.** Hoje existem 10,5 px (estado do bot na barra lateral), 10 px (tecla e contador) e 11 px (rótulo de seção).

---

## 4. Tokens

Tudo deriva de §4.1 e de `app/src/styles/tokens.css`. Cores de agente e do mascote não mudam.

### 4.1 Mantidos (sem alteração)

`--surface-1 #050608` · `--surface-2 #0F1115` · `--surface-3 #14161B` · `--text-1 #F2F5FB` · `--text-2 #8B93A3` · `--text-3 #7D8595` · `--line rgba(255,255,255,.08)` · `--line-strong rgba(255,255,255,.16)` · `--action #EEF2FA` · `--text-inverse #0B0D12` · `--ok #7EF2C4` · `--warn #FEBC2E` · `--danger #FF6B6B` · `--link` e `--focus #9CC4FF` · `--sora #E2ECFF` · `--atlas #56A8FF` · `--luna #AC80FF` · `--nina #46E8A8`.

### 4.2 Novos

| Token | Valor | De onde vem | Uso |
|---|---|---|---|
| `--surface-side` | `#090B0F` | já é o fundo da barra lateral, escrito à mão em `etapa5.css` | barra lateral e painel Trabalho |
| `--line-soft` | `rgba(255,255,255,.05)` | `--line` mais fraca | divisórias dentro de tabela e lista |
| `--hover` | `rgba(255,255,255,.06)` | `--white-a06` | fundo de hover |
| `--ativo` | `rgba(255,255,255,.09)` | `--white-a09` | item selecionado |
| `--col` | `760px` | | coluna de leitura |
| `--side-w` | `260px` | | barra lateral |
| `--top-h` | `52px` | | cabeçalho |
| `--painel-w` | `360px` | | painel Trabalho |
| `--fs-15` | `15px` | já é citado em `pendencias.css` sem existir | nome no cabeçalho, título e texto dos cartões |
| `--r-12`, `--r-20` | `12px`, `20px` | `--r-12` já é citado em `pendencias.css` sem existir | tabela, código, bolha, modal |
| `--dur-layout` | `420ms` | | compositor descendo |
| `--ease` | `cubic-bezier(.2,.8,.2,1)` | | toda entrada e deslocamento |
| `--beam` | `#FFD6F5, #FF5CCD, #A868FF, #508CFF, #3CE0D2` | `BEAM_COLORS` de `mini-video/sora-demo.html` | BorderBeam |

### 4.3 Ajustados

| O quê | Hoje | Depois | Motivo |
|---|---|---|---|
| Foco | `box-shadow: 0 0 0 3px rgba(156,196,255,.4)` | `outline: 2px solid var(--focus); outline-offset: 2px` | o anel suave dá 2,55:1 contra o fundo; o cheio dá 11,35:1 |
| Enviar desativado | `--action` com `opacity: .28` | fundo `rgba(255,255,255,.14)`, ícone `#B6BDCB`, sem `opacity` | ícone sobre o fundo passa de 2,44:1 para 6,32:1 |
| `--text-3` | usado em 10 a 11 px | só a partir de 12 px | 5,46:1 em `--surface-1`, 4,88:1 em `--surface-3` |
| Botão de perigo | fundo vermelho cheio em "Esquecer" e "Apagar conta" na listagem | texto `--danger` sem fundo; vermelho cheio só no diálogo de confirmação | vermelho cheio numa linha de lista grita mais que a ação principal |
| Aliases legados | `--coffee-*`, `--browser-*` | sair de `tokens.css` quando nenhuma tela usar | restos da demonstração |

---

## 5. Peças que se repetem

### 5.1 Barra lateral

Antes: `antes-01-sora-vazia-1440.png`, `antes-09b-barra-lateral-com-pedido-1440.png`. Depois: qualquer foto `depois-0*-1440.png`.

> **Mudanças do dono do produto (2026-11-14), valem acima do texto abaixo:**
> 1. **"Precisa de você" sai da barra lateral.** No lugar entra **"Criar novo"** (ícone "+", mesma linha de menu de 40 px, sem borda), que abre um menu (`Popover`, `role="menu"`; setas, Enter e Esc) com três opções: **Nova conversa com a Sora** (vai para `/` e foca o campo), **Novo bot** (vai para `/` com o campo preenchido "Quero um bot que ", via `deixarPedidoInicial`) e **Novo grupo** (abre o Novo grupo, o mesmo do "+" de GRUPOS). A central "Precisa de você" continua existindo e fica acessível pelo indicador na linha de cada bot e grupo com pedido e pelo comando **"Precisa de você (N)"** da paleta Ctrl+K. O título "(N) Sora" da aba e o aviso do sistema não mudam.
> 2. **A marca no topo mostra só o mascote e o nome "Sora".** Sem subtítulo ("Chefe de equipe" saiu) e sem outro texto. O estado só aparece quando a Sora está trabalhando ou precisa de você: um **ponto de 8 px ao lado do nome** (pulsando quando trabalha; sólido e claro quando espera por você), com `title` e texto para leitor de tela dentro de `role="status"`. Parada, não aparece nada. "Chefe de equipe" continua só onde explica o papel dela num grupo (membros do grupo, Novo grupo).
> 3. No celular, o menu ☰ tem a mesma marca e o mesmo item "Criar novo".
> 4. O e-mail sai do rodapé; "Livre" não aparece em bot nem em grupo (decisões do §11).

Problemas confirmados:
- "Precisa de você" e "Buscar" usam a mesma classe (`shell-search`): caixa de 235×38 com borda e texto de 16 px. Os dois parecem campos de texto; com pedido pendente a borda fica mais clara e a impressão piora.
- "Buscar" é o elemento mais forte da barra numa conta que ainda não tem o que buscar.
- Nome do bot em 13 px cinza e estado em 10,5 px. "Livre" repetido em toda linha não informa nada.
- Cerca de 75% da altura fica vazia e, mesmo assim, o topo tem 68 px de marca mais 34 px de respiro.

Depois (de cima para baixo, padding 8 px):

| Peça | Medida | Estados |
|---|---|---|
| **Sora** (link para `/`) | linha de 48 px, raio 10; orb 28; "Sora" 15/600; **sem segunda linha** | Parada: só orb e nome. Trabalhando ou aguardando você: ponto de 8 px ao lado do nome (`role="status"` com o texto "Coordenando 2 bots", "Aguardando você" etc. para leitor de tela). Selecionada: fundo `--ativo`. |
| **Criar novo** (no lugar de "Precisa de você") | linha de 40 px, **sem borda e sem fundo**; ícone "+" 18; texto 14 `--text-2` | Hover e menu aberto: `--text-1` e fundo `--hover`. Abre o menu de três opções (nota acima). |
| **Buscar** | mesma linha de 40 px; ícone 18; "Ctrl K" à direita em 12 px `--text-3`, sem caixinha | Hover: `--text-1` e fundo `--hover`. |
| Rótulo **BOTS** / **GRUPOS** | 32 px, 16 px acima; 12/600 caixa alta `--text-3`; contador ou "+" (28×28) à direita | |
| Linha de **bot** | 40 px, raio 10; orb 24; nome 14/400 `--text-1`, uma linha com reticências | À direita: nada quando livre; ponto de 8 px na cor do bot pulsando (1,4 s) quando trabalha, com `title` e texto para leitor de tela; contador branco quando precisa de você. O orb também passa a `working`. Selecionada: `--ativo`. |
| Linha de **grupo** | igual; ícone de grupo 18 em `--text-2` no lugar do orb | Contador branco quando precisa de você. |
| **Conta** | 52 px, borda em cima; avatar 28; nome 13/500; engrenagem 36×36 | O e-mail sai da barra; fica em Configurações → Conta. |

### 5.2 Cabeçalho da tela

Antes: `antes-01-sora-vazia-1440.png` ("Sora" na barra lateral e "Sora · ● Sora" no topo, lado a lado), `antes-12-bots-galeria-1440.png` ("Bots" no topo e "Seus bots" logo abaixo), `antes-11-config-01-modelos-de-ia-1440.png` ("Configurações" duas vezes).

| Tela | Esquerda | Direita |
|---|---|---|
| Sora (`/`) | **vazio no desktop**; a identidade já está na barra lateral | menu "…" (36×36) |
| Bot | orb 28 + nome 15/600 + estado na mesma linha em 13 px ("· Pesquisando" na cor do bot; "· Precisa de você" em `--text-2`; nada quando disponível) | botão do painel Trabalho (`aria-pressed`) + menu "…" |
| Grupo | nome 15/600 + "· Sora + 2 bots" em 13 px `--text-2` | pilha de orbs (24 px, sobrepostos 4 px) que abre os membros + menu "…" |
| Bots, Grupos, Configurações | título 15/600 | uma ação principal, quando houver ("Criar com a Sora", "Novo grupo") |

O texto de estado nunca repete o nome. Hoje a Sora ociosa mostra "● Sora".

### 5.3 Compositor

Antes: `antes-01-sora-vazia-1440.png` (56 px de altura, 1.140 px de largura, colado no rodapé), `antes-03a-bot-vazio-1440.png` (pílula "Conversar por voz" solta em cima), `antes-03a-bot-vazio-390.png` (placeholder cortado em "Mensagem para Bot de").

Um componente só para Sora, bot e grupo:

- Fundo `--surface-3`, borda 1 px `--line` (hover e foco: `--line-strong`), raio 24, sombra `0 12px 40px rgba(0,0,0,.28)`.
- **Compacto** (rodapé): uma linha, altura mínima 54 px, padding 8. Ordem: **"+" Anexar** (36×36, hoje escondido no compacto) · texto · ações à direita.
- **Grande** (estado vazio da Sora, só desktop): texto em cima (mínimo de 54 px), linha de ações embaixo, altura mínima 120 px.
- Texto 16/24, placeholder `--text-2`. Cresce até 200 px e depois rola por dentro.
- Ações à direita, todas 36×36 redondas (44×44 no celular): **@** (só no grupo) · **microfone** e **conversar por voz** (só no bot, como já decidido) · **Enviar**.
- Enviar: fundo `--action`, seta `--text-inverse`; hover `#fff`; ao pressionar `scale(.94)`. Desativado conforme §4.3. Gerando: vira **Parar** (quadrado cheio), mesmo fundo claro.
- "Conversar por voz" deixa de ser uma pílula acima do campo e vira um ícone dentro dele. No celular isso tira uma das três faixas empilhadas no rodapé.
- No celular o placeholder é curto ("Mensagem…") quando o nome não cabe; o `aria-label` continua completo ("Mensagem para Bot de pesquisa…").
- No grupo o placeholder é "Mensagem para o grupo…". A dica "(@ para chamar um bot)" sai do placeholder e vira o botão **@**.

### 5.4 Mensagens

Antes: `antes-02-sora-conversa-1440.png`, `antes-03c-bot-markdown-topo-1440.png`, `antes-03d-bot-fontes-imagem-menu-1440.png`, `e2e-etapa5-bot-fontes-imagem-menu.png` (em `app/qa/shots/`).

**Pergunta do usuário**
- Hoje: bolha encostada na borda direita da janela (x = 1.424 de 1.440), a 1.100 px do começo da resposta; 13 px de texto no celular.
- Depois: alinhada à direita **da coluna**, largura do conteúdo, no máximo 78% da coluna (86% no celular). Fundo `--surface-3`, sem borda, raio `20 20 6 20`, padding 10/16, texto 16/24. Menção (`@todos`) em `--link`, peso 500.
- Ações (Copiar, Editar pergunta) à **esquerda da bolha**, na mesma linha, só no hover ou no foco. Não ocupam altura.

**Resposta do bot**
- Hoje: orb de 30 px numa coluna à esquerda e texto recuado, com 1.106 px de largura na Sora.
- Depois: cabeçalho de uma linha (orb 24 + nome 13/600 na cor do bot; Sora em `--text-1`) e o texto **sem recuo**, com a largura da coluna. No grupo, "entregou" vem depois do nome em 12 px `--text-3`.
- Markdown: 16/26; `h2` 20/28 com 24 px acima; lista com recuo de 22 px e 6 px entre itens; marcador em `--text-3`.
- **Tabela:** largura do conteúdo (não estica), borda `--line`, raio 12, cabeçalho 13/600 `--text-2` sem caixa alta, células 14/20 com padding 10/14, linhas separadas por `--line-soft`. Rola na horizontal dentro da moldura.
- **Código:** fundo `--surface-2`, borda `--line`, raio 12; barra de 36 px com a linguagem em 12 px e "Copiar" (28 px, sem borda); código 13/20.
- **Marca de fonte no texto:** `[1]` vira uma pílula de 18 px (fundo `--line`, número 12/600 `--text-2`), que leva ao chip correspondente. Hoje é um link azul sublinhado com colchetes.

**Fontes**
- Hoje: cartões de 2 linhas acima do resto da resposta, título em **negrito de 16 px** ("[1] Guia de cafés especiais"), raio 12 e padding 10. Três fontes ocupam duas linhas e pesam mais que a resposta.
- Depois: uma linha **abaixo do texto**. Rótulo "Fontes" (12/600 `--text-3`) e chips de 28 px: círculo de 20 px com o número e o **domínio** em 13 px `--text-2`. Fundo `--line-soft`; hover `--line` e `--text-1`. O título da página vai no `title` e na dica. Largura máxima de 220 px com reticências. No celular, 36 px de altura.

**Imagem na resposta**
- Hoje: imagem dentro de uma caixa com borda, e embaixo "Baixar grafico.png" em 16 px.
- Depois: sem caixa. Imagem com raio 12, no máximo 420 px de altura, cursor de ampliar. "Baixar" é um botão de ícone (36×36, fundo `rgba(5,6,8,.72)`) no canto superior direito, visível no hover, no foco e sempre no toque. Embaixo, legenda em 12 px `--text-3`: "imagem.png · 18 KB".

**Ações da mensagem**
- Hoje: botões de 32 px com ícone de **15 px**, invisíveis até o hover, inclusive na última resposta.
- Depois: botões de 32×32 (raio 10) com ícone de **18 px**, cor `--text-3`; hover `--text-1` com fundo `--hover`. Aparecem no hover e no foco, e ficam **sempre visíveis na última resposta**. No celular: 44×44, sempre visíveis na última; nas anteriores, pelo botão "…".

**"Resposta interrompida"**
- Hoje: `MensagemChat.tsx:110` desenha o aviso dentro do bloco da **pergunta**, alinhado à direita, em amarelo, a 4 px da bolha. Parece que a pergunta deu erro.
- Depois: pertence à resposta. Fica à esquerda, 10 px abaixo do texto parcial: quadradinho de 8 px, "Resposta interrompida" em 13 px `--text-2` e o link **Refazer resposta**. Se a resposta parou antes do primeiro caractere, o aviso ocupa o lugar da resposta (com o cabeçalho do autor), a 28 px da pergunta. Sem amarelo: parar foi escolha do usuário, não é erro.

**"Ir para o fim"**
- Hoje: pílula com texto, por cima da resposta (`antes-03c-bot-markdown-topo-1440.png`).
- Depois: botão redondo de 36 px, centralizado 12 px acima do compositor, fundo `--surface-3`, borda `--line-strong`, só a seta. Com mensagens novas, ponto de 8 px em `--action`. `aria-label="Ir para o fim"`.

### 5.5 Botões

Altura 40 px (32 no pequeno, 44 no celular), raio 999, texto 14/600.

| Variante | Visual | Uso |
|---|---|---|
| Principal | fundo `--action`, texto `--text-inverse`; hover `#fff` | uma por bloco |
| Secundário | borda `--line-strong`; hover fundo `--hover` | alternativa |
| Fantasma | texto `--text-2`; hover `--text-1` com fundo `--hover` | cancelar, descartar |
| Perigo | texto `--danger`; hover fundo `rgba(255,107,107,.1)` | recusar, esquecer |

Desativado: fundo `rgba(255,255,255,.14)`, texto `#B6BDCB`, e um texto de 13 px ao lado dizendo o que falta ("Escolha pelo menos 2 bots"). Hoje "Criar rotina" e "Criar grupo" desativados são pílulas cinza de largura total, sem explicação.

### 5.6 Estados vazios

Um padrão só (hoje há orbs de 150, 110 e 96 px, com e sem moldura tracejada): orb 96 px, título 20/28, texto 14/22 `--text-2` com no máximo 420 px, **um** botão principal. Centralizado, sem caixa.

---

## 6. Telas: antes e depois

Caminhos relativos a `app/qa/shots/design/`.

### 6.1 Sora vazia

| | |
|---|---|
| Antes | `antes-01-sora-vazia-1440.png`, `antes-01b-sora-vazia-digitando-1440.png`, `antes-01-sora-vazia-390.png` |
| Depois | `depois-01-sora-vazia-1440.png`, `depois-01b-sora-vazia-foco-1440.png`, `depois-06a-celular-sora-vazia-390.png` |

Problemas confirmados: o título fica no centro e o campo no rodapé, a 270 px um do outro; o campo, que é a ação principal, é o elemento mais fraco da tela. O aviso "Nenhuma API de IA conectada ainda" aparece entre o texto e as sugestões, com cara de sugestão. No celular o orb tem cerca de 300 px e é cortado pelo cabeçalho.

Depois (desktop):
- Um bloco centralizado na horizontal. O compositor fica um pouco abaixo do meio da área (linhas da grade `1.1fr · compositor · 1fr`).
- De cima para baixo: orb **120 px** (estado `arriving` na primeira abertura, depois `idle`) → 20 px → título "Converse com a Sora" 32/40 → 8 px → frase em 16/24 `--text-2`, uma linha → 28 px → **compositor grande** (760 px) → 12 px → aviso de API em 13 px, centralizado, com o link em `--text-1` sublinhado → 20 px → sugestões.
- Sugestões: chips de 36 px, 13 px, borda `--line`, texto `--text-2`; hover `--text-1` e borda `--line-strong`. No máximo duas linhas. Clicar só preenche o campo e dá foco.
- Digitando: o mascote passa a `listening` (olha para o campo) e o BorderBeam corre (§7.5).
- Sem cabeçalho à esquerda.

### 6.2 Conversa com a Sora

| | |
|---|---|
| Antes | `antes-02-sora-conversa-1440.png`, `antes-02b-sora-pensando-1440.png`, `antes-02-sora-conversa-390.png` |
| Depois | `depois-01d-depois-do-envio-1440.png`, `depois-02-conversa-1440.png`, `depois-02b-conversa-fim-1440.png`, `depois-02c-conversa-hover-1440.png` |

Aplicam-se §5.3 e §5.4. Cartões da Sora (rascunho de bot, proposta de grupo, "Precisa de você") entram na mesma coluna, alinhados à esquerda, com no máximo 560 px.

### 6.3 Bot: fontes, imagem e menu

| | |
|---|---|
| Antes | `antes-03a-bot-vazio-1440.png`, `antes-03c-bot-markdown-topo-1440.png`, `antes-03d-bot-fontes-imagem-menu-1440.png`, `antes-03d-bot-fontes-imagem-menu-390.png`, `antes-04c-bot-menu-1440.png` |
| Depois | `depois-02-conversa-1440.png`, `depois-02b-conversa-fim-1440.png` (mesmas peças), `depois-06b-celular-bot-390.png` |

- Estado vazio do bot: padrão de §5.6 com o orb na cor do bot, "Converse com Bot de pesquisa" e a função em uma linha. A frase "acompanhe os passos no painel Trabalho" sai.
- Menu "…": itens de 36 px, 14 px, raio 12 no menu, sombra `--shadow-md`. "Editar agente" passa a "Editar bot".

### 6.4 Bot: painel Trabalho

| | |
|---|---|
| Antes | `antes-04a-bot-painel-trabalho-1440.png`, `antes-04b-bot-painel-recursos-1440.png`, `antes-08a-bot-cartao-precisa-1440.png` (aba Recursos rolada), `antes-04a-bot-painel-trabalho-390.png` |
| Depois | `depois-03-bot-trabalho-1440.png`, `depois-03b-bot-recursos-1440.png` |

Problemas confirmados: o painel é um cartão flutuante com raio e margem, o que cria uma segunda moldura dentro da tela. Abaixo das abas ele repete orb, nome e estado, que já estão no cabeçalho. A aba Recursos abre com um orb de 150 px e o nome em 24 px (terceira repetição), "Progresso 0%" com o bot parado, ferramentas como quadrados azuis com uma letra ilegível, e um formulário de pendência com `select` nativo e botão cinza de largura total.

Depois:
- Painel de 360 px, de cima a baixo, fundo `--surface-side`, `border-left` `--line`. Abre e fecha pelo botão do cabeçalho; a largura anima em 320 ms com `--ease`. Aberto por padrão a partir de 1.280 px; a escolha fica lembrada.
- Cabeçalho do painel de 52 px: abas de texto **Trabalho · Recursos** (14/600; a ativa em `--text-1` com sublinhado de 2 px; a outra em `--text-2`) e o "×".
- **Trabalho** é uma linha do tempo. Cada passo: marca de 20 px (✓ em `--ok` quando termina; ponto de 8 px na cor do bot pulsando quando roda; × em `--danger` no erro), título 14/500, duração em 12 px `--text-3` à direita, segunda linha em 13 px com o id da ferramenta numa etiqueta mono de 12 px e um resumo ("5 resultados"). "Ver detalhes" abre parâmetros e resultado em mono 12/18, fundo `--surface-2`, raio 10; links clicáveis em `--link`. Linha vertical de 1 px `--line` liga as marcas. O passo em curso tem o título com Shimmer.
- Trabalho vazio: uma frase de 13 px `--text-2` no topo ("Bot de pesquisa está disponível. Os passos aparecem aqui quando o trabalho começar."), sem orb e sem repetir a identidade.
- **Recursos:** seções com rótulo de 12 px e 24 px entre elas. *Função* (texto + "Editar bot"), *Ferramentas* (linhas de 40 px: ícone de traço 18 px em `--text-2`, nome 14, estado à direita em 12 px), *Navegador*, *Rotinas*, *Memória*, *Pendências*. O formulário de pendência só abre ao clicar em "+ Nova pendência". "Progresso" só aparece enquanto o bot trabalha.
- No chat, enquanto o bot trabalha: linha "pensando" (§7.3) e o compositor com **Parar**.

### 6.5 Grupo

| | |
|---|---|
| Antes | `antes-05b-grupo-sem-mensagens-1440.png`, `antes-05d-grupo-mensagens-2-1440.png`, `antes-05c-grupo-mensagens-390.png`, `antes-05g-grupos-lista-390.png`, `antes-05h-grupo-mencao-390.png`, `antes-05a-grupos-vazio-1440.png` |
| Depois | `depois-04-grupo-1440.png`, `depois-04b-grupo-membros-1440.png`, `depois-06c-celular-grupo-390.png` |

Problemas confirmados:
- **Duas listas de grupos lado a lado** no desktop: a da barra lateral e uma coluna de 280 px dentro da tela. "Grupos" aparece três vezes e o nome do grupo, três.
- Membros como cartões de 164×54 numa faixa de 79 px. "Parar" tem 12 px, alvo de 42×17 e `opacity: .45` (2,11:1): quase invisível.
- A bolha do usuário é **branca** no grupo e escura no 1:1.
- Resposta de bot dentro de caixa com borda esverdeada, limitada a 82% da largura; "Responder" fixo embaixo de toda mensagem.
- No celular: os membros são cortados na horizontal ("Bot de pesq"), há dois cabeçalhos empilhados (Grupos + Novo grupo e depois o nome do grupo) e o placeholder é cortado ("Mensagem para o grupo… (@ para").

Depois:
- `/grupos/:id` mostra **só a conversa**. A coluna interna de grupos sai; a lista vive na barra lateral. `/grupos` (sem id) é a página da lista: linhas de 64 px (nome 15/600, "Sora + 2 bots" em 13 px, pilha de orbs à direita, estado) e "Novo grupo" como ação principal no cabeçalho.
- Cabeçalho: nome do grupo + "· Sora + 2 bots" · pilha de orbs (Sora primeiro; quem trabalha fica em `working`) · menu "…". "Novo grupo" não aparece dentro de um grupo.
- **Membros:** clicar na pilha abre um painel flutuante de 320 px (raio 16, `--surface-2`, borda `--line-strong`): linhas de 48 px com orb 28, nome na cor do bot, estado em 12 px e, **só para quem está trabalhando**, o botão secundário pequeno **■ Parar** (ou **Retomar** para quem foi parado). No rodapé, "Adicionar bots".
- **Faixa de trabalho:** enquanto algum bot trabalha, uma pílula de 40 px abaixo do cabeçalho, na coluna: ponto pulsando na cor do bot, nome, "trabalhando · último passo" e **■ Parar** à direita. Some quando ninguém trabalha. É assim que "Parar" fica visível na hora em que importa.
- Mensagens: as mesmas de §5.4 (bolha escura à direita, resposta sem caixa, markdown). "Em resposta a …" é uma linha citada: borda esquerda de 2 px `--line-strong`, 13 px `--text-2`, uma linha com reticências. **Responder** vira ação de hover, ao lado de Copiar.
- Bot escrevendo: linha "pensando" com o orb do bot e "Bot de textos está escrevendo…" em Shimmer.
- Compositor de §5.3 com o botão **@**. A lista de menções abre acima do campo: linhas de 44 px (orb 24 + nome), `@todos` primeiro, navegação com ↑ ↓ Enter Esc.
- Estado vazio do grupo: "Converse com o grupo. Use @bot para direcionar ou @todos para chamar a equipe inteira." centralizado na coluna, 14 px `--text-2`.

### 6.6 Novo grupo

| | |
|---|---|
| Antes | `antes-06-novo-grupo-1440.png`, `antes-06-novo-grupo-390.png` |

Já está perto. Ajustes:
- Largura 520 px, raio 20. Um título só: "Novo grupo" (20/28), com a descrição "Reúna de 2 a 5 bots. A Sora sempre participa como chefe de equipe." O sobretítulo "NOVO GRUPO" sai.
- A Sora deixa de ser um cartão igual aos bots (parece clicável): vira uma linha de texto com orb 24, "Sora · Chefe de equipe · sempre participa", em `--text-2`.
- Linhas de bot de 56 px, sem borda individual, separadas por `--line-soft`: orb 28, nome 15/600, função em 13 px **com uma linha e reticências** (hoje quebra em quatro linhas no celular), marcação redonda de 24 px à direita. Marcada: fundo `--hover` e ✓ em `--action`. "Livre" sai; só aparece estado quando o bot está trabalhando.
- "Escolha de 2 a 5 bots" com o contador "2/5" na mesma linha.
- Rodapé: **Cancelar** (fantasma) e **Criar grupo** (principal). Desativado conforme §5.5, com "Escolha pelo menos 2 bots" ao lado.
- Celular: folha de baixo com altura total, rodapé fixo, botões de 44 px lado a lado.

### 6.7 Cartão de rascunho de bot

| | |
|---|---|
| Antes | `antes-07-rascunho-bot-1440.png`, `antes-07b-rascunho-bot-inteiro-1440.png`, `antes-07-rascunho-bot-390.png`, `antes-07c-bot-criado-1440.png` |

Problemas confirmados: cantos retos e borda azul, diferente de todos os outros cartões; 620 px de largura fora de qualquer eixo; **"Descartar" e "Criar bot" são duas pílulas cinza idênticas**, sem ação principal; depois de criar sobram três textos soltos no fim da conversa ("Bot criado", o nome e "Abrir conversa com…").

Depois:
- Cartão na coluna, no máximo 560 px, `--surface-2`, borda `--line`, raio 16, padding 16.
- Cabeçalho: orb 40 na cor escolhida (prévia ao vivo do movimento), "Rascunho de bot" em 12 px `--text-3` e o nome em 20/28. A frase "Confira as seções abaixo. O bot só nasce quando você confirmar." em 13 px `--text-2`.
- Seções como linhas de 48 px separadas por `--line-soft`: título 14/600, resumo à direita em 13 px `--text-2` e seta. Só Identidade abre de início. Abrir e fechar: altura em 200 ms.
- Campos de 40 px, raio 10, fundo `--surface-1`, borda `--line`; foco conforme §4.3.
- Cor: amostras de 28 px com 8 px entre elas (alvo de 44 no celular); a escolhida ganha anel de 2 px `--text-1` afastado 2 px. Movimento: chips de 32 px; o escolhido com fundo `--ativo` e texto `--text-1` (hoje é azul, cor que pertence a um agente).
- Rodapé: **Descartar** (fantasma) e **Criar bot** (principal, claro).
- Depois de criar, o cartão encolhe (240 ms) para uma linha: ✓ em `--ok`, "Bot criado", o nome na cor do bot e o link "Abrir conversa".

### 6.8 Cartão e central "Precisa de você"

| | |
|---|---|
| Antes | `antes-08b-sora-cartao-pergunta-1440.png`, `antes-09-central-precisa-1440.png`, `antes-09a-central-vazia-1440.png`, `antes-09-central-precisa-390.png`, `antes-13b-menu-com-pedido-390.png` |
| Depois | `depois-05b-cartao-na-conversa-1440.png`, `depois-05-central-precisa-1440.png`, `depois-06d-celular-precisa-390.png` |

Problemas confirmados: o item da barra lateral parece campo de texto (§5.1). O cartão na conversa ocupa a largura inteira (cerca de 1.150 px) para uma pergunta de uma linha. Na central, "Precisa de você" aparece no título do modal e de novo dentro de cada cartão; cada pedido é uma caixa dentro da caixa; "Abrir a conversa com a Sora" fica solto embaixo, em tamanho de rodapé.

**Cartão na conversa**
- No máximo 560 px, `--surface-2`, borda `--line`, raio 16, padding 16; faixa de 3 px à esquerda **na cor de quem pede** (Sora: `--sora`).
- Cabeça: ponto de 8 px em `--action`, "Precisa de você" em 12/600 `--text-2`, hora à direita em 12 px `--text-3`.
- Título 15/600 ("Aprovar ação", "Responder pergunta"), texto 15/22, detalhe em 13 px `--text-2`.
- Botões de 40 px: **Permitir uma vez** (principal) · **Sempre permitir** (secundário, quando o servidor aceita) · **Recusar** (perigo, só texto). Pergunta com opções: a primeira é a principal, as outras secundárias. Resposta livre: campo de 40 px e "Enviar".
- Enviando: botões desativados e o orb de quem pediu em `thinking`. Resolvido: o cartão encolhe para uma linha ("✓ Permitido uma vez") em 240 ms.

**Central**
- Modal de 560 px, raio 20, a 11% do topo. Título "Precisa de você" 20/28 e "2 pedidos esperam uma decisão sua." em 13 px.
- Cada pedido é uma **faixa** separada por `--line`, não uma caixa: linha de origem (orb 24, nome na cor do bot, "· agora", e à direita "Abrir a conversa com o bot ›" em 13 px), depois título, texto e os mesmos botões do cartão. O rótulo "Precisa de você" não se repete dentro.
- Vazia: orb 56 em `idle`, "Nada espera por você agora." e a explicação em 13 px.
- Resolver um pedido: a faixa sai (altura e opacidade, 200 ms) e o contador da barra lateral desce no mesmo instante.
- Celular: folha de baixo com no máximo 82% da altura. O botão principal ocupa a linha; os outros dividem a seguinte; todos com 44 px.

### 6.9 Paleta Ctrl+K

| | |
|---|---|
| Antes | `antes-10-paleta-1440.png` |

Problemas: 640 px de largura a 108 px do topo; o bloco "ATALHOS" toma um terço da paleta com sete atalhos em duas linhas.

Depois:
- 600 px de largura, a 18% do topo, raio 16, `--surface-2`, borda `--line-strong`, sombra `--shadow-lg`.
- Campo de 52 px: lupa 18, texto 16, "Esc" à direita em 12 px. Sem borda própria; só a divisória embaixo.
- Grupos ("Ações", "Bots", "Grupos", "Mensagens") com rótulo de 12 px. Linhas de 40 px (44 no celular), raio 10: ícone ou orb 20, texto 14, atalho à direita em 12 px `--text-3`. Selecionada: fundo `--ativo`, sem a barra azul à esquerda.
- Rodapé de 36 px com três dicas: "↑↓ Navegar · Enter Abrir · Esc Fechar". A lista completa de atalhos sai da paleta e vira a ação "Ver atalhos".
- Celular: tela cheia, campo no topo com foco automático, botão de fechar de 44 px.

### 6.10 Configurações

| | |
|---|---|
| Antes | `antes-11-config-01-modelos-de-ia-1440.png` até `antes-11-config-09-conta-1440.png` e as mesmas em `-390.png` |

Problemas confirmados: "Configurações" no cabeçalho e de novo como título da navegação, encostado na divisória da coluna; uma pilha de cartões de provedor de 86 px (só sete cabem na primeira dobra), todos "Não conectado", empurrando a escolha do modelo padrão para fora da tela; formulários com `select` nativo, campos de larguras diferentes e botão cinza de largura total; "Esquecer" e "Apagar conta" em vermelho cheio; no celular a faixa de abas corta em "Habil", sem indicar que rola.

Depois (vale para as nove seções):
- Cabeçalho da tela: "Configurações". A navegação interna (200 px, linhas de 36 px, raio 10, ativa em `--ativo`) **não tem título** e começa alinhada ao título da seção.
- Conteúdo com no máximo 720 px: título 24/32, descrição 14/22 `--text-2` com no máximo 600 px, 24 px até o primeiro bloco.
- **Modelos de IA:** os provedores viram **uma lista** com borda única e raio 16, linhas de 64 px separadas por `--line-soft`: ícone 36, nome 15/600, descrição em 13 px, e à direita **Conectar** (secundário pequeno) ou "● Conectado" em `--ok` com a seta. Conectados primeiro. "Modelo padrão" sobe para antes da lista assim que houver um provedor conectado.
- **Formulários** (Memória, Rotinas, Habilidades, Conectores, Navegador): no máximo 560 px, rótulo 13/600, campos de 40 px com raio 10, `select` com o mesmo desenho dos campos, botão principal com a largura do texto e alinhado à direita, desativado conforme §5.5. Nota de vazio em 13 px `--text-2`.
- **Listas** (lembranças, rotinas, perfis): linhas de 56 px separadas por `--line-soft`, ação de perigo como texto (§4.3).
- **Ilha:** as cinco caixas viram uma lista de linhas de 56 px com a chave à direita. "Ligadas / Ligada / Ligados" ao lado da chave sai; o estado vai no `aria-checked`.
- **Conta:** "Uso do mês" como primeiro bloco; "Apagar todos os dados" e "Apagar conta" numa seção "Zona de perigo", como botões de perigo em texto com confirmação.
- **Celular:** a faixa de abas ganha máscara de degradê de 24 px nas bordas quando há mais para rolar, `scroll-snap`, e a aba ativa rola para dentro da vista ao abrir. Abas de 44 px.

### 6.11 Galeria de bots

| | |
|---|---|
| Antes | `antes-12-bots-galeria-1440.png`, `antes-12a-bots-vazio-1440.png`, `antes-12-bots-galeria-390.png` |

Problemas: "Bots" no cabeçalho e "Seus bots" logo abaixo; cartões de 254×304 com orb grande e dois botões cada ("Conversar", "Editar"); no celular, duas colunas com os cartões e textos cortados na borda direita.

Depois:
- Cabeçalho "Bots" com **Criar com a Sora** à direita. A frase "Bots persistentes criados em conversa com a Sora." em 14 px `--text-2` no topo do conteúdo; "Seus bots" sai.
- Grade `repeat(auto-fill, minmax(280px, 1fr))` com 16 px de espaço, no máximo 1.040 px.
- Cartão de 96 px, horizontal, `--surface-2`, borda `--line`, raio 16, padding 16: orb 48, nome 15/600, função em 13 px `--text-2` (duas linhas no máximo), estado em 12 px na cor do bot quando não está livre. **O cartão inteiro abre a conversa.** Menu "…" de 32 px no canto (Editar bot, Renomear, Apagar). Hover: borda `--line-strong` e o orb passa a `listening`.
- Celular: uma coluna, cartões de 80 px.
- Vazio: padrão de §5.6 com "Criar meu primeiro bot". Neste caso o botão do cabeçalho some, para não haver dois CTAs.

---

## 7. Microinterações

Todas com `--ease` e desligadas em `prefers-reduced-motion: reduce` (ficam só as trocas de estado).

### 7.1 Compositor central que desce depois do 1º envio

Veja ao vivo na aba "Sora vazia" do protótipo; quadros em `depois-01c-compositor-descendo-1440.png` e `depois-01d-depois-do-envio-1440.png`.

1. **0 ms** (Enter ou clique): o texto do campo some; título, frase, aviso e sugestões saem com `opacity 1 → 0` em 120 ms.
2. **0 a 420 ms:** o compositor vai do centro ao rodapé pela técnica FLIP: mede a posição antes, troca o layout, mede depois e anima `transform: translate(dx, dy)` e a altura (120 → 54 px) em `--dur-layout`. Não anime `top` nem `margin`.
3. **0 a 320 ms:** o orb grande encolhe (`scale 1 → .23`), some (`opacity → 0`) e o orb da barra lateral dá o pulso de "entendeu" (`pulseKey`).
4. **80 ms:** a bolha do usuário entra (§7.4).
5. **240 ms:** entra a linha "pensando" (§7.3).

O foco continua no campo. A partir daí o compositor é o mesmo componente, no modo compacto. Ao limpar a conversa, o caminho inverso roda em 320 ms. No celular não há descida: o compositor já está embaixo, por causa do teclado.

### 7.2 Ações da mensagem

- Aparecem com `opacity 0 → 1` em 120 ms no `:hover` e no `:focus-within` da mensagem; somem em 120 ms.
- O espaço delas (32 px + 8 px) é reservado desde o início na resposta: nada pula. Na pergunta, ficam ao lado da bolha.
- A **última resposta** mostra sempre.
- Teclado: Tab entra na barra (`role="toolbar"`), ← → andam entre as ações.
- Copiar: o ícone vira ✓ em `--ok` por 1,2 s, além do aviso "Copiado".
- Boa resposta e Resposta ruim: `aria-pressed`; a escolhida fica em `--text-1` com fundo `--ativo`.

### 7.3 "Pensando" com o thinking orb

- Linha na coluna, a 28 px da pergunta: `SoraThinking` de **28 px** na cor de quem responde e o texto em 14 px com **Shimmer** ("Sora está pensando…", "Pesquisando na web…", "Bot de textos está escrevendo…"). `role="status"`.
- Nenhum spinner, nenhum trio de pontos pulando.
- Quando chega o primeiro pedaço de texto, o orb **não troca de lugar**: encolhe de 28 para 24 px (160 ms) e vira o orb do cabeçalho do autor; o Shimmer dá lugar ao nome.
- Enquanto o texto chega: cursor em bloco de 7×16 px piscando a 1 s no fim, e o orb do cabeçalho em `thinking`. No fim, orb em `idle` e as ações aparecem.
- Na barra lateral e no cabeçalho, o orb do bot fica em `working` e o estado ao lado do nome mostra o verbo.

### 7.4 Entrada das mensagens

| Peça | Animação |
|---|---|
| Bolha do usuário | `opacity 0 → 1` e `translateY(8px → 0)`, 200 ms |
| Cabeçalho da resposta | `opacity 0 → 1`, 160 ms |
| Texto em streaming | sem animação por letra; render no máximo uma vez por quadro |
| Cartões (rascunho, proposta, Precisa de você) | `opacity 0 → 1`, `translateY(12px → 0)` e `scale(.98 → 1)`, 240 ms |
| Chips de fonte e imagem | `opacity 0 → 1`, 160 ms, quando a resposta termina |
| Mensagens antigas ("Carregar anteriores") e recarga da página | nenhuma |

A rolagem só acompanha quando o usuário já está no fim (comportamento atual de `useRolagemFim`).

### 7.5 BorderBeam no foco do compositor

- **Sem foco:** borda `--line`.
- **Foco:** borda `--line-strong` e o beam aparece em 320 ms, com intensidade 0,45, uma volta a cada 3,2 s. Cores de `--beam`.
- **Digitando ou falando** (última tecla há menos de 1,2 s, ou microfone ativo): intensidade 0,7, como hoje. Voltando ao repouso, cai para 0,45 em 320 ms.
- **Perdeu o foco:** some em 320 ms.
- **Processando:** continua o VoiceBeam que já existe.
- Movimento reduzido: sem beam; no foco, a borda vira 1,5 px sólido em `--focus`.

Hoje o beam só aparece enquanto o usuário digita, então clicar no campo não dá retorno nenhum. No app o efeito continua vindo da biblioteca `border-beam` (prop `active` ligada ao foco e `strength` variando); o CSS do protótipo é só uma aproximação.

### 7.6 Outras

- Linhas da barra lateral e botões: fundo e cor em 120 ms.
- Painel Trabalho: largura `0 ↔ 360px` em 320 ms; a coluna de leitura acompanha.
- Membros do grupo, menus e paleta: `opacity` e `translateY(8px → 0)` em 200 ms; saem em 120 ms.
- Modal: véu em 200 ms; caixa com `translateY(8px → 0)` em 320 ms.
- Faixa de trabalho do grupo: altura `0 ↔ 40px` em 200 ms.
- Contador "Precisa de você": quando aumenta, `scale(1 → 1.25 → 1)` em 320 ms, uma vez.

---

## 8. Celular (390 px)

Fotos do depois: `depois-06a` a `depois-06d`. Ponto de quebra: 720 px, como hoje.

- **Cabeçalho** de 52 px mais a área segura: ☰ (44×44) à esquerda, identidade no centro (orb 22 + nome 15/600), ações de 44×44 à direita. No grupo: ‹ voltar · nome · pilha de orbs · "…". **Um cabeçalho só**; hoje o grupo tem dois.
- **Sora vazia:** orb de **96 px** inteiro, título 24/30 e frase 14/22 centralizados no espaço livre. Embaixo: três sugestões em lista (linhas de 44 px separadas por `--line-soft`), o aviso de API e o compositor compacto.
- **Conversa:** respiro lateral de 16 px, bolha com até 86% da largura e 16 px de texto. Tabela e código rolam por dentro, nunca a página.
- **Bot:** a pílula flutuante "Trabalho · Recursos · Disponível" sai de cima do campo e vira o botão do painel no cabeçalho (com um ponto na cor do bot enquanto ele trabalha). O painel abre como folha de baixo, com as mesmas abas. "Conversar por voz" entra no compositor. O rodapé passa de três faixas para uma.
- **Grupo:** `/grupos` é só a lista e `/grupos/:id` é só a conversa. Os membros saem da faixa horizontal cortada e vão para a pilha do cabeçalho, que abre uma folha com a lista e os botões Parar e Retomar de 44 px. A faixa de trabalho continua, com "■ Parar".
- **Compositor:** placeholder curto; botões de 44 px; `font-size` de 16 px para o iOS não dar zoom.
- **Menu ☰:** folha com a mesma navegação de §5.1, linhas de 48 px. Hoje a folha repete os dois "campos" com borda.
- **Central Precisa de você:** folha de baixo (§6.8).
- **Galeria de bots:** uma coluna.
- **Configurações:** faixa de abas com degradê nas bordas (§6.10).
- Nada rola na horizontal no nível da página.

---

## 9. Acessibilidade

**Contraste** (calculado; mínimo de 4,5:1 para texto e 3:1 para foco e bordas de controle):

| Par | Razão |
|---|---|
| `--text-1` em `--surface-1` / `-2` / `-3` | 18,56 / 17,30 / 16,57 |
| `--text-2` em `--surface-1` / `-2` / `-3` | 6,56 / 6,12 / 5,86 |
| `--text-3` em `--surface-1` / `-2` / `-3` | 5,46 / 5,09 / 4,88 |
| `#6B7280` (o "apagado" de §4.1) em `--surface-1` | **4,19: não usar em texto** |
| `--atlas` / `--luna` / `--nina` em `--surface-1` | 8,15 / 7,03 / 12,90 |
| `--link`, `--ok`, `--warn`, `--danger` em `--surface-1` | 11,35 / 14,85 / 12,01 / 7,30 |
| `--text-inverse` em `--action` | 17,32 |
| Enviar desativado: `#B6BDCB` em `rgba(255,255,255,.14)` sobre `--surface-3` | 6,32 (hoje 2,44) |
| "Parar" do grupo hoje (`opacity: .45`) | 2,11: reprovado |
| Foco `--focus` em `--surface-1` / `--surface-3` | 11,35 / 10,13 (o anel suave de hoje dá 2,55) |

Cor nova de bot escolhida na paleta precisa dar pelo menos 4,5:1 sobre `--surface-1`, porque o nome do bot é escrito nela.

**Foco visível**
- `outline: 2px solid var(--focus); outline-offset: 2px` em tudo que recebe foco por teclado (`:focus-visible`).
- Compositor: o foco é a borda `--line-strong` mais o beam; em movimento reduzido, borda de 1,5 px em `--focus`.
- Ordem de tabulação: barra lateral → cabeçalho → conversa → compositor → painel.
- Modal, folha e paleta prendem o foco e o devolvem a quem abriu.

**Alvos**
- Toque: **44×44 px** no mínimo (botões do cabeçalho, do compositor, ações da mensagem, linhas de lista, "Parar").
- Mouse: visual de 32 px ou mais, e nunca menos de 24×24 (WCAG 2.5.8). O "+" de 28 px em "GRUPOS" ganha área de 44 px no celular.
- Chips de fonte: 28 px no desktop, 36 px no celular com 8 px entre eles.

**Leitor de tela e semântica**
- Estado não depende só de cor: o ponto pulsando tem texto ("Trabalhando"), o contador tem `aria-label` ("Precisa de você, 2 pedidos").
- `role="status"` no estado da Sora, na linha "pensando", na faixa de trabalho e em "Resposta interrompida".
- A conversa mantém `aria-live="polite"`; o texto em streaming não é anunciado letra a letra, só a mensagem pronta.
- Cartão "Precisa de você": `section` com `aria-label`, botões num `role="group"`. Central: `role="dialog"` com `aria-modal`.
- Pilha de orbs do grupo: `aria-label` com os nomes ("Membros do grupo: Sora, Bot de pesquisa e Bot de textos") e `aria-expanded`.
- Texto mínimo de 12 px; a interface aguenta zoom de 200% sem rolagem horizontal.
- `prefers-reduced-motion`: sem deslocamento, sem beam, sem Shimmer (o texto fica em `--text-2`). O mascote continua "respirando": é o indicador de estado, com amplitude baixa.

---

## 10. Tarefas de implementação

Ordem sugerida. Cada tarefa fecha com `npm run build`, `npx oxlint`, `npm test` e as fotos indicadas em 1440×900 e 390×844. As fotos do "antes" e do "depois" estão em `app/qa/shots/design/`; para o "pronto", repita o roteiro com o prefixo `pronto-`.

**0. Roteiro de fotos**
- Arquivos: novo `app/qa/design.mjs`, apoiado em `qa/entrar.mjs` e na interceptação de `qa/conversa-fontes.mjs` (fontes e imagem na resposta).
- Conta própria (`qa-design@sora.local`), para não apagar dados de outro agente. Sequência: Sora vazia → paleta → central vazia → `/bots` e `/grupos` vazios → dois rascunhos ("Bot de pesquisa", "Bot de textos") → conversa da Sora → bot com markdown, fontes e imagem → painel Trabalho e Recursos → `[aprovacao]` e `[pergunta]` → central → galeria → Novo grupo → grupo com `@todos` → as nove seções de Configurações.
- Pronto: `node qa/design.mjs` gera as 71 fotos `pronto-*.png` sem erro de página.

**1. Tokens e tipografia**
- Arquivos: `app/src/styles/tokens.css`, `app/src/index.css`.
- Fazer: tokens de §4.2; foco de §4.3; `--fs-15`; pesos só 400/500/600/700.
- Pronto: nenhuma regra em `app/src/**/*.css` com `font-size` abaixo de 12 px nem com `font-weight` 450, 580, 640 ou 650 (busca por texto); foco por teclado mostra contorno de 2 px em qualquer botão (`pronto-foco-1440.png`).

**2. Barra lateral**
- Arquivos: `components/layout/Sidebar.tsx`, `components/layout/etapa5.css`, `components/layout/useSoraStatus.ts`.
- Fazer: §5.1. "Precisa de você" e "Buscar" deixam de usar `shell-search`; estado da Sora na linha da marca; bots em uma linha com indicador à direita.
- Pronto: em `pronto-01-sora-vazia-1440.png` nenhum item da barra tem borda; com um pedido aberto (`pronto-09b`), "Precisa de você" mostra o contador branco e continua sem borda; a barra mede 260 px.

**3. Cabeçalho sem repetição**
- Arquivos: `components/layout/AppShell.tsx`, `components/ui/sora.css` (`.topbar*`), `screens/Agentes.tsx`, `screens/Configuracoes.tsx`.
- Fazer: §5.2; altura de 52 px; sem identidade da Sora no desktop em `/`; estado na mesma linha do nome.
- Pronto: em `pronto-01`, o texto "Sora" aparece uma vez fora do título; em `pronto-12-bots-galeria` não existe "Seus bots"; em `pronto-11-config-01`, "Configurações" aparece uma vez.

**4. Coluna de leitura**
- Arquivos: `screens/SoraChat.tsx`, `screens/AgentChat.tsx`, `components/ui/sora.css` (`.conversation*`, `.chat-composer`).
- Fazer: envolver mensagens, cartões e compositor em `max-width: calc(var(--col) + 48px)` centralizado.
- Pronto: em `pronto-02-sora-conversa-1440.png`, a borda esquerda da resposta e a do compositor têm o mesmo x, a borda direita da bolha coincide com a direita do compositor e a largura do texto é de 760 px (medido por `getBoundingClientRect`).

**5. Compositor único**
- Arquivos: `components/ui/MessageComposer.tsx`, `components/ui/sora.css` (`.composer*`), `components/ui/ConversaVoz.tsx`, `components/grupos/CompositorGrupo.tsx`.
- Fazer: §5.3. "+" visível no compacto; texto de 16 px; Enviar desativado novo; voz dentro do campo; botão @ no grupo; placeholder curto no celular.
- Pronto: `pronto-03a-bot-vazio-390.png` mostra o placeholder inteiro e uma faixa só no rodapé; não existe pílula "Conversar por voz" fora do campo; os testes de `ui/__tests__/digitacao.test.tsx` seguem verdes.

**6. Estado vazio da Sora com compositor central**
- Arquivos: `screens/SoraChat.tsx`, `components/inicio/InicioSora.tsx`, `components/inicio/inicio.css`, `components/layout/etapa5.css` (`.sora-chat-empty`).
- Fazer: §6.1 e a descida de §7.1 (FLIP com `Element.animate`).
- Pronto: em `pronto-01-sora-vazia-1440.png`, o centro vertical do compositor fica entre 45% e 60% da altura e o orb mede 120 px; em `-390`, o orb aparece inteiro e mede 96 px; um vídeo ou três quadros (`pronto-01c-*`) mostram o compositor entre o centro e o rodapé depois do Enter.

**7. Mensagens**
- Arquivos: `components/ui/MensagemChat.tsx`, `components/ui/mensagens.css`, `components/ui/markdown.css`, `components/ui/Markdown.tsx`.
- Fazer: §5.4 (bolha, resposta sem recuo, tabela, código, ações de 18 px, última resposta sempre com ações).
- Pronto: `pronto-03c-bot-markdown-topo-1440.png` mostra a bolha com no máximo 78% da coluna, a tabela sem esticar e o texto sem coluna de avatar; em `pronto-03d`, os ícones de ação medem 18 px e aparecem sem hover na última resposta; no celular a bolha usa 16 px.

**8. "Resposta interrompida" no lugar certo**
- Arquivos: `components/ui/MensagemChat.tsx` (linhas 110 e 127), `components/ui/mensagens.css`, `state/projetos.ts` (`textoVisivel`, de onde vem `vis.interrompida`).
- Fazer: §5.4.
- Pronto: com o modelo falso, enviar e parar. Em `pronto-08-interrompida-1440.png` o aviso está à esquerda, a pelo menos 24 px da bolha, em `--text-2`, com "Refazer resposta"; nenhum `.chat-msg.is-user` contém `.msg-interrompida` (teste de componente).

**9. Fontes e imagem**
- Arquivos: `components/ui/FontesMensagem.tsx`, `components/ui/fontes.ts`, `components/ui/AnexosResposta.tsx`, `components/ui/ImagemAnexo.tsx`, `components/ui/mensagens.css`, `components/ui/markdownSeguro.ts` (marca `[n]`).
- Fazer: §5.4. O `id` do chip e o `href` da marca continuam os mesmos (o E2E depende deles).
- Pronto: em `pronto-03d`, os chips ficam abaixo do texto, com 28 px de altura, peso 400 e o domínio visível; três fontes cabem numa linha; a imagem não tem moldura e "Baixar" é um botão de ícone; `qa/e2e.mjs` segue verde (ajustar a asserção do texto do chip, que hoje espera `[1]` + título + domínio).

**10. "Pensando", entrada e "Ir para o fim"**
- Arquivos: `screens/SoraChat.tsx`, `screens/AgentChat.tsx`, `components/mascot/SoraThinking.tsx` (só o tamanho de uso), `components/ui/ShimmerText.tsx`, `components/ui/IrParaFim.tsx`, `components/ui/mensagens.css`.
- Fazer: §7.3, §7.4 e "Ir para o fim" de §5.4.
- Pronto: `pronto-02b-sora-pensando-1440.png` mostra o orb de 28 px com texto em Shimmer na coluna; não existe elemento com `spinner` nem `loader` no DOM; "Ir para o fim" é um círculo de 36 px que não cobre texto.

**11. BorderBeam no foco**
- Arquivos: `components/ui/MessageComposer.tsx`, `components/ui/sora.css`.
- Fazer: §7.5 (`active` no foco; `strength` 0,45 em repouso e 0,7 digitando).
- Pronto: `pronto-01b-sora-vazia-foco-1440.png`, tirada com o campo **vazio e focado**, já mostra o beam; com `reducedMotion: 'reduce'` no Playwright, a borda fica sólida em `--focus`.

**12. Painel Trabalho**
- Arquivos: `components/layout/PainelLateral.tsx`, `components/work/{PainelTrabalho,LinhaDoTempo,ChamadaFerramenta,GavetaTrabalho}.tsx`, `components/work/work.css`, `screens/AgentChat.tsx`.
- Fazer: §6.4.
- Pronto: em `pronto-04a-bot-painel-trabalho-1440.png`, o painel encosta no topo, no rodapé e na borda direita, sem raio; o nome do bot aparece uma vez na tela (cabeçalho); em `pronto-04b`, não há orb grande nem "Progresso 0%"; no celular não existe a pílula "Trabalho · Recursos" sobre a conversa.

**13. Grupo**
- Arquivos: `screens/Grupos.tsx`, `components/grupos/{MembrosGrupo,MensagemGrupo,CompositorGrupo,TarefasGrupo}.tsx`, `components/grupos/grupos.css`.
- Fazer: §6.5. Tirar `aside.grp-lista` de `/grupos/:id`; membros na pilha; faixa de trabalho; mensagens com `MensagemChat`.
- Pronto: em `pronto-05c-grupo-mensagens-1440.png`, o nome do grupo aparece duas vezes no máximo (barra lateral e cabeçalho) e não há segunda lista; a bolha do usuário é escura; nenhuma resposta tem borda; com um bot trabalhando, "Parar" tem pelo menos 32 px de altura e contraste de 4,5:1; em `-390`, nenhum elemento passa de `clientWidth` e há um cabeçalho só.

**14. Novo grupo**
- Arquivos: `components/grupos/{NovoGrupo,SeletorDeBots,GerirGrupo}.tsx`, `components/grupos/grupos.css`.
- Fazer: §6.6.
- Pronto: em `pronto-06-novo-grupo-390.png`, a função de cada bot ocupa uma linha; a Sora não parece selecionável; com menos de 2 bots marcados aparece "Escolha pelo menos 2 bots".

**15. Cartão de rascunho**
- Arquivos: `components/builder/CartaoRascunhoBot.tsx`, `components/builder/builder.css`.
- Fazer: §6.7. O corpo enviado ao backend não muda.
- Pronto: em `pronto-07-rascunho-bot-1440.png`, o cartão tem raio 16, no máximo 560 px, e "Criar bot" é o único botão claro; em `pronto-07c`, o cartão criado virou uma linha.

**16. Cartão e central "Precisa de você"**
- Arquivos: `components/pendencias/{CartaoPrecisaDeVoce,CentralPrecisaDeVoce,CartaoPropostaGrupo,decisao}.tsx`, `components/pendencias/pendencias.css`, `components/ilha/**` (só consumir).
- Fazer: §6.8.
- Pronto: em `pronto-08b-sora-cartao-pergunta-1440.png`, o cartão tem no máximo 560 px e a faixa na cor de quem pede; em `pronto-09-central-precisa-1440.png`, o texto "Precisa de você" aparece uma vez dentro do modal e os pedidos são faixas sem caixa interna; em `-390`, a central é uma folha e os botões têm 44 px.

**17. Paleta Ctrl+K**
- Arquivos: `components/comandos/PaletaComandos.tsx`, `components/comandos/comandos.css`.
- Fazer: §6.9.
- Pronto: `pronto-10-paleta-1440.png` mostra o rodapé de uma linha (sem o bloco "ATALHOS"); em `-390`, a paleta ocupa a tela.

**18. Configurações**
- Arquivos: `screens/Configuracoes.tsx`, `components/settings/{ProviderCard,ModelDefaults,SecoesPecas}.tsx`, `components/settings/{settings,pecas}.css`.
- Fazer: §6.10.
- Pronto: em `pronto-11-config-01-modelos-de-ia-1440.png`, a lista inteira de provedores cabe em 900 px de altura (hoje só sete aparecem); nenhum formulário tem `select` com desenho nativo; não há botão vermelho cheio nas listas; em `-390`, a faixa de abas mostra o degradê e a aba ativa está inteira.

**19. Galeria de bots e estados vazios**
- Arquivos: `screens/Agentes.tsx`, `screens/Grupos.tsx` (vazio), `screens/AgentChat.tsx` (vazio), CSS correspondente.
- Fazer: §6.11 e §5.6.
- Pronto: em `pronto-12-bots-galeria-390.png`, os cartões estão em uma coluna, sem corte; cada cartão tem um alvo só (o cartão) e o menu "…"; os três estados vazios usam orb de 96 px e um botão.

**20. Fechamento**
- Arquivos: `app/tests/visual/telas.spec.ts` e imagens de referência; `app/qa/contraste.mjs`.
- Fazer: regenerar as imagens do `test:visual`; rodar o contraste.
- Pronto: `npm run test:visual` verde; `node qa/contraste.mjs` sem par abaixo de 4,5:1; `node qa/e2e.mjs` e `node qa/ilha.mjs` verdes; as 71 fotos `pronto-*` conferidas lado a lado com `depois-*`.

Dependências: 1 antes de tudo; 4 antes de 5, 6, 7 e 13; 7 antes de 8, 9 e 13. As tarefas 2, 3, 12, 14, 15, 16, 17, 18 e 19 são independentes entre si.

---

## 11. Para o Heitor decidir

1. **Título do estado vazio.** O app diz "Converse com a Sora"; o `CLAUDE.md` §4.2 diz "Em que posso te ajudar hoje?". Mantive o texto do app no protótipo. A frase de §4.2 é mais convidativa e dispensa a linha de apoio; se preferir, é só trocar o texto.
2. **E-mail na barra lateral.** A proposta tira o e-mail do rodapé (fica em Configurações → Conta). Se a equipe usa mais de uma conta, vale manter.
3. **"Livre" na barra lateral.** A proposta mostra estado só quando o bot trabalha ou precisa de você. Se "Livre" for considerado informação, volta como segunda linha de 12 px.

**Decidido (Heitor, 2026-11-14):** proposta aprovada. (1) Título do estado vazio: **"Em que posso te ajudar hoje?"**, sem a linha de apoio. (2) E-mail sai do rodapé da barra lateral (fica em Configurações → Conta). (3) "Livre" some da barra lateral; estado só quando o bot trabalha ou precisa de você.
