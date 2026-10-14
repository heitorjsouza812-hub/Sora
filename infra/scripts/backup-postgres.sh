#!/usr/bin/env sh
: "${POSTGRES_DB:?POSTGRES_DB obrigatório}"
: "${BACKUP_DIRETORIO:?BACKUP_DIRETORIO obrigatório}"
: "${BACKUP_DESTINO_S3:?BACKUP_DESTINO_S3 obrigatório}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT obrigatório}"

set -eu
umask 077

arquivo="${BACKUP_DIRETORIO}/sora-$(date -u +%Y-%m-%dT%H%M%SZ).dump.gz.age"
mkdir -p "${BACKUP_DIRETORIO}"
pg_dump --format=custom "${DATABASE_URL:?DATABASE_URL obrigatório}" \
  | gzip \
  | age --recipient "${AGE_RECIPIENT}" --output "${arquivo}"
aws s3 cp "${arquivo}" "${BACKUP_DESTINO_S3}/diarios/"
find "${BACKUP_DIRETORIO}" -type f -name 'sora-*.dump.gz.age' -mtime +7 -delete

