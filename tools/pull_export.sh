#!/usr/bin/env bash
# [EXP-3] 내보내기 산출물 회수 — 볼륨 → 로컬 다운로드 폴더.
#
# 🔴 **읽기만 한다.** 컨테이너에 쓰지 않고, 재시작하지 않고, DB·Redis 를
#    만지지 않는다. `railway ssh` 는 읽기 전용으로만 쓴다(규율 7).
# 🔴 볼륨 경로를 **손으로 적지 않는다** — 컨테이너의 `RAILWAY_VOLUME_MOUNT_PATH`
#    에 물어본다. 여기 `/data` 를 적는 순간 그것은 사본이고, 마운트가 바뀌는
#    날 따라가지 않는다.
# 🔴 **덮지 않는다** — 이름이 겹치면 `_r2`·`_r3` 로 늘린다(서버 규칙과 같다).
# ⚠️ 받을 것이 없으면 **조용히 끝내지 않는다** — 찍고 1로 나간다.
#    "받았다"와 "받을 게 없었다"가 구분되지 않으면 내일 아침에 알 수 없다.
#
# 사용:  tools/pull_export.sh [날짜]          기본값 = 오늘 KST
set -uo pipefail

PROJECT="${RAILWAY_PROJECT_ID:-d29edc63-4309-4656-a8af-543b8b773437}"
SERVICE="${RAILWAY_SERVICE:-analystbot-scheduler}"
ENVIRON="${RAILWAY_ENVIRONMENT_NAME:-production}"
KEY="${RAILWAY_SSH_KEY:-$HOME/.ssh/id_ed25519_new}"
LOCAL_DIR="$HOME/Downloads/analystbot_export"
DATE="${1:-$(TZ=Asia/Seoul date +%F)}"

# 🔴 stderr 를 **합치지 않는다.** Railway 는 Config-as-Code 경고 배너를 stderr 로
#    찍는데, `2>&1` 로 합치면 그 배너가 받아온 파일 안에 섞인다. 실측으로 잡았다:
#      printf %s → 개행이 없어 배너가 값과 같은 줄에 붙고, 줄 단위 grep 이
#      값까지 통째로 버렸다(VOL 이 빈 문자열이 됐다).
#    stdout 만 받으면 서버 원본과 **바이트가 같다**(8165 = 8165, 실측).
rssh() {
  railway ssh -i "$KEY" --project "$PROJECT" --environment "$ENVIRON" \
    --service "$SERVICE" "$1" 2>/dev/null
}

# 🔴 값을 **자기 줄에** 실어 보낸다 — 이름표가 있어야 섞인 줄과 구분된다.
VOL=$(rssh 'echo "VOL=${RAILWAY_VOLUME_MOUNT_PATH:-}"' \
      | sed -n 's/^VOL=//p' | tr -d '\r' | head -1)
if [ -z "$VOL" ]; then
  echo "🔴 볼륨이 없다 — 컨테이너의 RAILWAY_VOLUME_MOUNT_PATH 가 비었다." >&2
  echo "   볼륨 밖에 쓴 파일은 재배포마다 사라진다(docs/FORKS.md F-18)." >&2
  exit 1
fi
REMOTE_DIR="$VOL/export"

# ⚠️ `mapfile` 을 쓰지 않는다 — macOS 기본 bash 는 3.2 라 그 내장이 없다(실측).
FILES=()
while IFS= read -r line; do
  [ -n "$line" ] && FILES+=("$line")
done < <(rssh "ls -1 $REMOTE_DIR 2>/dev/null | grep '^${DATE}_' || true" | tr -d '\r')

if [ "${#FILES[@]:-0}" -eq 0 ]; then
  echo "🔴 $DATE 산출물이 $REMOTE_DIR 에 없다 — 받을 것이 없다." >&2
  echo "   잡이 돌았는지 확인하라: export_t3h_10m · export_lineup_5m" >&2
  exit 1
fi

mkdir -p "$LOCAL_DIR"
got=0
for f in "${FILES[@]}"; do
  dst="$LOCAL_DIR/$f"
  if [ -e "$dst" ]; then                      # 덮지 않는다 — 번호를 올린다
    base="${f%.*}"; ext="${f##*.}"; n=1
    while [ -e "$dst" ]; do n=$((n + 1)); dst="$LOCAL_DIR/${base}_r${n}.${ext}"; done
  fi
  if rssh "cat $REMOTE_DIR/$f" > "$dst" && [ -s "$dst" ]; then
    printf '  ↓ %-44s %8d바이트  →  %s\n' "$f" "$(wc -c < "$dst")" "$dst"
    got=$((got + 1))
  else
    rm -f "$dst"
    echo "  🔴 $f 회수 실패" >&2
  fi
done
echo "받음 ${got}/${#FILES[@]}건 · $LOCAL_DIR"
[ "$got" -gt 0 ]
