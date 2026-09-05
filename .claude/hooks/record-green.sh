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
case "$CMD" in
  *pytest*tests*) : ;;
  *) exit 0 ;;
esac
case "$CMD" in
  *" -k "*|*"tests/test_"*) exit 0 ;;      # 부분 실행 — 마커 없음
esac

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
