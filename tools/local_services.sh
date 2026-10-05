#!/bin/bash
# 로컬 운영 서비스 기동 — 🔴 **터미널에서 띄운 프로세스는 운영으로 치지 않는다**
# (§17-g-8). launchd 가 이 스크립트를 부르고, 이 스크립트가 순서를 지킨다.
#
#   colima(도커 런타임) → docker compose(postgres·redis·searxng) → ollama
#
# 🔴 루프백에만 바인딩한다. compose 의 포트 매핑이 그것을 강제한다.
# 🔴 이 스크립트는 **멱등**이다 — 이미 떠 있으면 아무것도 안 한다.
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

if ! colima status >/dev/null 2>&1; then
  log "colima 기동"
  colima start || { log "colima 실패"; exit 1; }
else
  log "colima 이미 떠 있다"
fi

log "compose up"
docker compose up -d || { log "compose 실패"; exit 1; }

# ── Ollama — §17-a. 로컬 LLM 이 없으면 추출이 통째로 죽는다.
if ! curl -sf -m 3 "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}/api/tags" >/dev/null; then
  if command -v ollama >/dev/null 2>&1; then
    log "ollama serve 기동"
    nohup ollama serve >/tmp/ollama.log 2>&1 &
  else
    log "⚠️ ollama 가 설치돼 있지 않다 — LLM 추출은 돌지 않는다"
  fi
else
  log "ollama 이미 떠 있다"
fi

# ── 기동 확인. 🔴 "명령을 보냈다 ≠ 반영됐다"(실사고 2026-09-05).
for i in $(seq 1 30); do
  ok=1
  curl -sf -m 3 "http://127.0.0.1:8888/search?q=ping&format=json" >/dev/null || ok=0
  docker exec analystbot-postgres pg_isready -U analyst -d analystbot >/dev/null 2>&1 || ok=0
  [ "$ok" = 1 ] && { log "확인 완료 — searxng·postgres 응답"; exit 0; }
  sleep 4
done
log "⚠️ 기동 확인 실패 — searxng 또는 postgres 가 응답하지 않는다"
exit 1
