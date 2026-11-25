# SORA — Plano de correções na arquitetura atual (antes de decidir sobre o DSH)

**Data:** 2026-11-25 | **Para:** Tech Lead no T3 Code, Codex e Claude Code | **Dono das decisões:** Heitor

**Autoridade deste documento:** este é o plano vigente. O `SORA_V2_PLANO_FINAL_SEM_LEGADO.md` (DeepSeek Harness + Hatchet + Cua) **fica suspenso**, não cancelado. Ele volta a valer **só** se o **Gate de decisão (§8)** reprovar. Até lá, ninguém instala DSH, Hatchet ou Cua, e ninguém apaga LangGraph, ARQ ou o executor Rust.

**Referências de linha:** conferidas em 2026-11-25 no ramo `onda3` **com** as alterações locais de 21–22/11. Depois de cada commit as linhas podem andar alguns números; procure pelo nome da função citada.

---

## 1. Por que este plano existe

Uma auditoria do código real (2026-11-25, leitura apenas) comparou o plano V2 com o que o Sora faz hoje. Conclusão: **as falhas que estamos vendo estão no código da Sora, não nos motores**. Trocar LangGraph/ARQ/Rust levaria os mesmos defeitos junto.

| Falha observada | Causa real | Onde |
|---|---|---|
| Bot do PC desiste, "limite de passos", trava em "pensando" | Chat e tela rodam **no mesmo loop**, mesmo teto (40 modelo / 64 ferramentas) e mesmo prazo (285 s dentro dos 360 s do ARQ) | `backend/workers/conversa.py:195,233-235,425-426`, `backend/app/agentes/middleware/limites.py:24,28,57`, `backend/workers/configuracao.py:150` |
| Chamadas de catálogo gastam orçamento; estourar vira erro | `conectores_buscar/carregar/executar` contam no teto; `exit_behavior="error"` | `limites.py:56-61,101-103`, `backend/app/agentes/ancora.py:198-318`, `backend/app/agentes/montagem.py:308-314`, `workers/conversa.py:443-452` |
| Bot "fica cego" no meio da tarefa | Reserva na posição 2 pode ser modelo **sem visão** (`completar_sem_visao=True`) | `backend/app/agentes/visao.py:208-222,255-295,319-328` |
| Clique errado, texto miúdo ilegível | Captura da **tela inteira** reduzida a 1280 px; sem recorte nem zoom | `app/src-tauri/src/pc/sistema.rs:64,81-92,160-191`, `backend/app/computador/visao.py:38` |
| Ação em lote clica no lugar errado | Lote de até 5 ações resolvido contra **uma** observação; refs de elemento `eN` só para exibição; clique no **centro da janela** | `backend/app/computador/servico.py:310-328,357`, `backend/app/computador/interface.py:31,107` |
| "Conferido" sem ter feito | "Conferida" = **o sha256 do PNG mudou** (relógio ou cursor piscando bastam) | `interface.py:47`, `servico.py:387,396-412`, `backend/app/computador/conferencia.py:25,99` |
| "Relatório Sora.xlsx" ou VS Code com o repo `sora` ficam pretos | Bloqueio por **pedaço do título** | `app/src-tauri/src/pc/regras.rs:87-111,131-145` |
| Linha presa em "executando" para sempre | `CancelledError` do ARQ não é tratado (só `except Exception`), inclusive no próprio turno do chat | `backend/workers/cadeia.py:655-707` (`_executar_com_agente`), `:966-1037` (`verificar_cadeia`), `backend/workers/equipe.py:273-403,478-500`, `workers/conversa.py:425-445` |
| Pedido some se o Redis piscar | API faz commit e **depois** enfileira, sem outbox | `backend/app/api/conversas.py:233-236,410-411`, `backend/app/api/aprovacoes.py:160,177-197` |
| **Ferramenta MCP de escrita roda sem cartão** | Ver §3.3 (bypass confirmado) | `backend/app/conectores/carregar.py:35`, `backend/app/conectores/servidores.py:229`, `backend/app/revisor/execucao.py:49-54` |

O que o plano V2 acerta (Tool Gateway, GUI Agent separado, observar → agir → conferir, baseline, CI) **não depende de trocar motor**. Este plano faz essas partes agora, na arquitetura atual, e **mede**. Se depois disso ainda faltar, o DSH entra com dados na mão e com o trabalho de hoje aproveitado (§8.3).

---

## 2. Regras para todos os agentes (valem do primeiro ao último commit)

1. **Leia o `CLAUDE.md`/`AGENTS.md` antes de tudo.** PT-BR em tudo. Logs em `log/AAAA-MM-DD.md` + `log/ONDE-PARAMOS.md`.
2. **Ramos e PRs:**
   - Tarefas **0.1 e 0.2** são commits diretos no ramo `onda3` (exceção única).
   - Daí em diante, cada tarefa tem ramo próprio `fix/…` ou `feat/…` criado a partir de `onda3`, e volta por **PR com base `onda3`**.
   - **Antes da Fase 0**, o Heitor autoriza no chat, de uma vez, o push desses ramos e a abertura de PR contra `onda3`. Sem essa autorização, parar e pedir.
   - Merge em `onda3` só com os 4 jobs do CI verdes **e** revisão cruzada aprovada (Codex revisa Claude e vice-versa).
   - Ao fim de cada gate (G0…G4), PR `onda3 → main`, que **só** é mesclado com o "ok" do Heitor no chat.
3. **Nunca:** `git reset --hard`, `git clean`, `git stash`/`stash drop`, `git checkout -- .`, `git restore .`, `git add --renormalize`, `git worktree prune`, reescrever histórico, apagar worktrees (`C:/dev/sora-e4`, `C:/dev/sora-e5`) ou ramos de backup. Deploy, `alembic upgrade head` no servidor e merge na `main` só com o "ok" do Heitor.
4. **Worktrees por agente:** o worktree principal `C:/dev/sora` (ramo `onda3`) é do **Tech Lead**. Codex e Claude trabalham cada um no seu: `git worktree add ../sora-codex -b fix/<tarefa> onda3` e `git worktree add ../sora-claude -b feat/<tarefa> onda3`, com portas próprias (`PORT`, `SORA_BACKEND_URL`, `SORA_QA_BASE`, `SORA_QA_API`, ver CLAUDE.md §7.1).
5. **`STATUS.md` na raiz** é editado **só pelo Tech Lead**, no worktree principal, em commit direto em `onda3`. Codex e Claude pedem lock de arquivo e informam resultado pelo T3 Code; o Tech Lead registra. Conteúdo: fase, tarefa, dono, ramo, commit, comando de verificação, resultado real, bloqueio, próximo passo, **locks de arquivo**.
6. **Uma mudança por área em andamento.** Duas trilhas só andam em paralelo se não tocarem os mesmos arquivos (donos em §9). Arquivo compartilhado tem um dono por vez, registrado no `STATUS.md`.
7. **Migração Alembic:** uma por PR, com `downgrade` funcional, numerada depois da última (`0027` hoje): `0028_gateway_ferramentas` (Fase 1) e `0029_outbox` (Fase 2). Lock no `STATUS.md`.
8. **`CLAUDE.md` e `AGENTS.md`** são cópias idênticas: atualizar os dois juntos, e só no PR de fechamento de cada fase (evita conflito entre PRs paralelos).
9. **Prova real:** mock só em unitário. Gate de fase precisa de teste de integração (Docker Postgres + Redis) e, quando é tela, execução no Windows real com o app de desktop. Screenshot sozinho ou resposta do modelo **não é prova**. Teste **pulado não conta** como passou.
10. **Sem segredos** em commit, log, prompt ou trace. A chave de QA fica só no `backend/.env`.
11. **Não apagar teste para passar.** Teste que quebra por mudança intencional é ajustado no mesmo PR, com a justificativa na descrição.
12. **Não apagar prompts** (nem os `v1` substituídos) nem testes antigos neste plano. Limpeza só depois do Gate de decisão, com ok do Heitor.

Comandos de verificação (rodar antes de abrir PR):

```bash
# bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest tests/unitarios -q
cd backend && SORA_MODELO_FALSO=1 uv run pytest tests/integracao/<arquivo>.py -q -rs   # Docker com Postgres e Redis
cd app && npm run build && npx oxlint && npm test
cd app/src-tauri && cargo clippy -- -D warnings && cargo test
```

```powershell
# PowerShell (Windows do Heitor)
cd backend; uv run ruff check .; uv run ruff format --check .; uv run pytest tests/unitarios -q
$env:SORA_MODELO_FALSO='1'; uv run pytest tests/integracao/<arquivo>.py -q -rs
```

---

## 3. FASE 0 — Esta semana (até 2026-12-02): proteger, religar o CI, fechar o furo, criar a rede de segurança

Ordem: 0.1 → 0.2 → (0.3, 0.4 e 0.5 em paralelo, em worktrees separados). O baseline (0.5) é medido no commit final da 0.1, **antes** de qualquer merge da 0.3.

### 3.1 Tarefa 0.1 — Commitar o trabalho de 21–22/11 (dono: Tech Lead), primeiro de tudo

Hoje há ~39 arquivos modificados (+773/−143) e ~13 não rastreados só no disco. Incluem correções que funcionam: `backend/app/llm/saude.py`, `backend/app/agentes/middleware/rastro.py`, `test_modelo_travado.py`, `test_saude_provedor.py`, prazo de 285 s em `workers/conversa.py`, exceção do Bloco de Notas em `sistema.rs`, prompts `v2`.

Passos:
1. `git status` e `git diff --stat`; anotar a lista no `STATUS.md`.
2. Conferir que nenhum arquivo tem segredo (`.env`, chaves, `settings.local.json`). Se tiver, **não** commitar e avisar o Heitor.
3. **Não mexer no `.gitattributes`.** Conferido em 2026-11-25: não há ruído de fim de linha (`--ignore-cr-at-eol` dá o mesmo diff). Se aparecer ruído, parar e perguntar.
4. Agrupar em 2–4 commits por assunto, respeitando dependências:
   - `backend/app/agentes/prompts.py` vai **no mesmo commit** que os `backend/prompts/*.v2.md` e o `bot_de_grupo.v1.md` (o `VERSOES` aponta para eles; separar quebra o carregamento).
   - `rastro.py` e `saude.py` vão junto com os arquivos que os importam.
   - Este plano (`docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`) vai num commit "Docs: plano de correções".
   - `.claude/launch.json` **fica fora** e entra no `.gitignore` (configuração local), salvo ordem contrária do Heitor.
5. Depois de **cada** commit: `uv run pytest tests/unitarios -q`. Teste que já falhava antes é anotado no `STATUS.md`, não escondido.
6. Pedir ao Heitor autorização para `git push -u origin onda3` (o ramo ainda não existe no origin; é a cópia fora da máquina).

**Pronto quando:** `git status` limpo (exceto o que for deliberadamente ignorado), SHAs no `STATUS.md`, push feito com autorização.

### 3.2 Tarefa 0.2 — Religar o CI em push e PR (dono: Tech Lead)

1. Em `.github/workflows/ci.yml`, trocar o bloco `on:` (hoje só `workflow_dispatch`) por:
   ```yaml
   on:
     push:
       branches: [main, onda3]
     pull_request:
     workflow_dispatch:
   ```
   e atualizar o comentário do topo (2026-11-25, plano de correções).
2. No job `backend-integracao`, trocar o laço `for arquivo in tests/integracao/test_*.py` por `for arquivo in tests/integracao/test_*.py tests/ponta_a_ponta/test_*.py` (os testes da 0.4 rodam 1 vez por PR).
3. Criar o job `ponta-a-ponta-repetido` com `on: schedule` (diário) + `workflow_dispatch`, que roda `uv run pytest "$arquivo" -q --count=20 -p no:cacheprovider` para cada arquivo de `tests/ponta_a_ponta/`. É o 20/20 dos gates, fora do caminho de cada PR.
4. Adicionar `pytest-repeat` com `uv add --group dev pytest-repeat` e **commitar o `backend/uv.lock`** junto (o CI usa `uv sync --frozen`).
5. Garantir `SORA_MODELO_FALSO=1` e nenhuma chave real no CI. Teste instável: anotar no `STATUS.md` e consertar; **não** desligar o job.
6. Pedir ao Heitor para religar a proteção da `main` **e** proteger `onda3` com os 4 jobs obrigatórios (GitHub → Settings → Branches). Isso é com ele.

**Pronto quando:** um PR de teste contra `onda3` dispara os 4 jobs automaticamente e todos ficam verdes.

### 3.3 Tarefa 0.3 — Fechar o bypass de aprovação do MCP (dono: Codex), segurança, prioridade máxima

**O furo (confirmado no código):**
- `backend/app/conectores/carregar.py:35` chama `carregar_ferramentas(servidores, ambiente_local=...)` **sem** `antes_de_executar`.
- `backend/app/conectores/servidores.py:229` faz `return montar_catalogo(embrulhadas, antes_de_executar=antes_de_executar)`, e `antes_de_executar` vale `None` (padrão do parâmetro em `servidores.py:202`).
- Em `backend/app/ferramentas/catalogo_preguicoso.py` (`LIMITE_DIRETO = 20` na linha 32; teste do limite na 387), com **mais de 20** ferramentas elas viram as meta-ferramentas do catálogo, e o gancho de revisão é opcional (linhas 276-277): sem gancho, executa direto.
- `backend/app/revisor/execucao.py:49-54` isenta `conectores_executar_ferramenta` do `MiddlewareRevisor`, porque supõe que o gancho do catálogo revisa.
- **Resultado:** numa **conversa supervisionada**, com 21+ ferramentas MCP, uma ferramenta de escrita (`delete_*`, `send_*`) roda **sem cartão "Precisa de você"**. Em **rotina** o furo não acontece: `carregar.py:41-42` já filtra o executor do catálogo (`pode_sem_supervisao`).

**Correção:**
1. `servidores.py:229`: devolver a lista plana `embrulhadas`. O catálogo é montado **só** na camada do agente (`ancora.py:198-318`, `_catalogo_revisado`), que já passa o gancho `antes` com o nome real da ferramenta (`ancora.py:282-308`).
2. `catalogo_preguicoso.py`: `antes_de_executar` vira argumento nomeado **obrigatório, sem padrão**, em `montar_catalogo`/`CatalogoFerramentas.executar`. Quando o catálogo é de fato montado (lista maior que `limite_direto`) e o gancho é `None`, levantar `ValueError` (falha fechada).
3. **Manter** `conectores_executar_ferramenta` em `PREFIXOS_PROPRIOS` até a Fase 1 (tirar agora faria o juiz revisar a meta-ferramenta **além** do gancho: juiz extra e cartão duplo). No lugar, um teste garante que **toda** meta-ferramenta `*_executar_ferramenta` entregue ao modelo vem de um catálogo com gancho não nulo.
4. No mesmo PR, ajustar os testes que dependem do comportamento antigo, explicando na descrição: `tests/unitarios/test_rakazo_fase1.py:184,190,247` e `tests/unitarios/test_engrenagem_pedido.py:43-44,217` (passar gancho); `tests/unitarios/test_rakazo_fase3.py:169-178` (agora lista plana). Conferir `backend/app/api/conectores.py:168` (o teste de conexão passa a mostrar os nomes reais das ferramentas; ok).
5. **Fora desta tarefa:** a confiança no **nome** da ferramenta MCP (`get_*`/`list_*` liberado em rotina) é corrigida na Fase 1 (§4.2 passo 8).

**Testes (obrigatórios no mesmo PR):**
- `tests/integracao/test_mcp_aprovacao.py` (novo). Injetar as ferramentas falsas por monkeypatch (`ferramentas_dos_conectores` não aceita `cliente=`; trocar `app.conectores.servidores.carregar_ferramentas`, que `carregar.py` importa dentro da função, ou subir `tests/integracao/auxiliares/servidor_mcp.py`). Usar um **modelo roteirizado** no teste (o modelo falso padrão não chama `delete_everything`) que chame `conectores_executar_ferramenta` com `id=delete_everything`.
  - Caso **25 ferramentas, conversa supervisionada**, papéis `pesquisador` e `individual`: deve **abrir cartão e não executar**. **Este caso falha no código antigo** e passa no novo.
  - Casos **5 ferramentas** (caminho direto) e **`sem_supervisao=True`**: testes de **regressão** (passam antes e depois).
- Unitário: montar catálogo de 25 ferramentas com `antes_de_executar=None` levanta `ValueError`.
- Unitário: `montar_agente` com 25 ferramentas MCP falsas → toda `*_executar_ferramenta` tem gancho.

**Pronto quando:** o caso de 25 ferramentas falha no commit antigo e passa no novo (anotar os dois resultados no `STATUS.md`); CI verde.

### 3.4 Tarefa 0.4 — Testes de ponta a ponta que valem para qualquer motor (dono: Codex, revisão: Claude)

Objetivo: uma **especificação executável** do comportamento que importa. Esses testes são o **gate de toda mudança** deste plano e, se o DSH vier, do DSH também.

**Regra de fronteira:** os **testes** (ações e asserções) falam **só** por HTTP, SSE e SQL. O **fixture** pode importar `workers.configuracao.WorkerSettings` e `arq.worker.Worker` para subir o worker real em processo. Nenhum teste chama função de job, middleware ou grafo diretamente.

**Passo 0 (pré-requisitos, mesmo dono):**
1. Em `backend/app/llm/falso.py`, criar gatilhos novos: `[lento:N]` (espera N s antes de responder), `[falha_provedor:500]` e `[falha_provedor:timeout]` (só o **1º** modelo da lista falha; a reserva responde) e `[falha_bot]` (um bot do grupo falha). Os gatilhos atuais continuam (`[aprovacao]`, `[pergunta]`, `[orcamento]`; obs.: `[aprovacao]` abre cartão de `propor_instrucoes`, que não tem efeito contável).
2. Ler o prazo interno e o do job de variáveis, com os padrões de hoje: `SORA_PRAZO_TURNO_S` (285) em `workers/conversa.py:425-426` e `SORA_PRAZO_JOB_S` (360) em `workers/configuracao.py:150`.
3. Ferramenta **de teste** com efeito contável (ex.: grava uma linha numa tabela de teste ou um arquivo; o teste conta por SQL), só registrada com `SORA_MODELO_FALSO=1`, para provar "rodou exatamente 1 vez".
4. `backend/tests/ponta_a_ponta/conftest.py` (a pasta já existe, só com `__init__.py`): reaproveitar `docker_disponivel`, `pytest_collection_modifyitems` e `event_loop_policy` de `tests/integracao/conftest.py` (mover para `tests/conftest.py` ou importar via `pytest_plugins`) e o fixture `mundo` de `tests/integracao/relogio_base.py`. Criar `SORA_EXIGIR_DOCKER=1`: sem Docker, **erro**, não skip.

Reaproveitar os melhores casos de `tests/integracao/test_fase_b_robustez.py`, `test_ancora_pecas.py`, `test_vela8_aprovacoes.py` e `test_vela12_retomar.py`, reescritos para falar só por HTTP/SSE/SQL.

| Arquivo | Cenário | Critério |
|---|---|---|
| `test_e2e_aprovacao.py` | pedido com efeito (ferramenta de teste) → cartão → **Permitir** → retoma | efeito **exatamente 1 vez**; `aprovacao.resolvida` + `mensagem.fim` no SSE |
| idem | **Recusar** | efeito **0 vezes**; bot avisa que não foi feito |
| idem | decidir o **cartão errado** (outro pedido/conversa/usuário) | 403/404; nada retoma |
| idem | decidir **duas vezes** (duplo clique, duas abas) | segunda decisão ignorada; efeito 1 vez |
| idem | cartão **expirado** | efeito 0; estado final explícito |
| `test_e2e_cancelamento.py` | **Parar** no meio do turno (`[lento:10]`) | turno cancelado; nenhuma linha em `executando`/`rodando`; SSE recebe o fim |
| `test_e2e_prazo.py` | `SORA_PRAZO_TURNO_S=3` + `[lento:10]` | linha em estado final (falha/interrompido) + evento final; UI não fica "pensando" |
| `test_e2e_troca_provedor.py` | `[falha_provedor:timeout]` e `[falha_provedor:500]` com reserva | resposta chega; troca aparece na linha do tempo; nada silencioso |
| idem | modelo fixo (sem reserva) falha | erro claro ao usuário, sem trocar de modelo |
| `test_e2e_rotina.py` | rotina vence; dispatcher roda 2 vezes no mesmo minuto | **um** disparo só |
| idem | webhook com mesmo `webhook-id` duas vezes | **uma** execução |
| `test_e2e_grupo.py` | grupo com 3 bots, `@todos`, `[falha_bot]` em um | os outros entregam; falha parcial explícita; Sora sintetiza |
| `test_e2e_reconexao_sse.py` | cliente cai e volta com `Last-Event-ID` | sem evento duplicado nem perdido; refresh não reexecuta |

**Pronto quando:** os 13 cenários passam **20/20** (job `ponta-a-ponta-repetido`), com `-rs` mostrando **0 skipped**, na arquitetura atual.

### 3.5 Tarefa 0.5 — Baseline medido (dono: Claude, com o Heitor no Windows)

Sem baseline não há como dizer se "funcionou" (§8).

**Antes de começar:**
- Medir no **SHA final da 0.1** (anotar em `baseline.md`), num worktree separado, antes de qualquer merge da 0.3.
- O **Heitor escolhe agora o modelo fixo com visão** (provedor/modelo/versão) usado no baseline e no §8. O mesmo modelo é usado em todas as medições.
- **Tempo do Heitor no Windows** (o Tech Lead agenda no `STATUS.md`): ~4 h baseline G, ~2 h G3, ~4 h G4, ~4 h rodada final. Cada PR do Rust precisa de `npm run desktop:build` antes de medir.
- As tarefas longas L01–L10 o Claude roda sozinho, com o modelo fixo e a chave de QA do `backend/.env`.

1. **Fixtures de tela (G01–G10)** em `docs/benchmarks/fixtures-gui.md`, tarefas genéricas:

   | ID | Tarefa | Prova obrigatória |
   |---|---|---|
   | G01 | Abrir o Bloco de Notas e escrever três linhas | texto exato no controle ou no arquivo salvo |
   | G02 | Editar um trecho, salvar (Ctrl+S) e reabrir | conteúdo confere |
   | G03 | Calculadora: operação definida | valor exibido confere |
   | G04 | Alternar entre duas janelas e voltar | janela certa em primeiro plano (HWND/processo) |
   | G05 | Ler um valor exibido em um app | valor exato |
   | G06 | 15 ações dependentes num editor | estado final conferido fora do bot |
   | G07 | Grade/controles densos: achar e alterar valores | valores conferidos |
   | G08 | Inserir e modificar objeto/estilo num app de conteúdo | arquivo salvo e inspecionado |
   | G09 | Preencher formulário local de teste | estado do fixture confere |
   | G10 | Foco muda/controle aparece tarde; recuperar | objetivo concluído sem agir no app errado |

2. **Tarefas longas (L01–L10)** em `docs/benchmarks/fixtures-longas.md`: 10 tarefas com ≥10 etapas dependentes sem tela (ler/transformar/escrever arquivo, memória, página fixture, MCP de teste, erro de ferramenta, aprovação e retomada).
3. Rodar cada caso **3 vezes** com o modelo fixo; anotar máquina, resolução e DPI. Ligar `SORA_RASTRO`.
4. Registrar em `docs/benchmarks/baseline.md`, por execução: resultado (ok / parcial / falhou / não executado), prova, duração, chamadas de modelo e de ferramenta, tokens/custo, se bateu limite e **classe da falha**:

   | Classe | Exemplo |
   |---|---|
   | `modelo` | escolheu mal, alucinou sucesso |
   | `schema` | tool call inválida, JSON quebrado, dialeto do provedor |
   | `orcamento` | bateu 20/30 ou 40/64 |
   | `prazo` | 285 s / 360 s |
   | `contexto` | estourou janela, perdeu instrução |
   | `aprovacao` | cartão não abriu, abriu duas vezes, retomou errado |
   | `transporte` | ponte desktop, Redis, long-poll |
   | `executor` | clique no lugar errado, captura ruim, árvore incompleta, foco/DPI |
   | `estado` | linha presa, evento perdido |
   | `ui` | app mostrou errado |

5. Reproduzir e documentar **3 falhas reais** que o Heitor viu (Excel, Wikipédia, Bloco de Notas de `log/2026-11-21.md` e `log/2026-11-22.md`).

**Pronto quando:** `baseline.md` tem 30 execuções de tela + 30 longas, com classe de falha, e as 3 falhas reais reproduzidas.

### Gate G0 (fim da Fase 0)
- [ ] Trabalho de 21–22/11 commitado e com push.
- [ ] CI automático e verde; `onda3` e `main` protegidas.
- [ ] Bypass MCP fechado, com o caso de 25 ferramentas provado antes/depois.
- [ ] 13 cenários de ponta a ponta 20/20, 0 skipped.
- [ ] Baseline com classes de falha, no SHA da 0.1.
- [ ] PR `onda3 → main` aberto; merge só com ok do Heitor.

---

## 4. FASE 1 — Tool Gateway (semana 2; dono: Codex, revisão: Claude)

**Objetivo:** **um** ponto de execução por onde passa **toda** ferramenta (direta, catálogo, MCP, navegador, PC, job, retomada), com política deny-by-default. Hoje a autorização depende de **como** a ferramenta foi montada (`MiddlewareRevisor` em `backend/app/agentes/middleware/revisor.py:26-65` + gancho separado em `ancora.py:282-308`), e o executor (`backend/app/ferramentas/registro.py:185-195`) não confere nada.

**Coordenação com a Fase 3 (Claude, em paralelo):** o Codex **não edita** `backend/app/computador/**`. O metadado das ferramentas do PC (quem abre o próprio cartão, texto digitado) é acrescentado pelo Claude num PR curto antes do G1. O contrato do gateway para `computador_*` é fechado entre os dois (via Tech Lead, no `STATUS.md`) antes de a Fase 3 mudar o contrato das ações.

### 4.1 Contrato

Criar `backend/app/gateway/` com:

```python
# nomes propostos; adaptar ao estilo do código
async def executar(nome: str, argumentos: dict, ctx: ContextoFerramenta) -> ResultadoFerramenta: ...

@dataclass
class ResultadoFerramenta:
    status: Literal["ok", "erro", "negado", "precisa_aprovacao", "cancelado", "prazo"]
    conteudo: Any
    erro: ErroTipado | None
    evidencia: dict | None          # o que prova o efeito (id externo, valor lido, hash)
    artefatos: list[str]
    duracao_ms: int
    efeito: Literal["nenhum", "confirmado", "incerto"]
```

`executar` faz, nesta ordem: procurar no catálogo (**ferramenta desconhecida = negado**) → validar schema → validar escopo (caminho, URL, domínio, programa) → `conferir_acao` (política + cartão) → reserva de uso único → executar com prazo e cancelamento → normalizar resultado → registrar no ledger. Identidade (`usuario_id`, `conversa_id`, `agente_id`, `chamada_id`) vem **só** do `ContextoFerramenta` do host, nunca dos argumentos do modelo. Marca idempotente por `chamada_id` para nunca abrir dois cartões para a mesma chamada.

### 4.2 Passos
1. `registro.criar_ferramentas`, o catálogo preguiçoso e o embrulho MCP passam a chamar `gateway.executar`. O `MiddlewareRevisor` fica **só** para eventos de UI/rastro (não decide mais nada). Para o MCP chegar ao gateway com contexto, passar `ContextoFerramenta` por `ferramentas_dos_conectores` → `carregar_ferramentas` → `embrulhar` (`servidores.py:162-195`; hoje só recebem `usuario_id`).
2. Remover as listas de permissão por nome (`CUIDAM_DO_PROPRIO_CARTAO`, `PREFIXOS_PROPRIOS` em `revisor/execucao.py:46-54`). Ferramenta que abre o próprio cartão (`criar_agente`, `propor_grupo`, navegador com domínio, PC com programa) declara isso **no metadado do catálogo**, e o gateway respeita.
3. **Uma tabela só** de papel → ferramentas, em `backend/app/ferramentas/permissoes.py` (módulo sem dependências; `montagem.py:21` já importa `FERRAMENTAS_NAVEGADOR` de lá). Apagar a cópia de `montagem.py:36-70` e importar. **Atenção:** as duas tabelas diferem hoje (em `montagem.py` o papel `individual` tem navegador e `navegador_pedir_senha`; em `permissoes.py` não). Escolher a versão de `montagem.py` (é a que roda) e conferir o efeito em `api/agentes.py:24`, `api/compartilhar.py:373`, `bot_por_descricao.py:8` e `rascunhos_bot.py`. Unificar também `FERRAMENTAS_COM_CERCA` (`middleware/cerca.py:19` e `permissoes.py:58`). Teste que falha se alguma das duas for definida em mais de um módulo.
4. **Política de envio e destrutivo** (`revisor/execucao.py:389-429`, `revisor/decisoes.py:301-320`): quando `e_envio(acao)` ou ação destrutiva, **sempre** abre cartão. O juiz LLM só pode **endurecer** (pedir cartão), nunca aprovar sozinho. "Acesso total" (`aprova_sozinho`) também não aprova envio/destrutivo sem política explícita por conector.
5. **Uso único e vínculo com argumentos:** coluna `acao_hash` (sha256 de ferramenta + argumentos canônicos + turno) na tabela de aprovações (`backend/app/modelos/tabelas.py:416-432`), com **índice único parcial `WHERE status = 'pendente'`** (um total quebraria "Recusar e propor de novo") + índice comum para busca. Procurar o cartão pelo hash, não por igualdade de JSONB. Estender a reserva que hoje só existe para envio (`execucao.py:446-473`) a **toda** ferramenta não-LIVRE. Argumento mudou = cartão novo.
6. **Texto digitado no PC:** o cartão mostra o texto real (mascarando só segredo detectado) ou guarda o hash do texto real, para que outro texto nunca case com a aprovação (`execucao.py:128-178`).
7. **Ledger de invocações:** tabela `invocacoes_ferramenta` (`turno_id`, `chamada_id`, `ferramenta`, `acao_hash`, `efeito`, `id_externo`, `criado_em`, `terminado_em`). Antes de executar ferramenta com efeito, se já existe linha com `efeito in (confirmado, incerto)` para a mesma chamada → **não reexecuta**: devolve o resultado gravado ou pede reconciliação.
8. **Classificação de risco MCP por conector:** tabela `politicas_ferramenta_mcp` (`usuario_id`, `conector_id`, `ferramenta`, `politica`, `confirmada_pelo_usuario`, `atualizado_em`). Ferramenta nova entra como `REVISOR`; o nome só **sugere** (`revisor/politica.py:172-190,268-292`). Rotina sem supervisão só usa ferramenta **confirmada** pelo usuário (hoje `carregar.py:41-42` libera `get_*`/`list_*` pelo nome). Inclui UI em `app/src/components/settings/` (lista de ferramentas por conector: Leitura / Precisa de você / Liberada em rotina), **exceção aprovada** ao "fora do escopo" de textos do app; dono da UI: Claude, contrato da API: Codex.
9. **MCP mais confiável** (`servidores.py:218-224`, `carregar.py:34-40`): carregar servidores em paralelo (`asyncio.gather`, prazo por servidor); servidor fora do ar aparece como indisponível para o modelo e na UI (não some em silêncio); uma sessão por servidor por turno em vez de `initialize` a cada chamada; fixar a versão de `langchain-mcp-adapters` no `pyproject.toml` (hoje `>=0.2,<1`).
10. **Migração `0028_gateway_ferramentas`**: `aprovacoes.acao_hash` + índices, `invocacoes_ferramenta`, `politicas_ferramenta_mcp`. `downgrade` funcional.

### 4.3 Testes obrigatórios (bloqueiam o gate)
`tests/integracao/test_gateway.py`: ferramenta desconhecida negada · argumentos alterados depois da aprovação exigem cartão novo · cartão de outro usuário/conversa rejeitado · cartão expirado rejeitado · aprovação revogada no meio · política indisponível = nega · envio com juiz dizendo PERMITIR ainda abre cartão · "Acesso total" com envio abre cartão · retry do job não repete efeito confirmado · efeito incerto não é repetido às cegas · nenhuma chamada a ferramenta fora do gateway (teste de varredura do código) · **`test_gateway_sem_cartao_extra`**: em leituras (`buscar_web`, `ler_pagina`, `navegador_observar`, MCP já classificado como leitura, `computador_observar`) o número de linhas criadas em `aprovacoes` por turno é 0, como antes. Mais os 13 de ponta a ponta 20/20, comparando a contagem de `aprovacao.pedida` com a do G0.

### Gate G1
- [ ] Toda execução de ferramenta passa por `gateway.executar` (teste de varredura).
- [ ] Testes do §4.3 verdes; ponta a ponta 20/20, 0 skipped.
- [ ] Nenhum cartão a mais em leitura (`test_gateway_sem_cartao_extra` + contagem igual ao G0).

---

## 5. FASE 2 — Prazos por função, outbox e duas filas (semana 3; dono: Codex)

Começa depois do G1 (para não mexer em `workers/` junto com o gateway). Anda em paralelo à Fase 3 (arquivos diferentes).

### 5.1 Higiene de cancelamento e prazo
1. Em **todos** estes pontos, tratar cancelamento e prazo como caminho terminal:
   - `workers/conversa.py:425-445` (em volta de `montar_e_rodar_agente`, garantindo `_fechar_turno_vivo`). O padrão atual só cobre `Exception` e **não serve de modelo** para cancelamento;
   - `_executar_com_agente` (`workers/cadeia.py:655-707`, chamado por `executar_etapa` em `workers/cadeia.py:747`);
   - `verificar_cadeia` (`workers/cadeia.py:966-1037`);
   - `_turno_real` (`workers/equipe.py:273-403`) e `_concluir_turno` (`workers/equipe.py:478-500`).
   ```python
   try:
       async with asyncio.timeout(prazo_interno):
           ...
   except (asyncio.CancelledError, TimeoutError):
       await marcar_interrompido(...)   # grava estado final + publica evento
       raise
   ```
2. **Prazo por função** no ARQ (`arq.worker.func(<função>, timeout=...)`) em vez do `job_timeout = 360` global (`workers/configuracao.py:150`), lido das variáveis da 0.4 com os padrões atuais. Tabela de prazos documentada no próprio arquivo: chat, etapa de cadeia, manutenção e o job de GUI `operar_computador` da **Fase 4** (prazo interno 600 s, `timeout` do ARQ 660 s; a trava do PC precisa de TTL ≥ 660 s).
3. `reconciliar_travados` (`workers/travados.py:69-113`, cron de 15 s) passa a chamar também `recuperar_equipe_apos_queda` (`workers/equipe.py:122`), que hoje só roda em `ao_iniciar` (`workers/configuracao.py:88`). Ela já ignora itens com batimento vivo.
4. **Desligamento gracioso:** ao parar o worker, parar de pegar jobs e esperar os em andamento até o prazo; o que sobrar é marcado `interrompido` e retomado pelo reconciliador **consultando o ledger** (Fase 1), nunca repetindo efeito.

### 5.2 Outbox transacional
1. Tabela `outbox` (`id`, `fila` (`agentes`|`manutencao`), `tipo_job`, `argumentos`, `chave_job` estável, `adiar_ate` (nulo), `criado_em`, `enviado_em`, `tentativas`). Migração `0029_outbox`.
2. Listar **todos** os pontos que enfileiram: `grep -rnE "enqueue_job|enfileirar\(" backend/app backend/workers`. Hoje: `enqueue_job` em `api/conversas.py` (234, 326, 411, 413, 589, 704), `api/aprovacoes.py` (177, 184, 192), `api/perguntas.py` (99, 107), `api/computador.py:110`, `api/navegador.py:261`, `api/rotinas.py:271`, `workers/fila.py:76` (com `_defer_until`); e `enfileirar(` (de `workers/fila.py:66`) em `api/auth.py:145`, `api/canais.py:202`, `api/canais_empresa/sugestoes.py:148`, `api/canais_empresa/webhooks.py:61`, `api/equipe.py:180`, `api/ganchos.py:102`, `api/pecas.py:366`.
3. Criar a interface `OperationalScheduler` (`submeter`, `cancelar`, `status`, `agendar`) em `backend/app/filas/agendador.py`, implementada sobre o ARQ. **Todos** os pontos acima passam por ela. Rotas que fazem commit gravam na `outbox` **na mesma transação**.
4. **Exceção:** RPC síncrona `api/navegador.py:261` (enfileira `abrir_aba_de_perfil` e espera `job.result(timeout=60)`): `submeter(..., aguardar_resultado=True)` enfileira direto, sem outbox (o usuário está esperando e não há commit a proteger). Fica na lista de exceções do teste de varredura.
5. Cron `despachar_outbox` (a cada 2 s, fila `manutencao`) enfileira com `_job_id = chave_job`, respeita `fila` e `adiar_ate`, marca `enviado_em`. Reenfileirar com a mesma chave é inofensivo.

### 5.3 Duas filas
1. `WorkerSettingsAgentes` (`queue_name='arq:agentes'`, sem crons, com navegador e checkpointer no startup; recebe `abrir_aba_de_perfil` porque o navegador está lá) e `WorkerSettingsManutencao` (`queue_name='arq:manutencao'`, **todos** os `cron_jobs`, sem Playwright). Crons em um só lugar (não duplicar).
2. Compose (`infra/docker-compose.yml:62`, hoje `arq workers.configuracao.WorkerSettings`): dois serviços, `arq workers.configuracao.WorkerSettingsAgentes` e `arq workers.configuracao.WorkerSettingsManutencao`.
3. **Dev no Windows:** `uv run python -m workers` **sem argumento** passa a rodar **os dois** workers no mesmo processo (`asyncio.gather`); `--fila agentes|manutencao` roda só um. (Hoje `workers/__main__.py` não aceita argumento.) Documentar no README e no CLAUDE.md §7.
4. Semáforo por usuário no despacho da fila `agentes` (Redis), para um usuário não ocupar todos os `max_jobs`.

### 5.4 Testes
`test_e2e_prazo.py` e `test_e2e_cancelamento.py` continuam verdes · matar o worker no meio do job → reconciliador fecha a linha em ≤ 30 s · Redis fora no commit → job sai pela outbox quando o Redis volta · dez jobs longos na fila `agentes` não atrasam o reconciliador · usuário A com 10 pedidos não bloqueia o usuário B · teste de varredura: só `app/filas/agendador.py` chama `enqueue_job` (exceções listadas).

### Gate G2
- [ ] Zero linhas presas em `executando`/`rodando` depois de timeout, cancelamento ou queda (teste).
- [ ] Nenhum enfileiramento fora da `OperationalScheduler` (teste de varredura).
- [ ] Dois workers no Compose e `python -m workers` rodando os dois no dev local, documentado.

---

## 6. FASE 3 — Computador: captura por janela, refs com versão e conferência real (semanas 2–3; dono: Claude)

Anda **em paralelo às Fases 1 e 2** (ver coordenação no §4). Arquivos: `app/src-tauri/src/pc/**`, `backend/app/computador/**`, `app/src/desktop/**`, `backend/prompts/computador_pc.*`.

O executor Rust **continua** e **nenhuma** destas proteções sai (o Codex confere no review):
- tarja de pixels de janelas bloqueadas antes da imagem sair do PC (`sistema.rs:160-226,367-384`);
- rechecagem da janela da frente a cada passo, e de campo de senha/programa depois de tecla que muda o foco, a cada 8 caracteres (`regras::CONFERIR_A_CADA`, `regras.rs:806`) e quando a janela muda (`mod.rs:638-684`);
- encerramento de processo bloqueado aberto pelo bot (`mod.rs:553-583`);
- pausa pela **entrada física, mouse e teclado** (ganchos `WH_MOUSE_LL`/`WH_KEYBOARD_LL` em `borda.rs`).

### 6.1 Captura
1. Novo modo de observação **`janela`** em `sistema.rs`: captura só o HWND alvo (`DWMWA_EXTENDED_FRAME_BOUNDS`) em resolução quase nativa (lado maior até ~1568 px, configurável por modelo), no **monitor da janela**, não só no principal (`sistema.rs:600-641`).
2. Nova operação **`zoom`** (retângulo dentro da janela) para texto pequeno. A tarja continua aplicada no recorte.
3. A observação devolve: `geracao`, HWND, PID/executável, tamanho físico, escala/DPI, monitor.
4. Backend: `backend/app/computador/visao.py:38` (`LARGURA_MAXIMA_VISAO=1280`) passa a respeitar o limite do modelo.

### 6.2 Árvore de acessibilidade
1. Coletar o HWND em primeiro plano **e** as janelas popup/possuídas do mesmo PID (menus `#32768`, combos, diálogos do Office), hoje fora (`sistema.rs:837`, `alvo_em_foco()`).
2. Manter controles `Custom`/`Group`/`Pane` quando têm nome ou padrão Invoke/Value (`sistema.rs:801-832`).
3. **Refinar** a prioridade que já existe em `regras::escolher_elementos` (`regras.rs:778-798`, chamada em `sistema.rs:939`; candidatos até `MAX_CANDIDATOS=3_000` em `sistema.rs:67`, saída `MAX_ELEMENTOS=250` em `sistema.rs:65`): hoje ela já põe foco e valor primeiro e o resto na ordem do documento. Acrescentar "interativo visível" antes dos não interativos e alinhar com o corte do Python (`pc_usuario.py:142`, `MAX_ELEMENTOS=400`). **Não reescrever** a função.
4. Valor do documento em foco até ~2 000 caracteres: hoje cortado em `sistema.rs:919` (200), `sistema.rs:926` (`GetText(200)`) e `pc_usuario.py:380` (`_limpo(valor, 200)`). (`sistema.rs:909` é o corte do **nome**, 120; manter.)

### 6.3 Refs com versão (acabar com clique em coordenada velha)
1. **Pré-requisito:** emitir `runtime_id` UIA por elemento em `sistema.rs::arvore` (`sistema.rs:907-942`) e incluir o campo na lista de campos aceitos em `pc_usuario.py:368-383` (hoje só ref/papel/nome/centro/valor/estados; `ref` cortada em 12 caracteres na linha 371; aumentar).
2. Estender o formato já versionado `@cN:jM` (regex `_REF` em `interface.py:304`, `ler_ref` em `interface.py:318-322`) para aceitar também `@cN:eM` (elemento). A checagem de geração **já existe** para janela (`servico.py:310-314`, lança `ErroFerramenta`): estender para elemento e devolver o código `ref_vencida`.
3. O Rust **relocaliza** o elemento pelo `runtime_id` (ou nome+papel em `ElementFromPoint`) antes de clicar; se mudou ou sumiu → `ref_vencida`.
4. Toda ação leva `geracao`, HWND esperado e tamanho de tela da observação. O Rust recusa se a tela mudou de tamanho/escala ou se a raiz de `WindowFromPoint` não é o HWND esperado (`mod.rs:612-632`).
5. **Lote:** só a primeira ação pode ser de ponteiro; ações de ponteiro seguintes exigem observação nova (`servico.py:357`). Digitação e teclas independentes podem ir em lote.
6. **Nunca clicar no centro da janela** para focar (`servico.py:327-328`): focar por HWND (`trazer_para_frente`) e conferir `foreground == hwnd`.
7. Trocar por **espera por condição** (primeiro plano = HWND, foco UIA mudou, elemento estável), com prazo, **só** `sistema.rs:583` (350 ms em `afastar_a_sora`) e `sistema.rs:1166-1178` (150/300/400 ms ao abrir programa). **Não mexer** no ritmo entre eventos de `mod.rs:685-693`: os 28 ms por caractere no Bloco de Notas evitam letras perdidas no WinUI; o resto é cadência do `SendInput`.
8. **Versão do protocolo:** campo `versao_protocolo` no pedido e na resposta da ponte do PC. Backend novo com desktop antigo → erro claro "Atualize o app de desktop", nada é executado.
9. Prompt: criar `backend/prompts/computador_pc.v3.md` (refs `@cN:eM`, `esperado`, zoom) e subir `VERSOES["computador_pc"]` para 3 em `backend/app/agentes/prompts.py`. Não apagar o v2.

### 6.4 Conferência real
1. Cada ação pode levar `esperado` (ref do elemento + valor/nome/estado esperado, ou janela/programa esperado). Depois da espera estável, o Rust relê **aquele** elemento e devolve `conferido` ou `divergente` com o valor lido.
2. "Conferida" passa a ser **por ação contra o próprio `esperado`**, não "algum PNG mudou no turno" (`interface.py:47`, `servico.py:387`, `conferencia.py:25,99`).
3. Leitura de texto: normalizar `\r\n`/`\n`, ler o intervalo completo do documento em foco (ou `FindText`), não `GetText(200)`. Substituir o caso especial do Bloco de Notas (`servico.py:396-412`) pelo mecanismo geral.

### 6.5 Bloqueio por identidade, com falha fechada
1. `regras.rs:87-145`: **o título com "sora" continua bloqueando em qualquer processo**, **exceto** numa lista explícita de editores de documento (`excel.exe`, `winword.exe`, `powerpnt.exe`, `code.exe`, `notepad.exe`), onde vale o executável. Em navegador, se a barra de endereço não puder ser lida (PWA/app mode), **bloqueia**. "devtools" e títulos de macro/VBA seguem como hoje, restritos a navegadores e Office. (Não afrouxar: a Sora em PWA ou num navegador fora da lista não pode ficar clicável pelo bot, senão ele aprova os próprios cartões.)
2. Depois que a regra geral cobrir, tirar a exceção especial do Bloco de Notas inteira: `sistema.rs:516-535`, campo `AlvoJanela.bloco_de_notas_oficial` (`regras.rs:150`), parâmetro de `titulo_bloqueado` (`regras.rs:133-138`) e a chamada em `sistema.rs:840`.
3. Manter o teste de paridade Rust↔Python das regras.

### 6.6 Testes
`cargo test` com casos novos: "Relatório Sora.xlsx" em `excel.exe` **não** bloqueia · PWA da Sora em `msedge` sem barra **bloqueia** · Brave com aba "Sora" **bloqueia** · ref vencida recusada · lote com ponteiro dependente recusado · desktop com `versao_protocolo` antiga recusado. Fixtures G01–G05 no Windows real, 3× cada, comparadas com o baseline (desktop recompilado com `npm run desktop:build`).

### Gate G3
- [ ] Nenhuma proteção do Rust removida (lista acima, conferida pelo Codex).
- [ ] G01–G05 sem regressão contra o baseline; zero ação em app errado; zero "conferido" falso.

---

## 7. FASE 4 — GUI Agent como job próprio (semana 4; dono: Claude)

Depende de G1 (gateway), G2 (prazo por função, `OperationalScheduler`) e G3. Mexe em arquivos do Codex (`workers/`, `montagem.py`, `limites.py`, `revisor/`): pedir cada lock ao Tech Lead no `STATUS.md`.

### 7.1 O que muda
Hoje o bot do chat faz cada observar/clicar/conferir dentro do próprio turno (`workers/conversa.py:195,233-235`; `montagem.py:278-330`). Depois:

1. O chat **não tem mais** ferramentas `computador_*` diretas. Ele ganha **uma**:
   ```
   usar_computador(objetivo: str, alvo: "pc_usuario" | "virtual", apps: list[str], criterio_de_sucesso: str)
   ```
   `alvo` **obrigatório** (hoje o padrão silencioso é `"virtual"`, `backend/app/computador/ferramentas.py:42,53`).
2. `usar_computador` enfileira (pela `OperationalScheduler`) o job `operar_computador` e **devolve na hora** `{"status": "enfileirado", "job_id": ...}`. O turno do chat termina normalmente e o chat fica livre para outras mensagens.
3. O job `operar_computador` roda com:
   - papel novo `operador_pc` em `permissoes.FERRAMENTAS_POR_PAPEL` (só ferramentas de computador + `falar` de progresso);
   - prompt novo `backend/prompts/operador_pc.v1.md` + entrada em `VERSOES`;
   - `thread_id` próprio (`computador:{turno_id}`) e checkpoint próprio;
   - **orçamento próprio:** 60 ações **ou** 10 min (ponto de partida; ajustar pelo baseline, nunca tirar o limite);
   - prazo do job: interno 600 s, ARQ 660 s (§5.1);
   - **trava do PC:** estender a que já existe (`CanalPc.pegar_vez`/`soltar_vez`, `backend/app/computador/pc_usuario_canal.py:295-331`, chave `pc:vez:{usuario}`, hoje por usuário e sem fencing) com **token de fencing**, chave por dispositivo e TTL ≥ 660 s. **Não** criar uma segunda trava.
4. Quando o job termina, ele enfileira `retomar_conversa` com o resultado normalizado como mensagem de sistema **cercada** (dado, não instrução), na thread da conversa:
   ```json
   {"status": "ok|parcial|falhou|precisa_aprovacao", "motivo": "...", "prova": {...}, "artefatos": [...], "efeitos": {"confirmados": [...], "incertos": [...]}}
   ```
   Durante o job, o chat recebe progresso **resumido** (eventos `passo`), não cada screenshot nem cada árvore.
5. **Parar** no chat cancela o job (propagação até o Rust soltar teclas e parar). Dispositivo offline ou tela bloqueada → `precisa_aprovacao`/pausa explícita, nunca troca para outro dispositivo.
6. **Modelo falso:** roteiro para o papel `operador_pc` em `backend/app/llm/falso.py` (observar → agir → conferir → resultado; hoje papel desconhecido devolve só "um texto de exemplo") e um dispositivo PC falso nos testes.

### 7.2 Modelo com visão fixo
1. No job `operar_computador`, **toda** entrada da lista de modelos precisa ter `Capacidade.VISAO`: tirar `completar_sem_visao=True` desse caminho (`agentes/visao.py:319-328`); reservas de outro provedor só se tiverem visão (`visao.py:208-222`).
2. Sem modelo com visão, ou modelo fixo cego (`visao.py:255-259`) → **não começa**: cartão "Este bot precisa de um modelo que enxerga a tela".
3. Modelo **fixo durante o job**; troca só por falha, sempre para outro com visão, e aparece na linha do tempo.
4. Visão decidida por `(provedor_id, modelo)` do catálogo, não pelo nome (`backend/app/computador/visao.py:232`).

### 7.3 Limites por papel (vale para todos, não só GUI)
1. `limites.py:57`: limite por **papel/tipo de job**, não por "tem ferramenta de navegador/computador". Desfazer o efeito da mudança local em `montagem.py:51` que deu 40/64 a todo turno da Sora.
2. Chamadas das meta-ferramentas do catálogo (`conectores_buscar/carregar`) **não contam** no teto de ferramentas; conta a execução real.
3. Trocar `exit_behavior="error"` por `"end"` em `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware` (`limites.py:101-103`). O `MiddlewareAvisoDeUltimoPasso` **já existe** (`limites.py:78-90`, ligado na 104): não criar outro. Ajustar `workers/conversa.py:443-452` para tratar o fim por limite como entrega parcial, não como erro.
4. Toda batida de limite vai para o rastro, para calibrar pelo baseline.

### 7.4 Juiz por clique
O juiz LLM de `computador_agir` (que entra em `REVISADAS`, `revisor/politica.py:137`; chamado em `revisor/execucao.py:422-426`) vira **política determinística**, **estendendo** o que já dispensa o juiz: `teclado_local.dispensa_juiz` (`backend/app/computador/teclado_local.py:54`, usado em `execucao.py:407-414`; hoje só digitar/teclas de edição/rolar em editores locais) e `regra_permite` (`execucao.py:415-421`). Regra: programa já aprovado no cartão daquele programa → clique permitido; ação privilegiada (UAC, configurações sensíveis, campo de senha) → bloqueio, como hoje. Edita `revisor/` (dono Codex): pedir o lock.

### 7.5 Testes
Ponta a ponta com modelo falso + PC falso: chat pede tarefa de tela → job separado → chat responde outra mensagem durante → resultado volta pela `retomar_conversa` · Parar cancela o job · sem modelo com visão → cartão, nada roda · bateu 60 ações → `parcial` com o que foi feito · segundo bot tentando o PC durante o job → espera ou recusa (trava). G01–G10 no Windows real, 3× cada.

### Gate G4
- [ ] Nenhum clique no loop do chat (teste de varredura: papel do chat não tem `computador_*`).
- [ ] G01–G10 rodados e comparados com o baseline.

---

## 8. Gate de decisão: "funcionou?" (até 2026-12-30)

Aqui o Heitor decide se segue na arquitetura atual ou ativa o plano V2. Os critérios estão fixados **agora**, antes dos resultados, e não mudam depois para forçar aprovação.

### 8.1 Critérios (mesmo modelo fixo, máquina e fixtures do baseline)

| Área | Funcionou se… |
|---|---|
| Tela (G01–G10, 3× cada = 30 execuções) | **≥ 24/30** conferidas com prova **e** ≥ 8/10 tarefas com maioria de sucesso **e** zero ação em app errado **e** zero "fiz" sem prova |
| Tarefas longas (L01–L10, 3× cada) | **≥ 90%** concluídas com prova **ou** **+15 pontos** sobre o baseline |
| Aprovação | 13 cenários de ponta a ponta **20/20**; zero efeito sem cartão; zero efeito duplicado |
| Estado | zero linha presa depois de timeout/cancelamento/queda |
| Segurança | bypass MCP fechado; testes do gateway verdes |

### 8.2 Se reprovar: qual motor trocar (pela **classe da falha** que sobrou)

Comparar as falhas restantes com o `baseline.md`:

| Falhas que sobraram são sobretudo… | Então se justifica |
|---|---|
| `modelo`, `contexto`, `schema` no loop (planejamento ruim, loop de ferramenta, perda de instrução) mesmo com limites certos | **DeepSeek Harness** no lugar do LangGraph |
| `executor` na tela (UIA não alcança, ação não suportada no Windows) | **Cua Driver** como executor alternativo atrás do mesmo contrato de ação |
| `prazo`, `estado`, `transporte` de filas (jobs longos, justiça entre usuários, filhos/dependências) | **Hatchet** no lugar do ARQ |
| espalhadas entre várias | plano V2 completo, se o Heitor decidir |

A decisão é do **Heitor**. Se for o V2 completo, o `SORA_V2_PLANO_FINAL_SEM_LEGADO.md` volta a valer, com os ajustes do §8.3.

### 8.3 O que é aproveitado se o DSH/V2 vier (nada deste plano é jogado fora)

| Feito aqui | Vira no V2 |
|---|---|
| `gateway.executar` + ledger + `acao_hash` (Fase 1) | o **Tool Gateway** do §5 do V2, pronto; o DSH chama ferramentas por ele |
| 13 testes de ponta a ponta (Fase 0) | gate de paridade: o DSH tem de passar nos mesmos testes |
| `OperationalScheduler` (Fase 2) | troca-se só a implementação ARQ → Hatchet |
| `usar_computador` + resultado normalizado (Fase 4) | o contrato do GUI Agent do §6.2 do V2 |
| Refs com versão, `esperado`, captura por janela (Fase 3) | requisitos do §6.3 do V2; o Cua tem de igualar |
| Baseline + fixtures G/L (Fase 0) | a comparação antes/depois que o V2 exige |
| Outbox (Fase 2) | o outbox do §12.3 do V2 |

**Antes de qualquer código do DSH** (pesquisa externa de 2026-11-25; conferir de novo na versão escolhida):
1. **Não** usar o perfil `sdk-minimal` como está: ele traz shell persistente (bash/pwsh) e `danger-full-access`. Criar perfil próprio **sem shell, sem filesystem nativo, sem instalação de plugin**, com pedido de aprovação ligado, e provar que as ferramentas nativas saíram.
2. **Desligar o envio do log de sessão para a DeepSeek** (ligado por padrão) e provar com teste de saída de rede. Sem isso, viola o BYOK local e a LGPD.
3. Pacote Python `deepseek-harness-sdk` com versão e hash fixos; **não** confundir com o pacote `deepseek-harness` do PyPI, que é de terceiros.
4. DSH é pré-1.0 (só tags alpha/rc). Provar que ele **pausa e retoma** como o "Precisa de você" faz hoje com `interrupt()` + checkpointer, antes de desligar o LangGraph.
5. Entrar atrás de uma interface `HarnessBridge`, com o LangGraph como reserva até passar nos 13 testes e nas fixtures. Recomendação forte: trocar **um motor por vez**.

**Cua:** só o binário MIT do driver, com checksum (nunca `irm | iex`); **não** usar `cua-perception`/`cua-som` (AGPL) nem componentes FSL. A tabela de suporte do próprio projeto marca atalhos de teclado em segundo plano como indisponíveis no Windows: provar G01/G02 (Ctrl+S) primeiro, e provar que as proteções do §6 continuam.
**Hatchet:** o SDK v2 está em alpha; escrever código assíncrono compatível com v2 e confirmar se uma espera durável ocupa vaga de worker.

---

## 9. Equipe, donos e ordem

| Semana | Codex (backend) | Claude (desktop/GUI) | Tech Lead |
|---|---|---|---|
| 1 (até 2026-12-02) | 0.3 bypass MCP · 0.4 ponta a ponta | 0.5 baseline (com o Heitor no Windows) · revisa 0.3/0.4 | 0.1 commit · 0.2 CI · `STATUS.md` · G0 |
| 2 | Fase 1 Tool Gateway | Fase 3 (captura, árvore) · PR do metadado do PC para o gateway · UI da classificação MCP · revisa Fase 1 | G1 |
| 3 | Fase 2 prazos/outbox/filas | Fase 3 (refs, conferência, regras) | G2, G3 |
| 4 | revisa Fase 4 · ajustes | Fase 4 GUI Agent | G4 |
| até 2026-12-30 | rodada final L01–L10 | rodada final G01–G10 no Windows (com o Heitor) | relatório do Gate de decisão (§8) ao Heitor |

**Donos de arquivo** (um por vez; trocar só via `STATUS.md`):

| Arquivos | Dono |
|---|---|
| `backend/app/gateway/**`, `backend/app/revisor/**`, `backend/app/conectores/**`, `backend/app/ferramentas/registro.py`, `backend/app/ferramentas/catalogo_preguicoso.py`, `backend/app/ferramentas/permissoes.py`, `backend/app/agentes/ancora.py`, `backend/app/agentes/middleware/revisor.py`, `backend/app/agentes/middleware/cerca.py`, `backend/app/llm/falso.py` | Codex |
| `backend/workers/**` (inclui `cadeia.py`, `equipe.py`, `conversa.py`, `configuracao.py`, `travados.py`), `backend/app/filas/**`, `backend/app/api/**` (enfileiramento), `backend/app/orquestrador/**`, `infra/**` | Codex (Fase 4: Claude pede o lock) |
| `backend/app/computador/**`, `backend/app/agentes/visao.py`, `app/src-tauri/src/pc/**`, `app/src/desktop/**`, `app/src/components/settings/**` (UI da classificação MCP), `backend/prompts/computador_pc.*`, `backend/prompts/operador_pc.*` | Claude |
| `backend/app/agentes/montagem.py`, `backend/app/agentes/middleware/limites.py`, `backend/app/agentes/prompts.py` | Codex na Fase 1; Claude na Fase 4 |
| `backend/migrations/versions/**`, `backend/app/modelos/tabelas.py` | quem estiver com o lock no `STATUS.md` |
| `.github/**`, `STATUS.md`, `docs/benchmarks/**`, `CLAUDE.md`, `AGENTS.md`, `log/**` | Tech Lead |

**Fora do escopo (não fazer agora):** trocar LangGraph, ARQ ou executor Rust; instalar DSH/Hatchet/Cua; apagar prompts (inclusive `v1`) ou testes antigos; mudar visual, mascote ou textos do app (exceto a UI de classificação MCP do §4.2 passo 8).

**Inventário real (corrigindo o V2):** 66 ferramentas registradas, 24 prompts ativos (os outros arquivos são versões `v1` substituídas, que ficam), 26 classes de middleware, 25 funções de job + 9 crons (33 entradas).

---

## 10. Prompts para iniciar

### Tech Lead (T3 Code)

Leia `CLAUDE.md` e `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md` inteiros. Este é o único plano vigente; o `SORA_V2_PLANO_FINAL_SEM_LEGADO.md` está suspenso até o Gate de decisão (§8). Você coordena no worktree principal `C:/dev/sora` (ramo `onda3`). Antes de tudo, me peça no chat: (1) autorização para o push de `onda3` e dos ramos de tarefa e para abrir PRs contra `onda3`; (2) o modelo fixo com visão do baseline. Depois: crie o `STATUS.md` (só você edita), faça a 0.1 (commitar o trabalho local de 21–22/11, sem reset, clean, stash, restore ou renormalize, conferindo que não há segredo, seguindo os agrupamentos do §3.1) e a 0.2 (CI em push/PR, `tests/ponta_a_ponta` no job de integração, job diário 20×, `pytest-repeat` + `uv.lock`). Crie os worktrees `../sora-codex` e `../sora-claude` e distribua a 0.3/0.4 para o Codex e a 0.5 para o Claude. Uma mudança por área, PR pequeno com CI verde, revisão cruzada, locks de arquivo no `STATUS.md`. Não instale DSH, Hatchet ou Cua; não remova LangGraph, ARQ nem o executor Rust. Peça meu ok antes de merge na `main`, deploy, `alembic upgrade` no servidor ou qualquer coisa irreversível. Ao fim de cada fase, me entregue: commits, comandos rodados, resultados reais, pendências e a decisão do gate; atualize `log/` e o bloco do Heitor no `CLAUDE.md`/`AGENTS.md`.

### Codex

Leia `CLAUDE.md`, `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md` e `STATUS.md`. Trabalhe no worktree `../sora-codex`, um ramo por tarefa a partir de `onda3`. Você é dono do backend: tarefa 0.3 (bypass de aprovação do MCP, §3.3: o caso de 25 ferramentas numa conversa supervisionada falha antes e passa depois; mantenha a isenção de `PREFIXOS_PROPRIOS` até a Fase 1), 0.4 (passo 0 + 13 testes de ponta a ponta só por HTTP/SSE/SQL, 20/20, 0 skipped), depois a Fase 1 (Tool Gateway, §4, migração 0028) e a Fase 2 (prazos, outbox, duas filas, §5, migração 0029). Peça locks e informe resultados ao Tech Lead; não edite `backend/app/computador/**`. Nunca relaxe uma proteção para um teste passar. Ferramenta com efeito nunca roda sem passar pelo gateway.

### Claude Code

Leia `CLAUDE.md`, `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md` e `STATUS.md`. Trabalhe no worktree `../sora-claude`, um ramo por tarefa a partir de `onda3`. Você é dono do computador e do desktop: tarefa 0.5 (baseline G01–G10 com o Heitor no Windows e L01–L10 com o modelo fixo, no SHA da 0.1, com classes de falha), a Fase 3 (§6: captura por janela, popups na árvore, refs `@cN:eM` com `runtime_id`, conferência por `esperado`, bloqueio por identidade com falha fechada, `versao_protocolo`, prompt `computador_pc.v3`) e a Fase 4 (§7: GUI Agent como job próprio, `usar_computador` que devolve na hora, resultado pela `retomar_conversa`, orçamento próprio, modelo com visão fixo, trava existente com fencing). Não remova nenhuma proteção do Rust (tarja, rechecagem por passo, encerramento de processo bloqueado, pausa por mouse **e** teclado) e não mexa no ritmo de `mod.rs:685-693`. Prova é execução real no Windows, não screenshot isolado nem resposta do modelo. Peça o lock ao Tech Lead antes de mexer em `workers/`, `montagem.py`, `limites.py` ou `revisor/`.
