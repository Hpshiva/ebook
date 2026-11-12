#!/usr/bin/env bash
# One command to run Creator Finder locally at http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install --no-audit --no-fund); fi
if [ ! -d frontend/dist ] || [ "${REBUILD:-0}" = "1" ]; then (cd frontend && npm run build); fi

cd backend
exec .venv/bin/python -m uvicorn app.main:app --port "${PORT:-8000}"
