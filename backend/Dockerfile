# Imagens fixadas por versão + digest (INF-003). Para atualizar: trocar a tag, pegar o digest com
# `docker buildx imagetools inspect <imagem:tag>` e rodar o build e os testes.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

# Copia um binario versionado da imagem oficial, sem executar instalador da rede no build.
COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /srv/sora

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY config ./config
COPY migrations ./migrations
COPY prompts ./prompts
COPY workers ./workers
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev \
    && groupadd --system --gid 10001 sora \
    && useradd --system --uid 10001 --gid sora --home-dir /srv/sora --shell /usr/sbin/nologin sora \
    && mkdir -p /srv/sora/arquivos \
    && chown -R sora:sora /srv/sora

USER 10001:10001

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

