#!/bin/bash
# 단계 게이트 계약 테스트 — **태어나는 날 함께 태어난다.**
#
# 두 가지를 증명해야 한다:
#   ① 게이트가 비활성이면 **기존 워크플로가 그대로 돈다** (오탐 0)
#   ② 단계를 건너뛰면 **실제로 차단된다** (exit 2)
# 나머지는 세 상태(미실행·실패·건너뜀) 구분과 fail closed, 그리고 빠져나갈 문.
cd "$(dirname "$0")/../.." || exit 1
source .claude/hooks/lib.sh
G=.claude/hooks/step-gate.sh
S=.claude/hooks/step.sh
PASS=0; FAIL=0
FIXID=ZZZ-9            # 테스트 전용 수정 단위

# ── 상태 대피 (이 테스트는 실제 상태 디렉토리를 쓴다) ──────────────────
BAK=$(mktemp -d)
[ -f "$FIXDIR/active" ] && cp "$FIXDIR/active" "$BAK/active"
[ -f "$MODEFILE" ] && cp "$MODEFILE" "$BAK/mode"
[ -f "$GREEN" ] && cp "$GREEN" "$BAK/last-green"
restore() {
  chmod 755 "$FIXDIR/$FIXID" 2>/dev/null
  rm -rf "$FIXDIR/$FIXID" 2>/dev/null
  rm -f "$FIXDIR/active" "$OVRTOKEN" "$STATE/step-warn-t8"
  [ -f "$BAK/active" ] && cp "$BAK/active" "$FIXDIR/active"
  [ -f "$BAK/mode" ] && cp "$BAK/mode" "$MODEFILE" || rm -f "$MODEFILE"
  [ -f "$BAK/last-green" ] && cp "$BAK/last-green" "$GREEN"
  rm -rf "$BAK"
}
trap restore EXIT

hook() {  # $1=JSON  → 전역 OUT/CODE. 모드는 STEP_GATE 로 준다.
  OUT=$(printf '%s' "$1" | STEP_GATE="${MODE:-enforce}" $G 2>&1); CODE=$?
}
edit_json() { printf '{"tool_name":"Edit","session_id":"t8","tool_input":{"file_path":"%s","new_string":%s}}' \
  "$1" "$(printf '%s' "${2:-x}" | jq -Rs .)"; }
bash_json() { printf '{"tool_name":"Bash","session_id":"t8","tool_input":{"command":%s}}' \
  "$(printf '%s' "$1" | jq -Rs .)"; }

chk() {  # $1=이름 $2=기대(deny|allow) [$3=출력에 있어야 할 문자열]
  local got; got=$([ "$CODE" -eq 2 ] && echo deny || echo allow)
  local ok=1
  [ "$got" = "$2" ] || ok=0
  [ -n "${3:-}" ] && ! printf '%s' "$OUT" | grep -q "$3" && ok=0
  if [ $ok -eq 1 ]; then PASS=$((PASS+1)); m="✅"; else FAIL=$((FAIL+1)); m="🔴"; fi
  printf "  %s %-44s 기대=%-5s 결과=%-5s(exit %d)\n" "$m" "$1" "$2" "$got" "$CODE"
  [ $ok -eq 0 ] && printf '%s\n' "$OUT" | head -3 | sed 's/^/         /'
  return 0
}

echo "══ ① 게이트가 비활성이면 기존 워크플로가 그대로 돈다 ══"
rm -f "$FIXDIR/active"
MODE=enforce
hook "$(edit_json app/x.py)"                 ; chk "활성 FIX 없음 → 코드 편집"   allow
hook "$(bash_json 'git commit -m "x"')"      ; chk "활성 FIX 없음 → 커밋"        allow
hook "$(bash_json 'tools/deploy.sh all')"    ; chk "활성 FIX 없음 → 배포"        allow
hook "$(bash_json 'PYTHONPATH=. uv run pytest tests -q')" ; chk "테스트 실행"    allow
hook "$(edit_json docs/MODEL.md)"            ; chk "문서 편집"                   allow

for t in selftest.sh selftest6.sh selftest7.sh; do
  if .claude/hooks/$t >/dev/null 2>&1; then PASS=$((PASS+1)); echo "  ✅ 기존 $t 그대로 통과"
  else FAIL=$((FAIL+1)); echo "  🔴 기존 $t 가 깨졌다"; fi
done

echo "══ ② 단계를 건너뛰면 차단된다 ══"
rm -rf "$FIXDIR/$FIXID"; printf '%s\n' "$FIXID" > "$FIXDIR/active"
hook "$(edit_json app/x.py)"     ; chk "①미실행 → 코드 편집"        deny "기록된 적이 없다"
hook "$(bash_json 'sed -i "" s/a/b/ app/x.py')" ; chk "①미실행 → sed -i" deny

# 🔴 실측 오탐 2026-09-08: 테스트 파일을 쓰는 명령의 **본문에** 운영 경로가
#    있다고 "운영 코드 편집"으로 읽었다. 쓰기 힌트와 경로는 같은 줄에 있어야 한다.
FP_CMD='cat > tests/test_deploy_order.py <<EOF
import shutil, subprocess
shutil.copy(SRC, DST)
subprocess.run(["tools/deploy.sh", "all"])
EOF'
hook "$(bash_json "$FP_CMD")"  ; chk "운영 경로를 언급만 하는 테스트 작성" allow
REAL_EDIT='sed -i "" s/a/b/ app/pipeline.py'
hook "$(bash_json "$REAL_EDIT")" ; chk "진짜 운영 코드 편집"            deny

echo "══ 세 상태를 구분한다 (미실행 · 실패 · 건너뜀) ══"
$S repro "$FIXID" -- true >/dev/null 2>&1      # 재현 실패(명령이 통과해 버림)
hook "$(edit_json app/x.py)"     ; chk "①실패 → 편집"               deny "실패로 기록됐다"
$S skip "$FIXID" 1 '재현 명령을 만들 수 없다 — 계측을 먼저 심는다' >/dev/null
hook "$(edit_json app/x.py)"     ; chk "①건너뜀 → 편집"             deny "건너뛰었다"

echo "══ ①② GREEN 이면 편집이 열린다 ══"
$S repro "$FIXID" -- 'exit 3' >/dev/null 2>&1
step_put "$FIXID" 02-map "status=GREEN" "path=x.md" "when=$(date '+%F %T')"
hook "$(edit_json app/x.py)"     ; chk "①②GREEN → 편집"             allow

echo "══ 코드가 바뀌면 ④가 무효가 된다 ══"
step_put "$FIXID" 04-norepro "status=GREEN" "sig=deadbeef" "when=now"
step_put "$FIXID" 05-contract "status=GREEN" "sig=deadbeef" "when=now"
hook "$(bash_json "git commit -m \"$FIXID 종결\"")" ; chk "낡은 서명의 ④ → 종결 커밋" deny "무효"
step_put "$FIXID" 04-norepro "status=GREEN" "sig=$(worktree_sig)" "when=now"
step_put "$FIXID" 05-contract "status=GREEN" "sig=$(worktree_sig)" "when=now"
hook "$(bash_json "git commit -m \"$FIXID 종결\"")" ; chk "신선한 ④⑤ → 종결 커밋"   allow

echo "══ 중간 커밋은 벽이 아니라 과속방지턱이다 ══"
step_put "$FIXID" 04-norepro "status=NONE"
rm -f "$STATE/step-warn-t8"
hook "$(bash_json 'git commit -m "작업 중간 저장"')" ; chk "④없는 일반 커밋 1회차" deny
hook "$(bash_json 'git commit -m "작업 중간 저장"')" ; chk "④없는 일반 커밋 2회차" allow

echo "══ 빠져나갈 문 — 사유가 있어야 열린다 ══"
rm -rf "$FIXDIR/$FIXID"; printf '%s\n' "$FIXID" > "$FIXDIR/active"
hook "$(bash_json "STEP_OVERRIDE='P0 카드 0장 — 즉시 고친다' sed -i '' s/a/b/ app/x.py")"
chk "사유 있는 STEP_OVERRIDE"  allow
grep -q "OVERRIDE step" "$AUDIT" && { PASS=$((PASS+1)); echo "  ✅ 사유가 감사 로그에 남았다"; } \
  || { FAIL=$((FAIL+1)); echo "  🔴 감사 로그에 사유가 없다"; }
hook "$(bash_json "STEP_OVERRIDE='' sed -i '' s/a/b/ app/x.py")"
chk "빈 사유 STEP_OVERRIDE"    deny
$S override '문서 오탈자만 고친다 — 코드 아님' >/dev/null
hook "$(edit_json app/x.py)"     ; chk "1회성 토큰 → 편집"           allow
hook "$(edit_json app/x.py)"     ; chk "토큰은 1회용이다"            deny

echo "══ FINDINGS 종결 표기 — 활성 FIX 가 없어도 막는다 ══"
rm -f "$FIXDIR/active"; rm -rf "$FIXDIR/$FIXID"
hook "$(edit_json FINDINGS.md "## $FIXID — ✅ 종결. 고쳤다")"
chk "④ 없이 종결 표기"        deny "$FIXID"
hook "$(edit_json FINDINGS.md "## 🔴 $FIXID — 조사 중이다")"
chk "종결 아닌 편집"          allow
# 🔴 실측 오탐 (재생 1,200건 중 52건): 감사의 `✅ 정상 확인` 은 "고쳤다"가 아니라
#    "조사했더니 결함이 없다"다. 이걸 막으면 감사 세션이 통째로 멈춘다.
hook "$(edit_json FINDINGS.md "## ✅ $FIXID 정상 확인 — 결함이 없다")"
chk "감사의 ✅ 정상 확인"      allow
hook "$(edit_json FINDINGS.md "> 인용: **✅ 종결 2026-09-01** 이라고 적혀 있었다")"
chk "인용문 안의 종결 선언"    allow
hook "$(edit_json FINDINGS.md '```
**✅ 종결 2026-09-01 (사용자 지시).** '"$FIXID"' 을 고쳐 문서와 일치시켰다.
```')"
chk "코드펜스 안의 과거 종결"  allow
# 실제 CRW-6 이 죽은 형태 — 제목의 id + 아래 줄의 종결 선언
hook "$(edit_json docs/AUDIT_OPEN_ITEMS.md "## $FIXID 크롤러 주기
**✅ 종결 2026-09-01 (사용자 지시).** deploy.sh 2곳을 고쳐 문서와 일치시켰다.")"
chk "제목 id + 다음 줄 종결 선언" deny "$FIXID"
mkdir -p "$FIXDIR/$FIXID"
step_put "$FIXID" meta "head=$(git rev-parse HEAD)" "sig=$(worktree_sig)"
step_put "$FIXID" 04-norepro "status=GREEN" "sig=$(worktree_sig)" "when=now"
hook "$(edit_json FINDINGS.md "## ✅ $FIXID — 고쳤다")"
chk "④ 있으면 종결 표기 통과"  allow
hook "$(bash_json "cat >> FINDINGS.md <<'X'
## $FIXID — ✅ 종결
X")"                          ; chk "heredoc 로 쓰는 종결 표기도 본다" allow

echo "══ fail closed — 상태를 못 읽으면 통과가 아니다 ══"
printf '%s\n' "$FIXID" > "$FIXDIR/active"
chmod 000 "$FIXDIR/$FIXID"
hook "$(edit_json app/x.py)"     ; chk "상태 디렉토리 읽기 불가"      deny
chmod 755 "$FIXDIR/$FIXID"

echo "══ 조용한 무력화 방지 — 어느 셸에서 읽어도 같은 저장소를 본다 ══"
# 🔴 실측 2026-09-08: `${BASH_SOURCE[0]}` 는 zsh 에서 비어 있다. 그러면 REPO 가
#    홈 디렉토리로 잡히고, 게이트는 **엉뚱한 곳의 상태를 읽으며 조용히 통과**한다.
#    차단 0건이 "정상"으로 보인다 — 이 저장소가 반복해서 당한 '조용한 0'이다.
B=$(bash -c 'source .claude/hooks/lib.sh; echo "$REPO"')
if command -v zsh >/dev/null 2>&1; then
  Z=$(zsh -c 'source .claude/hooks/lib.sh; echo "$REPO"' 2>/dev/null)
  [ "$Z" = "$B" ] && { PASS=$((PASS+1)); echo "  ✅ zsh·bash 가 같은 REPO 를 본다"; } \
    || { FAIL=$((FAIL+1)); echo "  🔴 zsh=$Z · bash=$B — 셸에 따라 다른 상태를 읽는다"; }
else
  echo "  ⏭  zsh 없음"
fi
[ "$B" = "$(pwd)" ] && { PASS=$((PASS+1)); echo "  ✅ REPO 가 저장소 루트다"; } \
  || { FAIL=$((FAIL+1)); echo "  🔴 REPO=$B 가 저장소 루트가 아니다"; }

echo "══ 관측 모드는 막지 않는다 (오탐을 세는 동안) ══"
rm -rf "$FIXDIR/$FIXID"; printf '%s\n' "$FIXID" > "$FIXDIR/active"
MODE=observe
hook "$(edit_json app/x.py)"     ; chk "observe → 편집"              allow
grep -q "WOULD-DENY" "$AUDIT" && { PASS=$((PASS+1)); echo "  ✅ WOULD-DENY 가 기록됐다"; } \
  || { FAIL=$((FAIL+1)); echo "  🔴 관측 모드인데 아무것도 안 셌다"; }
MODE=off
hook "$(edit_json app/x.py)"     ; chk "off → 편집"                  allow

echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
