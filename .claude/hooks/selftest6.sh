#!/bin/bash
# 마커 기록 판정 — 구간별로 본다.
#
# 실측 2026-09-06: `pytest tests/test_x.py -q; pytest tests -q` 를 부분 실행으로
# 읽어 마커를 남기지 않았고, 전체를 돌렸는데 커밋이 막혔다.
cd "$(dirname "$0")/../.." || exit 1
H=.claude/hooks/record-green.sh
STATE=.claude/state/last-green
PASS=0; FAIL=0
BAK=$(mktemp); [ -f "$STATE" ] && cp "$STATE" "$BAK"

check() {  # $1=이름 $2=기대(record|skip) $3=명령
  rm -f "$STATE"
  printf '{"tool_input":{"command":%s},"tool_response":{"stdout":"2086 passed, 4 skipped in 56s"}}' \
    "$(printf '%s' "$3" | jq -Rs .)" | $H >/dev/null 2>&1
  got=$([ -f "$STATE" ] && echo record || echo skip)
  if [ "$got" = "$2" ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-46s 기대=%-6s 결과=%s\n" "$m" "$1" "$2" "$got"
}

echo "══ 전체 실행은 기록한다 ══"
check "pytest tests -q"                       record "PYTHONPATH=. uv run pytest tests -q"
check "부분 뒤에 전체 (세미콜론)"                record "pytest tests/test_x.py -q; pytest tests -q"
check "부분 뒤에 전체 (&&)"                    record "pytest tests/test_x.py -q && pytest tests -q"
check "파이프가 뒤에 붙어도"                    record "PYTHONPATH=. uv run pytest tests -q 2>&1 | tail -3"

echo "══ 부분 실행만이면 기록하지 않는다 ══"
check "단일 파일만"                            skip   "pytest tests/test_situation.py -q"
check "-k 필터만"                              skip   "pytest tests -k situation -q"
check "pytest 아님"                            skip   "git status"

echo "══ 실패가 섞이면 기록하지 않는다 ══"
rm -f "$STATE"
printf '{"tool_input":{"command":"pytest tests -q"},"tool_response":{"stdout":"1 failed, 2085 passed"}}' \
  | $H >/dev/null 2>&1
if [ -f "$STATE" ]; then FAIL=$((FAIL+1)); echo "  🔴 실패 포함인데 기록했다"; \
  else PASS=$((PASS+1)); echo "  ✅ 실패 포함 → 기록 안 함"; fi

[ -s "$BAK" ] && cp "$BAK" "$STATE" || rm -f "$STATE"
rm -f "$BAK"
echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
