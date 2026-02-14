#!/usr/bin/env bash
# QuantumState — start frontend + backend
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> QuantumState"
echo "    Root: $ROOT"
echo ""

# Activate project venv if available
if [ -f "$ROOT/.venv/bin/activate" ]; then
  source "$ROOT/.venv/bin/activate"
fi

# Backend
echo "==> Backend  →  http://localhost:8000"
cd "$ROOT/backend"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
echo "==> Frontend →  http://localhost:8080"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Landing:  http://localhost:8080"
echo "  Console:  http://localhost:8080/console"
echo "  Sim:      http://localhost:8080/sim"
echo "  API:      http://localhost:8000"
echo ""
echo "  Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
