# app/llm

Camada de modelos de IA (especificação §5, §6.1, §8.5). Dona: Bússola.

| Módulo | Responsabilidade |
| --- | --- |
| `provedores.py` | `TipoProvedor`, `ConfigProvedor` (chave em `SecretStr`), teste da chave listando modelos |
| `fabrica.py` | `ChatLiteLLM` por modelo do usuário, com `api_key` e `api_base` por chamada |
| `custo.py` | tokens, custo em US$ por chamada, gasto do mês por provedor (teto do seletor) |
| `troca.py` | classificar erro (429/5xx/prazo), pausa do provedor, fábrica única do middleware de fallback (`agentes/middleware/troca_provedor.py` só reexporta) |
| `imagem.py` | `gerar_imagens` (LiteLLM `image_generation`) para o Designer |
| `falso.py` | modelo falso com `SORA_MODELO_FALSO=1` (nunca em produção) |

Regras: a chave do usuário só vive em memória durante a chamada e nunca aparece em log, evento
ou mensagem. LangChain/LiteLLM são importados dentro das funções.

Estado: esqueleto (etapa 1). Os corpos levantam `NotImplementedError`.
