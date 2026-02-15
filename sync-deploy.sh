#!/usr/bin/env bash
set -e

MODE=${1:-dry}   # default = dry-run

RSYNC_FLAGS="-av --delete --itemize-changes --ignore-times"

if [[ "$MODE" == "dry" ]]; then
  echo "🧪 DRY-RUN MODE (no files will be changed)"
  RSYNC_FLAGS="$RSYNC_FLAGS --dry-run"
elif [[ "$MODE" == "apply" ]]; then
  echo "🚀 APPLY MODE (files WILL be changed)"
else
  echo "❌ Unknown mode: $MODE"
  echo "Usage: ./sync-deploy.sh [dry|apply]"
  exit 1
fi

echo "=================================="
echo " Syncing QuantumState Deploy Repos "
echo "=================================="

BASE="/Users/paddy/Documents/Github/quantumstate"

BACKEND_SRC="$BASE/backend/"
BACKEND_DEST="/Users/paddy/Documents/Github/QuantumState-Backend/"

FRONTEND_SRC="$BASE/frontend/"
FRONTEND_DEST="/Users/paddy/Documents/Github/QuantumState-Frontend/"

COMMON_EXCLUDES=(
  --exclude '.git'
  --exclude '.git/**'
  --exclude '.DS_Store'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.env'
  --exclude '.env.*'
)

echo ""
echo "▶ BACKEND changes (→ QuantumState-Backend):"
rsync $RSYNC_FLAGS \
  "${COMMON_EXCLUDES[@]}" \
  "$BACKEND_SRC" "$BACKEND_DEST" \
  | grep -E '^[><].*([+s])|\*deleting' || echo "✔ No backend changes"

echo ""
echo "▶ FRONTEND changes (→ QuantumState-Frontend):"
rsync $RSYNC_FLAGS \
  "${COMMON_EXCLUDES[@]}" \
  --exclude 'node_modules' \
  --exclude 'dist' \
  "$FRONTEND_SRC" "$FRONTEND_DEST" \
  | grep -E '^[><].*([+s])|\*deleting' || echo "✔ No frontend changes"

echo ""
echo "✅ Sync completed ($MODE mode)"
echo ""
if [[ "$MODE" == "apply" ]]; then
  echo "Next steps:"
  echo "  cd /Users/paddy/Documents/Github/QuantumState-Backend && git add -A && git commit -m \"sync\" && git push"
  echo "  cd /Users/paddy/Documents/Github/QuantumState-Frontend && git add -A && git commit -m \"sync\" && git push"
fi
