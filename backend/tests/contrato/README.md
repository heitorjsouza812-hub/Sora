# contrato (backend ↔ app)

Um exemplo por evento do canal SSE (especificação §2, tabela de eventos, e §3;
regra em §8.5, "Contrato com o app"). O backend valida que emite exatamente
este formato (`test_contrato.py`, contra os modelos de `app/eventos/tipos.py`),
e o app (Vitest) roda `src/state/aplicarEvento.ts` com os mesmos arquivos.
**Mudou um formato aqui, os dois lados mudam juntos.**

Formato de cada arquivo (o mesmo de uma mensagem SSE):

```json
{ "id": "1697040000007-0", "event": "etapa.atualizada", "data": { "...": "..." } }
```

- `id`: o id real do Redis Stream (`<milissegundos>-<sequência>`), tratado como
  **string opaca**. O app só guarda o último e manda de volta em `Last-Event-ID`;
  nunca compara nem soma ids.
- `event`: o nome do evento.
- `data`: os campos da §2, nada a mais e nada a menos.

Os exemplos formam uma história só (a campanha da cafeteria): mesma conversa,
mesma cadeia, etapas e agentes com ids fixos, para o app conseguir aplicar
todos em sequência.

## Dois canais

| Pasta | Canal | Stream no Redis | O que chega |
| --- | --- | --- | --- |
| `*.json` (raiz) | `GET /v1/conversas/{id}/eventos` | `eventos:{conversa_id}` | Os 17 eventos, com os campos da §2 |
| `usuario/*.json` | `GET /v1/eventos` (Ilha e barra lateral) | `eventos:usuario:{usuario_id}` | Só os 9 eventos de estado, **sempre com `conversa_id`** em `data` |

No canal do usuário, `data` = `{"conversa_id": ..., ...campos do evento}` (o
`enriquecer_evento_do_usuario` de `app/eventos/streams.py`). Cada canal é um
stream próprio, então os ids dos dois canais não se misturam.

| Evento | Conversa | Usuário |
| --- | --- | --- |
| `mensagem.inicio`, `mensagem.delta`, `mensagem.fim` | sim | não |
| `roteamento` | sim | não |
| `conversa.atualizada` | sim | sim |
| `agente.criado` | sim | sim |
| `cadeia.criada`, `cadeia.atualizada` | sim | sim |
| `etapa.atualizada` | sim | sim |
| `passo` | sim | sim |
| `entrega` | sim | sim |
| `pergunta` | sim | não |
| `aprovacao.pedida`, `aprovacao.resolvida` | sim | sim |
| `sugestoes` | sim | não |
| `erro` | sim | não |
| `ping` | sim | não há exemplo (sem dados; o SSE manda a cada 15 s nos dois canais) |

## Retomada com `Last-Event-ID` vencido (`retomada/erro.json`)

Os streams guardam 24 h. Se o app reconecta com um `Last-Event-ID` que já foi
cortado (ou a chave do stream já expirou), o backend **não** entrega o resto
com buracos: manda primeiro um `erro` com `codigo: "recarregar"`, **nos dois
canais** e sem `conversa_id` (vale para o canal inteiro), e segue do fim do
stream, como numa conexão nova. O `id` desse aviso é o do fim do stream: se o
app reconectar antes de recarregar, não recebe o aviso de novo.

O app, ao receber `codigo: "recarregar"`, busca o estado completo de novo
(`GET /v1/conversas`, `GET /v1/cadeias/{id}`) e volta a aplicar só os eventos
seguintes. Não mostra o texto como falha para o usuário. `Last-Event-ID: 0-0`
é o pedido explícito de "tudo o que houver" e nunca gera o aviso.

Dono: Trama (Pessoa 3).
