#!/bin/bash
# heredoc 회귀 — 파일에 쓰는 문자열은 실행이 아니다.
#
# 실측 2026-09-05: deploy.sh 의 도움말 문구를 heredoc 으로 쓰다가 배포
# 게이트에 걸렸고, 훅 자기테스트를 짜다가 force-push 게이트에 걸렸다.
# 문서를 쓰는 것만으로 발동하는 게이트는 곧 꺼진다.
cd "$(dirname "$0")/../.." || exit 1
G=.claude/hooks/guard-bash.sh
PASS=0; FAIL=0
check() {
  code=$(printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$3" | jq -Rs .)" | $G >/dev/null 2>&1; echo $?)
  got=$([ "$code" -eq 2 ] && echo deny || echo allow)
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-44s 기대=%-5s 결과=%s\n" "$m" "$1" "$2" "$got"
}

HD_DEPLOY='cat > /tmp/help.txt <<EOF
사용법: tools/deploy.sh scheduler
EOF'
HD_PUSH='cat > /tmp/doc.md <<DOC
금지: git push --force origin main
DOC'
HD_RM='cat > /tmp/doc.md <<DOC
금지: rm -rf app/
DOC'
HD_THEN_REAL='cat > /tmp/x <<EOF
안내문
EOF
tools/deploy.sh scheduler'

echo "══ heredoc 본문은 실행이 아니다 ══"
check "heredoc 안의 deploy.sh"                allow "$HD_DEPLOY"
check "heredoc 안의 force push"               allow "$HD_PUSH"
check "heredoc 안의 rm -rf"                   allow "$HD_RM"
echo "══ 종료 표시자 뒤는 다시 코드다 ══"
check "heredoc 종료 후 실제 배포"              deny  "$HD_THEN_REAL"
echo "══ 기존 게이트가 살아 있는가 ══"
check "실제 배포 실행"                         deny  "tools/deploy.sh all"
check "실제 rm -rf"                           deny  "rm -rf app/"
check "읽기는 통과"                            allow "cat tools/deploy.sh"
echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
