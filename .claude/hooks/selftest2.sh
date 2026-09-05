#!/bin/bash
# 배포 게이트 오탐 회귀 — "읽기"는 막지 않고 "실행"만 막는다.
cd "$(dirname "$0")/../.." || exit 1
G=.claude/hooks/guard-bash.sh
PASS=0; FAIL=0
check() {
  code=$(printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$3" | jq -Rs .)" | $G >/dev/null 2>&1; echo $?)
  got=$([ "$code" -eq 2 ] && echo deny || echo allow)
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-40s 기대=%-5s 결과=%s\n" "$m" "$1" "$2" "$got"
}
echo "══ 배포 게이트 — 읽기 vs 실행 ══"
check "sed 로 읽기"              allow "sed -n '60,95p' tools/deploy.sh"
check "cat 로 읽기"              allow "cat tools/deploy.sh"
check "grep 으로 읽기"            allow "grep -n SUCCESS tools/deploy.sh"
check "파일명이 인자로 등장"        allow "git add tools/deploy.sh"
check "실행 (tools/ 접두)"        deny  "tools/deploy.sh scheduler"
check "실행 (./ 접두)"            deny  "./tools/deploy.sh all"
check "실행 (bash 경유)"          deny  "bash tools/deploy.sh bot"
check "railway up 실행"          deny  "railway up --service x"
check "railway logs (무관)"       allow "railway logs --service analystbot-bot"
check "&& 뒤 실행"                deny  "git status && tools/deploy.sh scheduler"
echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
