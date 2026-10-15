#!/usr/bin/env bash
set -euo pipefail
: "${POSTGRES_DB:?POSTGRES_DB obrigatório}"
: "${BACKUP_DIRETORIO:?BACKUP_DIRETORIO obrigatório}"
: "${BACKUP_DESTINO_S3:?BACKUP_DESTINO_S3 obrigatório}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT obrigatório}"
: "${PGHOST:?PGHOST obrigatório}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=${POSTGRES_DB}}"
: "${PGUSER:?PGUSER obrigatório}"

umask 077

pgpass_temporario=""
limpar_pgpass() {
  if [[ -n "${pgpass_temporario}" ]]; then
    rm -f -- "${pgpass_temporario}"
  fi
}
trap limpar_pgpass EXIT

if [[ -z "${PGPASSFILE:-}" ]]; then
  : "${PGPASSWORD:?defina PGPASSFILE ou PGPASSWORD}"
  pgpass_temporario="$(mktemp)"
  chmod 0600 "${pgpass_temporario}"
  escapar_pgpass() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/:/\\:/g'; }
  printf '%s:%s:%s:%s:%s\n' \
    "$(escapar_pgpass "${PGHOST}")" \
    "$(escapar_pgpass "${PGPORT}")" \
    "$(escapar_pgpass "${PGDATABASE}")" \
    "$(escapar_pgpass "${PGUSER}")" \
    "$(escapar_pgpass "${PGPASSWORD}")" >"${pgpass_temporario}"
  export PGPASSFILE="${pgpass_temporario}"
  unset PGPASSWORD
fi

arquivo="${BACKUP_DIRETORIO}/sora-$(date -u +%Y-%m-%dT%H%M%SZ).dump.gz.age"
mkdir -p "${BACKUP_DIRETORIO}"

# Com pipefail, o pipeline falha se o pg_dump falhar; o arquivo parcial é removido.
if ! pg_dump --format=custom --host "${PGHOST}" --port "${PGPORT}" \
  --username "${PGUSER}" --dbname "${PGDATABASE}" \
  | gzip \
  | age --recipient "${AGE_RECIPIENT}" --output "${arquivo}"; then
  rm -f "${arquivo}"
  echo "backup-postgres: pg_dump falhou; nenhum backup antigo foi apagado." >&2
  exit 1
fi

if [ ! -s "${arquivo}" ]; then
  rm -f "${arquivo}"
  echo "backup-postgres: backup vazio; nenhum backup antigo foi apagado." >&2
  exit 1
fi

aws s3 cp "${arquivo}" "${BACKUP_DESTINO_S3}/diarios/"

# Só chega aqui com o backup novo íntegro e enviado.
find "${BACKUP_DIRETORIO}" -type f -name 'sora-*.dump.gz.age' -mtime +7 -delete
