#!/bin/sh
set -eu

case "${1:-serve}" in
  serve)
    exec uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
