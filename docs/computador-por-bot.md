# Computador e navegador por bot

Pedido do Heitor em 2026-11-14 (`log/etapa6-acabamento.md`, "Computador e navegador por bot"): cada bot pode usar **um navegador próprio** (C1) e **um computador próprio** (C2); no app de desktop, o bot pode **controlar o PC do usuário** (C3, feito depois por outro agente em cima da interface descrita aqui). Dono no backend: Farol.

## Resumo

| Peça | Estado | Onde |
|---|---|---|
| C1 navegador próprio por bot | pronto | `app/modelos/tabelas.py` (padrão `agente`), `app/api/agentes.py` (`perfil_navegador` na saída), `app/api/navegador.py` (PUT aceita `agente`) |
| C2 computador virtual por bot | pronto | `app/computador/{interface,virtual,servico,ferramentas,eventos}.py`, `app/api/computador.py`, `workers/computador.py`, `infra/computador/` |
| C3 PC do usuário | implementado; validação interativa pendente | `app/computador/pc_usuario*.py`, `app/api/computador_pc.py`, ponte Tauri `src/pc/` |
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
       └─ alvo "pc_usuario" → ProvedorPcUsuario → canal autenticado → ponte Tauri no Windows

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

## C3: controle do PC do usuário (Vela-3 / Vela-4, 2026-11-14)

O C3 implementa **outro alvo da mesma interface** (`Alvo.PC_USUARIO`), sem ferramentas novas: o bot chama `computador_observar`/`computador_agir` com `alvo: "pc_usuario"`. Implementado e validado por testes automatizados; a validação interativa no desktop ainda está pendente.

### Onde roda

- A execução mora numa **ponte local no Tauri** (Rust), nunca no servidor: o servidor nem tem acesso ao PC. O worker pede uma ação; o app de desktop conectado a executa e devolve a observação.
- Transporte implementado: `POST /v1/computador-pc/sessao`, `PUT/DELETE /sessao/{id}`, `GET /comandos?sessao_id=…&espera=20`, `POST /comandos/{id}/resultado`, `POST /parar`, `POST /pausar` e `GET /estado`. Todas exigem login; mutações e long-poll exigem `X-Sora-Cliente: desktop`. O cabeçalho identifica o cliente, não é uma credencial: a autorização final ocorre no Rust, na janela principal, com conta e bot habilitados localmente.
- Canal Redis em `pc_usuario_canal.py`: sessão expira em 60 s sem polling, comandos têm id, prazo absoluto `prazo_em_ms` e resposta única. O Rust também recusa repetição, comando vencido e interrompe a ação ao vencer o prazo. Outra sessão substitui a anterior; indisponibilidade da API solta o controle local.
- **Observar**: captura GDI da tela principal (máximo 1280 px) + **árvore de UI Automation** da janela em foco em `Observacao.arvore` (papel, nome, valor, estados e centro). Campos com `IsPassword` saem sem valor. A imagem passa pelo middleware de visão do Farol-2, sem acumular telas no histórico.
- **Agir**: `SendInput` com conferência de programa, foco e UI Automation antes da entrada; falha ao consultar campo de senha recusa a ação. Padrões Invoke/Value por ref ainda não estão implementados. Arquivos locais e abertura por comando livre são recusados; menu Iniciar, Executar e busca continuam bloqueados. Desde a Vela-12 o bot **abre pelo nome** só os programas de uma lista fechada (`computador_abrir_programa`, ver abaixo); qualquer outro, ele pede ao usuário.

### Regras obrigatórias

1. **Desligado por padrão**, ligado **por bot** em Configurações (aba Computador). O servidor só pede ao app se o bot estiver autorizado; a ponte confere de novo localmente.
2. **Um bot por vez** (vez/fila): a ponte guarda quem está com a vez; outro bot espera ou recebe "o computador está ocupado com o Atlas".
3. **Borda acesa** na tela enquanto um bot controla, na cor do bot, e **Parar** sempre visível (atalho global também). Parar cancela o pedido atual e devolve a vez.
4. **Mexer no mouse ou no teclado pausa** o bot (a ponte detecta entrada física) até o usuário mandar continuar.
5. **Primeira ação em cada programa** vira cartão "Precisa de você" (Permitir uma vez · Sempre permitir neste programa · Recusar). A aprovação fica por bot e por programa (nome do executável). "Permitir uma vez" vence 5 min depois da decisão.
6. **Nunca digita senha**: a ponte recusa `digitar` em elemento com `IsPassword` ou em janelas de credencial do Windows (UAC, `CredentialUIBroker.exe`), além da recusa que o serviço já faz.
7. **Nunca controla o servidor**: a ponte só fala com a API como cliente.
8. Nada de gravação contínua: só a captura do momento, com o mesmo evento `computador.tela` (`alvo: "pc_usuario"`).

### Limites e verificação

- **Revisão Vela-7 (2026-11-15):** o rastro do PC usa somente o executável em `janela_ativa`, sem títulos de documentos (inclusive textos curtos). A primeira movimentação física já pausa; falha ao ler `IsPassword` também oculta o valor na árvore. Backend commitado separadamente; evidências e limite do teste ao vivo em `.maestri/relatorios/vela7.md`.

- Autorizações de bot ficam em `computador-pc.json`, por conta e PC. A primeira ação por executável usa o sistema existente de aprovações e atenção; “Permitir uma vez” vale 5 min, com prazo absoluto (Vela-11), “Sempre permitir” fica por bot/programa. Parar bloqueia nova aquisição por 120 s; sem comandos a vez vence em 90 s.
- Borda nativa transparente com passagem de cliques e botão Parar; atalho `Ctrl+Shift+F12`. Entrada física pausa sem carência e a ponte abre cartão mesmo entre comandos. Com o cartão pendente o turno do bot **pausa** e o "Permitir" retoma o mesmo turno (Vela-12, ver abaixo).
- Bloqueados: credenciais/UAC, configurações e segurança do Windows, gerenciadores de senha, terminais, lançadores e executores de script, a própria Sora e a Sora web. Rotina sem supervisão é recusada pelo serviço existente. O rastro registra quantidade de caracteres, nunca o texto digitado.
- Testes: `test_pc_usuario.py`, integração HTTP com Postgres/Redis em `test_computador_pc.py`, testes da ponte React e testes Rust `pc::`. A integração simula o cliente desktop: não comprova ganchos físicos, borda nativa ou IsPassword em aplicativo real.
- Ainda sem teste interativo: abrir/digitar/conferir no Bloco de Notas via bot, mover mouse físico para pausar, recusar um campo real de senha, múltiplos monitores/DPI e falha na instalação de ganchos. Captura e coordenadas limitam-se ao monitor principal.

### Segurança (Vela-8 a Vela-11, 2026-11-15; achados Cerca A1–B4 e Prumo A2/B1)

- **Lançadores (A1).** Bloqueados na ponte e no servidor, além dos terminais: `explorer.exe` (barra de endereço, caixa Executar), busca e menu Iniciar (`searchhost`, `startmenuexperiencehost`, `shellexperiencehost`), executores de script (`wscript`, `cscript`, `mshta`, `rundll32`, `regsvr32`, `msiexec`, `wsl`, `bash`, `certutil`, `bitsadmin`, `schtasks`, `msbuild`, `installutil`, `control`). Janela com título exato "Executar"/"Run" também. Teclas recusadas nos dois lados: Windows, ctrl/alt+Esc, alt+Tab, ctrl+alt+Delete, F12 e ctrl+shift+I/J/C. A mensagem ao bot não ensina atalho nenhum. **Depois de cada ação** a ponte compara os processos: processo bloqueado que nasceu filho de programa liberado, de lançador ou de outro processo novo é fechado (`TerminateProcess`, melhor esforço); janela bloqueada nova ou programa bloqueado (ou a Sora) na frente também param. O erro `processo_bloqueado` faz o servidor parar o bot e abrir o cartão "Um bot abriu um programa bloqueado"; Permitir solta, Recusar mantém parado (até 15 min). Limite: processo que nasce mais de ~150 ms depois do último passo da ação não é visto naquela ação.
- **A Sora não aprova pela Sora (A2).** Na ponte, toda janela cujo título tem a palavra "Sora" conta como bloqueada (agir, árvore e captura). No servidor, enquanto um bot tem a vez do PC e não está pausado, `POST /v1/aprovacoes/{id}/decidir` responde 409 para **qualquer** sessão. O bot solta a vez quando um cartão dele abre (cartão do PC e cartão do revisor) e a entrada física pausa; então o usuário decide normalmente.
- **Captura (A3).** Antes de codificar, a ponte pinta de preto **a parte à mostra** de toda janela bloqueada e da própria Sora (conferida antes e depois da cópia; as duas tarjas se somam). Com programa bloqueado, a Sora ou nada em primeiro plano, a ponte não copia a tela: manda `captura_omitida: true`, sem PNG e sem árvore. O servidor descarta qualquer imagem que venha junto, usa uma imagem preta pequena e avisa o bot para pedir ao usuário que troque de janela. A tela do PC fica 5 min no Redis (a do computador virtual, 1 h).
- **Tarja só no que aparece (D1, 2026-11-15).** Antes, o retângulo inteiro de toda janela bloqueada era pintado, mesmo atrás de outras: um Chrome maximizado com a aba "Sora" no fundo deixava a captura 100 % preta. Agora a ponte percorre as janelas de topo na ordem z do `EnumWindows` (da frente para trás) e soma a área já coberta; de cada janela bloqueada, tarja só o retângulo dela (`GetWindowRect`, com a moldura invisível) **menos** o que as janelas da frente cobrem. Função pura `regras::areas_a_tarjar`, com testes Rust (coberta inteira → nada; parcialmente coberta → só o pedaço à mostra; bloqueada por cima → inteira; cantos; teto de pedaços).
  - **Quem cobre:** janela visível, não minimizada e não camuflada, com a moldura real do DWM (`DWMWA_EXTENDED_FRAME_BOUNDS`, sem sombra nem borda invisível) e sem os cantos arredondados (10 px; janela maximizada cobre inteira).
  - **Quem não cobre** (na dúvida, pinta-se a mais): janelas da própria Sora (principal, ilha, borda, Parar), `WS_EX_LAYERED` e `WS_EX_TRANSPARENT` (podem ser transparentes), janelas de ferramenta (menus, sombras, avisos), janela com região própria (`SetWindowRgn`), fundo acrílico (`DWMSBT_TRANSIENTWINDOW`), `Windows.UI.Core.CoreWindow` (Iniciar, busca, teclado virtual), área de trabalho e barra de tarefas, e janela sem moldura do DWM. A borda e o Parar ficam fora da captura (`WDA_EXCLUDEFROMCAPTURE`): nem tarjam nem cobrem.
  - **Limites:** se mais de 4.096 pedaços sobrarem, a janela é tarjada inteira. Uma troca de ordem das janelas no meio da cópia (milissegundos entre a conferência de antes e a de depois) pode deixar passar um quadro: uma janela bloqueada coberta nas duas conferências e descoberta só durante a cópia. Janela de outro programa com conteúdo translúcido que o Windows não informa (acrílico desenhado pelo próprio app) conta como opaca.
  - **A ilha** é uma janela da Sora de 800×460 px quase toda transparente. Ela é tarjada só **na pílula**: o retângulo que a própria ilha informa ao comando `ilha_retangulo` (o mesmo que deixa o clique passar) é guardado em `regras::ilha_definir_pilula` e o HWND da janela em `ilha_definir_janela` (setup). Na coleta, a ponte converte o retângulo (CSS px relativos ao canto da janela) em pixels físicos pelo DPI da janela e recorta à janela (`regras::tarja_da_ilha`). Sem retângulo conhecido (ainda não informado, janela recém-aberta ou inválido), tarja a janela inteira, como antes. A ilha continua sem cobrir nenhuma outra janela na conta de região e **não** usa `WDA_EXCLUDEFROMCAPTURE`: segue aparecendo em gravação e compartilhamento de tela (decisão do dono do produto). Teste Rust `ilha_tarja_so_a_pilula`; teste real: passo 4 de `app/qa/pc-tarja.mjs` (foto `qa/shots/desktop-real/63-tarja-ilha.png`: pílula preta, resto da janela da ilha mostra o que está atrás).
- **"Sempre permitir" (M3, Prumo A2/B1).** Regra única em `backend/app/revisor/decisoes.py`, usada pela rota de decisão (422 "Este pedido só aceita Permitir uma vez ou Recusar.") e pela lista `/atencao` (só manda a opção quando vale). Nunca aceitam "sempre": instruções do bot, envio externo, domínio novo em perfil logado, sugestão de melhoria, retomar o PC, programa bloqueado, `computador_agir` no PC do usuário e ferramenta genérica sem condição. No C3, a regra fica presa ao programa e ao bot (`explorer.exe` nunca). Os cartões do chat e da central mostram "Sempre permitir" só quando `/atencao` manda a opção.
- **Texto digitado (B1).** O cartão de `computador_*` guarda `[N caracteres]` no lugar de `texto`.
- **Uma vez (B2).** 5 min de prazo absoluto por programa; ler não renova; Parar apaga.
- **Sessão do PC (B3).** `POST /v1/computador-pc/sessao` exige `token_renovacao` de uma sessão de login **do desktop** desta conta (o do cofre do Windows). Token de acesso roubado, token web, de outra conta ou vencido: 403. Se o login acabar (Sair, revogado, vencido), o long-poll recebe 409 e o PC solta a vez.
- **Ilha (B4).** A janela `ilha` não tem `core:event:allow-emit`; o comando `ilha_emitir` só repassa `sora-armazenamento` e `sora-sessao-pedir` para a janela `main`. `pc-estado` e `pc-parar` saem só do Rust (`emit_to("main")`).
- **Testes.** `tests/unitarios/test_vela8_seguranca.py`, `tests/integracao/test_vela8_aprovacoes.py`, `test_computador_pc.py`, Rust `pc::regras::testes` (`ataques_vela9_recusados`, `sora_no_titulo_e_caixa_executar_sao_bloqueadas`, `processo_bloqueado_filho_da_acao_e_pego`, `tarja_so_a_parte_visivel_das_bloqueadas`, `quem_nao_cobre_nao_esconde_nada`, `muitos_pedacos_tarjam_a_janela_inteira`) e `testes_eventos_pc::ilha_nao_forja_eventos_pc`. Teste real da tarja no Windows: `app/qa/pc-tarja.mjs` (janela magenta com "Sora" no título parcialmente coberta, totalmente coberta e na frente; nenhum pixel magenta pode sair). O fechamento de processo ainda depende de teste manual.

### Vela-12 (2026-11-16): retomar de verdade, mais rápido e sem mentir que terminou

O teste do Heitor (2026-11-15) mostrou três defeitos: "Permitir" no cartão de retomar não fazia o bot voltar, o bot era lento demais para abrir o Excel e montar uma tabela, e dizia que tinha terminado sem ter feito nada.

**Causas achadas.**
- O cartão "Retomar?" nasce na rota `/pausar`, sem conversa nem etapa. O bot esperava 90 s **dentro da ferramenta** e desistia; o "Permitir" que vinha depois (no banco do Heitor: 1,5 a 2 min depois) não tinha turno para retomar. Não era a Cerca A2: a pausa já libera a decisão.
- O usuário pede pelo chat **na janela da Sora**, então a Sora estava sempre na frente: captura omitida e ação recusada (Cerca A2/A3). O bot pedia "minimize a Sora".
- `Café\t2\t10,50\n` era recusado como **senha** (Tab e Enter não separavam palavras).
- A árvore do Excel tem ~726 elementos, 551 deles células vazias; o servidor cortava o JSON em 8 mil caracteres e **nenhuma célula** chegava ao modelo, que não tinha como conferir.
- Cada ação: até 3 observações completas na conferência e uma chamada ao **juiz do revisor** (que no PC do usuário nunca aceita "Sempre permitir"); a digitação conferia UI Automation a cada caractere, criando um `CUIAutomation` novo a cada vez.
- A borda ficava acesa até 90 s depois do turno: mexer no mouse abria "Retomar?" de um bot que já tinha terminado.
- O "Pronto!" que aparece a cada turno no chat do bot é da tela (`app/src/screens/AgentChat.tsx`: todo turno encerrado mostra "Pronto!"), não do bot. **Aberto**: é do Vitral (app).

**O que mudou.**
- **Cartão pausa o turno** (`pc_usuario.py`): no worker, cartão pendente (retomar ou primeira ação num programa) espera 4 s; ainda pendente, `Cartoes.vincular` grava etapa, grupo e `acao.conversa_id` **só se ainda estiver pendente** (a mesma linha que a decisão trava) e o turno pausa com `interrupt`, como os cartões do revisor. A decisão põe na fila `executar_etapa`/`retomar_conversa`/`retomar_tarefa_canal`; a ferramenta roda de novo, acha o cartão decidido, manda `retomar` à ponte (que **traz de volta a janela em que o bot trabalhava**) e segue. Cartão vencido com o turno pausado vale recusa (sem novo cartão em laço); a expiração é agendada. Só pausa se nada foi feito ainda na chamada (a retomada repete a chamada inteira); pausa pelo mouse no meio de uma ação devolve "Pausei…" e a próxima chamada é que pausa.
- **A Sora sai da frente** (`sistema::afastar_a_sora`): quando um bot vai usar o PC e a janela principal da Sora está na frente, a ponte a minimiza (a ilha aparece fora do app); se a frente é a ilha, volta a janela do bot. Sem tecla injetada.
- **`computador_abrir_programa`** (lista fechada em `regras::PROGRAMAS_ABRIVEIS`: Excel, Word, PowerPoint, Bloco de Notas, Paint, LibreOffice Calc e Writer). Executável pelo registro App Paths (ou `System32` para Bloco de Notas e Paint), conferido pelo nome (App Paths adulterado que aponte para terminal é recusado), aberto com `ShellExecuteW` direto e argumentos fixos. Exige o programa liberado no cartão da primeira ação e roda as mesmas conferências de processo e janela bloqueada depois de agir. Vem junto com `computador_agir` (`permissoes.IMPLICITAS`).
- **Teclado de edição sem o juiz** (`teclado_local.py`): chamada só com digitar (sem cara de senha), rolar e teclas de edição (Tab, Enter, setas, Esc, F2, ctrl+n/z/y…) no alvo `pc_usuario` dispensa o juiz, e **nessa chamada a ponte só aceita editores locais** (Excel, Word, PowerPoint, Bloco de Notas, Paint, LibreOffice) liberados no cartão. Clique, arrastar e outras teclas continuam com o juiz. O juiz respeita o modelo escolhido na conversa.
- **Conferência e árvore**: depois de agir, uma observação `estavel` (a ponte compara as capturas localmente e codifica um PNG só). A ponte lê até 3.000 elementos e escolhe 250: foco e valores primeiro, sem célula vazia nem cabeçalho de grade. O modelo recebe linhas curtas (`e136 item de tabela "A1" = "Produto" @94,217`), células primeiro; depois de agir, só o que mudou.
- **Digitação**: janela da frente conferida a cada passo; senha e programa depois de Tab/Enter/setas, a cada 8 passos e quando a janela muda; UI Automation em cache por thread.
- **Senha por célula**: texto com Tab/Enter é julgado célula por célula, com a mesma regra (igual a digitar uma célula por vez).
- **Não mentir** (`conferencia.py` + `MiddlewareConferenciaPc`): se o turno termina afirmando que fez algo no computador sem nenhuma ação conferida na tela (ou sem nem ter tentado), a mensagem vira "Não consegui confirmar que fiz isso no seu computador…", com o último erro. No fim do turno o bot devolve a vez e a borda apaga.
- **Prompt** `computador_pc.v1`: abrir pelo nome, Esc na tela inicial do Excel, a tabela inteira numa ação `digitar` terminada com `\n`, conferir pelos `item de tabela`, só dizer que terminou depois de ver. Nenhum atalho de sistema.
- **Borda pronta**: com `abrir_programa` o primeiro comando pode ser uma ação; ela espera até 2 s pela borda e pelos ganchos (antes era recusada por corrida).

**Medição** (PC do Heitor, 1920×1080, Excel instalado; `app/qa/pc_medir.py`, mesmo caminho do bot, sem modelo):

| | Antes | Depois |
|---|---|---|
| Observar | 2,4–3,1 s | dentro de abrir/agir |
| Uma ação + conferência | 3,9–6,3 s | 1,8–3,2 s |
| Texto ao modelo por passo | ~8.400 caracteres, sem células | 0,6–2,4 mil, com as 12 células |
| Tabela 3×4 no Excel | 26,4 s (e 3 linhas recusadas como "senha" sem a correção) | 12,3 s (abrir 6,3 s, Esc 2,8 s, tabela 3,2 s) |

**Aceitação ao vivo** (`app/qa/pc-excel-live.mjs`, conta `qa-desktop-real@sora.local`, bot "Piloto do PC", Groq): pedido pelo chat na janela da Sora → a Sora minimizou, o bot abriu o Excel, preencheu Produto/Quantidade/Preço com 3 produtos e respondeu "Planilha criada e preenchida" em **97 s com 5 chamadas ao modelo** (nenhuma do juiz). Desses 97 s, ~59 s foram espera de limite do plano grátis da Groq; latência do modelo somada 6,4 s; o PC ~12 s. A última célula ficou em edição (o modelo não terminou com Enter): o prompt agora pede o `\n` final. **Pausa ao vivo**: `/pausar` com o bot no PC → cartão "Retomar?" → o turno pausou (job encerrado em 14,6 s) → "Permitir" 16 s depois → `retomar_conversa` → a ferramenta rodou de novo e observou o Excel. Em seguida a cota diária da Groq acabou. A pausa pelo **mouse físico** só o Heitor testa (entrada sintética conta como do bot).

**Testes.** `test_vela12_pc.py` (senha por célula, não mentir, middleware, pausa → cartão → permitir → retoma, cartão vencido, pausa no meio, programa novo no meio do lote, abrir programa, teclado local, árvore), integração `test_vela12_retomar.py` (API + Postgres + Redis: `/pausar` → turno pausado com o cartão ligado → `POST /decidir` → job `retomar_conversa` → `retomar` + `observar`) e Rust `abrir_pelo_nome_so_na_lista_e_nunca_bloqueado`, `arvore_mostra_primeiro_o_que_tem_valor`, `teclas_que_mudam_o_foco`, `retomar_so_devolve_a_janela_do_proprio_bot_e_encerrar_esquece`.

## Pendências

- **Vela-12:** o "Pronto!" de todo turno no chat do bot (`AgentChat.tsx`, do Vitral); modelo pequeno às vezes encerra o turno com resposta vazia (visto ao vivo depois de duas esperas de limite); pausa pelo mouse físico e Permitir clicado pelo Heitor; com o painel "Recuperação de documentos" aberto o Excel só expõe esse painel à UI Automation (as células somem da árvore até fechá-lo).

- **Árvore de acessibilidade no virtual** (AT-SPI): hoje o alvo virtual só tem janelas e pixels.
- **Produção**: construir as duas imagens no host do sandbox e conferir que ele alcança a internet só pela rede `sora-pc-saida`.
