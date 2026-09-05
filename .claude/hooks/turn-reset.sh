#!/bin/bash
# [UserPromptSubmit] 턴 경계 — 계획 게이트의 파일 카운터를 비운다.
source "$(dirname "$0")/lib.sh"
S=$(cat | jq -r '.session_id // "x"' 2>/dev/null)
rm -f "$STATE/turn-$S" "$STATE/plan-ack-$S" 2>/dev/null
exit 0
