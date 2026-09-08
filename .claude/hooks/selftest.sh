#!/bin/bash
# 훅 자기검증 — 고의 위반으로 각 게이트를 발동시킨다.
#
# ⚠️ 페이로드를 이 파일 안에 둔다. 명령줄에 위반 문자열을 그대로 쓰면
#    **훅이 자기 테스트를 막는다** (실측 2026-09-05: force-push 테스트가
#    그렇게 차단됐다 — 훅이 살아 있다는 증거이기도 하다).
cd "$(dirname "$0")/../.." || exit 1
G=.claude/hooks/guard-bash.sh
PASS=0; FAIL=0

check() {  # $1=이름  $2=기대(deny|allow)  $3=명령
  out=$(printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$3" | jq -Rs .)" | $G 2>&1)
  code=$?
  got=$([ $code -eq 2 ] && echo deny || echo allow)
  if [ "$got" = "$2" ]; then
    PASS=$((PASS+1)); mark="✅"
  else
    FAIL=$((FAIL+1)); mark="🔴"
  fi
  printf "  %s %-32s 기대=%-5s 결과=%-5s(exit %d)\n" "$mark" "$1" "$2" "$got" "$code"
  [ $code -eq 2 ] && printf '%s\n' "$out" | sed -n '1p' | sed 's/^/         /'
  return 0
}

echo "══ (c) 위험 명령 ══"
check "rm -rf 소스 디렉토리"   deny  "rm -rf app/"
check "rm -rf 스크래치패드"    allow "rm -rf /private/tmp/claude-501/x/scratchpad/t"
check "rm -rf __pycache__"    allow "rm -rf app/__pycache__/"
check "main 강제 push"        deny  "git push --force origin main"
check "브랜치 일반 push"       allow "git push origin rework/form-only"
check "일반 rm"               allow "rm docs/tmp.md"

echo "══ (c-2) 슬레이트 성역 (KST $(TZ=Asia/Seoul date +%H:%M)) ══"
H=$(TZ=Asia/Seoul date '+%-H')
if [ "$H" -ge 17 ] && [ "$H" -lt 22 ]; then
  check "슬레이트 창 배포"      deny  "tools/deploy.sh scheduler"
  # ⚠️ OVERRIDE 는 **성역 게이트만** 통과시킨다. 뒤의 게이트(미커밋·미검증)는
  #    그대로 걸린다 — 게이트는 순서대로 쌓인다. 그래서 "allow" 를 기대하면
  #    안 되고, "슬레이트 사유로는 막히지 않는가"를 봐야 한다.
  out=$(printf '{"tool_input":{"command":%s}}' \
        "$(printf '%s' "SLATE_OVERRIDE='P0 카드0장' tools/deploy.sh scheduler" | jq -Rs .)" | $G 2>&1)
  if printf '%s' "$out" | grep -q "슬레이트 창 배포 차단"; then
    FAIL=$((FAIL+1)); printf "  🔴 %-32s OVERRIDE 가 성역을 통과시키지 못했다\n" "SLATE_OVERRIDE 명시"
  else
    PASS=$((PASS+1)); printf "  ✅ %-32s 성역 통과 (다음 게이트로 넘어감)\n" "SLATE_OVERRIDE 명시"
  fi
else
  echo "  ⏭  지금은 슬레이트 창이 아니다(${H}시) — 창 밖 동작만 확인한다"
  # 🔴 [2026-09-08] 종전에는 그냥 deny 를 기대했다. 그 기대는 "작업트리가
  #    더럽거나 마커가 낡았다"는 **주변 상태에 얹혀 있었다.** 전부 커밋하고
  #    전체 스위트를 통과시킨 직후(= 정상 배포 가능 상태)에는 통과가 옳고,
  #    테스트만 빨개졌다. 이 파일이 커밋 게이트 절에 적어둔 규율 그대로다 —
  #    **상태는 테스트가 직접 만든다.**
  # ⚠️ **lib.sh 를 먼저 읽는다.** 이 절이 쓰이는 시점에는 아래 커밋 게이트 절의
  #    GREEN= 이 아직 실행되지 않았다. 종전 판에서 그걸 빠뜨려 빈 경로에 쓰고,
  #    마지막 정리에서 **진짜 마커를 지웠다**(실측 2026-09-08, 내가 냈다).
  source .claude/hooks/lib.sh
  GBAK=$(mktemp); HADG=0
  [ -f "$GREEN" ] && { cp "$GREEN" "$GBAK"; HADG=1; }
  printf 'deadbeef\n2000-01-01 00:00:00\n0 passed\n' > "$GREEN"   # 미검증 코드
  check "창 밖 배포 · 마커 낡음"    deny  "tools/deploy.sh scheduler"
  printf '%s\n%s\n%s\n' "$(worktree_sig)" "$(date '+%F %T')" "9999 passed" > "$GREEN"
  if [ -z "$(git status --porcelain)" ]; then
    check "창 밖 배포 · 깨끗+검증됨"  allow "tools/deploy.sh scheduler"
  else
    check "창 밖 배포 · 미커밋 있음"  deny  "tools/deploy.sh scheduler"
  fi
  # 원상 복구 — 있었으면 되돌리고, 없었으면 없는 상태로 되돌린다.
  if [ "$HADG" = 1 ]; then cp "$GBAK" "$GREEN"; else rm -f "$GREEN"; fi
  rm -f "$GBAK"
fi

echo "══ (a) 커밋 게이트 ══"
# ⚠️ 이 게이트는 **마커 상태에 의존한다.** 테스트가 상태를 직접 만든다 —
#    "지금 마커가 어떤가"에 따라 결과가 달라지면 그건 테스트가 아니다.
GREEN=".claude/state/last-green"
BAK=$(mktemp)
[ -f "$GREEN" ] && cp "$GREEN" "$BAK"

rm -f "$GREEN"                                   # 마커 없음
check "마커 없음 → 커밋"        deny  "git commit -m x"
check "마커 없음 → SKIP 명시"    allow "SKIP_TEST_GATE=1 git commit -m docs"

printf 'deadbeef\n2000-01-01 00:00:00\n0 passed\n' > "$GREEN"   # 낡은 마커
check "낡은 마커 → 커밋"        deny  "git commit -m x"

source .claude/hooks/lib.sh                      # worktree_sig 사용
printf '%s\n%s\n%s\n' "$(worktree_sig)" "$(date '+%F %T')" "9999 passed" > "$GREEN"
check "신선한 마커 → 커밋"      allow "git commit -m x"

[ -s "$BAK" ] && cp "$BAK" "$GREEN" || rm -f "$GREEN"
rm -f "$BAK"

check "git log (무관)"         allow "git log --oneline -3"
check "git status (무관)"      allow "git status --porcelain"

echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
