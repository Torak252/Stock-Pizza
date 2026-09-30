#!/usr/bin/env bash
# Run everything locally with one command: API, collector (worker) and dashboard.
#   ./start.sh          first run installs dependencies (~5 min), later runs start in seconds
# Stop with Ctrl-C. Data lives in backend/pizza_tracker.db.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  echo "==> Creating Python environment (first run only)"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  if [ "$(uname)" = "Darwin" ]; then
    backend/.venv/bin/pip install -q torch torchvision
  else  # CPU-only wheels: ~200 MB instead of multi-GB CUDA builds
    backend/.venv/bin/pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  fi
  backend/.venv/bin/pip install -q -e "backend[vision]"
fi
[ -f backend/.env ] || { cp backend/.env.example backend/.env; echo "==> Created backend/.env (set SPT_CONTACT_EMAIL for SEC data)"; }

if [ ! -d frontend/node_modules ]; then (cd frontend && npm install --no-audit --no-fund); fi
echo "==> Building dashboard"
(cd frontend && npm run build >/dev/null)

cd backend
.venv/bin/python -m pizza_tracker.cli init
.venv/bin/uvicorn pizza_tracker.api.main:app --host 127.0.0.1 --port 8000 --log-level warning &
API=$!
.venv/bin/python -m pizza_tracker.cli worker &
WORKER=$!
(cd ../frontend && npx next start -p 3000 >/dev/null) &
WEB=$!
trap 'echo; echo "==> Stopping"; kill $API $WORKER $WEB 2>/dev/null; wait 2>/dev/null' EXIT INT TERM

echo "==> Dashboard: http://localhost:3000   (API: http://127.0.0.1:8000/docs)"
echo "==> The collector maps cameras on first start, then samples every 2 minutes."
wait
