# Lince — linha de base da etapa 2 (rodada 0)

_2026-10-17. Commit medido: `8f23833` (HEAD, etapa 1 concluída)._

## Como foi medido

Quando o Lince começou, os outros agentes já tinham alterado a árvore de trabalho (`app/src/App.tsx`, `state/modelos.ts`, `vite.config.ts`, `src-tauri/**`, `qa/*.mjs`…) e já havia um vite deles na porta 5173 (com proxy para um backend que ainda não existe → 502). Uma rodada na árvore suja deu falhas que **não** são da linha de base (ver "Árvore suja" abaixo). Por isso a linha de base oficial vem de uma **cópia limpa do HEAD** (`git archive HEAD` em `/tmp/lince-base`, fora do repositório), com cópia do `node_modules`, vite na porta **5199** e `qa/e2e.mjs`/`qa/ilha.mjs` apontados para 5199 (só na cópia). Nada de produção foi editado.

## Resultados (HEAD limpo)

| Comando | Resultado |
| --- | --- |
| `app: npm run build` | OK (vite, ~0,5–1,8 s). Único aviso: chunk `index-*.js` com ~611 kB (> 500 kB) — já existe |
| `app: npx oxlint` | OK, 0 avisos/erros |
| `app: npm test` (vitest) | **82 passed / 8 arquivos**, 0 falhas |
| `app: node qa/e2e.mjs` (dev server) | **aprovado**: 13 screenshots, sem erros de console (*) |
| `app: node qa/ilha.mjs` (dev server) | **aprovado**: fluxo completo + filtro de agentes, 7 screenshots, console limpo (*) |
| `backend: uv run ruff check .` | OK |
| `backend: uv run ruff format --check .` | OK, 198 arquivos já formatados |
| `backend: uv run pytest -q` (Docker ligado, testcontainers) | **835 passed, 2 skipped**, 5 warnings, ~76–124 s |

(*) Na cópia, o vite devolve 403 para a fonte `inter-latin-wght-normal.woff2` por causa do `node_modules` copiado (o vite resolve o caminho real em `C:/dev/sora/app/node_modules`, fora da raiz da cópia). É artefato do método, não do app: nessa cópia os dois scripts ignoram só erros de console com "status of 403". Todos os fluxos passaram; na árvore real (`C:/dev/sora/app`) esse 403 não existe.

### Falhas/avisos já existentes (não são regressão)

- **2 testes pulados** no backend: `tests/unitarios/test_arquivos.py:140` — "Sem permissão para criar link simbólico neste sistema" (Windows sem privilégio de symlink).
- **5 warnings** no pytest: depreciação do `testcontainers` (`wait_container_is_ready`), aviso do pydantic sobre `ReadOnly` em TypedDict do `openai`, `InsecureKeyLengthWarning` do JWT nos testes (chave de 31 bytes).
- Build: aviso de chunk > 500 kB.
- Nenhuma falha no app nem no backend.

## Árvore suja (fotografia no início do Lince, NÃO é linha de base)

Com a árvore já modificada pelos outros, na mesma hora: `npm run build`, `npx oxlint` e `npm test` (82/82) passaram; backend ruff/format/pytest (835 passed, 2 skipped) passaram. `qa/e2e.mjs` e `qa/ilha.mjs` falharam (502 no proxy `/v1` sem backend; "Failed to reload /src/App.tsx"; sem tela Entrar nos scripts ainda) — esperado até o backend local subir e o `qa/entrar.mjs` entrar em uso.

## Pendência de ambiente

- O vite da cópia limpa (porta **5199**, npm PID 2664; o node que escuta é o PID 20432, `/tmp/lince-base/app`) **continua ligado**: o pedido para encerrá-lo foi bloqueado (sem resposta de aprovação) e o Lince não repetiu a ação. Pode ser encerrado sem risco (`Stop-Process -Id 20432`). O vite da porta 5173 é dos outros agentes.
- Cópia limpa: `/tmp/lince-base` (= `C:\Users\heito\AppData\Local\Temp\lince-base`), pode ser apagada.

## Rodada 1 — preparado, ainda não rodado

`app/qa/lince-provedor-falso.mjs`: `node qa/lince-provedor-falso.mjs [porta]` (padrão 8765). `GET /v1/models` → 3 modelos (`lince-pequeno`, `lince-medio`, `lince-grande`); só aceita `Authorization: Bearer sk-teste-lince-1234567890`, o resto → 401 estilo OpenAI; `POST /v1/chat/completions` mínimo; `GET /health`. No app: tipo "Compatível com OpenAI", base `http://localhost:8765/v1`.
