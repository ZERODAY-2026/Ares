#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON_ENV="$ROOT/.venv"
LLAMA_BIN="${LEGALLENS_LLAMA_SERVER:-/Users/sakshamgupta/llama.cpp/build/bin/llama-server}"
MODEL_PATH="${LEGALLENS_MODEL_PATH:-/Users/sakshamgupta/Models/gemma-3n-E2B-it/gemma-3n-E2B-it-Q8_0.gguf}"
API_PORT=8000
LLAMA_PORT=8080
FRONTEND_PORT=5173

stop_process_on_port() {
  local port="$1"
  local pids
  # Only terminate listeners. Do not kill browser/client processes connected to the port.
  pids="$(lsof -nP -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "Stopping existing listener(s) on port $port: $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -nP -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

[[ -d "$PYTHON_ENV" ]] || { echo "Missing Python environment: $PYTHON_ENV"; exit 1; }
[[ -x "$LLAMA_BIN" ]] || { echo "llama-server not found: $LLAMA_BIN"; exit 1; }
[[ -f "$MODEL_PATH" ]] || { echo "Gemma model not found: $MODEL_PATH"; exit 1; }
[[ -d "$ROOT/frontend/node_modules" ]] || {
  echo "Missing frontend dependencies. Run 'npm install' once while online."; exit 1;
}

# LegalLens owns these local development ports. Clear stale processes before
# validating dependencies or starting any service.
stop_process_on_port "$API_PORT"
stop_process_on_port "$LLAMA_PORT"
stop_process_on_port "$FRONTEND_PORT"

API_PID=""
LLAMA_PID=""
FRONTEND_PID=""
cleanup() {
  echo
  echo "Stopping LegalLens local services..."
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "$LLAMA_PID" ]] && kill "$LLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source "$PYTHON_ENV/bin/activate"

echo "Starting local Gemma server..."
"$LLAMA_BIN" \
  -m "$MODEL_PATH" \
  -c 2048 \
  -t 4 \
  --host 127.0.0.1 \
  --port "$LLAMA_PORT" \
  >/tmp/legallens-llama.log 2>&1 &
LLAMA_PID=$!

for _ in {1..90}; do
  if curl -fsS "http://127.0.0.1:$LLAMA_PORT/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$LLAMA_PORT/health" >/dev/null || {
  echo "Gemma server failed to start. See /tmp/legallens-llama.log"; exit 1;
}

echo "Starting local FastAPI backend..."
uvicorn backend.api:app --host 127.0.0.1 --port "$API_PORT" >/tmp/legallens-api.log 2>&1 &
API_PID=$!

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null || {
  echo "FastAPI failed to start. See /tmp/legallens-api.log"; exit 1;
}

echo "Starting local React frontend..."
(cd "$ROOT/frontend" && npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT") >/tmp/legallens-frontend.log 2>&1 &
FRONTEND_PID=$!
sleep 2

printf '\nLegalLens is running completely offline:\n'
printf '  Frontend: http://127.0.0.1:%s\n' "$FRONTEND_PORT"
printf '  Backend:  http://127.0.0.1:%s\n' "$API_PORT"
printf '  Gemma:    http://127.0.0.1:%s\n' "$LLAMA_PORT"
printf '\nPress Ctrl+C to stop all three services.\n\n'
wait "$FRONTEND_PID"
