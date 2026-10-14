# workers

Jobs ARQ da Sora (especificação §6). O banco é a fonte da verdade: se um
worker cair, outro retoma do último estado salvo.

| Arquivo | Jobs |
| --- | --- |
| `fila.py` | `enfileirar(job, **args)`: único ponto que fala com a fila |
| `cadeia.py` | `planejar_cadeia`, `avancar_cadeia`, `executar_etapa`, `verificar_cadeia`, `entregar_resultado`, `ajustar` |
| `conversa.py` | `responder_direto` |
| `aprovacoes.py` | `expirar_aprovacao` |
| `configuracao.py` | `WorkerSettings` (funções, retentativas, prazo, início e fim) |

Subir: `uv run arq workers.configuracao.WorkerSettings` (a partir de `backend/`).

A lógica fica em `app/orquestrador` e `app/agentes`; aqui só a casca dos jobs.
Dono: Trama (Pessoa 3).
