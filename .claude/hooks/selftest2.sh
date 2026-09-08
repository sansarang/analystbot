#!/bin/bash
# 배포 게이트 오탐 회귀 — "읽기"는 막지 않고 "실행"만 막는다.
cd "$(dirname "$0")/../.." || exit 1
G=.claude/hooks/guard-bash.sh
PASS=0; FAIL=0
# ⚠️ 이 파일이 보는 것은 "**배포 명령으로 인식하는가**"이지 배포 조건이 아니다.
#    그러니 deny 의 이유를 테스트가 직접 만든다 — 마커를 낡게 해 둔다.
#    🔴 실측 2026-09-08: 전부 커밋되고 전체 스위트가 통과한 상태(= 배포가
#       통과해야 마땅한 상태)가 되자, 이유를 만들지 않은 이 파일이 통째로
#       빨개졌다. 개발 중엔 늘 작업트리가 더러워 **맞는 이유 없이 통과**하고
#       있었던 것이다.
source .claude/hooks/lib.sh
GBAK=$(mktemp); HADG=0; [ -f "$GREEN" ] && { cp "$GREEN" "$GBAK"; HADG=1; }
printf 'deadbeef\n2000-01-01 00:00:00\n0 passed\n' > "$GREEN"
restore_green() { if [ "$HADG" = 1 ]; then cp "$GBAK" "$GREEN"; else rm -f "$GREEN"; fi; rm -f "$GBAK"; }
trap restore_green EXIT
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
