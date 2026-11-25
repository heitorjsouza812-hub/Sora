# Baseline da tarefa 0.5 (plano de correções §3.5)

Dono: Claude (Opus 5.5), com o Heitor no Windows para as tarefas de tela. Ramo `feat/baseline`, worktree `C:/dev/sora-claude`.
Este arquivo é a referência do Gate de decisão (§8): o mesmo modelo, a mesma máquina e as mesmas fixtures valem até lá.

## 1. Código medido

| Item | Valor |
|---|---|
| SHA final da tarefa 0.1 (código medido) | `a30c98f` |
| Ramo de partida do worktree | `onda3` em `f2fb882` |
| Diferença entre os dois | `git diff --stat a30c98f f2fb882`: só `.github/workflows/ci.yml`, `STATUS.md`, `backend/pyproject.toml` e `backend/uv.lock` (grupo dev, `pytest-repeat`). Nenhum arquivo que roda no produto. |
| Banco | Postgres local de dev (`sora-e5-pg`, 127.0.0.1:46432), migração `0027 (head)`, conferida com `alembic current` em 2026-11-25 |
| Fila | Redis local de dev (`sora-e5-redis`, 127.0.0.1:57379) |
| Serviços | API `uv run uvicorn app.main:app --port 8000` e worker `SORA_RASTRO=1 uv run python -m workers`, os dois a partir de `C:/dev/sora-claude/backend` |

## 2. Modelo fixo (decisão do Heitor: "use o que estiver disponível")

Escolhido em **2026-11-25**, antes da primeira medição:

| Campo | Valor |
|---|---|
| Provedor | Groq (conexão de QA cadastrada a partir de `SORA_QA_GROQ_CHAVE` do `backend/.env`; a chave não aparece em nenhum documento) |
| Modelo (ID exato) | `qwen/qwen3.8-27b` (no Sora: `groq/qwen/qwen3.8-27b`) |
| Versão | a Groq não publica versão além do ID; `created = 1786984846` (2026-08-17 UTC) na listagem `/openai/v1/models` de 2026-11-25. Se esse número mudar, o modelo mudou: anotar aqui antes de medir. |
| Visão | **sim**, provada por chamada direta à Groq em 2026-11-25: imagem PNG (quadrado vermelho + "NUMERO 4721") com uma ferramenta `registrar` → o modelo chamou `registrar(cor="vermelho", numero="4721")` em 1,1 s |
| Chamada de ferramenta | **sim** (mesma prova) |
| Contexto | 131 072 tokens |
| Raciocínio no seletor | `auto` |
| Permissão no seletor | `perguntar` |

**Por quê:** a conta de QA só tem a conexão da Groq. Dos modelos de chat que a chave lista (`allam-2-7b`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `openai/gpt-oss-safeguard-20b`, `qwen/qwen3.8-27b`; os demais são voz, guarda e transcrição), só o `qwen/qwen3.8-27b` aceita imagem: os dois `gpt-oss` responderam `400 messages[0].content must be a string` ao receber imagem. É, portanto, o único que serve para tela **e** para as tarefas longas com o mesmo modelo. Ele não está no `config/catalogo_modelos.yaml`: a conexão o criou ativo com `ferramentas, json`, **sem** `visao`; por isso o dono marcou as capacidades `ferramentas, json, visao` pela API (`PATCH /v1/modelos/{id}`), como o CLAUDE.md §7.3 prevê para modelo fora do catálogo.

**Como ficou fixo (sem troca silenciosa):**
- Conta de QA própria do baseline (`baseline-05-…@bancada.local`, criada com convite pelo `app.cli`).
- Na conta, o único modelo de chat **ativo** é `groq/qwen/qwen3.8-27b`. Desligados (`ativo=false`): `groq/openai/gpt-oss-120b`, `groq/openai/gpt-oss-20b`, `groq/allam-2-7b`. Os modelos que não são de chat (guarda, voz, transcrição) não aparecem na listagem de chat e ficaram como a conexão os criou.
- Cada bot de bancada recebe `PATCH /v1/agentes/{id}` com `provedor_id` + `modelo = groq/qwen/qwen3.8-27b` (escolha explícita: o worker monta lista de **um** modelo, sem reserva — `docs/seletor-modelo-permissao.md`).
- O executor grava, por execução, os modelos que aparecem em `chamadas_modelo` no intervalo. Qualquer modelo diferente do fixo é anotado e a execução recebe a classe `modelo` ou `transporte`, conforme o caso.

## 3. Máquina

| Item | Valor (lido em 2026-11-25) |
|---|---|
| CPU | AMD Ryzen 5 3600, 6 núcleos / 12 threads |
| RAM | 15,9 GB |
| Sistema | Windows 11 Pro 10.0.26300 (build 26300) |
| Vídeo | NVIDIA GeForce GTX 1660 Ti |
| Monitor | 1 monitor, 1920×1080 a 60 Hz |
| Escala / DPI | 100 % (96 DPI; `AppliedDPI = 96`) |
| Office | Microsoft 365, `C:\Program Files\Microsoft Office\Root\Office16` (Excel, Word) |
| Bloco de Notas | pacote `Microsoft.WindowsNotepad` 11.2609.11.0 |
| Calculadora | pacote `Microsoft.WindowsCalculator` 11.2607.0.0 |
| Navegadores | Edge 158.0.4370.33, Chrome 138.0.7204.184 |
| Node / Rust | v24.14.1 / rustc 1.99.0 |

## 4. Tarefas longas L01–L10 (sem tela)

Fixtures: `docs/benchmarks/fixtures-longas.md`. Executor: `docs/benchmarks/ferramentas/rodar_longas.py`.

_Medições: em andamento._

## 5. Tarefas de tela G01–G10

Fixtures: `docs/benchmarks/fixtures-gui.md`. Roteiro da sessão com o Heitor: `docs/benchmarks/roteiro-sessao-heitor.md`.

_Medições: dependem da sessão do Heitor no Windows (a agendar pelo Tech Lead)._

## 6. Reprodução das 3 falhas reais (logs de 21 e 22/11)

_Em andamento._
