#!/usr/bin/env sh
: "${BACKUP_ARQUIVO:?BACKUP_ARQUIVO obrigatório}"
: "${AGE_IDENTITY:?AGE_IDENTITY obrigatório}"
: "${DATABASE_URL_RESTAURACAO:?DATABASE_URL_RESTAURACAO obrigatório}"

set -eu

age --decrypt --identity "${AGE_IDENTITY}" "${BACKUP_ARQUIVO}" \
  | gzip -d \
  | pg_restore --clean --if-exists --no-owner --dbname "${DATABASE_URL_RESTAURACAO}"
psql "${DATABASE_URL_RESTAURACAO}" -c 'select count(*) from usuarios;'

