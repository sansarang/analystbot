#!/bin/bash
# reset --hard 가드 — 커밋 안 된 작업이 있을 때만 막는다.
cd "$(dirname "$0")/../.." || exit 1
G=.claude/hooks/guard-bash.sh
PASS=0; FAIL=0
check() {
  code=$(printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$3" | jq -Rs .)" | $G >/dev/null 2>&1; echo $?)
  got=$([ "$code" -eq 2 ] && echo deny || echo allow)
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-40s 기대=%-5s 결과=%s\n" "$1" "$m" "$2" "$got"
}
DIRTY=$([ -n "$(git status --porcelain)" ] && echo yes || echo no)
echo "══ git reset --hard (작업트리 dirty=$DIRTY) ══"
if [ "$DIRTY" = "yes" ]; then
  check "reset --hard HEAD~1"  deny  "git reset --hard HEAD~1"
  check "reset --hard origin"  deny  "git reset --hard origin/main"
else
  echo "  ⏭  클린 상태 — 이 가드는 dirty 일 때만 막는다"
  check "reset --hard (클린)"   allow "git reset --hard HEAD~1"
fi
check "reset --soft (안전)"    allow "git reset --soft HEAD~1"
check "reset --mixed (안전)"   allow "git reset --mixed HEAD~1"
check "reset (인자 없음)"       allow "git reset"
check "git log (무관)"          allow "git log --oneline"
echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
