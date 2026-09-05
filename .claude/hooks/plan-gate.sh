#!/bin/bash
# [PreToolUse · Edit|Write|NotebookEdit] 3파일 이상 작업은 계획서를 먼저.
#
# 🔴 **벽이 아니라 과속방지턱이다.** 턴당 한 번만 막고, 그 뒤로는 통과시킨다.
#    매번 막으면 이 훅은 곧 꺼진다 — 꺼진 훅은 없는 훅이다.
#    목적은 "3번째 파일을 여는 순간 잠깐 멈춰 서서 계획을 말하게" 하는 것이다.
source "$(dirname "$0")/lib.sh"

IN=$(cat)
FILE=$(printf '%s' "$IN" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
SESSION=$(printf '%s' "$IN" | jq -r '.session_id // "x"' 2>/dev/null)
[ -z "$FILE" ] && exit 0

TURN="$STATE/turn-$SESSION"
ACK="$STATE/plan-ack-$SESSION"

# 이번 턴에 만진 파일 목록에 추가(중복 제거)
touch "$TURN"
grep -qxF "$FILE" "$TURN" 2>/dev/null || printf '%s\n' "$FILE" >> "$TURN"
N=$(sort -u "$TURN" 2>/dev/null | wc -l | tr -d ' ')

# 이미 한 번 알렸으면 통과
[ -f "$ACK" ] && exit 0
[ "$N" -lt 3 ] && exit 0

# 문서·설정만 만지는 작업은 계획서 대상이 아니다.
if ! sort -u "$TURN" | grep -qvE '\.(md|json|ya?ml|txt|toml|cfg|ini)$|/\.claude/'; then
  exit 0
fi

: > "$ACK"
log_audit "PLAN-GATE ${N}파일 session=${SESSION:0:8}"
cat >&2 <<MSG
⏸ 세 번째 파일이다 (이번 턴 ${N}개). 계획을 먼저 말하라.

$(sort -u "$TURN" | sed 's/^/   · /')

3파일 이상은 즉흥으로 시작하면 중간에 방향이 바뀌고, 그때는 이미 되돌리기
어렵다. 지금 할 일:
  ① 무엇을 바꾸는지 · 왜 · 어떤 순서로 — 세 줄로 정리해 사용자에게 말한다
  ② 되돌릴 수 없는 변경이 있으면 승인을 받는다
  ③ 그 다음 계속한다 — 이 훅은 이번 턴에 다시 막지 않는다
MSG
exit 2
