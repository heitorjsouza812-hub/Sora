# app/revisor

Aprovações (especificação §4, §6.1; plano 01 "Segurança e aprovações"). Dona: Bússola.

| Módulo | Fase | Responsabilidade |
| --- | --- | --- |
| `esquemas.py` | 1 | `AvaliacaoRevisor`, `CartaoAprovacao`, `DecisaoUsuario`, enums |
| `cartao.py` | 1 | cartão fixo do `criar_agente` (sem modelo): criar, decidir, `marcar_aprovacao_expirada` (o job de prazo é `workers/aprovacoes.py`) |
| `acoes.py` | 3 | revisor de ações com modelo (`revisar_acao`), regras "sempre permitir", registro de ações |

Só o `cartao.py` entra na fase 1. O `acoes.py` é esqueleto e fica atrás da flag `revisor.acoes_ativo`.
O revisor falha fechado: erro ou JSON inválido = BLOQUEAR.

Estado: esqueleto (etapa 1). Os corpos levantam `NotImplementedError`.
