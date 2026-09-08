#!/bin/bash
# 기록자(step.sh) 계약 테스트 — **주장이 아니라 종료 코드를 남기는가.**
#
# 핵심 둘:
#   · ① 은 명령이 **실패**해야 GREEN 이다 → `-- true` 로는 통과할 수 없다.
#   · ⑤ 는 **HEAD 사본에 새 테스트만 얹어** 돌려 실패하는지까지 본다 —
#     "그 결함이 되살아나면 알려줄 테스트"인지 기계가 확인하는 유일한 방법.
cd "$(dirname "$0")/../.." || exit 1
source .claude/hooks/lib.sh
S=.claude/hooks/step.sh
FIX=ZZZ-8
PASS=0; FAIL=0
MARK=tests/zzz_selftest_marker.txt
TF=tests/test_zzz_selftest_tmp.py
TF2=tests/test_zzz_selftest_weak.py

cleanup() { rm -f "$MARK" "$TF" "$TF2"; rm -rf "$FIXDIR/$FIX"; }
trap cleanup EXIT
cleanup

ok() { PASS=$((PASS+1)); printf "  ✅ %s\n" "$1"; }
no() { FAIL=$((FAIL+1)); printf "  🔴 %s\n" "$1"; }
expect() {  # $1=이름 $2=기대종료 $3=실제종료 [$4=기대상태 $5=단계파일]
  local good=1
  [ "$3" = "$2" ] || good=0
  [ -n "${4:-}" ] && [ "$(step_status "$FIX" "$5")" != "$4" ] && good=0
  [ $good = 1 ] && ok "$1 (exit=$3${4:+ · status=$(step_status "$FIX" "$5")})" \
                 || no "$1 — 기대 exit=$2${4:+/status=$4}, 실제 exit=$3${4:+/status=$(step_status "$FIX" "$5")}"
}

echo "══ ① 재현: 통과하는 명령은 재현이 아니다 ══"
$S repro "$FIX" -- true >/dev/null 2>&1;      expect "-- true 는 거부된다"  1 $? FAIL 01-repro
$S repro "$FIX" -- "test -f $MARK" >/dev/null 2>&1
expect "결함 재현(파일 없음) → GREEN" 0 $? GREEN 01-repro

echo "══ ④ 재현 불가: 코드가 안 바뀌면 기록할 수 없다 ══"
OUT=$($S norepro "$FIX" 2>&1); RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "한 글자도"; then ok "③ 없이 ④ 시도 → 거부"
else no "③ 없이 ④ 를 기록해 버렸다 (exit=$RC)"; fi

echo "══ ③ 수정 후 ④ ══"
touch "$MARK"                                  # = 결함을 고쳤다 (서명이 바뀐다)
$S norepro "$FIX" >/dev/null 2>&1;            expect "같은 명령이 통과 → GREEN" 0 $? GREEN 04-norepro
step_fresh "$FIX" 04-norepro && ok "④ 가 지금 서명으로 신선하다" || no "④ 서명이 안 맞는다"
printf 'x\n' >> "$MARK"                        # 코드가 또 바뀌면
step_fresh "$FIX" 04-norepro && no "코드가 바뀌었는데 ④ 가 유효하다" || ok "코드가 바뀌자 ④ 가 무효가 됐다"

echo "══ ⑤ 계약 테스트 — HEAD 에서도 통과하는 테스트는 거부한다 ══"
cat > "$TF2" <<'PY'
def test_weak():
    assert True          # 결함을 겨누지 않는다 — HEAD 에서도 통과한다
PY
OUT=$($S contract "$FIX" --node "$TF2::test_weak" 2>&1); RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "수정 전 코드에서도 통과"; then ok "약한 테스트 → 거부"
else no "약한 테스트를 통과시켰다 (exit=$RC)"; fi

echo "══ ⑤ 결함을 겨눈 테스트는 통과한다 ══"
cat > "$TF" <<'PY'
import os
def test_marker_exists():
    # 수정 후에만 존재한다 → HEAD 사본에서는 실패해야 정상
    assert os.path.exists("tests/zzz_selftest_marker.txt")
PY
$S contract "$FIX" --node "$TF::test_marker_exists" >/dev/null 2>&1
expect "지금 통과 · HEAD 에서 실패" 0 $? GREEN 05-contract
[ "$(step_get "$FIX" 05-contract exit_head)" != 0 ] && ok "HEAD 실패 종료코드가 기록됐다($(step_get "$FIX" 05-contract exit_head))" \
  || no "HEAD 종료코드가 0 이다"

echo "══ ⑨ 는 ⑧ 없이 기록되지 않는다 ══"
OUT=$($S cycle "$FIX" -- true 2>&1); RC=$?
if [ $RC -ne 0 ] && printf '%s' "$OUT" | grep -q "⑧배포"; then ok "⑧ 없이 ⑨ 시도 → 거부"
else no "⑧ 없이 ⑨ 를 기록했다 (exit=$RC)"; fi
$S record deploy "$FIX" test-svc >/dev/null 2>&1
$S cycle "$FIX" -- 'exit 4' >/dev/null 2>&1;  expect "확인 명령 실패 → FAIL 기록" 1 $? FAIL 09-cycle
$S cycle "$FIX" -- true >/dev/null 2>&1;      expect "확인 명령 통과 → GREEN"     0 $? GREEN 09-cycle

echo "══ 건너뜀은 GREEN 이 아니고 사유가 필요하다 ══"
$S skip "$FIX" 5 '짧음' >/dev/null 2>&1;      expect "짧은 사유 → 거부" 1 $?
$S skip "$FIX" 5 '실데이터가 없어 계약 테스트를 못 쓴다' >/dev/null 2>&1
expect "사유 있는 건너뜀 → SKIP" 0 $? SKIP 05-contract
grep -q "SKIP step-5 fix=$FIX" "$AUDIT" && ok "사유가 감사 로그에 남았다" || no "감사 로그에 사유가 없다"

echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
