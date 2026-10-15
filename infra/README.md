# Infraestrutura

Compose da fase 1 com Caddy, API, worker, PostgreSQL/pgvector e Redis. Inclui
modelos de ambiente e scripts de backup; os serviços não foram iniciados neste PC.

## Permissão do volume de anexos

A API e o worker rodam como UID/GID `10001`, sem capabilities e com filesystem
somente leitura; apenas `/tmp` e o volume `/srv/sora/arquivos` são graváveis.
Volumes novos herdam a posse criada na imagem. Antes de subir uma instalação que
já possua o volume `sora_anexos`, ajuste-o uma única vez:

```bash
docker compose run --rm --no-deps --user 0 --cap-add CHOWN api \
  chown -R 10001:10001 /srv/sora/arquivos
```

