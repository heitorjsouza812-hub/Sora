# Sora — leia isto primeiro

> Este arquivo é lido pelo Codex no início (cópia do CLAUDE.md) de cada sessão. Antes de mexer em qualquer coisa:
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

O **front-end do app existe** em `app/` (feito em 2026-10-10 — veja **§7 Estado do app** para rodar, estrutura, decisões e pendências). Ainda **não há back-end**: tudo é simulado no navegador. Os vídeos de apresentação continuam como referência visual:

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
- **Onde parou:** front-end da Sora pronto em `app/` (todas as telas, mascote, fluxo simulado de equipes, construtor de agentes, painel Trabalho, Configurações de modelos). Tudo roda só no navegador, com dados simulados.
- **Próximo passo:** decidir o back-end (chamadas reais aos modelos, contas, salvar as chaves com segurança) e voltar aos **Plugins** (congelados de propósito). Ver pendências em §7.5.

**Histórico**
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
- Ao mudar algo de produto, atualize a **§7** e copie o `CLAUDE.md` para o `AGENTS.md` (o Codex lê o `AGENTS.md`).

---

## 7. Estado do app (front-end)

### 7.1 Como rodar

```bash
cd app
npm install
npm run dev          # http://localhost:5173
npm run build        # checagem de tipos + build
npx oxlint           # lint
```

Tudo é **simulado no navegador** (sem back-end). Os dados ficam no `localStorage` (`sora.projetos.v1`, `sora.modelos.v1`). Para começar do zero: Configurações → Conta → **Apagar todos os dados**.

### 7.2 Estrutura (`app/src`)

| Pasta / arquivo | O que tem |
|---|---|
| `components/mascot/` | **Mascote**: `SoraOrb` (canvas de pontos, porte fiel da demo), `SoraThinking`, `orbEngine.ts`. Estados: `arriving · idle · listening · thinking · coordinating · working · done`. |
| `state/projetos.ts` | **Store principal** (projetos, conversas, agentes, execuções, passos do painel Trabalho). O relógio é a fonte da verdade: status e % são calculados a partir do horário, então sobrevivem a recarregar a página. |
| `state/modelos.ts` | Provedores de IA, chaves (mascaradas) e modelo padrão da Sora/de cada agente. |
| `data/planejador.ts` | **Planejador simulado**: lê o pedido e escolhe um modelo de equipe (campanha, site, pesquisa, e-mails, vídeo ou genérico), com nomes, cores, movimentos, ferramentas e o roteiro de passos. |
| `screens/` | `Home` (1º prompt), `SoraChat` (chat do projeto), `AgentChat`, `Projetos`, `Agentes` (galeria), `CriarAgente` (construtor), `Revisao`, `Configuracoes`, `Plugins`, `Mobile` (/celular), `OrbLab` (/lab/orb). |
| `components/work/` | Painel **Trabalho** (prompt, chamadas de ferramenta, handoffs). |
| `components/builder/` | Construtor de agente (abas Criar/Configurar + prévia com chat de teste). |
| `components/settings/` | Cartões de provedores e modelo padrão. |
| `components/projetos/`, `gestao/` | Tela Projetos; diálogos Renomear/Apagar. |
| `components/review/`, `overlay/` | Tela de revisão; Modal, BottomSheet, Popover e menus acessíveis. |
| `components/layout/`, `ui/` | AppShell, barra lateral, composer (BorderBeam + VoiceBeam), cards, peças de campanha. |
| `components/studio/` | Editor de agente antigo, ainda usado no Modal "Editar agente". O construtor novo fica em `builder/`. |

Rotas: `/` · `/projeto/:id` · `/chat/:agenteId` · `/projetos` · `/agentes` · `/agentes/novo` · `/agentes/:id/editar` · `/revisao/:id` · `/configuracoes` · `/plugins` · `/celular` · `/lab/orb` (laboratório do mascote; `?solo=240&state=thinking&color=%23AC80FF` mostra um orb isolado).

### 7.3 Decisões de produto tomadas (2026-10-10)

1. **Início:** barra lateral vazia + Sora grande na tela do 1º prompt.
2. **A Sora cria os agentes a partir do pedido.** Se o pedido não exige trabalho ("oi, tudo bem?"), ela só responde. Os agentes aparecem em **CHATS**, embaixo da conversa onde nasceram.
3. **Projetos** (barra lateral): tela para escrever o prompt de um projeto; a Sora monta a equipe inteira. Os projetos ficam listados com filtro e busca.
4. **Agentes** (barra lateral): galeria + **construtor no estilo GPT builder** (aba *Criar*, conversando com a Sora; aba *Configurar*, formulário; à direita, a prévia com chat de teste). O usuário troca **nome, cor, movimento, função, instruções, ferramentas e modelo**. Agente novo recebe uma cor livre da paleta, e nunca `#E2ECFF`, que é da Sora.
5. **Painel Trabalho:** enquanto um agente trabalha, mostra ao vivo o **prompt** recebido, as **chamadas de ferramenta** (ex.: `figma.criar_frame`, com parâmetros e resultado) e as entregas passadas a outro agente.
6. **Apagar/renomear** chats, projetos e agentes, com confirmação. A Sora não pode ser apagada.
7. **Configurações → Modelos de IA:** conectar OpenAI, Anthropic, Gemini, xAI, DeepSeek, Mistral, OpenRouter, Ollama e qualquer API compatível com OpenAI; escolher o modelo padrão da Sora e dos agentes.
8. **Revisão:** "Revisar" abre as entregas; o usuário escolhe *Aprovar e publicar* ou *Pedir ajuste* (gera nova versão, com comparação).
9. **Plugins: congelados de propósito.** A tela existe, mas não mexer até o grupo decidir.

### 7.4 Ferramentas de QA (`app/qa/`)

- `node qa/shoot.mjs [rotas] [--wait ms]` → screenshots em 1440 e 390 px em `qa/shots/` + erros do console.
- `node qa/shoot.mjs --flow` → digita um pedido e fotografa o fluxo a cada 3 s.
- `node qa/e2e.mjs` → teste de ponta a ponta dos fluxos principais (criado pelo validador).
- `qa/ref/` → quadros da demo para comparar (gerados a partir do vídeo; não versionados).

### 7.5 Pendências / próximos passos

- **Back-end:** hoje o "Testar conexão" só confere o formato da chave e as respostas dos agentes são simuladas. Falta um servidor que chame os modelos de verdade e guarde as chaves com criptografia (**nunca** guardar chaves só no navegador em produção).
- **Plugins** reais (congelados).
- Testar o microfone (VoiceBeam com `useMicrophone`) num celular de verdade, via https.
- Contas/login e sincronização entre computador e celular.

### 7.6 Como o app foi feito (time de IA no Maestri)

O front-end foi construído em 2026-10-10 por um time de agentes no Maestri, coordenado por um Claude Code orquestrador, em rodadas: construir → validar com screenshots → corrigir, em loop.

| Agente | Modelo | Fez |
|---|---|---|
| Prisma | Claude Code (Opus) | mascote, thinking orb, store, planejador, integração geral |
| Forja | Codex (GPT-5.6) | telas da rodada 1–2, overlays, revisão, Configurações, construtor de agente |
| Brisa | Claude Code | tela Projetos, diálogos Renomear/Apagar |
| Vigia | Hermes (OpenAI) | validação: ferramentas de QA, auditoria de código/acessibilidade, testes E2E |

Os papéis ficam salvos no Maestri (workspace "Sora"); o histórico está nos commits do git (`git log`). O Hermes deve usar **só modelos da OpenAI**. Use raciocínio *medium* no Codex para não estourar a cota.
