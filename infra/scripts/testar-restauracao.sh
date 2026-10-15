#!/usr/bin/env bash
set -euo pipefail
: "${BACKUP_ARQUIVO:?BACKUP_ARQUIVO obrigatório}"
: "${AGE_IDENTITY:?AGE_IDENTITY obrigatório}"
: "${SORA_RESTAURACAO_TESTE:?SORA_RESTAURACAO_TESTE obrigatório}"
: "${DATABASE_URL:?DATABASE_URL obrigatório para a proteção contra produção}"
: "${DATABASE_URL_RESTAURACAO:?DATABASE_URL_RESTAURACAO obrigatório}"
: "${PGHOST:?PGHOST da conexão principal obrigatório}"
: "${PGPORT:=5432}"
: "${PGDATABASE:?PGDATABASE da conexão principal obrigatório}"
: "${RESTAURACAO_PGHOST:?RESTAURACAO_PGHOST obrigatório}"
: "${RESTAURACAO_PGPORT:=5432}"
: "${RESTAURACAO_PGDATABASE:?RESTAURACAO_PGDATABASE obrigatório}"
: "${RESTAURACAO_PGUSER:?RESTAURACAO_PGUSER obrigatório}"

if [[ "${SORA_RESTAURACAO_TESTE}" != "1" ]]; then
  echo "testar-restauracao: recusado; defina SORA_RESTAURACAO_TESTE=1 conscientemente." >&2
  exit 1
fi

normalizar_dsn() {
  printf '%s' "$1" | sed -E 's#^postgres(ql)?(\+[A-Za-z0-9_]+)?://#postgresql://#; s#/$##'
}

if [[ "$(normalizar_dsn "${DATABASE_URL_RESTAURACAO}")" == "$(normalizar_dsn "${DATABASE_URL}")" ]]; then
  echo "testar-restauracao: recusado; DATABASE_URL_RESTAURACAO aponta para DATABASE_URL." >&2
  exit 1
fi

if [[ "${RESTAURACAO_PGHOST}" == "${PGHOST}" \
  && "${RESTAURACAO_PGPORT}" == "${PGPORT:-5432}" \
  && "${RESTAURACAO_PGDATABASE}" == "${PGDATABASE}" ]]; then
  echo "testar-restauracao: recusado; host, porta e banco coincidem com a conexão principal." >&2
  exit 1
fi

pgpass_temporario=""
limpar_pgpass() {
  if [[ -n "${pgpass_temporario}" ]]; then
    rm -f -- "${pgpass_temporario}"
  fi
}
trap limpar_pgpass EXIT

if [[ -n "${RESTAURACAO_PGPASSFILE:-}" ]]; then
  export PGPASSFILE="${RESTAURACAO_PGPASSFILE}"
else
  : "${RESTAURACAO_PGPASSWORD:?defina RESTAURACAO_PGPASSFILE ou RESTAURACAO_PGPASSWORD}"
  pgpass_temporario="$(mktemp)"
  chmod 0600 "${pgpass_temporario}"
  escapar_pgpass() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/:/\\:/g'; }
  printf '%s:%s:%s:%s:%s\n' \
    "$(escapar_pgpass "${RESTAURACAO_PGHOST}")" \
    "$(escapar_pgpass "${RESTAURACAO_PGPORT}")" \
    "$(escapar_pgpass "${RESTAURACAO_PGDATABASE}")" \
    "$(escapar_pgpass "${RESTAURACAO_PGUSER}")" \
    "$(escapar_pgpass "${RESTAURACAO_PGPASSWORD}")" >"${pgpass_temporario}"
  export PGPASSFILE="${pgpass_temporario}"
  unset RESTAURACAO_PGPASSWORD
fi

age --decrypt --identity "${AGE_IDENTITY}" "${BACKUP_ARQUIVO}" \
  | gzip -d \
  | pg_restore --clean --if-exists --no-owner \
      --host "${RESTAURACAO_PGHOST}" --port "${RESTAURACAO_PGPORT}" \
      --username "${RESTAURACAO_PGUSER}" --dbname "${RESTAURACAO_PGDATABASE}"
psql --host "${RESTAURACAO_PGHOST}" --port "${RESTAURACAO_PGPORT}" \
  --username "${RESTAURACAO_PGUSER}" --dbname "${RESTAURACAO_PGDATABASE}" \
  -c 'select count(*) from usuarios;'

