# app/sistema1

Triagem rápida de todo pedido (especificação §5, §7; prompt em `docs/plano-de-implementacao/03-prompts.md`).
Dona: Bússola.

| Módulo | Responsabilidade |
| --- | --- |
| `esquemas.py` | `SaidaSistema1` (JSON do N1) e seus enums |
| `regras.py` | regras instantâneas (saudação, verbos de ação externa); só acrescentam risco |
| `saida_json.py` | extrair/validar o JSON; `SaidaInvalida` |
| `triagem.py` | `triar`: regras → (Laya) → N1 → conserto → N2 se falhar |
| `treino.py` | gravar em `roteamentos` e registrar rótulos para treinar o Laya |
| `laya.py` | cliente do `laya-svc` (fase 2–3), desligado por flag |

Não roda quando o usuário escolhe "Agente independente" (o modo já foi decidido). O prompt é um
arquivo em `backend/prompts/` (`sistema1.v1.md`), não string no código.

Estado: esqueleto (etapa 1). Os corpos levantam `NotImplementedError`.
