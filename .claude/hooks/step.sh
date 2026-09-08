#!/bin/bash
# 단계 기록자 — **명령을 직접 돌리고 그 종료 코드를 상태로 남긴다.**
#
# 🔴 왜 훅이 아니라 래퍼인가: PostToolUse 페이로드에는 **종료 코드 필드가 없다**
#    (실측 2026-09-08, 전 세션 toolUseResult 7,533건 키 전수 —
#     stdout·stderr·interrupted·isImage·noOutputExpected). `record-green.sh` 가
#     pytest **출력 문자열**을 grep 하는 것도 같은 이유다. 종료 코드를 사실로
#     남기려면 명령을 감싼 쪽이 $? 를 직접 써야 한다.
#
# 🔴 이 파일이 남기는 것은 "내가 했다"는 주장이 아니라 **돌린 결과**다.
#    손으로 상태 파일을 만들 수는 있지만, 그건 이 체계를 끄는 것과 같다 —
#    끄려면 STEP_OVERRIDE 를 써라. 그건 사유가 감사 로그에 남는다.
#
# 사용:
#   step.sh start <FIX>                     수정 단위 활성화 (예: CRW-6)
#   step.sh repro    <FIX> -- <명령>        ① 재현   — 명령이 **실패**해야 GREEN
#   step.sh map      <FIX> -- <파일.md>     ② 영향지도 5문
#   step.sh norepro  <FIX>                  ④ 재현 불가 — ①과 **같은 명령**이 통과
#   step.sh contract <FIX> --node <nodeid>  ⑤ 계약 테스트 (HEAD 에서는 실패해야)
#   step.sh record deploy <FIX> [서비스]     ⑧ 배포 (deploy.sh 가 부른다)
#   step.sh cycle    <FIX> -- <명령>        ⑨ 첫 사이클 실측
#   step.sh skip     <FIX> <단계> <사유>     건너뜀 기록 (GREEN 아니다)
#   step.sh override <사유>                  Edit/Write 용 1회성 통과권
#   step.sh status [<FIX>] · mode [모드] · done
source "$(dirname "$0")/lib.sh"
cd "$REPO" || exit 1

PYBIN="$REPO/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN=""

usage() { sed -n '18,32p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
die()   { echo "🔴 $*" >&2; exit 1; }
now()   { date '+%F %T'; }
b64()   { printf '%s' "$1" | base64 | tr -d '\n'; }
unb64() { printf '%s' "$1" | base64 -d; }
hash_of() { printf '%s' "$1" | shasum | cut -d' ' -f1; }

# `-- ` 뒤 전부를 하나의 명령 문자열로. (여러 인자면 공백으로 잇는다)
after_dashdash() {
  local seen=0 out=""
  for a in "$@"; do
    if [ $seen -eq 1 ]; then out="${out:+$out }$a"; else [ "$a" = "--" ] && seen=1; fi
  done
  printf '%s' "$out"
}

# 명령을 돌리고 (종료코드, 출력꼬리)를 돌려준다. 출력은 사람에게도 보인다.
run_capture() {  # $1=명령  → 전역 RC, OUTTAIL
  local T; T=$(mktemp)
  bash -c "$1" >"$T" 2>&1; RC=$?
  echo "── 출력 (마지막 20줄) ──"; tail -20 "$T"; echo "── exit=$RC ──"
  OUTTAIL=$(tail -3 "$T" | tr '\n' ' ' | cut -c1-200)
  rm -f "$T"
}

CMD_="${1:-}"; shift 2>/dev/null

case "$CMD_" in

start)
  FIX="${1:-}"; [ -n "$FIX" ] || usage
  mkdir -p "$FIXDIR/$FIX" || die "상태 디렉토리를 만들 수 없다"
  step_put "$FIX" meta "start=$(now)" "head=$(git rev-parse HEAD)" "sig=$(worktree_sig)" \
    || die "meta 기록 실패"
  printf '%s\n' "$FIX" > "$FIXDIR/active" || die "활성화 실패"
  log_audit "STEP start $FIX"
  echo "▶ 수정 단위 $FIX 활성. 다음: step.sh repro $FIX -- <결함을 재현하는 명령>"
  ;;

done)
  rm -f "$FIXDIR/active"; log_audit "STEP done"; echo "▶ 활성 수정 단위 해제" ;;

mode)
  if [ -n "${1:-}" ]; then
    case "$1" in observe|enforce|off) printf '%s\n' "$1" > "$MODEFILE"
      log_audit "STEP mode=$1"; echo "▶ 게이트 모드 = $1" ;;
      *) die "모드는 observe|enforce|off" ;; esac
  else echo "$(step_mode)"; fi ;;

# ── ① 재현 ───────────────────────────────────────────────────────────
# GREEN 조건이 **exit ≠ 0** 이다. 그래서 `-- true` 로는 통과할 수 없다.
repro)
  FIX="${1:-}"; shift; CMD=$(after_dashdash "$@")
  [ -n "$FIX" ] && [ -n "$CMD" ] || usage
  run_capture "$CMD"
  if [ "$RC" -ne 0 ]; then
    step_put "$FIX" 01-repro "status=GREEN" "exit=$RC" "cmdhash=$(hash_of "$CMD")" \
      "cmd_b64=$(b64 "$CMD")" "sig=$(worktree_sig)" "when=$(now)" "tail=$OUTTAIL" \
      || die "기록 실패"
    log_audit "STEP ①재현 GREEN $FIX exit=$RC"
    echo "✅ ① 재현됨 (exit=$RC). 이 명령이 ④에서 그대로 다시 돈다."
  else
    step_put "$FIX" 01-repro "status=FAIL" "exit=0" "cmdhash=$(hash_of "$CMD")" \
      "cmd_b64=$(b64 "$CMD")" "sig=$(worktree_sig)" "when=$(now)" \
      "why=재현 명령이 exit 0 이었다 — 결함이 재현되지 않았다"
    log_audit "STEP ①재현 FAIL $FIX"
    die "① 실패 — 명령이 통과해 버렸다. **재현 없는 수정 금지**(ENGINEERING §3).
   재현이 안 되면 계측을 먼저 심어라. 지금 상태는 '미실행'이 아니라 '실패'로 기록됐다."
  fi ;;

# ── ② 영향지도 5문 ───────────────────────────────────────────────────
map)
  FIX="${1:-}"; shift; P=$(after_dashdash "$@")
  [ -n "$FIX" ] && [ -n "$P" ] || usage
  [ -f "$P" ] || die "파일이 없다: $P"
  MISS=$("${PYBIN:-python3}" - "$P" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
marks = "①②③④⑤"
pos = [(m, t.find(m)) for m in marks]
miss = [m for m, i in pos if i < 0]
# 각 표식 뒤 본문이 20자 이상인가 (다음 표식 전까지)
idx = [i for _, i in pos if i >= 0] + [len(t)]
for k, (m, i) in enumerate(pos):
    if i < 0: continue
    nxt = min([j for j in idx if j > i] or [len(t)])
    body = re.sub(r"\s+", "", t[i+1:nxt])
    if len(body) < 20:
        miss.append(m + "(답이 비었다)")
print(",".join(miss))
PY
)
  if [ -n "$MISS" ]; then
    step_put "$FIX" 02-map "status=FAIL" "path=$P" "when=$(now)" "why=5문 미답: $MISS"
    log_audit "STEP ②지도 FAIL $FIX miss=$MISS"
    die "② 영향지도 미완 — $MISS
   ENGINEERING §1 의 5문을 ①~⑤ 표식으로 적어라 (각 답 20자 이상)."
  fi
  step_put "$FIX" 02-map "status=GREEN" "path=$P" "when=$(now)" || die "기록 실패"
  log_audit "STEP ②지도 GREEN $FIX $P"
  echo "✅ ② 영향지도 5문 확인 — $P" ;;

# ── ④ 재현 불가 ──────────────────────────────────────────────────────
norepro)
  FIX="${1:-}"; [ -n "$FIX" ] || usage
  [ "$(step_status "$FIX" 01-repro)" = GREEN ] || die "④ 불가 — ①이 GREEN 이 아니다.
   $(step_say "$FIX" 01-repro '①재현')"
  CMD=$(unb64 "$(step_get "$FIX" 01-repro cmd_b64)")
  [ -n "$CMD" ] || die "①의 명령을 읽을 수 없다 (상태 손상)"
  OLD=$(step_get "$FIX" 01-repro sig); NEW=$(worktree_sig)
  if [ "$OLD" = "$NEW" ]; then
    die "④ 불가 — ① 이후 **코드가 한 글자도 바뀌지 않았다**(③ 수정이 없다).
   서명 $OLD"
  fi
  echo "▶ ①과 동일한 명령을 다시 돌린다:"; echo "   $CMD"
  run_capture "$CMD"
  if [ "$RC" -eq 0 ]; then
    step_put "$FIX" 04-norepro "status=GREEN" "exit=0" \
      "cmdhash=$(step_get "$FIX" 01-repro cmdhash)" "sig=$NEW" "when=$(now)" || die "기록 실패"
    log_audit "STEP ④재현불가 GREEN $FIX sig=$NEW"
    echo "✅ ④ 재현 불가 — 같은 명령이 이번엔 통과했다."
    echo "   ⚠️ 코드를 더 고치면 이 기록은 무효가 된다(서명이 바뀐다)."
  else
    step_put "$FIX" 04-norepro "status=FAIL" "exit=$RC" "sig=$NEW" "when=$(now)" \
      "why=수정 후에도 같은 명령이 exit $RC 로 실패한다"
    log_audit "STEP ④재현불가 FAIL $FIX exit=$RC"
    die "④ 실패 — 고쳤다는 수정이 재현을 없애지 못했다 (exit=$RC)."
  fi ;;

# ── ⑤ 계약 테스트 ────────────────────────────────────────────────────
# 강한 증명: **HEAD 사본에 새 테스트만 얹어** 돌려서 실패하는지 본다.
# "그 결함이 되살아나면 알려줄 테스트"인지 기계가 확인하는 유일한 방법이다.
contract)
  FIX="${1:-}"; shift
  NODE=""; [ "${1:-}" = "--node" ] && NODE="${2:-}"
  [ -n "$FIX" ] && [ -n "$NODE" ] || usage
  TF="${NODE%%::*}"
  [ -f "$TF" ] || die "테스트 파일이 없다: $TF"
  [ -n "$PYBIN" ] || die ".venv/bin/python 이 없다 — uv sync 후 다시 하라"

  echo "▶ (a) 지금 코드에서 통과하는가"
  run_capture "PYTHONPATH=. $PYBIN -m pytest '$NODE' -q"
  NOW=$RC
  if [ "$NOW" -ne 0 ]; then
    step_put "$FIX" 05-contract "status=FAIL" "node=$NODE" "exit_now=$NOW" \
      "sig=$(worktree_sig)" "when=$(now)" "why=새 테스트가 현재 코드에서 실패한다"
    die "⑤ 실패 — 계약 테스트가 지금 코드에서 통과하지 않는다."
  fi

  echo "▶ (b) 수정 전 코드(HEAD)에 이 테스트만 얹으면 실패하는가"
  WT=$(mktemp -d)/head
  git worktree add --detach -q "$WT" HEAD || die "worktree 생성 실패"
  mkdir -p "$WT/$(dirname "$TF")"; cp "$TF" "$WT/$TF"
  # ⚠️ .venv 를 그대로 쓴다 — 워크트리에서 uv sync 를 돌리면 몇 분이 든다.
  ( cd "$WT" && PYTHONPATH=. "$PYBIN" -m pytest "$NODE" -q ) >/tmp/.stepwt 2>&1
  HEADRC=$?
  tail -5 /tmp/.stepwt; rm -f /tmp/.stepwt
  git worktree remove --force "$WT" >/dev/null 2>&1
  rmdir "$(dirname "$WT")" 2>/dev/null

  if [ "$HEADRC" -eq 0 ]; then
    step_put "$FIX" 05-contract "status=FAIL" "node=$NODE" "exit_now=0" "exit_head=0" \
      "sig=$(worktree_sig)" "when=$(now)" \
      "why=HEAD 코드에서도 통과한다 — 이 결함이 되살아나도 알려주지 못한다"
    log_audit "STEP ⑤계약 FAIL $FIX node=$NODE head=0"
    die "⑤ 실패 — 이 테스트는 **수정 전 코드에서도 통과한다.**
   그러면 결함이 되살아나도 알려주지 못한다. 결함 자체를 겨눈 단언을 써라.
   (테스트가 새 모듈을 임포트만 해서 통과하는 형태가 흔하다)"
  fi
  step_put "$FIX" 05-contract "status=GREEN" "node=$NODE" "exit_now=0" "exit_head=$HEADRC" \
    "sig=$(worktree_sig)" "when=$(now)" || die "기록 실패"
  log_audit "STEP ⑤계약 GREEN $FIX node=$NODE head=$HEADRC"
  echo "✅ ⑤ 계약 테스트 — 지금 통과(0) · HEAD 에서 실패($HEADRC)" ;;

# ── ⑧ 배포 (deploy.sh 가 SUCCESS 확인 뒤에만 부른다) ──────────────────
record)
  [ "${1:-}" = deploy ] || usage
  FIX="${2:-}"; SVC="${3:-}"; [ -n "$FIX" ] || usage
  step_put "$FIX" 08-deploy "status=GREEN" "sha=$(git rev-parse HEAD)" "svc=$SVC" "when=$(now)" \
    || die "기록 실패"
  log_audit "STEP ⑧배포 GREEN $FIX sha=$(git rev-parse --short HEAD) svc=$SVC"
  echo "✅ ⑧ 배포 기록 — 다음: step.sh cycle $FIX -- <새 코드가 처음 실행되는 로그/키 확인>" ;;

# ── ⑨ 첫 사이클 실측 ─────────────────────────────────────────────────
cycle)
  FIX="${1:-}"; shift; CMD=$(after_dashdash "$@")
  [ -n "$FIX" ] && [ -n "$CMD" ] || usage
  [ "$(step_status "$FIX" 08-deploy)" = GREEN ] || die "⑨ 불가 — $(step_say "$FIX" 08-deploy '⑧배포')"
  DSHA=$(step_get "$FIX" 08-deploy sha); HSHA=$(git rev-parse HEAD)
  [ "$DSHA" = "$HSHA" ] || die "⑨ 불가 — 배포된 커밋(${DSHA:0:7})과 지금 HEAD(${HSHA:0:7})가 다르다."
  run_capture "$CMD"
  if [ "$RC" -eq 0 ]; then
    step_put "$FIX" 09-cycle "status=GREEN" "exit=0" "sha=$HSHA" "cmd_b64=$(b64 "$CMD")" \
      "when=$(now)" "tail=$OUTTAIL" || die "기록 실패"
    log_audit "STEP ⑨실측 GREEN $FIX sha=${HSHA:0:7}"
    echo "✅ ⑨ 첫 사이클 실측 — 새 코드가 실제로 돈 것을 확인했다."
  else
    step_put "$FIX" 09-cycle "status=FAIL" "exit=$RC" "sha=$HSHA" "when=$(now)" \
      "why=확인 명령이 exit $RC — 새 코드가 도는 증거를 못 잡았다"
    die "⑨ 실패 (exit=$RC) — **등록 확인은 실행 확인이 아니다**(ENGINEERING §4)."
  fi ;;

# ── 건너뜀 (GREEN 아니다. 사유가 남고 배너가 계속 뜬다) ────────────────
skip)
  FIX="${1:-}"; N="${2:-}"; R="${3:-}"
  [ -n "$FIX" ] && [ -n "$N" ] && [ -n "$R" ] || usage
  [ "$(printf '%s' "$R" | wc -m | tr -d ' ')" -ge 8 ] || die "사유가 너무 짧다(8자 이상)."
  case "$N" in
    1) F=01-repro ;; 2) F=02-map ;; 4) F=04-norepro ;;
    5) F=05-contract ;; 8) F=08-deploy ;; 9) F=09-cycle ;;
    *) die "단계는 1·2·4·5·8·9" ;;
  esac
  step_put "$FIX" "$F" "status=SKIP" "reason=$R" "sig=$(worktree_sig)" "when=$(now)" || die "기록 실패"
  log_audit "SKIP step-$N fix=$FIX reason=$R"
  echo "⏭  $FIX 단계 $N 건너뜀 — 사유가 감사 로그에 남았다. **GREEN 이 아니다.**" ;;

# ── Edit/Write 용 1회성 통과권 (env 를 못 붙이는 도구가 있다) ──────────
override)
  R="${1:-}"
  [ "$(printf '%s' "$R" | wc -m | tr -d ' ')" -ge 8 ] || die "사유가 너무 짧다(8자 이상)."
  printf '%s\n%s\n' "$R" "$(date +%s)" > "$OVRTOKEN" || die "토큰 기록 실패"
  log_audit "OVERRIDE token 발급 reason=$R"
  echo "▶ 다음 편집 1회를 통과시킨다 (10분 유효). 사유: $R" ;;

status)
  FIX="${1:-$(fix_active)}"
  [ -n "$FIX" ] || { echo "활성 수정 단위 없음 — 게이트는 무동작(모드 $(step_mode))"; exit 0; }
  echo "수정 단위 $FIX   모드 $(step_mode)   서명 $(worktree_sig | cut -c1-12)"
  for p in "01-repro:①재현" "02-map:②영향지도" "04-norepro:④재현불가" \
           "05-contract:⑤계약테스트" "08-deploy:⑧배포" "09-cycle:⑨첫사이클"; do
    f="${p%%:*}"; n="${p##*:}"
    extra=""
    case "$f" in 04-norepro|05-contract)
      [ "$(step_status "$FIX" "$f")" = GREEN ] && ! step_fresh "$FIX" "$f" \
        && extra="  ⚠️ 코드가 바뀌어 **무효**" ;;
    esac
    printf '  %s%s\n' "$(step_say "$FIX" "$f" "$n")" "$extra"
  done
  SIG=$(worktree_sig)
  if [ "$(step_status "$FIX" 01-repro)" = GREEN ]; then
    [ "$(step_get "$FIX" 01-repro sig)" != "$SIG" ] \
      && echo "  ③수정: 코드가 ① 이후 바뀌었다" || echo "  ③수정: **아직 안 바뀌었다**"
  fi
  [ -f "$GREEN" ] && [ "$(head -1 "$GREEN")" = "$SIG" ] \
    && echo "  ⑥전체스위트: 통과 ($(sed -n 3p "$GREEN"))" \
    || echo "  ⑥전체스위트: **이 코드로는 기록 없음**" ;;

*) usage ;;
esac
