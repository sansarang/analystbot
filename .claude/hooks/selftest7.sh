#!/bin/bash
# 완료 주장 게이트 — 파일을 고친 턴에만 운다.
#
# 실측 2026-09-06: 조사만 한 턴에서 "확인 완료"라는 말에 헛울렸다.
# 코드를 안 고쳤으면 돌릴 테스트도 없다. 헛경보가 쌓이면 훅은 꺼진다.
cd "$(dirname "$0")/../.." || exit 1
H=.claude/hooks/claim-gate.sh
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

mk() {  # $1=파일 $2=본문텍스트 $3=도구JSON배열(없으면 빈)
  T="$TMP/$1.jsonl"
  printf '%s\n' '{"type":"user","message":{"content":[{"type":"text","text":"작업해줘"}]}}' > "$T"
  printf '{"type":"assistant","message":{"content":[{"type":"text","text":%s}%s]}}\n' \
    "$(printf '%s' "$2" | jq -Rs .)" "$3" >> "$T"
  echo "$T"
}

run() {  # $1=이름 $2=기대(warn|pass) $3=transcript
  out=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$3" | $H 2>&1)
  code=$?
  got=$([ $code -eq 2 ] && echo warn || echo pass)
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-40s 기대=%-5s 결과=%s\n" "$m" "$1" "$2" "$got"
}

EDIT=',{"type":"tool_use","name":"Edit","input":{"file_path":"app/x.py"}}'
BASH_W=',{"type":"tool_use","name":"Bash","input":{"command":"sed -i s/a/b/ app/x.py"}}'
BASH_R=',{"type":"tool_use","name":"Bash","input":{"command":"grep -n foo app/x.py"}}'
TEST=',{"type":"tool_use","name":"Bash","input":{"command":"PYTHONPATH=. uv run pytest tests -q"}}'

echo "══ 파일을 고쳤는데 테스트가 없으면 운다 ══"
run "Edit + 완료 주장"        warn "$(mk a '수정 완료했습니다' "$EDIT")"
run "Bash 쓰기 + 완료 주장"    warn "$(mk b '고쳤습니다. 완료.' "$BASH_W")"

echo "══ 테스트를 돌렸으면 통과 ══"
run "Edit + pytest + 완료"    pass "$(mk c '수정 완료' "$EDIT$TEST")"

echo "══ 파일을 안 고친 턴은 통과 ══"
run "조사만 + 완료 주장"       pass "$(mk d '확인 완료했습니다' "$BASH_R")"
run "도구 없이 보고만"         pass "$(mk e '조사 완료입니다' '')"

echo "══ 완료를 주장하지 않으면 통과 ══"
run "Edit + 주장 없음"        pass "$(mk f '진행 중입니다' "$EDIT")"

echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
