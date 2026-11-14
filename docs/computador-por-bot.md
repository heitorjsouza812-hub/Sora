# Computador e navegador por bot

Pedido do Heitor em 2026-11-14 (`log/etapa6-acabamento.md`, "Computador e navegador por bot"): cada bot pode usar **um navegador próprio** (C1) e **um computador próprio** (C2); no app de desktop, o bot pode **controlar o PC do usuário** (C3, feito depois por outro agente em cima da interface descrita aqui). Dono no backend: Farol.

## Resumo

| Peça | Estado | Onde |
|---|---|---|
| C1 navegador próprio por bot | pronto | `app/modelos/tabelas.py` (padrão `agente`), `app/api/agentes.py` (`perfil_navegador` na saída), `app/api/navegador.py` (PUT aceita `agente`) |
| C2 computador virtual por bot | pronto | `app/computador/{interface,virtual,servico,ferramentas,eventos}.py`, `app/api/computador.py`, `workers/computador.py`, `infra/computador/` |
| C3 PC do usuário | só a interface e um stub que recusa | `app/computador/pc_usuario.py` |
| Visão da tela, navegador ao vivo, entregar arquivo (Farol-2) | pronto | `app/computador/visao.py`, `app/navegador/ao_vivo.py`, `app/api/navegador_ao_vivo.py` |

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
| `computador_entregar_arquivo` | livre (leva o arquivo para um anexo do próprio dono, até 10 MB) | não |
| `computador_desligar` | livre | não |

Todas aceitam `alvo` (`virtual` padrão; `pc_usuario` para o C3). Para um bot usar o computador, o usuário liga as ferramentas no bot (`agentes.ferramentas`, validadas em `app/api/agentes.py`). Com o sandbox desligado a ferramenta responde "O computador virtual está desligado neste servidor."

### Senha e segredo

- `digitar` recusa texto que parece senha ou chave: padrões da redação (`limpar_texto_sensivel`: chaves de API, tokens, JWT) e uma heurística (`parece_senha`): uma palavra só, 8 a 128 caracteres, com 3 das 4 classes (minúscula, maiúscula, dígito, símbolo) e que **não** é endereço, e-mail nem **código de negócio**. Resposta: "Não digito senhas, chaves nem códigos de acesso…".
- **Código de negócio** (`parece_codigo_de_negocio`, Farol-2): um rótulo só de letras (2 ou mais) seguido de um ou mais grupos `separador + letras/dígitos`, com separador de código (`# - _ / . :`) e **metade ou mais de dígitos** no resto. Passam: `Pedido#123A`, `NF-2024-001`, `PED-1234`, `OS_5521B`, `Protocolo/2024.77`. Continuam recusadas: `Cafe@2024`, `Xk9#mPq2rT`, `Ab1!Ab1!`, `Senha#abcd9` (poucos dígitos), `Pedido#123A!` (símbolo fora da lista). O critério é uma rede de segurança, não uma barreira: quem divide o texto em dois pedaços passa. O que protege de verdade é o bot não receber segredo (a memória e a redação o barram) e o cartão "Precisa de você" de `computador_agir`.
- O Chromium do computador não tem login do usuário, sem gerenciador de senhas nem preenchimento automático (políticas em `infra/computador/politicas-chromium.json`).
- O evento e o estado nunca levam o texto digitado ("Digitou 12 caracteres"); títulos passam pela redação. Os parâmetros do passo (painel Trabalho) passam por `parametros_sem_segredos`, como no navegador.

## O bot vê a tela (Farol-2)

Quando o modelo da chamada tem a capacidade `visao` (a do catálogo ou a que o usuário marcou em Configurações), o bot recebe a captura como **imagem**. Código: `app/computador/visao.py`.

- **Como chega.** `computador_observar` e `computador_agir` seguem devolvendo texto. O `MiddlewareVisaoTela` (montado só para bot que tem `computador_*`) junta, **só na chamada ao modelo**, uma mensagem do usuário no fim com `[texto explicando a captura, bloco image_url]`: o mesmo formato multimodal dos anexos (`app/agentes/visao.py`). A imagem **não** entra no histórico do bot, então o contexto nunca acumula telas: o modelo recebe **no máximo uma** imagem por chamada, a da leitura que o último resultado de `computador_*` citou (`leitura @cN`). Resultado de turno anterior ou leitura que este worker não guarda mais: sem imagem (melhor nenhuma que errada).
- **Tamanho.** Reduzida a no máximo 1280 px de largura (tela de 1280 px passa 1:1). PNG (texto nítido); se passar de 700 KB, JPEG qualidade 85.
- **Escala.** O texto diz o tamanho da imagem, o da tela real e, quando há redução, "multiplique por 2,00 o x/y que você lê na imagem". As ações continuam em pixels da tela real.
- **Qual modelo.** Bot com `computador_*` pede ao seletor modelos com visão (`preparar_entrada(..., precisa_visao=True)`); se o usuário não tem nenhum, segue com os de sempre. Quem decide a imagem é o modelo **da chamada** (`request.model`), então uma troca de provedor no meio do turno vale.
- **Sem visão.** Nenhuma imagem; o prompt de sistema diz ao bot que ele não vê a tela, para não chutar coordenadas e trabalhar por terminal, atalhos e refs de janela, e para pedir ao usuário um modelo com visão quando o pedido só se resolve olhando.
- **Testes.** `tests/unitarios/test_farol2_visao.py` (formato, escala, só a última, sem visão, troca de modelo, montagem) e `tests/integracao/test_computador_visao.py` (contêiner real: a mensagem que chega ao modelo leva a imagem 1280x800 da tela e muda depois do clique).

## Navegador do bot ao vivo (Farol-2, item 18)

O usuário vê a aba que o bot usa e, **assumindo** a aba, clica e digita nela. Código: `app/navegador/ao_vivo.py` (worker), `app/api/navegador_ao_vivo.py` (rotas). O Chromium mora no worker; a API só fala com ele por Redis.

```
app --POST /agentes/{id}/navegador/assistir--> API --SET navegador:assistindo:<bot> (12 s)--> Redis
worker (laço a cada 0,9 s): bot assistido? --sim--> screenshot JPEG da aba em uso
        |- Redis: navegador:captura:<aba> (JPEG inteiro, 120 s) + navegador:dono:<aba>
        '- SSE navegador.tela (miniatura até 640 px) --> app
app --POST /navegador/abas/{aba}/clicar|digitar|tecla|rolar--> API --RPUSH navegador:comandos:<aba>--> worker
        (só com a aba assumida; o worker confere de novo: dono + marca de assumida)
```

- **Só quando alguém assiste.** Sem a marca `assistindo` (expira em 12 s; o app a renova a cada ~5 s enquanto o painel estiver aberto) o worker não captura nada.
- **Ritmo.** Um quadro a cada 0,9 s por bot assistido (medido: máximo < 1 s entre quadros). Quadro igual ao anterior sai **sem miniatura** (`mudou: false`): mantém o ritmo sem gastar banda.
- **Qual aba.** A que o usuário assumiu; senão a mais recente do bot. Uma por bot.
- **Stream do usuário.** O stream `eventos:usuario:<id>` guarda 24 h; um quadro por segundo ocuparia gigabytes. Só os **últimos 3 quadros** de cada aba ficam (os mais velhos saem com `XDEL`). Quem reconecta perde quadros velhos, o que não importa para imagem ao vivo.
- **Clicar.** `x`,`y` na escala da imagem que o usuário viu (miniatura ou captura inteira) mais o `largura`/`altura` dessa imagem; o worker converte para a janela real (`navegador.tela.largura/altura`). Domínio novo num perfil com login salvo continua barrado pela revisão: o clique não navega e o quadro seguinte traz `aviso` explicando.
- **Segredo.** O texto de `digitar` passa pela fila do Redis (vive milissegundos; a fila expira em 30 s e tem teto de 50 pedidos) e é digitado na página. **Nunca** vai para o rastro, para os eventos, para o log (só o nome da classe do erro), nem para o estado; `Comando.__repr__` não mostra o texto. O usuário não passa pelo navegador por árvore, então o rastro do bot não vê nada. Senha digitada num campo de senha aparece como pontos na captura.
- **Devolver.** `POST …/devolver` (já existia) solta a marca; os pedidos do usuário passam a ser descartados e a próxima ferramenta `navegador_*` do bot já usa a aba (`_sincronizar_assuncao`). O backend **não** escreve mensagem no chat: se o app quiser acordar o bot depois do "Devolver", manda uma mensagem normal ("Devolvi a aba, pode continuar").
- **Testes.** `tests/unitarios/test_farol2_navegador_ao_vivo.py` (Chromium real: quadro, captura com dono, só enquanto assistem e < 1 s, escolha da aba, clique em escala, digitar sem rastro, teclas, laço de pedidos, devolver) e `tests/integracao/test_navegador_ao_vivo_rotas.py` (API real: dono, 409 sem assumir, validação, teto da fila).

## Arquivos do bot: o que some e o que fica (Farol-2)

A área `/home/bot` é `tmpfs` (512 MB) e **some quando o computador desliga** (ociosidade de 15 min, `computador_desligar` ou o botão). Decisão: **não** usar volume nomeado por bot.

- Volume nomeado com limite de tamanho só existe de verdade com cota de disco do sistema de arquivos do host (xfs `pquota`), que não é portátil (nem no Docker Desktop do Windows de desenvolvimento). Sem limite, um bot (ou uma injeção de comando num site) enche o disco do host do sandbox: risco pior que o problema.
- Volume que sobra quando o bot é apagado é lixo com dado do usuário: exigiria apagar junto, com rotina de limpeza e política de retenção (LGPD).
- O que o usuário quer guardar quase sempre é **entregável**, não arquivo de trabalho. Por isso a solução é levar o arquivo para a conversa: **`computador_entregar_arquivo`** (até 10 MB) copia o arquivo da área para um anexo do usuário (`origem: "computador"`), que sobrevive ao desligar, tem dono e limites de anexo e sai na próxima mensagem do bot (`saidas_do_turno`). Política `livre` (só leva o que é do bot para a conversa do próprio dono); não existe em rotina sem supervisão.

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

### Navegador ao vivo (Farol-2): evento e rotas

Evento SSE `navegador.tela` (stream do usuário): `{aba_id, agente_id, url, titulo, largura, altura, miniatura: "data:image/jpeg;base64,…"|null, mudou, assumida_pelo_usuario, aviso, em}`. `largura`/`altura` são o tamanho real da janela da aba; `miniatura` é nula quando o quadro é igual ao anterior.

| Rota | Resposta |
|---|---|
| `POST /v1/agentes/{id}/navegador/assistir` | 200 `{expira_em_segundos: 12}`; repetir a cada ~5 s enquanto o painel estiver aberto. Bot de outra conta: 404. |
| `GET /v1/navegador/abas/{aba_id}/captura` | JPEG inteiro do último quadro (`no-store`); 404 se não houver ou for de outra conta. |
| `POST /v1/navegador/abas/{aba_id}/clicar` | `{x, y, largura, altura}` na escala da imagem → 202. |
| `POST …/digitar` · `…/tecla` · `…/rolar` | `{texto}` (1–500) · `{tecla}` (Enter, Tab, Escape, Backspace, Delete, setas, Home, End, PageUp, PageDown) · `{dy}` (−5000 a 5000) → 202. |

Os quatro `POST` de ação exigem a aba **assumida** (`POST /v1/navegador/abas/{id}/assumir`): sem isso, 409 "Assuma a aba antes…". Aba de outra conta: 404; validação: 422; fila cheia: 429.

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

- **Árvore de acessibilidade no virtual** (AT-SPI): hoje o alvo virtual só tem janelas e pixels.
- **Produção**: construir as duas imagens no host do sandbox e conferir que ele alcança a internet só pela rede `sora-pc-saida`.
