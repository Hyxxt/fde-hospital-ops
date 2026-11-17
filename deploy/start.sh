#!/usr/bin/env bash
set -euo pipefail

args=(app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --no-access-log)
if [[ "${PUBLIC_DEMO:-0}" != 1 || -n "${DATABASE_URL:-}" ]]; then
  exec uvicorn "${args[@]}"
fi

# The public sample can rebuild its immutable, fictional dataset after any restart.
demo_dir=$(mktemp -d /tmp/hospital-demo.XXXXXXXX)
chown postgres:postgres "$demo_dir"
gosu postgres initdb -D "$demo_dir/data" -A trust --no-locale -E UTF8 >/dev/null
gosu postgres pg_ctl -D "$demo_dir/data" -l "$demo_dir/postgres.log" \
  -o "-c listen_addresses='' -c unix_socket_directories=$demo_dir -c shared_buffers=24MB -c max_connections=12" -w start
trap 'gosu postgres pg_ctl -D "$demo_dir/data" -m fast -w stop' EXIT
export DATABASE_URL="dbname=postgres user=postgres host=$demo_dir"
gosu postgres uvicorn "${args[@]}" &
web_pid=$!
trap 'kill -TERM "$web_pid" 2>/dev/null || true; wait "$web_pid" || true; exit 0' TERM INT
wait "$web_pid"
