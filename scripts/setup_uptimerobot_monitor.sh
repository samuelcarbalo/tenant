#!/usr/bin/env bash
# Crea (o lista) un monitor HTTP en UptimeRobot para el health check de Render.
#
# Uso (una sola vez, con API key de https://uptimerobot.com/dashboard#mySettings):
#   export UPTIMEROBOT_API_KEY="tu_api_key"
#   bash scripts/setup_uptimerobot_monitor.sh
#
# Intervalo: 600 s = 10 min (mínimo plan free: 300 s / 5 min).

set -euo pipefail

HEALTH_URL="${HEALTH_URL:-https://missingdigitalback.onrender.com/api/v1/health/}"
MONITOR_NAME="${MONITOR_NAME:-Chever Backend (Render health)}"
INTERVAL="${INTERVAL:-600}"

if [[ -z "${UPTIMEROBOT_API_KEY:-}" ]]; then
  echo "Error: define UPTIMEROBOT_API_KEY (Settings → API Settings en UptimeRobot)." >&2
  exit 1
fi

echo "Comprobando monitors existentes para ${HEALTH_URL}..."
existing=$(curl -s -X POST "https://api.uptimerobot.com/v2/getMonitors" \
  -d "api_key=${UPTIMEROBOT_API_KEY}&format=json&logs=0" \
  | python -c "
import json, sys
data = json.load(sys.stdin)
url = sys.argv[1]
for m in data.get('monitors', []) or []:
    if m.get('url') == url:
        print(m.get('id', ''))
        break
" "$HEALTH_URL" 2>/dev/null || true)

if [[ -n "$existing" ]]; then
  echo "Ya existe monitor id=${existing} → ${HEALTH_URL}"
  exit 0
fi

echo "Creando monitor HTTP (intervalo ${INTERVAL}s)..."
response=$(curl -s -X POST "https://api.uptimerobot.com/v2/newMonitor" \
  -d "api_key=${UPTIMEROBOT_API_KEY}" \
  -d "format=json" \
  -d "type=1" \
  -d "url=${HEALTH_URL}" \
  -d "friendly_name=${MONITOR_NAME}" \
  -d "interval=${INTERVAL}")

echo "$response" | python -m json.tool 2>/dev/null || echo "$response"
