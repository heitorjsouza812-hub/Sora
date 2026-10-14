# agentes

Agentes da Sora em LangChain 1.x (especificação §6.1): Sora, especialistas
(Pesquisador, Redator, Designer, Verificador) e agentes individuais.

| Arquivo | O que faz |
| --- | --- |
| `montagem.py` | `ContextoAgente`, prompt de sistema, `montar_agente()` com `create_agent`, `rodar_etapa()` |
| `aparencia.py` | `APARENCIA_POR_PAPEL`, nomes e paleta do app, `Movimento`, escolha de nome e cor |
| `prompts.py` | Lê `backend/prompts/{nome}.v{n}.md`, preenche `{chaves}` e monta a cerca `<dado_externo>` |
| `checkpointer.py` | `AsyncPostgresSaver`, `thread_id = "etapa:{id}"` |

## middleware/ (uma peça por arquivo, tabela da §6.1)

| Arquivo | Peça | Base |
| --- | --- | --- |
| `troca_provedor.py` | Troca de provedor em 429/5xx/prazo | só reexporta a fábrica de `app/llm/troca.py` (Bússola) |
| `limites.py` | Limite de passos da etapa | `ModelCallLimitMiddleware` + `ToolCallLimitMiddleware` |
| `conserto_json.py` | Conserto de JSON | `ToolErrorMiddleware` |
| `resumo.py` | Resumo de contexto (fase 2) | `SummarizationMiddleware` |
| `lembretes.py` | Lembretes automáticos | nosso |
| `loop.py` | Detector de loop | nosso |
| `orcamento.py` | Orçamento de tokens (Redis) | nosso |
| `cancelamento.py` | Cancelamento (`cancelar:{cadeia_id}`) | nosso |
| `passos.py` | Evento `passo` do painel Trabalho | nosso |
| `cerca.py` | Cerca de dado não confiável | nosso |
| `saida_grande.py` | Saída grande em arquivo | nosso |
| `prazo_ferramenta.py` | Prazo de 2 min por ferramenta | nosso |

LangChain só em `agentes/`, `ferramentas/`, `llm/`, `sistema1/` e
`orquestrador/` (§8.4). Dono: Trama (Pessoa 3).
