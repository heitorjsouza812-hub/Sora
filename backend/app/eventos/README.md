# Eventos

Contratos dos eventos da seção 2, persistência em Redis Stream por conversa e
usuário e adaptação para SSE com retomada por `Last-Event-ID`.

| Arquivo | O que faz |
| --- | --- |
| `tipos.py` | Um modelo Pydantic por evento da §2; `TIPOS_EVENTOS_ESTADO` (lista central do canal do usuário) |
| `streams.py` | `publicar_evento(redis, evento, conversa_id, usuario_id)`: `XADD` em `eventos:{conversa_id}` (e em `eventos:usuario:{usuario_id}` com `conversa_id`, se for de estado), corte de 24 h por `MINID` e `EXPIRE`; devolve o id do stream. `ler_lote` / `ler_eventos`: `XREAD` a partir do `Last-Event-ID` |
| `sse.py` | `gerar_sse`: mensagens `{id, event, data}`; `mensagem_ping`: `event: ping` sem `id`, a cada 15 s |

Regras:

- O `id` do SSE é o id do Redis Stream (`<ms>-<seq>`), string opaca para o app.
- Sem `Last-Event-ID` (ou com um inválido), a leitura começa no fim do stream:
  o app já buscou o estado completo pela API antes de abrir o canal.
- Reconectar com `Last-Event-ID` entrega tudo depois dele, sem perder nem repetir.
- O ping não leva `id`, para não mexer no `Last-Event-ID` do app.

Rotas em `app/api/eventos.py`. Contrato com o app em `tests/contrato/`.
Dono: Trama (desde a etapa 3).
