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


## Computador virtual por bot

`infra/computador/` é a imagem do computador de cada bot (Xvfb, Openbox, Chromium, xdotool).
O worker cria um contêiner `sora-pc-<agente>` por bot no host do sandbox, numa rede interna só
dele com saída pelo `sora-pc-proxy` (imagem de `infra/proxy-egresso`). Construa as duas imagens
nesse host antes de ligar `SANDBOX_PROVEDOR=docker`:

```bash
docker build -t sora-computador:1 infra/computador
docker build -t sora-proxy-egresso:1 infra/proxy-egresso
```

Arquitetura, limites e regras: `docs/computador-por-bot.md`.

O `executar_comando` com internet (`com_internet=true`) usa o mesmo proxy de egresso: o contêiner
fica na rede interna `sora-sbx-internet` e só sai pelo proxy, que recusa IP privado e o
169.254.169.254 depois do DNS. Antes ele usava a `bridge` do host do sandbox.

## Redis com senha

O Compose exige `REDIS_SENHA` no `.env` e o `REDIS_URL` leva a mesma senha
(`redis://:<senha>@redis:6379/0`). A rede `interna` também tem o Caddy: sem senha, um contêiner
comprometido leria a fila, os eventos e os limites de login.

## Saúde e escala

- `/health`: o processo está vivo (não toca no banco nem no Redis).
- `/health/pronto`: banco e Redis respondem em até 3 s (503 se não). É o healthcheck da API no
  Compose; o Caddy só sobe depois dela.
- Cada worker roda até `WORKER_MAX_JOBS` jobs ao mesmo tempo (padrão 10; um turno de bot ocupa a
  vaga por até 6 min). Para mais usuários simultâneos, suba réplicas em vez de aumentar muito o
  número: `docker compose up -d --scale worker=3`.
- `SENTRY_DSN` liga o Sentry na API e no worker (sem cabeçalhos, corpo das requisições nem
  variáveis locais). `LOG_NIVEL` muda o nível do log.
- O Caddy recusa corpos acima de 25 MB em `/v1/*` (a API recusa de novo, sem depender do proxy).
