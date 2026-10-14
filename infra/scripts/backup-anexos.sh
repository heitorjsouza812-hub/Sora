#!/usr/bin/env sh
: "${ANEXOS_DIRETORIO:?ANEXOS_DIRETORIO obrigatório}"
: "${BACKUP_DIRETORIO:?BACKUP_DIRETORIO obrigatório}"
: "${BACKUP_DESTINO_S3:?BACKUP_DESTINO_S3 obrigatório}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT obrigatório}"

set -eu
umask 077

arquivo="${BACKUP_DIRETORIO}/anexos-$(date -u +%Y-%m-%dT%H%M%SZ).tar.gz.age"
mkdir -p "${BACKUP_DIRETORIO}"
tar -C "${ANEXOS_DIRETORIO}" -czf - . \
  | age --recipient "${AGE_RECIPIENT}" --output "${arquivo}"
aws s3 cp "${arquivo}" "${BACKUP_DESTINO_S3}/anexos/"

