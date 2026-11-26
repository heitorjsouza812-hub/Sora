# STATUS — Plano de correções no lugar

> Editado **só pelo Tech Lead**, no worktree principal `C:/dev/sora` (ramo `onda3`), em commit direto.
> Codex e Claude pedem lock e informam resultado pelo T3 Code; o Tech Lead registra aqui.
> Plano vigente: `docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`. O `SORA_V2_PLANO_FINAL_SEM_LEGADO.md` está suspenso até o Gate de decisão (2026-12-30, §8).

## Decisões do Heitor

| Data | Decisão |
|---|---|
| 2026-11-25 | Autoriza, de uma vez: `git push -u origin onda3`, push dos ramos `fix/…` e `feat/…` e abertura de PRs com base `onda3`. Merge na `main`, deploy e `alembic upgrade` no servidor continuam pedindo ok separado. |
| 2026-11-25 | Modelo fixo com visão do baseline e do §8: "o que estiver disponível". Nesta máquina só há a chave de QA da Groq (`backend/.env`); o modelo exato (provedor/modelo/versão) é escolhido e anotado aqui e em `docs/benchmarks/baseline.md` antes da primeira medição da 0.5, e não muda até o Gate. |
| 2026-11-25 | Delegados: Codex `gpt-6.2-sol` (raciocínio medium) nas tarefas de backend; Claude Opus 5.5 na 0.5, na Fase 3/4 e nas revisões. |

## Fase atual: 0 (até 2026-12-02)

| Tarefa | Dono | Ramo | Commit | Verificação | Resultado real | Bloqueio | Próximo passo |
|---|---|---|---|---|---|---|---|
| 0.1 Commitar trabalho de 21–22/11 | Tech Lead | `onda3` | `75434fd`, `081bdfd`, `2f7042f` + commit de docs | ruff check/format + `uv run pytest tests/unitarios -q` por commit (worktree `C:/dev/sora-tl-verifica`); `cargo clippy -D warnings` + `cargo test` | 2242 → 2244 → 2246 passam, 0 falham, 5 pulados; Rust 35 passam, 1 ignorado | Docker Desktop desligado (integração não rodada localmente) | push de `onda3` |
| 0.2 Religar o CI | Tech Lead | `onda3` | `f2fb882`, `99f16b3` (teste do App no Node 20) | PR de teste #3 contra `onda3` dispara os 4 jobs | Disparou sozinho. Rodada 45694848208: backend ✅, desktop ✅, App ❌ (teste antigo no Node 20; corrigido em `99f16b3`, App verde no PR #4), integração ❌ (2 testes, abaixo) | integração vermelha até o [PR #5](https://github.com/heitorjsouza812-hub/Sora/pull/5) entrar; proteção da `main`/`onda3` é com o Heitor | PR #5 (`fix/ci-integracao`, Codex `05d7b79`, aberto pelo Tech Lead): CI + revisão do Claude → merge no `onda3` → atualizar `ci/teste-pr-onda3` e ver o #3 verde |
| 0.3 Bypass de aprovação do MCP | Codex (correção) + Claude (teste) | `fix/mcp-aprovacao` | `397a2fa` (correção), `f1d737a` (teste de integração do §3.3, Claude), `b69a91f` (merge do `onda3`) — [PR #4](https://github.com/heitorjsouza812-hub/Sora/pull/4) | `SORA_MODELO_FALSO=1 SORA_EXIGIR_DOCKER=1 uv run pytest tests/integracao/test_mcp_aprovacao.py -q -rs`, Docker local | **Antes** (`onda3` `7635710` + só o teste): 3 falham, 5 passam. `delete_everything` executou sem cartão com 25 ferramentas nos papéis `pesquisador` e `individual` (efeito `[{'alvo': 'tudo'}]`), e a rotina com 5 recebeu as meta-ferramentas (a regressão do PR #5). **Depois** (`f1d737a`): 8 passam, 0 falham, 0 pulados | integração do CI depende do PR #5 | CI do #4 + revisão do Codex; conferência dos #4 e #5 juntos (Tech Lead) |
| 0.4 Testes de ponta a ponta | Codex | `feat/ponta-a-ponta` (criado em `99f16b3`, sem commits) | — | 13 cenários 20/20, 0 skipped | — | — | Retomada depois da cota: base `origin/onda3` + merge de `origin/fix/ci-integracao`; commit e push por cenário; síntese do `@todos` no PR separado `feat/grupo-sintese` |
| 0.5 Baseline | Claude (Opus 5.5) + Heitor | `feat/baseline` (`C:/dev/sora-claude`) | `54cd737` | 30 tela + 30 longas com classe de falha | Modelo fixo anotado: Groq `qwen/qwen3.8-27b`, o único da chave de QA com visão e ferramentas (provado por chamada direta). Medições L ainda não registradas | sessão do Heitor no Windows para G01–G10 | Retomada depois da cota: fixtures, L01–L10 ×3, roteiro da sessão, PR em rascunho |

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
