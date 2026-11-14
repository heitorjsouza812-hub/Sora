# Computador e navegador por bot

Pedido do Heitor em 2026-11-14 (`log/etapa6-acabamento.md`, "Computador e navegador por bot"): cada bot pode usar **um navegador próprio** (C1) e **um computador próprio** (C2); no app de desktop, o bot pode **controlar o PC do usuário** (C3, feito depois por outro agente em cima da interface descrita aqui). Dono no backend: Farol.

## Resumo

| Peça | Estado | Onde |
|---|---|---|
| C1 navegador próprio por bot | pronto | `app/modelos/tabelas.py` (padrão `agente`), `app/api/agentes.py` (`perfil_navegador` na saída), `app/api/navegador.py` (PUT aceita `agente`) |
| C2 computador virtual por bot | pronto | `app/computador/{interface,virtual,servico,ferramentas,eventos}.py`, `app/api/computador.py`, `workers/computador.py`, `infra/computador/` |
| C3 PC do usuário | só a interface e um stub que recusa | `app/computador/pc_usuario.py` |

## C1: navegador próprio por bot

O navegador persistente já tinha três perfis por agente (`app/navegador/perfis.py`): **compartilhado** (um por conta), **só deste agente** (`TipoPerfil.AGENTE`) e **nomeado**. Agora:

- **Bot novo nasce com o perfil só dele** (`agentes.perfil_navegador = "agente"`, padrão do ORM). Bots que já existem mantêm a escolha gravada; o padrão do banco não mudou e não há migração. A **Sora** continua no perfil compartilhado (usa o login da conta), criada assim de propósito em `core/contas.py` e `api/agentes.py`.
- A saída do bot (`AgenteSaida`, em `GET /v1/agentes`, `GET /v1/agentes/{id}`, criação e confirmação de rascunho) traz `perfil_navegador`: `efemero` · `compartilhado` · `agente` · `perfil`. O detalhe (com o nome do perfil nomeado) continua em `GET /v1/agentes/{id}/navegador`.
- `PUT /v1/agentes/{id}/navegador` passou a aceitar `{"tipo": "agente"}` (antes a rota não deixava voltar para o perfil próprio).
- Cada perfil é um *contexto* separado do Chromium (cookies, `localStorage`, cache) e uma linha cifrada separada no banco (AAD com a partição). Dois bots navegam em paralelo sem um ver o login do outro: provado com Chromium real em `tests/unitarios/test_navegador_por_bot.py` (e a contraprova: no perfil compartilhado o login de um vale para o outro).

## C2: computador virtual por bot

### Arquitetura

```
worker (ferramentas computador_*)
  └─ ServicoComputador  (observar → agir → conferir, refs, regras, tela ao vivo)
       ├─ alvo "virtual"    → GerenteComputadoresDocker → docker exec no contêiner do bot
       └─ alvo "pc_usuario" → ProvedorPcUsuario (C3: hoje recusa)

host Docker (o do sandbox; em produção, separado)
  ├─ sora-pc-<agente>   contêiner do bot  ── rede sora-pc-<agente> (--internal, só dele)
  └─ sora-pc-proxy      proxy de egresso  ── ligado a cada rede de bot (alias sora-proxy)
                                          └─ rede sora-pc-saida → internet pública
```

- **Imagem** `infra/computador/Dockerfile` (Debian bookworm-slim fixado por digest): Xvfb (tela 1280×800), Openbox, Chromium (pt-BR, sem gerenciador de senhas, downloads na área do bot), xterm, xdotool, wmctrl, ImageMagick. Construir: `docker build -t sora-computador:1 infra/computador` e `docker build -t sora-proxy-egresso:1 infra/proxy-egresso`.
- **Sob demanda e reaproveitado:** a primeira ferramenta `computador_*` do bot cria o contêiner `sora-pc-<agente_id>`; os turnos seguintes usam o mesmo. Contêiner parado ou quebrado é recriado.
- **Desligado por ociosidade:** o cron `desligar_computadores_ociosos` (a cada minuto) remove contêiner e rede de quem passou de `COMPUTADOR_OCIOSO_SEGUNDOS` (padrão 15 min) sem uso. O último uso fica no Redis (`computador:uso`), então vale para várias cópias do worker. Desligar **apaga a área de arquivos**.
- **Paralelo:** uma trava por bot (as ações do mesmo bot vão em fila); bots diferentes rodam ao mesmo tempo, cada um no seu contêiner.

### Isolamento e limites

| Regra | Como |
|---|---|
| Só com sandbox ligado | `SANDBOX_PROVEDOR=docker`; em produção só com `SANDBOX_DOCKER_HOST` (host separado). Mesma regra do `executar_comando` (`Configuracao.sandbox_ativo`). |
| Fora de rotina sem supervisão | As ferramentas não estão em `SEGURAS_SEM_SUPERVISAO`, então nem aparecem na rotina; e o serviço recusa se for chamado com `sem_supervisao`. |
| Nada do host | Sem `-v`/`--mount`/`--privileged`; arquivos entram e saem só pelas ferramentas. |
| Raiz só leitura | `--read-only`; escrita só em `tmpfs`: `/home/bot` 512 MB (área do bot, perfil do Chromium) e `/tmp` 256 MB. Esse é o limite de disco. |
| Sem privilégios | Usuário 1000, `--cap-drop ALL`, `no-new-privileges`, `--ipc private`, `--init`. O sandbox interno do Chromium fica desligado porque o contêiner é o isolamento. |
| CPU, memória, processos | `--cpus 1`, `--memory 1g` (sem swap), `--pids-limit 512`, `/dev/shm` 256 MB. |
| Rede | Rede **interna só do bot** (bots não se enxergam). A única saída é o `proxy-egresso`, que resolve o nome e recusa IP privado, de loopback, link-local, CGNAT e metadados de nuvem **depois do DNS**. O DNS interno do Docker não resolve nomes de fora. |
| Comandos | Todo controle é `docker exec` com lista de argumentos fixa (`xdotool`, `wmctrl`, `import`, `readlink`, `find`, `head`). Nunca `sh -c` com texto do modelo; na gravação o caminho vai como `$1`. |
| Área de arquivos | Caminho relativo, sem `..`, sem barra inicial; links simbólicos resolvidos dentro do contêiner (`readlink`) e recusados se saírem de `/home/bot/arquivos`. |

### Interface `Computador` (`app/computador/interface.py`)

Um alvo implementa:

| Método | O que faz |
|---|---|
| `observar() -> Observacao` | `Tela` (PNG, largura, altura), `janelas` (id nativo, título, posição, tamanho, ativa, programa) e `arvore` (elementos de acessibilidade; o virtual não tem, o C3 terá). |
| `agir(AcaoResolvida)` | Executa uma ação já conferida pelo serviço (ponto, janela e tecla resolvidos). |
| `listar_arquivos(pasta)` · `ler_arquivo(caminho, limite)` · `escrever_arquivo(caminho, dados)` | Área de arquivos do bot. |

`ProvedorComputadores` entrega o computador do bot (`obter(usuario_id, agente_id)`) e o desliga (`desligar(agente_id)`).

**Ações** (`AcaoComputador`): `clicar`, `clique_duplo`, `clicar_direito` (por `x`/`y` da última captura ou `ref` de janela), `digitar` (`texto`, até 2.000 caracteres), `tecla` (lista fechada: Enter, Tab, Escape, setas, PageUp/PageDown, Home, End, Backspace, Delete, F1 a F12 e combinações com ctrl/alt/shift; `super` e ctrl+alt+Delete recusados), `rolar` (`direcao`, `quantidade`), `arrastar` (`x`,`y` → `ate_x`,`ate_y`), `abrir` (`programa`: `navegador` ou `terminal`, nunca linha de comando).

### Ciclo observar → agir → conferir (`app/computador/servico.py`)

Ideia do agent-desktop (Apache 2.0, já trazida para o navegador por árvore; `docs/referencias/agent-desktop.md`), reescrita para tela inteira:

1. **Observar** guarda a leitura `@cN` e dá a cada janela uma ref `@cN:jM`.
2. **Agir** exige uma leitura deste worker; confere **todas** as ações antes da primeira (ref velha, ref que não existe, ponto fora da tela, tecla fora da lista, texto que parece senha) e só então executa, parando na primeira que falhar e dizendo quantas já foram feitas.
3. **Conferir**: espera a tela parar de mudar (até 3 capturas), guarda a leitura nova e compara a assinatura da tela. A resposta diz "a tela mudou" ou "a tela NÃO mudou… confira antes de repetir", com as refs novas.

Títulos de janela e conteúdo de arquivo voltam ao modelo dentro da cerca `<dado_externo>`.

### Ferramentas e política

| Ferramenta | Política (`revisor/politica.py`) | Rotina sem supervisão |
|---|---|---|
| `computador_observar` | livre | não |
| `computador_agir` | **revisor** (juiz + cartão "Precisa de você"; "sempre permitir" do usuário libera) | não |
| `computador_arquivos` (listar/ler) | livre | não |
| `computador_escrever_arquivo` | livre (só a área do próprio bot) | não |
| `computador_desligar` | livre | não |

Todas aceitam `alvo` (`virtual` padrão; `pc_usuario` para o C3). Para um bot usar o computador, o usuário liga as ferramentas no bot (`agentes.ferramentas`, validadas em `app/api/agentes.py`). Com o sandbox desligado a ferramenta responde "O computador virtual está desligado neste servidor."

### Senha e segredo

- `digitar` recusa texto que parece senha ou chave: padrões da redação (`limpar_texto_sensivel`: chaves de API, tokens, JWT) e uma heurística (uma palavra só, 8 a 128 caracteres, com 3 das 4 classes — minúscula, maiúscula, dígito, símbolo — e que não é endereço nem e-mail). Resposta: "Não digito senhas, chaves nem códigos de acesso…".
- O Chromium do computador não tem login do usuário, sem gerenciador de senhas nem preenchimento automático (políticas em `infra/computador/politicas-chromium.json`).
- O evento e o estado nunca levam o texto digitado ("Digitou 12 caracteres"); títulos passam pela redação. Os parâmetros do passo (painel Trabalho) passam por `parametros_sem_segredos`, como no navegador.

## Contrato com o app

### Evento SSE `computador.tela` (stream do usuário, `GET /v1/eventos`)

Emitido a cada observar e a cada agir (com a tela já conferida), e com `ligado: false` ao desligar.

```json
{
  "agente_id": "uuid",
  "alvo": "virtual",
  "ligado": true,
  "geracao": 4,
  "largura": 1280,
  "altura": 800,
  "miniatura": "data:image/jpeg;base64,…",
  "janela_ativa": "Google - Chromium",
  "acao": "Clicou em 640,120; Digitou 9 caracteres",
  "mudou": true,
  "em": "2026-11-14T15:00:00Z"
}
```

`miniatura` é um JPEG de até 480 px de largura (até 64 KB); se não couber vem `null` e o app busca a captura cheia.

### Rotas

| Rota | Resposta |
|---|---|
| `GET /v1/agentes/{id}/computador` | `{agente_id, disponivel, ligado, alvo, largura, altura, janela_ativa, acao, atualizado_em}`. `disponivel` = o servidor oferece computador virtual. |
| `GET /v1/agentes/{id}/computador/captura` | Última captura PNG em tamanho cheio (`Cache-Control: no-store`); 404 se não houver. Guardada por 1 hora. |
| `POST /v1/agentes/{id}/computador/desligar` | 202 `{pedido: true}`; o worker desliga e emite `computador.tela` com `ligado: false`. |

Todas exigem login e só valem para bot do próprio usuário (bot de outra conta ou apagado: 404).

### Para o painel Trabalho

Mostrar a `miniatura` do último `computador.tela` do bot, com `janela_ativa`, `acao` e "a tela não mudou" quando `mudou === false`; clicar abre a captura cheia pela rota. "Desligar computador" chama a rota de desligar. Os passos das ferramentas aparecem como "Computador" (`rotulos.py`).

## C3: controle do PC do usuário (para quem fizer depois)

O C3 entra como **outro alvo da mesma interface** (`Alvo.PC_USUARIO`), sem ferramentas novas: o bot chama `computador_observar`/`computador_agir` com `alvo: "pc_usuario"`. Hoje `ProvedorPcUsuario` recusa tudo.

### Onde roda

- A execução mora numa **ponte local no Tauri** (Rust), nunca no servidor: o servidor nem tem acesso ao PC. O worker pede uma ação; o app de desktop conectado a executa e devolve a observação.
- Transporte sugerido: a ponte abre uma conexão autenticada com a API (WebSocket com o token do desktop) e recebe pedidos `{pedido_id, agente_id, operacao, acao}`; responde `{pedido_id, observacao | erro}`. No worker, `ProvedorPcUsuario.obter` passa a devolver um `Computador` que publica o pedido (Redis) e espera a resposta com prazo. Sem app conectado: "Abra o app de desktop da Sora para eu usar o seu computador."
- **Observar**: captura da tela (Windows Graphics Capture) + **árvore de UI Automation** da janela em foco em `Observacao.arvore` (papel, nome, valor, estados, retângulo, ref `@cN:eM`), no mesmo formato de refs do navegador por árvore. Campos com `IsPassword` saem sem valor.
- **Agir**: preferir padrões da UI Automation (Invoke, Value, Toggle, Scroll…) por ref; `SendInput` só quando não houver padrão.

### Regras obrigatórias

1. **Desligado por padrão**, ligado **por bot** em Configurações (aba Computador). O servidor só pede ao app se o bot estiver autorizado; a ponte confere de novo localmente.
2. **Um bot por vez** (vez/fila): a ponte guarda quem está com a vez; outro bot espera ou recebe "o computador está ocupado com o Atlas".
3. **Borda acesa** na tela enquanto um bot controla, na cor do bot, e **Parar** sempre visível (atalho global também). Parar cancela o pedido atual e devolve a vez.
4. **Mexer no mouse ou no teclado pausa** o bot (a ponte detecta entrada física) até o usuário mandar continuar.
5. **Primeira ação em cada programa** vira cartão "Precisa de você" (Permitir uma vez · Sempre permitir neste programa · Recusar). A aprovação fica por bot e por programa (nome do executável).
6. **Nunca digita senha**: a ponte recusa `digitar` em elemento com `IsPassword` ou em janelas de credencial do Windows (UAC, `CredentialUIBroker.exe`), além da recusa que o serviço já faz.
7. **Nunca controla o servidor**: a ponte só fala com a API como cliente.
8. Nada de gravação contínua: só a captura do momento, com o mesmo evento `computador.tela` (`alvo: "pc_usuario"`).

## Pendências

- **Imagem para o modelo**: as ferramentas devolvem texto (janelas, conferência). Para modelos com visão, a próxima peça é anexar a captura como `image_url` no resultado de `computador_observar`/`computador_agir` (depende do middleware de mensagens, dono Âncora; `app/agentes/visao.py` já sabe montar a imagem).
- **Árvore de acessibilidade no virtual** (AT-SPI): hoje o alvo virtual só tem janelas e pixels.
- **Trazer arquivo para a Sora**: ler devolve texto; levar um arquivo do computador para uma mensagem com anexo fica para depois.
- **Produção**: construir as duas imagens no host do sandbox e conferir que ele alcança a internet só pela rede `sora-pc-saida`.
