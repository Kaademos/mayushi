#!/bin/sh
set -eu

case "${1:-serve}" in
  serve)
    exec uvicorn orders.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  seed)
    shift
    exec python -m orders.seed "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
