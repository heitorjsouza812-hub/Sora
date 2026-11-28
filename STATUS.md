# STATUS — Plano de correções no lugar

> Editado **só pelo Tech Lead**, no worktree principal `C:/dev/sora` (ramo `onda3`), em commit direto.
> Codex e Claude pedem lock e informam resultado pelo T3 Code; o Tech Lead registra aqui.
> Plano vigente: `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`. O `SORA_V2_PLANO_FINAL_SEM_LEGADO.md` está suspenso até o Gate de decisão (2026-12-30, §8).

## Decisões do Heitor

| Data | Decisão |
|---|---|
| 2026-11-25 | Autoriza, de uma vez: `git push -u origin onda3`, push dos ramos `fix/…` e `feat/…` e abertura de PRs com base `onda3`. Merge na `main`, deploy e `alembic upgrade` no servidor continuam pedindo ok separado. |
| 2026-11-25 | Modelo fixo com visão do baseline e do §8: "o que estiver disponível". Nesta máquina só há a chave de QA da Groq (`backend/.env`); o modelo exato (provedor/modelo/versão) é escolhido e anotado aqui e em `docs/benchmarks/baseline.md` antes da primeira medição da 0.5, e não muda até o Gate. |
| 2026-11-26 | O modelo fixo deixa de ser o Groq `qwen/qwen3.8-27b`: a chave de QA recusa com 413 qualquer pedido acima de 7 000 tokens de entrada. O novo é **um Gemini da conexão Google da conta do Heitor (chave do plano gratuito, só a cota grátis; vale a cota medida de RPM e RPD, as execuções podem ocupar vários dias e o produto não é cortado para caber nela)**, com ID estável, visão e ferramentas, escolhido e anotado no `baseline.md` §2 antes da 1ª medição. Ele vale até o Gate. A chave é copiada para a conta de bancada por script local (decifra e cadastra pela API, sem gravar nem imprimir), sem tocar na conta do Heitor. |
| 2026-11-25 | Delegados: Codex `gpt-6.2-sol` (raciocínio medium) nas tarefas de backend; Claude Opus 5.5 na 0.5, na Fase 3/4 e nas revisões. |

## Fase atual: 0 (até 2026-12-02)

| Tarefa | Dono | Ramo | Commit | Verificação | Resultado real | Bloqueio | Próximo passo |
|---|---|---|---|---|---|---|---|
| 0.1 Commitar trabalho de 21–22/11 | Tech Lead | `onda3` | `75434fd`, `081bdfd`, `2f7042f` + commit de docs | ruff check/format + `uv run pytest tests/unitarios -q` por commit (worktree `C:/dev/sora-tl-verifica`); `cargo clippy -D warnings` + `cargo test` | 2242 → 2244 → 2246 passam, 0 falham, 5 pulados; Rust 35 passam, 1 ignorado | Docker Desktop desligado (integração não rodada localmente) | push de `onda3` |
| 0.2 Religar o CI | Tech Lead | `onda3` | `f2fb882`, `99f16b3` (teste do App no Node 20); integração consertada pelo [PR #5](https://github.com/heitorjsouza812-hub/Sora/pull/5) (em `71799ad`) | PR de teste #3 contra `onda3` dispara os 4 jobs | **CONCLUÍDA (2026-11-28).** PR #3 (`29ddfbc`): os 4 jobs verdes na rodada 45851808445 (App, backend, desktop e integração em 14m33s); fechado sem mesclar. O job diário 20× passou duas vezes (45743363565 e 45851679177). Histórico: a 1ª rodada (45694848208) teve App ❌ (Node 20, corrigido em `99f16b3`) e integração ❌ (corrigida pelo #5) | proteção da `main`/`onda3` com os 4 jobs obrigatórios é com o Heitor | — |
| 0.3 Bypass de aprovação do MCP | Codex (correção) + Claude (teste) | `fix/mcp-aprovacao` | `397a2fa` (correção), `f1d737a` (teste de integração do §3.3, Claude), `b69a91f` (merge do `onda3`) — [PR #4](https://github.com/heitorjsouza812-hub/Sora/pull/4) | `SORA_MODELO_FALSO=1 SORA_EXIGIR_DOCKER=1 uv run pytest tests/integracao/test_mcp_aprovacao.py -q -rs`, Docker local | **Antes** (`onda3` `7635710` + só o teste): 3 falham, 5 passam. `delete_everything` executou sem cartão com 25 ferramentas nos papéis `pesquisador` e `individual` (efeito `[{'alvo': 'tudo'}]`), e a rotina com 5 recebeu as meta-ferramentas (a regressão do PR #5). **Depois** (`f1d737a`): 8 passam, 0 falham, 0 pulados | integração do CI depende do PR #5 | CI do #4 + revisão do Codex; conferência dos #4 e #5 juntos (Tech Lead) |
| 0.4 Testes de ponta a ponta | Codex | `feat/ponta-a-ponta` [#6](https://github.com/heitorjsouza812-hub/Sora/pull/6) (`78d578e`); filhos com base temporária `feat/ponta-a-ponta`: `fix/estado-fim-turno` [#7](https://github.com/heitorjsouza812-hub/Sora/pull/7) (`2fe72e4`), `fix/aviso-troca-modelo` [#8](https://github.com/heitorjsouza812-hub/Sora/pull/8) (`8cdefe1`), `feat/grupo-sintese` [#9](https://github.com/heitorjsouza812-hub/Sora/pull/9) (`ee70bfe`) | ver ramos | 13 cenários 20/20, 0 skipped | Codex, local com Docker, `--count=3`: 13 cenários, 42 execuções, 0 falhas, 0 pulados. #6: aprovação 15/15, rotinas 6/6, reconexão SSE 3/3; CI 4/4 verde. #7: Parar e prazo gravavam `concluido` no Postgres; agora `cancelado` e `falhou` (3/3 cada). #8: troca 9/9 (timeout, HTTP 500, modelo fixo sem reserva). #9: grupo 3/3, uma síntese por rodada, a retomada não duplica. Unitários 2250–2253 passam, 0 falham, 2 pulados (link simbólico) | 20/20 no CI: `workflow_dispatch` 45743363565 em `feat/ponta-a-ponta` (2026-11-26) | Revisão cruzada do Claude (#6/#7 e #8/#9). Ordem: #4 (com o #5) → #6 → base dos filhos vira `onda3` → #7, #8, #9 |
| 0.5 Baseline | Claude (Opus 5.5) + Heitor | `feat/baseline` [PR #10](https://github.com/heitorjsouza812-hub/Sora/pull/10), rascunho | `54cd737`, `e6ae126`, `ca31f45`, `0cd2c07`, `2319e05` | 30 tela + 30 longas com classe de falha | Modelo fixo: Groq `qwen/qwen3.8-27b`. **L01–L10: 30 não executadas** (classe `cota_provedor`): a chave de QA (tier `on_demand`) recusa com **413** todo pedido com mais de **7 000 tokens de entrada**, e o 1º pedido de um bot já tem ~6,8 mil (prompt + esquemas de 33 ferramentas). Rechecado em 2026-11-26: "Limit 7000, Requested 9020". **Wikipédia (navegador)**, r4–r6: 1 ok e 2 parciais (`schema`): o bot chamou `clicar` sem ref 8 vezes seguidas e nada parou a repetição. Excel e Bloco de Notas documentados (§6.1/§6.3), sem reprodução. G01–G10: 0/30 | **BLOQUEADA**: decisão do Heitor sobre o limite da Groq (subir o tier ou trocar o modelo fixo e refazer o §2). Depois, a sessão no Windows (`docs/benchmarks/roteiro-sessao-heitor.md`, ~4 h) | Decisão do Heitor → apagar os bots de bancada → refazer as 30 L → sessão G |

**2026-11-26:** o #4 foi mesclado no `onda3` em `71799ad`, levando o #5 junto (os dois aparecem como MERGED). Na hora do merge:
- 5/5 checks verdes em `8e29522`;
- revisão do Codex: APROVADO;
- revisão do Claude no #5: sem bloqueio além da ordem de merge.

**20/20 no CI** (`workflow_dispatch` 45743363565, `feat/ponta-a-ponta` em `78d578e`):

| Arquivo | Passaram | Falharam | Pulados |
|---|---|---|---|
| `test_e2e_aprovacao` | 100 | 0 | 0 |
| `test_e2e_reconexao_sse` | 20 | 0 | 0 |
| `test_e2e_rotina` | 40 | 0 | 0 |

Repetido sobre as correções da revisão (`9d9c56e`), rodada 45851679177: aprovação 120/0/0, reconexão SSE 20/0/0 e rotina 40/0/0 (passaram/falharam/pulados). Na mesma rodada, a integração ficou vermelha: a 0.4 criou um falso de reserva para a Sora e o bot (`criar_modelo_falso(nome, reserva=True)` em `app/orquestrador/modelos.py`), e o helper `_roteirizar` de `test_mcp_aprovacao.py` não aceitava o argumento (TypeError no turno). O Tech Lead corrigiu em `6e02fb6`, só no teste: a reserva usa o falso comum.

**Correções da revisão do #6** (Codex, antes de ser barrado por um filtro de segurança do provedor; o Tech Lead juntou o `onda3`):
- `80b2486`: partida a frio;
- `997e7ef`: reconexão com o socket caindo no meio da resposta;
- `385bf78`: Parar e depois Permitir não retoma o pedido;
- `bb5142e`: despachos simultâneos;
- `049425f`: unitário do modo real.

**Correção do #7:** `02726a5` encerra o item da fila pelo id.

**Ordem de merge dos PRs #4 e #5** (revisões cruzadas de 2026-11-25):
- O Claude achou, no #5 sem o #4, as meta-ferramentas `conectores_*` duplicadas com 21 ou mais MCP. Isso não abre furo, mas as MCP somem do turno.
- O Codex pediu, no #4, um caso que só passa com o #5.
- Por isso o `fix/mcp-aprovacao` recebe merge do `fix/ci-integracao`, e o #4 entra no `onda3` levando os dois. O `onda3` nunca fica com o #5 sozinho.
- Conferência local dos dois juntos (`d6bef30`, Docker): unitários 2252 passam e 2 pulados (link simbólico no Windows). Na integração:

  | Arquivo | Passam |
  |---|---|
  | `test_mcp_aprovacao` | 8 |
  | `test_relogio_externos` | 6 |
  | `test_etapa6_ancora4` | 14 |
  | `test_relogio_rotinas` | 6 |
  | `test_chave_ferramentas` | 38 |
  | `test_ferramentas_coordenacao` | 10 |

  Nenhuma falha e nenhum pulado na integração.
- Achado 2 do Claude no #5: um pedido que cita navegador ou PC deixa os MCP no catálogo, para não desfazer a economia de contexto de `2f7042f`. Corrigido pelo Tech Lead em `8927cb8`, com 3 unitários; os unitários completos dão 2252 passam.

PRs filhos da 0.4 (`fix/estado-fim-turno`, `fix/aviso-troca-modelo`, `feat/grupo-sintese`):
- Abertos com base temporária `feat/ponta-a-ponta`.
- O Tech Lead muda a base para o `onda3` quando o PR da 0.4 entrar.

2026-11-25 ~21:05: os três delegados pararam por fim da cota e foram retomados a partir do que já estava commitado (nada perdido).

Código medido pela 0.5: `a30c98f`. O `onda3` em `f2fb882` só muda `.github/workflows/ci.yml`, `STATUS.md` e o grupo dev (`pytest-repeat`); o código que roda é o mesmo.

PR de teste da 0.2: [#3](https://github.com/heitorjsouza812-hub/Sora/pull/3) (`ci/teste-pr-onda3`, commit vazio, rascunho, não mesclar).

## Locks de arquivo

| Arquivo / pasta | Dono | Desde | Motivo |
|---|---|---|---|
| `STATUS.md`, `.github/**`, `CLAUDE.md`, `AGENTS.md`, `log/**`, `docs/benchmarks/**` | Tech Lead | 2026-11-25 | §9 |
| `backend/pyproject.toml`, `backend/uv.lock` | Tech Lead | 2026-11-25 | 0.2 (`pytest-repeat`); liberado depois do `f2fb882` (pedir lock antes de mudar) |
| `backend/app/conectores/**`, `backend/app/ferramentas/catalogo_preguicoso.py`, `backend/tests/unitarios/{test_rakazo_fase1,test_rakazo_fase3,test_engrenagem_pedido}.py`, `backend/tests/integracao/test_mcp_aprovacao.py` (novo), `backend/app/agentes/ancora.py` (só se preciso) | Codex | 2026-11-25 | 0.3 |
| `backend/app/llm/falso.py`, `backend/workers/{conversa,configuracao}.py` (só leitura dos prazos por variável), `backend/tests/ponta_a_ponta/**`, `backend/tests/conftest.py`, `backend/tests/integracao/{conftest,relogio_base}.py`, ferramenta de teste nova (só com `SORA_MODELO_FALSO=1`) | Codex | 2026-11-25 | 0.4 (começa depois do PR da 0.3) |
| `docs/benchmarks/**` | Claude | 2026-11-25 | 0.5 (cedido pelo Tech Lead) |
| `backend/tests/integracao/test_mcp_aprovacao.py` no ramo `fix/mcp-aprovacao` | Claude | 2026-11-25 | 0.3, só testes; código de produção do PR #4 segue com o Codex |
| `backend/app/revisor/execucao.py` (só prazo de expiração do cartão configurável, lido apenas com `SORA_MODELO_FALSO=1`; padrão de 10 min intacto) | Codex | 2026-11-25 | 0.4 |
| `backend/app/canais_equipe/{roteamento,servico}.py` | Codex | 2026-11-25 | PR separado `feat/grupo-sintese`: cenário `test_e2e_grupo.py` + síntese da Sora depois do `@todos` (exigida pelo §3.4/§8.1). `@todos` continua só para os bots (decisão 5); uma síntese por rodada, cita entregas e falhas |
| `fix/ci-integracao`: `backend/workers/**`, `backend/app/agentes/{montagem,ancora,ferramentas_do_turno}.py`, `backend/app/ferramentas/**`, testes de integração tocados | Codex | 2026-11-25 | conserto do CI (regressão MCP em rotina + `test_etapa6_ancora4`) |
| `backend/tests/unitarios/test_prazo_aprovacao.py` (novo) | Codex | 2026-11-25 | 0.4 (prazo do cartão só com `SORA_MODELO_FALSO=1`) |
| `backend/workers/{conversa,equipe}.py` (fim por timeout/Parar gravado com o estado certo; hoje vira `concluido`) | Codex | 2026-11-25 | Correção de produto achada pela 0.4. PR separado `fix/estado-fim-turno` (correção + unitário + cenário), com antes/depois do estado no banco; sem estado novo no modelo de dados |
| `backend/workers/portas.py` (aviso de troca de modelo no chat direto) | Codex | 2026-11-25 | Correção de produto achada pela 0.4. PR separado `fix/aviso-troca-modelo`: PT-BR sem termo técnico, só quando a troca aconteceu, uma vez por turno; modelo explícito continua sem troca silenciosa |
| `backend/tests/unitarios/test_estado_fim_turno.py` (novo) | Codex | 2026-11-25 | PR `fix/estado-fim-turno` |
| `backend/tests/unitarios/test_aviso_troca_modelo.py` (novo) | Codex | 2026-11-25 | PR `fix/aviso-troca-modelo` |
| `backend/app/filas/__init__.py` (só a transição de encerramento pelo id do item, não pela pista) | Codex | 2026-11-26 | PR #7, achado da revisão do Claude |
| `backend/app/canais_equipe/sql.py` (só uma consulta de leitura nova: nomes dos bots da rodada por id, inclusive removidos/desativados, restrita ao `usuario_id` dono) | Codex | 2026-11-25 | PR `feat/grupo-sintese` |
| `backend/app/llm/troca.py`, `backend/app/agentes/montagem.py`, `backend/app/agentes/middleware/__init__.py` (só avisar no chat direto que uma reserva respondeu) | Codex | 2026-11-25 | PR `fix/aviso-troca-modelo`. Sem mudar política/ordem de troca nem o aviso da cadeia; modelo explícito sem reserva (unitário); `MiddlewareRevisor` sempre montado |
| `app/src/screens/{SoraChat,AgentChat}.tsx`, `app/src/state/aplicarEvento.ts` e o componente de mensagem que mostrar o aviso, com os testes do app correspondentes (só mostrar na conversa o aviso de que uma reserva respondeu, identificado por um campo próprio do evento e não pelo texto) | Codex | 2026-11-28 | PR #8, revisão do Claude: o aviso só aparecia no painel Trabalho. Decisão do Tech Lead: tem que aparecer na conversa da Sora e na do bot (decisão de 2026-11-16, sem troca silenciosa). Sem mudar o visual existente nem os tokens |
| `backend/tests/unitarios/test_pecas_openbot.py` (só acrescentar o unitário da síntese; o armazém em memória pode devolver os nomes em vez de `{}`; sem mudar nem remover testes existentes) | Codex | 2026-11-28 | PR #9, recomendação da revisão do Claude |
| `backend/workers/conversa.py` (gatilhos do modelo falso pelo turno real), `backend/workers/equipe.py` (`[falha_bot]`), `backend/app/orquestrador/modelos.py` (reserva falsa), `backend/app/ferramentas/registro.py`, `backend/app/agentes/montagem.py`, `backend/app/revisor/politica.py` (ferramenta de teste) | Codex | 2026-11-25 | 0.4. Condições: tudo o que é de teste só existe com `SORA_MODELO_FALSO=1`; nenhuma regra de `revisor/politica.py` fica mais permissiva para ferramenta real |

## 0.1 — inventário do trabalho local (2026-11-25, `onda3` sobre `f92a420`)

`git diff --stat`: 39 arquivos rastreados, +782 / −143 (`--ignore-cr-at-eol` dá o mesmo). Mais 15 não rastreados.
Os 12 `app/src-tauri/permissions/autogenerated/*.toml` aparecem como `M` no `git status`, mas o hash no disco é igual ao do índice (só o aviso LF→CRLF do `core.autocrlf=true`): zero linha de mudança. `.gitattributes` não foi tocado.
Varredura de segredos (chaves Groq/OpenAI/Google/Tavily/GitHub/AWS/Slack, chaves privadas, `*_CHAVE=`, senha/token literais) no diff e nos arquivos novos: nada. Só UUIDs de conversas de QA nos logs.

| Commit | Arquivos |
|---|---|
| 1. Modelos e provedor (`75434fd`) | `backend/app/llm/{fabrica,troca,saude}.py`, `backend/app/agentes/visao.py`, `backend/app/orquestrador/modelos.py`, `backend/app/agentes/middleware/{__init__,rastro}.py`, `tests/unitarios/test_modelo_travado.py`, `tests/integracao/test_saude_provedor.py` |
| 2. PC (`081bdfd`) | `backend/app/computador/{conferencia,pc_usuario,servico}.py`, `app/src-tauri/{Cargo.toml,src/pc/{mod,regras,sistema}.rs,permissions/autogenerated/*.toml}`, `tests/unitarios/{test_pc_usuario,test_vela12_pc}.py` |
| 3. Ciclo de ferramentas (`2f7042f`) | `backend/app/agentes/middleware/limite_provedor.py` + `tests/unitarios/test_ancora_limite_provedor.py` (o teste também cobre `falar(final=True)`; no grupo 1 ele reprovava), `backend/app/agentes/prompts.py` + `backend/prompts/{sora_base,lembrete_inicio_turno,lembrete_entrega,navegador_arvore,computador_pc}.v2.md` + `bot_de_grupo.v1.md`, `backend/app/agentes/{ancora,checkpointer,ferramentas_do_turno,montagem}.py`, `middleware/{encerra_depois_de_falar,revisor}.py`, `backend/app/ferramentas/{falar,permissoes,navegador_worker}.py`, `backend/app/navegador/{__init__,arvore/ferramentas,arvore/motor}.py`, `backend/app/revisor/execucao.py`, `backend/workers/{conversa,equipe}.py`, `tests/unitarios/{test_engrenagem_fala,test_navegador_arvore}.py`, `tests/integracao/{test_ancora_pecas,test_fase_b_robustez}.py` |
| 4. Docs | `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`, `log/2026-11-{21,22,25}.md`, `log/ONDE-PARAMOS.md`, `CLAUDE.md`, `AGENTS.md`, `.gitignore` (+ `.claude/launch.json`), `STATUS.md` |

Fica fora: `.claude/launch.json` (configuração local; entra no `.gitignore`).
`ruff format` aplicado (só espaço e quebra de linha) em `ancora.py`, `middleware/rastro.py` e `navegador/arvore/motor.py`: sem isso o `ruff format --check` do CI reprovava.

## Pendências de produto achadas na Fase 0 (fora dos PRs atuais)

| Achado | Onde | Origem |
|---|---|---|
| Parar no chat direto não fecha o cartão "Precisa de você" do pedido. O cartão continua pendente e, se for permitido depois, não tem efeito, porque o pedido já está `interrompida` | `_pedir_parada` só resolve cartões de cadeia | revisão do Claude no #6 |
| O painel da fila esconde os itens `cancelado`/`falhou` (rótulos e botão Repetir existem, mas o backend não lista), e o worker não avisa o app quando a fila muda | backend da listagem da fila + app | revisão do Claude no #7 |
| Falha do provedor ainda grava `concluido` no item da fila | `workers/conversa.py` | revisão do Claude no #7 (anterior ao PR) |
| A marca de conteúdo externo (`contaminacao.py`) não cobre resultado de MCP, nem direto nem pelo catálogo | `app/agentes/contaminacao.py` | revisão do Claude no #5 (anterior) |
| O prompt de todo bot leva a lista de colegas da conta e cresce ~30 tokens a cada bot criado (com 7 000 de limite de entrada, isso já impede o 1º pedido) | montagem do prompt de sistema | baseline 0.5 (Claude) |
| Navegador: o bot repetiu `clicar` sem ref 8 vezes seguidas, com as refs das sugestões disponíveis; nenhuma guarda de repetição interrompeu o turno | ferramentas do navegador / laço do turno | baseline 0.5, Wikipédia r4–r6 |
| Testes pulados no CI: 6 do computador virtual (imagem `sora-computador:1` não é construída) e 1 em `test_fase_b_robustez.py:1435` (só Windows) | CI | Tech Lead |

## Integração no CI (2026-11-25, rodada 45694848208 do PR #3)

Conferido com Docker local em `f92a420` (antes da 0.1) e `9ce14b1` (onda3 + commit vazio):

| Teste | antes da 0.1 | depois | Situação |
|---|---|---|---|
| `test_relogio_externos.py::test_conectores_mcp_de_ponta_a_ponta` | 6 passam | 1 falha (`mcp__clima__buscar_clima is not a valid tool` numa rotina com 2 ferramentas MCP) | **regressão do trabalho de 21–22/11** → Codex, `fix/ci-integracao` |
| `test_etapa6_ancora4.py` (aviso "não enxerga imagens", `capturado["antes"] >= 2`) | 1 falha | 1 falha | anterior à 0.1 → Codex, `fix/ci-integracao` |
| `test_computador_virtual.py` (4), `test_computador_visao.py` (2) | pulados | pulados | imagem `sora-computador:1` não é construída no CI. Pulado não conta: pendência para o G0 (construir a imagem no job ou rodar fora do CI com prova) |
| `test_fase_b_robustez.py` | — | 40 passam, 1 pulado | ver o motivo do pulado |

## Testes que já falhavam antes da 0.1

Nenhum. `f92a420` (antes): 2189 passam, 0 falham, 52 pulados (rodada sem o grupo `navegador`, ou seja, sem Playwright). Depois da 0.1: 2246 passam, 0 falham, 5 pulados — 2 por falta de permissão para link simbólico no Windows (`test_arquivos.py:140`) e 3 porque o Docker não respondia (`test_modelos_api.py:480,520,549`). Pulado não conta como passou: os 3 do Docker precisam rodar no CI ou com o Docker Desktop ligado.

## Agenda do Heitor no Windows (0.5 e gates)

| Bloco | Duração | Quando | Estado |
|---|---|---|---|
| Baseline G01–G10 | ~4 h | a combinar (até 2026-12-02) | a agendar |
| G3 | ~2 h | semana 3 | — |
| G4 | ~4 h | semana 4 | — |
| Rodada final | ~4 h | até 2026-12-30 | — |
