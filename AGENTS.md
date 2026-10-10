# Sora — leia isto primeiro

> Este arquivo é lido pelo Codex no início de cada sessão. Antes de mexer em qualquer coisa:
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

Ainda **não existe o app**. Até agora existem só os vídeos de apresentação, que definem o visual e o comportamento esperado:

| Arquivo | O que é |
|---|---|
| `mini-video/mini.html` | Comercial de 30 s (canvas) → `sora-comercial-30s.mp4` |
| `mini-video/sora-demo.html` | Demo de 75 s mostrando a interface completa → `sora-demo-75s.mp4` |
| `mini-video/plugins.js` | Ícones dos plugins (Simple Icons, CC0) |
| `mini-video/voice-level.js` | Níveis da fala usados no efeito VoiceBeam |
| `mini-video/assets/` | Logos de plugins e imagens da campanha de exemplo |

Cada HTML expõe `renderFrame(t)` determinístico (render feito com Playwright + ffmpeg). **O `sora-demo.html` é a referência visual principal**: cores, textos, telas e estados dos agentes vêm de lá.

Stack do app: **a definir** — registre a decisão no log quando for tomada.

---

## 2. Logs da equipe

Cada integrante tem um bloco. O bloco diz **o que a pessoa já fez**, **onde parou** e **qual é o próximo passo**. O histórico fica abaixo, da entrada mais recente para a mais antiga.

### Como registrar (regra para o Codex)

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
- **Onde parou:** vídeos de apresentação da Sora prontos (comercial 30 s e demo 75 s). Este `AGENTS.md` criado para começar o app.
- **Próximo passo:** definir a stack e começar pela tela inicial com o mascote.

**Histórico**
- **2026-10-10** — Criou o `AGENTS.md` com introdução, logs, mascote, interface e funções. Arquivos: `AGENTS.md`.
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
| **Chegando** (primeira abertura) | pontos espalhados se juntam e formam o corpo; os olhos abrem | tela vazia, só a Sora no centro |
| **Ocioso** | "respira" e gira devagar, pisca | tela inicial: "Em que posso te ajudar hoje?" |
| **Ouvindo** (usuário digitando ou falando) | a superfície ondula, os olhos olham para o campo de texto | BorderBeam correndo na borda do campo; no celular, VoiceBeam reagindo à voz |
| **Entendeu / enviou** | pulso de luz | a Sora encolhe e vai para a barra lateral como avatar; abre o chat |
| **Planejando** | pulso curto a cada agente criado | aparece o card "Plano" e os agentes surgem um por um no painel "Equipe" |
| **Coordenando** | gira devagar na barra lateral | status "Coordenando N agentes"; cada agente mostra o próprio status |
| **Agente concluiu** | pulso curto | check verde no agente, cards de entrega aparecem |
| **Pronto** | calma, olhos abertos | botão "Revisar" + aviso "Nada é publicado sem a sua aprovação." |

Regras:
- A Sora **nunca some**: se não está no centro, está como avatar na barra lateral ou no topo do celular.
- O **movimento** do mascote é o indicador de carregamento. Evite spinners genéricos onde o mascote puder mostrar o estado.
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

**Barra lateral (sempre visível no desktop)**
- Logo "Sora", botões **Novo chat** e **Plugins**.
- Seção **CHATS**: a Sora (agente principal) e cada agente da equipe, com avatar animado, nome e status colorido ("Pesquisando", "Aguardando referências", "Concluído").
- Rodapé: conta/empresa do usuário e plano (ex.: "Cafeteria Aroma · Plano Pro").

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

## 6. Regras de trabalho para o Codex

- Escreva em **PT-BR** (código pode ter nomes em português, como nos HTMLs atuais).
- **Leia os logs antes** de propor qualquer coisa e **atualize o log ao terminar**.
- Não altere a aparência do mascote nem as cores dos agentes sem pedido explícito.
- Ao criar telas novas, reaproveite os tokens e textos da seção 4; em caso de dúvida, consulte `mini-video/sora-demo.html`.
- Não apague os vídeos nem os HTMLs de referência.
