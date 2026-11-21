# OpenBot × Sora: o que eles têm e a Sora ainda não tem

> Análise de 2026-11-20 (Heitor, com Claude Code). Versão olhada: OpenBot **0.75.0** (commit
> `740efbb`, 2026-11-20). Fontes: `README.md`, `CHANGELOG.md` (versões 0.67 a 0.75 lidas em
> detalhe), `docs/glossary.md` e `docs/architecture/*.md` do repositório deles. Nada foi instalado
> nem testado: o que está aqui é o que a documentação deles diz que existe. Do lado da Sora, cada
> linha foi conferida no código da `main` (`72234e9`).
>
> **Licença:** o OpenBot é PolyForm Noncommercial. Vale a mesma regra de [openbot.md](openbot.md):
> só ideias e comportamento; nenhum código, prompt ou texto deles entra na Sora.

## 1. Antes de comparar: os dois produtos têm desenhos diferentes

| | OpenBot | Sora |
|---|---|---|
| Onde roda | App de desktop local (Electron); servidor opcional (Linux, Docker ou servidor hospedado pago) | Serviço na nuvem (API + worker) com app web, desktop (Tauri) e celular pelo navegador |
| Modelos | CLIs de assinatura (Codex, Claude Code, Grok, Gemini, Cursor, Copilot, Mistral, Hermes…) por ACP, e endpoints compatíveis com a OpenAI | Chaves de API do usuário pelo LiteLLM/LangChain (Groq, OpenAI, OpenRouter, Ollama, compatível…) |
| Segurança | Agentes com acesso total depois do consentimento inicial; eles mesmos dizem que isso não é barreira de segurança | Revisor com Perguntar/Automático/Total, bloqueios absolutos, sandbox e computador virtual isolados |
| Público | Pessoa técnica ou time pequeno, interface em 15 idiomas | Usuário leigo brasileiro, PT-BR, sem termo técnico |
| Ritmo | Versão nova quase todo dia | Etapas |

Por isso, parte do que o OpenBot tem **não deve** vir para a Sora (seção 5). O resto está na
lista completa por área (seção 3), com a recomendação de ordem na seção 2.

## 2. Recomendação: o que trazer primeiro

Esforço: **P** (até 2 dias), **M** (até 1 semana), **G** (mais de 1 semana). São estimativas, não
compromissos.

### Onda 1: base de produção (antes de abrir para clientes)

> **Feita em 2026-11-20**, na `main` (`d7dc113`, `log/2026-11-20.md`). Diferenças do que
> está abaixo: a recuperação de senha é por **link** (como a especificação §8.2 já previa), não
> por código; os modelos reserva valem para a **conta inteira** (por bot fica para depois); a
> atualização do desktop está pronta, mas **desligada** até o time gerar a chave de assinatura.

| # | O quê | Por quê | Esforço |
|---|---|---|---|
| 1 | **Recuperar senha ou entrar com código por e-mail** | A Sora não tem "esqueci minha senha" e não envia e-mail. O OpenBot entra só com código de uso único por e-mail. Sem isso, cada senha perdida vira suporte manual. | M |
| 2 | **Exportar meus dados** (LGPD, portabilidade) | A Sora já apaga a conta inteira, mas não exporta nada. O OpenBot exporta os dados e um diagnóstico pelo menu da conta. | M |
| 3 | **Várias chaves por provedor + modelos reserva escolhidos por bot** | O 429 da Groq trava o QA e vai travar o usuário. O OpenBot junta contas do mesmo provedor ("pool") e cada agente tem modelos reserva à vista. Combina com a decisão de 2026-11-16 (sem troca silenciosa): a lista é do usuário e a troca aparece na conversa. | M |
| 4 | **Atualização automática do app de desktop** | O OpenBot procura versão nova e oferece baixar e reiniciar. O Tauri tem plugin de atualização; a Sora ainda não usa. Depende do instalador assinado (já pendente). | M |
| 5 | **"Relatar problema" com diagnóstico sem dado pessoal** | O OpenBot gera um pacote de diagnóstico sem conteúdo privado e deixa corrigir ou retirar o relato depois. A Sora tem Sentry no servidor, mas o usuário não tem por onde avisar. | P |

### Onda 2: valor rápido para o usuário

> **Feita em 2026-11-20** (na `main`; `log/2026-11-20.md`). Diferenças do que está abaixo:
> senha segura **sem cofre** (a senha não é guardada; o login fica nos cookies do perfil do bot);
> biblioteca sem o bot organizar as pastas e sem visualizador além da prévia; agenda só com o mês
> (sem semana e sem criar rotina clicando num dia).


| # | O quê | Por quê | Esforço |
|---|---|---|---|
| 6 | **Rotina disparada por webhook** | Outro serviço (formulário, loja, pagamento) chama uma URL assinada e a rotina roda com os dados recebidos. Como a Sora já é um servidor na nuvem, isso é mais natural para nós do que para eles (eles precisam do computador ligado). Assinatura no padrão Standard Webhooks, filtro por tipo de evento, deduplicação e histórico. | M |
| 7 | **Notificação no celular para "Precisa de você"** | O OpenBot tem app de iPhone com Live Activity e notificações. O caminho barato da Sora é PWA + Web Push (PWA já está "a decidir"). Aprovação parada esperando alguém olhar o computador é o maior atraso do produto. | M |
| 8 | **Senha digitada com segurança no navegador do bot** | Hoje o bot nunca digita senha e o usuário precisa Assumir a aba. No OpenBot o agente pede, aparece um cartão, a pessoa digita a senha ali e ela vai direto para o campo da página, sem passar pelo modelo nem ficar no histórico; dá para guardar num cofre e escolher quais agentes usam cada login. Mantém a nossa regra (o modelo nunca vê a senha) e tira um passo do usuário. | M/G |
| 9 | **Mandar mensagem para o turno que está rodando** | No OpenBot, no modo "steer", a mensagem nova entra no turno atual ("não, use o logo azul") em vez de esperar. Na Sora ela espera na fila (que já pode ser editada e pausada). | M |
| 10 | **Biblioteca de arquivos** | Tudo o que os bots entregam, em pastas, com favoritos, "Recentes" e visualizador; o próprio bot organiza as pastas. Na Sora os arquivos ficam presos em cada conversa. Casa com as "Entregas" da especificação. | M |
| 11 | **Agenda das rotinas** | Ver as execuções em calendário (semana e mês), criar rotina clicando num dia e assinar um feed `.ics` no Google Agenda. A Sora tem só a lista em Configurações → Rotinas. | P/M |

### Onda 3: diferencial (precisa de decisão do grupo)

| # | O quê | Por quê | Esforço |
|---|---|---|---|
| 12 | **Catálogo de apps com login pelo navegador** | O OpenBot tem um Marketplace com 254 apps (conectores MCP com OAuth, por exemplo HubSpot, Canva, Notion, Stripe), 40 habilidades prontas e agentes prontos; também instala habilidade a partir de um link do GitHub. A Sora promete "mais de 1.000 plugins", mas hoje só aceita servidor MCP por URL + cabeçalho, e os Plugins estão escondidos (decisão 3). Sugestão: começar com 10 a 15 apps que o público brasileiro usa, escolhidos pelo grupo, com login OAuth. | G |
| 13 | **Fluxo entre rotinas, depois Workflows** | Eles têm um canvas de etapas (agente, modelo, condição sim/não, aprovação, imagem, vídeo, saída), com laços, gatilho por horário ou webhook, até 50 versões salvas e "rodar a partir desta etapa". Um passo menor vem antes: o resultado da rotina de um bot segue para outro bot. Para a Sora, o canvas só vale se for simples para leigo; o fluxo entre rotinas cabe dentro de Grupos. | M (fluxo) / G (canvas) |
| 14 | **Ensinar uma tarefa** | O usuário clica em "Ensinar", faz a tarefa no navegador e a gravação vira habilidade. Há também "aprender com a minha navegação", desligado por padrão. A Sora já tem o formato de playbook (vindo do Rakazo); falta a gravação. | M/G |
| 15 | **Aprender com correções** | O OpenBot revisa a conversa sozinho a cada N turnos (10, 20 ou 40) e transforma correção ("faça assim da próxima vez") em memória ou habilidade; segundo eles, gasta bem menos tokens do que o agente salvando na hora. Habilidades têm versões, revisão que confere a versão lida e botão "Atualizar". Na Sora o bot guarda com `lembrar` e `criar_habilidade` quando decide; o prompt `memoria_sintese.v1.md` existe, mas não achei revisão automática ligada. | M |
| 16 | **Compartilhar bot por link e importar/exportar** | Link público do bot (nome, instruções, avatar, rotinas e habilidades, sem arquivos nem memória) com imagem para redes sociais; exportar e importar em `.zip`; importar agentes de outro produto. Ajuda no crescimento ("olha o bot que eu fiz"). | M |
| 17 | **Geração de vídeo** | Etapas de imagem e vídeo com Higgsfield, Sunra, GPT Image e Grok Imagine; preço em créditos antes de rodar; fundo transparente; vídeo com som e referências. A Sora gera imagem pelo provedor do usuário, mas não vídeo. O Higgsfield já aparece entre os plugins da demo da Sora. | M |
| 18 | **Equipe: membros, papéis e acesso por bot** | Servidor com dono, admin e membro, papéis próprios que dizem quais agentes cada membro usa, convites e passar o servidor para outra conta. A Sora é uma conta por pessoa (o convite serve só para o cadastro), embora o modelo de dados já fale em "empresa" e "plano". | G |

### Ajustes pequenos (P, cabem a qualquer momento)

- **Fixar mensagem** no chat de um bot ou grupo.
- **Silenciar** um bot (sem notificação) e **esconder** um bot da barra lateral sem parar as rotinas dele.
- Barra lateral com **filtro** (só bots, só grupos, só não lidas), grupo **"Não lidas"** e ordem por atividade recente.
- **Reduzir movimento**: chave em Configurações para desligar desfoque e animações de fundo. O mascote é o indicador de carregamento, então o modo reduzido deixa a Sora visível, só mais calma.
- **Cartão "isso já é uma configuração"**: quando o usuário pede algo que uma configuração faz, o bot mostra o atalho em vez de improvisar.
- **Apagar vários bots** com um cartão de aprovação só.
- **Responder pela Ilha**: hoje a Ilha mostra quem trabalha e aprova; no OpenBot a doca de agentes também deixa responder sem abrir a janela.
- **Voz**: apertar e segurar para falar, e escolher quanto tempo de pausa encerra a fala.
- **Anexos maiores e de mais tipos**: o OpenBot aceita MP3, MOV, MP4, ZIP, SVG e qualquer arquivo até 100 MB (250 MB por mensagem). A Sora para em 20 MB por arquivo.
- **Página de status** pública (eles hospedam fora da própria nuvem para ela continuar no ar quando a nuvem cai).
- **Regras de comunicação no prompt** (texto nosso): não narrar preparação, tentar todos os caminhos antes de dizer que não consegue, delegar a um colega pelo perfil dele.
- Bolha do usuário na **cor do bot** no chat 1:1 (combina com "a cor do agente aparece em tudo", mas mexe no visual: precisa do "sim" do Heitor).

## 3. Lista completa por área

Coluna Sora: **Tem** · **Parcial** · **Não tem**.

### 3.1 Conta, dados e confiança

| OpenBot | Sora | Observação |
|---|---|---|
| Entrar com código de uso único por e-mail (sem senha) | Não tem | Sora: e-mail + senha com convite; sem recuperação de senha e sem envio de e-mail. |
| Exportar dados e diagnóstico sem conteúdo privado | Não tem | A Sora apaga tudo (LGPD), mas não exporta. |
| Relatar problema ao time, com corrigir ou retirar o relato | Não tem | Sora: Sentry só no servidor. |
| Transferir tudo para outro servidor (`.zip` com agentes, rotinas, canais e histórico) | Não tem | |
| Métricas de uso do produto (OpenPanel) com política de privacidade | Não tem | A Sora tem Sentry e log de erro, não métrica de uso. |

### 3.2 Bots e conversa

| OpenBot | Sora | Observação |
|---|---|---|
| Criar agente por conversa e revisar as seções antes de salvar | Tem | Cartão de rascunho e Novo bot direto. |
| Fios laterais em abas e "ramificar a partir deste turno" | Parcial | A fila da Sora tem pistas paralelas no backend, mas não há abas nem ramificação. |
| Agente divide trabalho em tarefas simultâneas e junta os resultados | Parcial | Cadeia com até 3 etapas em paralelo e especialistas; não aparecem como tarefas separadas. |
| Mensagem entra no turno em andamento ("steer") | Não tem | Na Sora vai para a fila. |
| Fixar mensagem; apagar mensagem | Não tem | A Sora edita a pergunta e refaz a resposta. |
| Achar conversas digitando `@` + texto | Parcial | Sora: busca nas mensagens pelo Ctrl+K. |
| Esconder e silenciar agente | Não tem | |
| Link público do agente, importar/exportar, importar de outro produto | Não tem | |
| Regras de comunicação no prompt compartilhado dos agentes | Parcial | Vale rever os prompts da Sora (texto nosso). |
| Formulário no chat, com campo secreto que nunca é guardado | Parcial | Sora: cartão de pergunta com 2 a 4 opções. |

### 3.3 Orquestração e automação

| OpenBot | Sora | Observação |
|---|---|---|
| Canais com vários agentes, responsável por tarefa, delegação, Parar/Retomar/Reatribuir | Tem | Grupos (2 a 5 bots) com a Sora de chefe. |
| Workflows em canvas (agente, modelo, condição, aprovação, imagem, vídeo; laços; versões; gatilhos) | Não tem | |
| Fluxo entre rotinas (a resposta de uma rotina segue para outros agentes) | Não tem | |
| Rotina por webhook assinado (filtros, deduplicação, histórico, retenção) | Não tem | Na Sora a rotina roda só por horário. |
| Rotina que termina calada quando não há novidade | Tem | `SEM_RESPOSTA` em `app/rotinas/silencio.py`. |
| Agenda de rotinas em calendário (semana e mês) e feed `.ics` | Não tem | |
| API local para scripts (enviar mensagem, rodar rotina, responder aprovação) com token e limite por hora | Não tem | A Sora tem REST, mas só com o login do app; não há token pessoal. |
| Limite de tarefas em paralelo por agente e por servidor | Tem | `limite_tarefas` e pistas da fila. |

### 3.4 Habilidades, memória e aprendizado

| OpenBot | Sora | Observação |
|---|---|---|
| Agente cria habilidade (`SKILL.md`) | Tem | `criar_habilidade` e `ler_habilidade`, `/Nome` na mensagem e `@Nome` na rotina. |
| Biblioteca de habilidades com versões, revisão, instalar em outro agente e atualizar | Não tem | |
| Habilidades prontas no Marketplace (40) e importação do GitHub | Não tem | |
| Revisão automática da memória a cada N turnos e habilidade aprendida com correções | Parcial | Sora: memória editável e "Guardei isto" com Desfazer; sem revisão automática ligada. |
| Ensinar uma tarefa (gravação de cliques) e aprender com a navegação | Não tem | O formato de playbook já existe na Sora. |
| Tabelas compartilhadas entre agentes (um banco comum) | Não tem | Útil para listas, controles e cadastros feitos pelos próprios bots. |
| CRM (leads, clientes, planos, pagamentos, Stripe), experimental e desligado por padrão | Parcial | Sora: tela Clientes a partir dos canais da empresa, só leitura. |

### 3.5 Conectores e integrações

| OpenBot | Sora | Observação |
|---|---|---|
| Marketplace com 254 apps e login pelo navegador (OAuth), várias contas do mesmo app, escolher quem recebe cada servidor MCP | Parcial | Sora: MCP por URL + cabeçalho cifrado, catálogo preguiçoso; Plugins escondidos. |
| Conector do GitHub embutido | Não tem | |
| Slack, Discord, Telegram e WhatsApp onde os agentes **respondem** (com um orquestrador no Slack) | Parcial | Sora: o usuário conversa com a Sora pelo Telegram; WhatsApp Business e Slack só leitura (decisão 15); sem Discord. |
| Rotina que lê um chat conectado (por exemplo, resumo de manhã) | Não tem (por decisão) | O resumo do dia saiu na decisão 15. |
| Memórias por espaço de trabalho do Slack; WhatsApp guarda 90 dias e busca por palavra ou data | Parcial | Sora: retenção configurável e base de conhecimento da empresa. |

### 3.6 Navegador, computador e credenciais

| OpenBot | Sora | Observação |
|---|---|---|
| Navegador persistente por agente, perfis, assumir a aba | Tem | A ideia veio do próprio OpenBot em 2026-11-01. |
| Senha digitada num cartão e preenchida sem o modelo ver; cofre com logins, cartões, contatos e chaves; acesso por agente; Bitwarden e 1Password | Não tem | Na Sora o bot nunca digita senha; o usuário assume a aba. |
| Painéis de Navegador e Arquivos no canal; escolher quem do canal usa o navegador | Parcial | Sora: painel Trabalho por bot. |
| Computer Use em macOS, Windows e Linux | Parcial | Sora: PC só no Windows (árvore de acessibilidade do Windows) e computador virtual por bot. |
| Área de trabalho remota do computador que roda os agentes | Parcial | Sora: tela ao vivo do computador virtual e do PC, com Assumir. |

### 3.7 Modelos e provedores

| OpenBot | Sora | Observação |
|---|---|---|
| CLIs de assinatura (Codex, Claude Code, Grok, Gemini, Cursor, Cline, Kimi, Devin, Copilot, Mistral, Hermes) e agentes ACP próprios | Não tem (por desenho) | Ver seção 5. |
| Endpoint compatível com a OpenAI, achar modelos, detectar Ollama e LM Studio no computador | Parcial | A Sora aceita compatível e Ollama por URL; não detecta (o servidor na nuvem não enxerga o PC). |
| Várias contas do mesmo provedor em "pool" | Não tem | |
| Modelos reserva por agente (automático ou manual) | Parcial | A Sora troca em 429/5xx pela ordem do seletor, mas o modelo escolhido é fixo e não há lista de reserva por bot. |
| Modo rápido com confirmação de preço | Não tem | Depende do provedor oferecer. |

### 3.8 Celular, desktop e notificações

| OpenBot | Sora | Observação |
|---|---|---|
| App de iPhone (e Android), Live Activity, notificações, atualização pelo ar | Parcial | Sora: `/celular` no navegador; PWA a decidir; sem push. |
| Ilha dinâmica no topo da tela | Tem | Ilha da Sora (inspirada no Coucou). |
| Doca de agentes na beirada da tela: arrastar, mudar tamanho, responder pela doca | Parcial | A Ilha aprova, mas não responde. |
| Atualização automática do app | Não tem | |
| Instaladores assinados (Windows e macOS), AppImage, Docker, Nix, Umbrel | Parcial | Sora: instalador Windows sem assinatura; servidor em Docker Compose próprio. |

### 3.9 Interface e personalização

| OpenBot | Sora | Observação |
|---|---|---|
| Tema claro, escuro ou do sistema, e paletas em arquivo | Não tem | Tema claro "a decidir". |
| Fundos de chat, inclusive feitos pelo próprio agente | Não tem | Baixa prioridade; pode brigar com o visual do mascote. |
| Desligar desfoque e animações | Não tem | |
| Interface em 15 idiomas, com escrita da direita para a esquerda | Não tem (por decisão) | Produto em PT-BR. |
| Barra lateral com pastas, filtros, "Não lidas", "Precisa de você" e páginas fixadas | Parcial | Sora: BOTS, GRUPOS e central "Precisa de você". |
| Bolha do usuário na cor do agente | Não tem | Precisa de "sim" (visual). |

### 3.10 Negócio e operação

| OpenBot | Sora | Observação |
|---|---|---|
| Cobrança com Stripe, planos, portal do cliente, cupom e indicação (10%) | Não tem | Sora: "Uso do mês" só mostra o gasto. |
| Servidor hospedado pago e armazenamento extra | Não se aplica | A Sora já é hospedada. |
| Página de status pública e webhooks de status | Não tem | |
| Site com notícias, guias e páginas do Marketplace | Não tem | |

### 3.11 Ferramentas de desenvolvimento

| OpenBot | Sora | Observação |
|---|---|---|
| Plano de verificação pelo que mudou e testes só dos arquivos afetados | Não tem | |
| Medição de RAM e CPU com 100 agentes falsos | Não tem | Útil antes de abrir para muitos usuários. |
| Dados de exemplo para desenvolvimento | Parcial | Sora: contas de QA e modelo falso. |
| Lint de design (só tokens), código morto e links quebrados nos `.md` | Parcial | Sora: oxlint, `qa/contraste.mjs` e `/lab/ui`; sem esses três. |
| Storybook | Parcial | Sora: `/lab/ui` (Catálogo). |

## 4. O que a Sora tem e o OpenBot não tem

Para não perder o que diferencia a Sora enquanto trazemos ideias:

- **Você no controle de verdade:** aprovação por ação (Perguntar/Automático/Total) com bloqueios que nenhum modo tira. No OpenBot os agentes rodam com acesso total.
- **Isolamento:** computador virtual por bot em contêiner, navegador em contêiner com proxy que recusa IP privado, e proteção contra prompt injection que tira o modo total depois de ler conteúdo de fora.
- **Controle do PC com proteções:** bloqueio de terminais, macros, gerenciadores de senha e da própria Sora; pausa ao mexer no mouse; primeira ação em cada programa vira cartão.
- **Canais da empresa com LGPD:** só leitura, máscara de CPF, cartão e senha, retenção, "apagar tudo deste cliente" e fichas de cliente.
- **Funciona com o computador desligado:** a Sora é servidor; o OpenBot precisa do computador da pessoa (ou de um servidor contratado) ligado para o celular e o navegador funcionarem.
- **Feita para leigo, em PT-BR:** a Sora como chefe de equipe, o mascote que mostra o estado, nada de termo técnico.

## 5. O que não vale trazer

| Recurso do OpenBot | Por que não |
|---|---|
| Usar as CLIs de assinatura (Codex, Claude Code etc.) como motor | Assinatura é pessoal e o uso por um serviço na nuvem esbarra nos termos dos provedores (o próprio OpenBot tem um documento só sobre isso); a Sora usa chave de API. |
| Acesso total sem confirmação | Vai contra "você no controle". |
| Responder clientes pelo WhatsApp ou Slack e resumo diário dos canais | Decisão 15 do Heitor. |
| Self-hosting (Docker, Nix, Umbrel, Mac compartilhado por vários clientes) e WebRTC entre computadores | É do modelo local-first deles; a Sora é hospedada. |
| 15 idiomas agora | O público é brasileiro. Deixar os textos fáceis de traduzir já ajuda no futuro. |
| Fundos animados e temas por arquivo | Pouco valor e risco de brigar com o mascote. |

## 6. Próximos passos sugeridos

1. Heitor escolhe o que entra (sugestão: Onda 1 inteira, mais webhooks e notificação no celular da Onda 2).
2. Para cada item escolhido: especificação curta em `docs/`, com regras e números nossos, como foi feito em 2026-11-01.
3. Decisões do grupo antes da Onda 3: catálogo de apps (decisão 3), equipe com membros, tema claro e PWA.
