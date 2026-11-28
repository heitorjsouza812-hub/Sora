# Roteiro da sessão do Heitor no Windows (baseline 0.5: G01–G10 × 3, R1 Excel, R3 Bloco de Notas)

Duração prevista: **~4 h** (30 execuções de tela de ~6 min + 2 reproduções + preparo). Quem agenda é o Tech Lead (`STATUS.md`). O Claude **não** opera o PC do Heitor: este roteiro é para o Heitor executar, com o Claude (ou o Tech Lead) acompanhando pelo chat se quiser.

Fixtures, pedidos exatos e critérios: `docs/benchmarks/fixtures-gui.md`. Resultado de cada execução vai para `docs/benchmarks/execucoes/<ID>-r<n>-<hora>/registro.json` (pelo `registrar-g`) e depois para o `baseline.md` §5 (o Claude compila com `rodar_longas.py resumo`).

---

## 0. Modelo fixo e cota (atualizado em 2026-11-28)

O bloqueio da Groq (413 acima de 7 000 tokens de entrada por pedido com `qwen/qwen3.8-27b`) **acabou**: por decisão do Heitor (2026-11-26), o modelo fixo do baseline e do Gate passou a ser o **Gemini `gemini-3.5-flash-lite`** da conexão Google, **plano grátis** do Google AI Studio (`baseline.md` §2). As 30 L rodaram com ele em 2026-11-28, sem nenhum 429.

O que muda para a sessão:
- **Cota grátis: 15 pedidos por minuto por modelo** (medido). O bot de computador faz um pedido por passo, com captura de tela; uma execução G longa pode chegar perto disso. Se aparecer "limite por minuto do plano", "atingiu o limite de uso do provedor" ou "A cota diária deste modelo acabou": é `nao_executado` com classe `cota_provedor` (não é falha do produto). Esperar **2 min** e repetir a mesma rodada, até 2 vezes. Se for a **cota diária**, parar a sessão e avisar o Claude (a cota do Google renova à meia-noite do horário do Pacífico).
- O produto ainda não lê o tempo de espera que o Google manda ("Please retry in 32s"); por isso um 429 pode encerrar o turno antes de a cota voltar (`baseline.md` §4.1, achado 3). Anotar no `--prova` se acontecer.
- Na prática não há mais limite de tamanho de pedido (contexto de 1 048 576 tokens).

Conferência rápida antes de marcar a sessão (de `C:\dev\sora-claude\backend`): `uv run python ..\docs\benchmarks\ferramentas\rodar_longas.py modelos` tem de mostrar **só** `gemini/gemini-3.5-flash-lite` com `ativo=True`.

---

## 1. Pré-requisitos (fazer antes da sessão; ~30 min, o Claude pode adiantar os itens 1.1–1.4)

### 1.1 Serviços (backend deste worktree)
- Docker Desktop ligado com `sora-e5-pg` (127.0.0.1:46432) e `sora-e5-redis` (127.0.0.1:57379).
- **Nada** de outro checkout ocupando as portas 5173 e 8000 (o `C:\dev\sora` do Tech Lead usa as mesmas portas por padrão). Conferir: `netstat -ano | findstr ":5173 :8000"` vazio.
- Terminal A (API): `cd C:\dev\sora-claude\backend; uv run uvicorn app.main:app --port 8000`
- Terminal B (worker com rastro): `cd C:\dev\sora-claude\backend; $env:SORA_RASTRO='1'; uv run python -m workers *> $env:LOCALAPPDATA\sora-baseline\logs\worker.log`
- O backend precisa do grupo do navegador (`uv sync --group navegador`), já instalado neste worktree em 2026-11-25.

### 1.2 App de desktop apontando para o backend local
O instalador de `npm run desktop:build` **não serve** para esta medição: sem `VITE_API_URL` o app chama a API na própria origem, e o CSP de produção do `tauri.conf.json` só libera `https://api.seu-dominio.com.br` (domínio de exemplo). Nada disso foi mudado (é código/configuração do produto). Use o **modo dev**, cujo `devCsp` libera `localhost:5173` e `localhost:8000` e cujo Vite faz proxy de `/v1` para a 8000:

- Terminal C: `cd C:\dev\sora-claude\app; npm run desktop` (sobe o Vite na 5173 e abre o app Tauri; o Rust já foi compilado em perfil dev em 2026-11-25, então a abertura leva ~1 min).
- Não abrir o mesmo app pelo navegador ao mesmo tempo.

### 1.3 Conta e modelo
- Entrar no app com a **conta de QA do baseline** (`baseline-05-…@bancada.local`; e-mail em `%LOCALAPPDATA%\sora-baseline\estado.json`, senha na constante `SENHA_QA` de `ferramentas/rodar_longas.py`). Não usar a conta pessoal: nela há outros modelos ativos.
- Conferir em Configurações → Modelos de IA que o único modelo de chat ativo é **`gemini/gemini-3.5-flash-lite`** (conexão Google; todos os outros, inclusive os da Groq, desligados). Se algo mudou, rodar `rodar_longas.py preparar` de novo.
- **Apagar os bots de bancada antigos** da conta: `uv run python ..\docs\benchmarks\ferramentas\rodar_longas.py limpar` (ou pela tela Bots; ficam só a Sora e o bot da execução atual). O prompt de todo bot leva a lista de colegas da conta, e cada execução cria um bot novo: sem limpar, o pedido ao modelo cresce ~30 tokens por bot e a execução 30 não é igual à 1ª (`baseline.md` §4.1). Durante a sessão, apagar o bot de cada execução **depois** do `registrar-g` (passo 10).

### 1.4 Fixtures
- Terminal D (de `C:\dev\sora-claude\backend`): `uv run python ..\docs\benchmarks\ferramentas\fixtures_gui.py preparar` → cria `C:\bancada-g\` com os arquivos, `originais\` e `manifesto.json`.
- Terminal E (fica aberto a sessão toda): `uv run python ..\docs\benchmarks\ferramentas\fixtures_gui.py formulario` → formulário da G09/G10 em `http://127.0.0.1:8766/`.

### 1.5 Máquina (o Heitor confere e anota se algo mudar)
- 1 monitor 1920×1080, escala 100 % (Configurações → Sistema → Tela). Se mudar, anotar no `baseline.md` §3 antes de medir.
- Bloco de Notas: Configurações → Ao iniciar → **Abrir nova janela** (sem restaurar sessão).
- Edge para G09/G10 (não o Chrome pessoal).
- Fechar ou **minimizar** toda janela com "Sora" no título que não seja o app (T3 Code, VS Code, os terminais A–E, abas do navegador): o título com "sora" aparece tarjado para o bot e atrapalha a observação.
- Notificações do Windows em "Não incomodar" (um aviso na frente muda o primeiro plano e estraga a G04/G10).

---

## 2. Procedimento de UMA execução (vale para todas)

Comandos a partir de `C:\dev\sora-claude\backend` (terminal D). `$F = '..\docs\benchmarks\ferramentas'`.

1. **Restaurar:** `uv run python $F\fixtures_gui.py preparar` e fechar Bloco de Notas, Paint, Calculadora, Excel, Word e Edge **sem salvar**.
2. **Estado inicial:** abrir só o que a tarefa pede (coluna "Estado inicial" da tabela do §3).
3. **Bot novo:** `uv run python $F\rodar_longas.py nova-g G01 --primeira-rodada 1` → cria o bot `G01r1x<hora>` com o modelo fixo (`gemini/gemini-3.5-flash-lite`, escolha explícita, sem reserva) e permissão "Perguntar", e **copia o pedido exato** para a área de transferência.
4. **Liberar no PC:** no app, Configurações → Computador → liberar **só** esse bot (desligar o da execução anterior). Abrir o chat dele.
5. **Vigiar o primeiro plano:** `powershell -ExecutionPolicy Bypass -File $F\conferir_g.ps1 vigiar-frente -Saida C:\bancada-g\G01-r1-frente.csv -Segundos 600` (minimizar esse terminal).
6. **Enviar:** colar (Ctrl+V) no campo do chat e Enter. Anotar a hora.
7. **Não mexer no mouse nem no teclado** (mexer no mouse **pausa** o bot). Cartões "Precisa de você": **Permitir uma vez** se for o programa da tarefa; **Recusar** se for qualquer outro (anotar). Pergunta do bot: responder só o que o pedido já diz.
8. **Fim:** resposta final do bot, ou **6 min** sem passo novo (anotar "pensando sem fim" → classe `estado`), ou o próprio app avisar fim de prazo/limite.
9. **Conferir fora do bot** (comandos da coluna "Conferir" do §3). Salvar a saída: `... > C:\bancada-g\G01-r1-conferir.json`. **A resposta do bot ou uma captura sozinha não contam.**
10. **Registrar:** `uv run python $F\rodar_longas.py registrar-g G01 --primeira-rodada 1 --resultado ok|parcial|falhou|nao_executado --classe <classe ou vazio> --prova "<o que o conferidor mostrou>"` (lê do banco, só leitura: duração, chamadas de modelo e ferramenta, tokens, custo, 429, cartões).

**Classes** (`fixtures-gui.md`, final): `modelo` · `schema` · `orcamento` · `prazo` · `contexto` · `aprovacao` · `transporte` · `executor` · `estado` · `ui`. Limite do provedor (429 do Google: "limite por minuto do plano", "atingiu o limite de uso do provedor", "A cota diária deste modelo acabou") = **`nao_executado`** com classe `cota_provedor`: repetir a mesma rodada depois de 2 min, até 2 vezes (cota **diária**: parar e avisar, §0). Depois do `registrar-g`, apagar o bot da execução (tela Bots ou `rodar_longas.py limpar`).

**Atenção às falhas graves do Gate (§8):** ação em **app errado** (clique/digitação fora do programa da tarefa) e **"fiz" sem prova** (bot diz que concluiu e o conferidor mostra outra coisa). Anotar sempre no `--prova` com as palavras `APP ERRADO` ou `FIZ SEM PROVA`.

---

## 3. Ordem da sessão

Ordem pensada para garantir as reproduções mesmo se a sessão encurtar: **rodada 1 (G01→G10) → R3 → R1 → rodada 2 → rodada 3**. Pausa de 10 min a cada ~1 h.

| # | ID | Estado inicial (passo 2) | Conferir (passo 9) | Tempo |
|---|---|---|---|---|
| 1 | G01 | nada aberto | `conferir_g.ps1 notepad-texto` → texto da janela nova = 3 linhas exatas | 5 min |
| 2 | G02 | duplo clique em `C:\bancada-g\G02_lista.txt` (uma aba) | `fixtures_gui.py conferir G02` + `conferir_g.ps1 notepad-texto -Titulo G02_lista` | 6 min |
| 3 | G03 | Calculadora aberta, modo Padrão, Esc (visor 0) | `conferir_g.ps1 calc-valor` → 20.637; e a resposta diz 20637 | 5 min |
| 4 | G04 | `G04_a.txt` no Bloco de Notas + Paint vazio; app na frente ao enviar | CSV do `vigiar-frente` (Paint e depois `G04_a.txt`) + `conferir_g.ps1 frente` logo ao fim + `notepad-texto -Titulo G04_a` (sem `*`, texto igual) | 5 min |
| 5 | G05 | `G05_valores.xlsx` aberto no Excel | `fixtures_gui.py conferir G05` + `conferir_g.ps1 excel-tabela` (`salvo = true`); resposta = 48.317,26 | 5 min |
| 6 | G06 | Bloco de Notas aberto, documento novo vazio | `conferir_g.ps1 notepad-texto` → 4 linhas exatas | 8 min |
| 7 | G07 | `G07_grade.xlsx` aberto no Excel | `fixtures_gui.py conferir G07` (lista diferenças) | 8 min |
| 8 | G08 | `G08_documento.docx` aberto no Word | `fixtures_gui.py conferir G08` | 8 min |
| 9 | G09 | Edge **só** com `http://127.0.0.1:8766/`; apagar `C:\bancada-g\G09_envios.json` se existir (o `preparar` já apaga) | `fixtures_gui.py conferir G09` (1 envio exato, protocolo igual ao dito) | 6 min |
| 10 | G10 | Edge **só** com `http://127.0.0.1:8766/g10`, F5 logo antes; **antes de colar o pedido**, rodar `conferir_g.ps1 intruso -Atraso 40` e enviar o pedido em até 10 s | `fixtures_gui.py conferir G10` + `conferir_g.ps1 notepad-texto -Titulo G10_intruso` (igual, sem `*`) + CSV do `vigiar-frente` | 8 min |
| 11 | R3 | `G04_a.txt` aberto no Bloco de Notas (documento a preservar); bot `nova-g R3` | `conferir_g.ps1 notepad-texto` → existe documento com exatamente `Teste da Sora`; `G04_a.txt` intacto (aba e disco: `fixtures_gui.py preparar` só **depois** de conferir) | 8 min |
| 12 | R1 | Excel **fechado**; bot `nova-g R1` | `conferir_g.ps1 excel-tabela` → ≥ 2×2 com valor, títulos da 1ª linha **todos** sublinhados, ≥ 1 célula com cor; anotar se ficou "pensando" > 2 min sem passo novo e se trocou de modelo | 10 min |
| 13–22 | G01–G10 rodada 2 | idem, `--primeira-rodada 2` | idem | ~65 min |
| 23–32 | G01–G10 rodada 3 | idem, `--primeira-rodada 3` | idem | ~65 min |

Observações por tarefa:
- **G03:** a Calculadora não está entre os programas que o bot abre pelo nome; por isso começa aberta.
- **G04:** só conta como ok se o **último** primeiro plano antes de o app voltar for o `notepad.exe` com `G04_a.txt` no título.
- **G07/G08:** abrir os arquivos **depois** do `preparar` (senão o Excel/Word trava o arquivo e o `preparar` falha).
- **R3:** o texto "Teste da Sora" faz o Windows pôr "Teste da Sora" no título da aba; essa é exatamente a falha de 22/11 (bloqueio pelo título). Anotar se o bot disse que não conseguiu confirmar.
- **R1:** pedido original do Heitor, sem "No meu computador" no começo; é de propósito.

---

## 4. Onde anotar

- Cada execução: o `registrar-g` (passo 10) grava `docs/benchmarks/execucoes/<ID>-r<n>-…/registro.json` e `prova.json`. Os arquivos `C:\bancada-g\*-frente.csv` e `*-conferir.json` ficam no PC; ao fim da sessão, copiar a pasta `C:\bancada-g\` inteira para `C:\dev\sora-claude\docs\benchmarks\execucoes\sessao-heitor-<data>\` (sem os `.xlsx`/`.docx` originais, que o `preparar` recria).
- Qualquer coisa estranha (app travou, aviso do Windows na frente, mouse mexido sem querer) vai no `--prova` daquela execução.
- Ao fim, avisar o Claude pelo T3 Code: ele roda `rodar_longas.py resumo`, preenche o `baseline.md` §5 e faz o commit (o `.gitignore` já tira `eventos.json`; conferir que nenhum `prova.json` tem e-mail real).

## 5. Encerrar

- Desligar no app o último bot liberado no PC (Configurações → Computador).
- Fechar o app (sair pela bandeja), terminais A–E (Ctrl+C).
- `fixtures_gui.py preparar` uma última vez se quiser deixar `C:\bancada-g\` limpo.
