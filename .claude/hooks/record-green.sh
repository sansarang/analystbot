#!/bin/bash
# [PostToolUse · Bash] 전체 테스트 스위트가 **실제로 통과**했을 때만 마커를 남긴다.
#
# 🔴 마커는 사람이 손으로 만들 수 없다 — 이 훅이 pytest 의 **실제 출력**을 보고
#    쓴다. "테스트 돌렸다"는 주장과 "돌아서 통과했다"는 사실을 분리하는 것이
#    이 체계 전체의 기반이다.
source "$(dirname "$0")/lib.sh"

IN=$(cat)
CMD=$(printf '%s' "$IN" | jq -r '.tool_input.command // ""' 2>/dev/null)
OUT=$(printf '%s' "$IN" | jq -r '(.tool_response.stdout // "") + "\n" + (.tool_response.stderr // "") + "\n" + (.tool_response | if type=="string" then . else "" end)' 2>/dev/null)

# 전체 스위트인가. `-k`/단일 파일 지정은 부분 실행이므로 인정하지 않는다.
#
# 🔴 [2026-09-06] **명령을 구간별로 본다.** 종전에는 명령 전체를 한 덩어리로
#    봐서, `pytest tests/test_x.py && pytest tests -q` 처럼 부분 실행과 전체
#    실행이 한 줄에 있으면 부분으로 판정하고 마커를 남기지 않았다.
#    그러면 전체를 돌렸는데도 커밋이 막힌다 — 실제로 막혔다.
FULL=0
while IFS= read -r seg; do
  case "$seg" in *pytest*) : ;; *) continue ;; esac
  case "$seg" in *" -k "*) continue ;; esac          # 필터 실행
  case "$seg" in *"tests/test_"*|*"tests/"*.py*) continue ;; esac  # 단일 파일
  case "$seg" in *pytest*tests*) FULL=1 ;; esac
done <<EOF
$(printf '%s' "$CMD" | tr ';&|' '\n')
EOF
[ "$FULL" -eq 1 ] || exit 0

# pytest 요약줄만 믿는다. "N passed" 가 있고 failed/error 가 없어야 한다.
if ! printf '%s' "$OUT" | grep -qE '[0-9]+ passed'; then exit 0; fi
if printf '%s' "$OUT" | grep -qE '[0-9]+ (failed|error)'; then
  log_audit "GREEN-SKIP 실패 포함 cmd=${CMD:0:60}"
  exit 0
fi

N=$(printf '%s' "$OUT" | grep -oE '[0-9]+ passed' | tail -1)
printf '%s\n%s\n%s\n' "$(worktree_sig)" "$(date '+%F %T')" "$N" > "$GREEN"
log_audit "GREEN 기록 $N sig=$(worktree_sig)"
exit 0
