#!/bin/bash
# [PreToolUse · Bash + Edit|Write|NotebookEdit] 단계 건너뛰기 게이트.
#
# 🔴 왜: "고쳤다"가 실제로는 안 고쳐진 사례가 반복됐다 (FINDINGS 실측).
#    CRW-6 — 09-01 에 "10m 으로 고쳤다"고 항목을 닫았는데 그 문자열은
#            railway 에 전달되지 않았다. 운영은 일주일째 60m 이었다.
#    PGP-2 — "죽으면 알리게" 수정이 **5일 전에 배선이 끊긴 함수** 안에 들어갔다.
#    둘 다 절차의 한 단계(④ 재현 불가 · ⑨ 첫 사이클 실측)를 조용히 건너뛴 것이다.
#
# 🔴 이 훅은 **아무것도 판단하지 않는다.** step.sh 가 남긴 종료 코드만 읽는다.
#    모델이 "①을 했다"고 말하는 것으로는 통과하지 않는다.
#
# 세 상태를 뭉개지 않는다: 미실행 · 실패 · 건너뜀 (lib.sh step_say).
# 모드: observe(기본·세기만 한다) · enforce(막는다) · off.
source "$(dirname "$0")/lib.sh"

IN=$(cat)
TOOL=$(printf '%s' "$IN" | jq -r '.tool_name // ""' 2>/dev/null)
SESSION=$(printf '%s' "$IN" | jq -r '.session_id // "x"' 2>/dev/null)
MODE=$(step_mode)
[ "$MODE" = off ] && exit 0

case "$TOOL" in
  Bash)
    CMD=$(printf '%s' "$IN" | jq -r '.tool_input.command // ""' 2>/dev/null)
    TEXT="$CMD"; FILE="" ;;
  Edit|Write|NotebookEdit|MultiEdit)
    CMD=""
    FILE=$(printf '%s' "$IN" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""' 2>/dev/null)
    TEXT=$(printf '%s' "$IN" | jq -r '
      [.tool_input.new_string?, .tool_input.content?, .tool_input.new_source?,
       (.tool_input.edits[]?.new_string?)] | map(select(. != null)) | join("\n")' 2>/dev/null) ;;
  *) exit 0 ;;
esac
[ -z "$TEXT$FILE" ] && exit 0
FILE="${FILE#$REPO/}"

# ── 빠져나갈 문 (요건 3) — 먼저 설계했다 ──────────────────────────────
# 빠져나갈 문이 없는 게이트는 곧 통째로 꺼진다. 대신 **사유가 남는다.**
#   Bash : STEP_OVERRIDE='사유' <명령>     (env 또는 명령 인라인)
#   Edit : step.sh override '사유'  → 다음 1회, 10분 유효
OVR_REASON=""; TOKEN_USED=0
try_override() {
  local r=""
  if [ -n "${STEP_OVERRIDE:-}" ]; then
    r="$STEP_OVERRIDE"
  elif printf '%s' "$TEXT" | grep -q 'STEP_OVERRIDE='; then
    # ⚠️ 따옴표 안의 **공백을 살려서** 꺼낸다. 종전 sed 는 첫 공백에서 잘라
    #    'P0 카드 0장 …' 이 'P0' 이 됐고, 사유가 있는데도 차단됐다(실측).
    line=$(printf '%s' "$TEXT" | sed -n 's/.*STEP_OVERRIDE=//p' | head -1)
    case "$line" in
      "'"*)  r=${line#\'}; r=${r%%\'*} ;;
      '"'*)  r=${line#\"}; r=${r%%\"*} ;;
      *)     r=${line%% *} ;;
    esac
  elif [ -f "$OVRTOKEN" ]; then
    local age=$(( $(date +%s) - $(sed -n 2p "$OVRTOKEN" 2>/dev/null || echo 0) ))
    if [ "$age" -ge 0 ] && [ "$age" -le 600 ]; then r=$(head -1 "$OVRTOKEN"); TOKEN_USED=1; fi
  fi
  [ "$(printf '%s' "$r" | LC_ALL=en_US.UTF-8 wc -m | tr -d ' ')" -ge 8 ] || return 1
  OVR_REASON="$r"; return 0
}

# 차단 지점 하나. 모드에 따라 막거나(enforce) 세기만(observe) 한다.
gate_block() {  # $1=코드 $2=사람에게 보일 메시지
  if try_override; then
    [ "$TOKEN_USED" = 1 ] && rm -f "$OVRTOKEN"
    log_audit "OVERRIDE step-gate $1 fix=${FIX:-none} reason=$OVR_REASON"
    exit 0
  fi
  if [ "$MODE" = observe ]; then
    log_audit "WOULD-DENY $1 fix=${FIX:-none} tool=$TOOL ${FILE:-${CMD:0:60}}"
    exit 0
  fi
  log_audit "DENY $1 fix=${FIX:-none} tool=$TOOL ${FILE:-${CMD:0:60}}"
  deny "$2"
}

esc_hint() {
  if [ "$TOOL" = Bash ]; then echo "   빠져나가려면: STEP_OVERRIDE='사유' <명령>  (사유는 감사 로그에 남는다)"
  else echo "   빠져나가려면: .claude/hooks/step.sh override '사유'  (다음 1회, 10분)"; fi
}

# ── (A) 종결 표기 게이트 — **활성 수정 단위가 없어도 켜져 있다** ────────
# CRW-6 이 죽은 지점이 정확히 여기다. 편집도 커밋도 정상이었고, 틀린 것은
# "고쳤다"고 문서에 적은 행위였다.
TOUCHES_FINDINGS=0
case "$FILE" in FINDINGS.md|docs/AUDIT_OPEN_ITEMS.md) TOUCHES_FINDINGS=1 ;; esac
if [ "$TOOL" = Bash ] \
   && printf '%s' "$CMD" | grep -qE '(FINDINGS\.md|AUDIT_OPEN_ITEMS\.md)' \
   && printf '%s' "$CMD" | grep -qE '(>>?|sed -i|tee |io\.open\()'; then
  TOUCHES_FINDINGS=1
fi

if [ "$TOUCHES_FINDINGS" = 1 ]; then
  IDS=$(printf '%s' "$TEXT" | python3 "$(dirname "$0")/closure_ids.py" 2>/dev/null)

  for id in $IDS; do
    if [ ! -d "$FIXDIR/$id" ]; then
      gate_block "close-undeclared:$id" "🚫 종결 표기 차단 — $id 는 **선언된 적 없는 수정 단위**다.
   기록이 하나도 없다. 무엇으로 고쳐졌다고 판단하는가?
      .claude/hooks/step.sh start $id
      .claude/hooks/step.sh repro $id -- <결함을 재현하는 명령>   ← 실패해야 GREEN
      … 수정 … .claude/hooks/step.sh norepro $id                  ← 같은 명령이 통과
   실사고 CRW-6: 09-01 에 '고쳤다'고 이 자리에서 닫았고, 운영은 일주일째 옛 값이었다.
$(esc_hint)"
    fi
    if [ "$(step_status "$id" 04-norepro)" != GREEN ]; then
      gate_block "close-no-norepro:$id" "🚫 종결 표기 차단 — $id 의 ④ 재현 불가가 없다.
   $(step_say "$id" 04-norepro '④재현불가')
   ①의 그 명령이 이번엔 통과하는지 기계가 봐야 한다:  step.sh norepro $id
$(esc_hint)"
    elif ! step_fresh "$id" 04-norepro; then
      gate_block "close-stale-norepro:$id" "🚫 종결 표기 차단 — $id 의 ④가 **무효**다.
   ④를 기록한 뒤 코드가 또 바뀌었다. 그 뒤 수정은 검증되지 않았다.
      step.sh norepro $id  를 다시 돌려라.
$(esc_hint)"
    fi
    # ⑨는 **운영 코드가 바뀐 수정 단위에만** 요구한다 (문서·테스트만이면 면제).
    HEAD0=$(step_get "$id" meta head)
    CODECHG=""
    [ -n "$HEAD0" ] && CODECHG=$(git diff --name-only "$HEAD0" HEAD -- app crawler 2>/dev/null)
    [ -z "$CODECHG" ] && CODECHG=$(git status --porcelain -- app crawler 2>/dev/null)
    if [ -n "$CODECHG" ] && [ "$(step_status "$id" 09-cycle)" != GREEN ]; then
      gate_block "close-no-cycle:$id" "🚫 종결 표기 차단 — $id 는 운영 코드를 바꿨는데 ⑨ 첫 사이클 실측이 없다.
   $(step_say "$id" 09-cycle '⑨첫사이클')
   **등록 확인은 실행 확인이 아니다**(ENGINEERING §4). 새 코드가 **처음 실행되는**
   로그 라인이나 운영 키를 잡아라:  step.sh cycle $id -- '<확인 명령>'
   실사고 CRW-6: deploy.sh 문자열만 고치고 닫았다. 운영 crawl:* 키는 60분 간격 그대로였다.
$(esc_hint)"
    fi
  done
fi

# ── 여기부터는 활성 수정 단위가 있을 때만 ─────────────────────────────
# ⚠️ 활성 단위가 없으면 **완전 무동작**이다. 없는 것을 fail closed 로 막으면
#    저장소의 모든 편집이 멈춘다 — 그런 게이트는 하루면 꺼진다.
FIX=$(fix_active) || exit 0

# fail closed (요건 2) — 상태가 **있는데 못 읽으면** 통과가 아니라 차단이다.
if [ -e "$FIXDIR/$FIX" ] && { [ ! -r "$FIXDIR/$FIX" ] || [ ! -x "$FIXDIR/$FIX" ]; }; then
  gate_block "state-unreadable" "🚫 차단 — 수정 단위 $FIX 의 상태를 읽을 수 없다.
   상태를 못 읽는 것은 '통과'가 아니다. .claude/state/fix/$FIX 권한을 확인하라."
fi
if [ -z "$(worktree_sig)" ]; then
  gate_block "sig-unreadable" "🚫 차단 — 작업트리 서명을 계산할 수 없다(git 상태 확인)."
fi

is_prod_path() {  # 운영 코드인가 (문서·테스트·훅은 아니다)
  case "${1#./}" in
    app/*|crawler/*|tools/*) return 0 ;;
    *) return 1 ;;
  esac
}

# ── (B) ③ 수정 게이트 — ①② 없이 운영 코드를 고칠 수 없다 ──────────────
NEEDS_B=0
if [ -n "$FILE" ] && is_prod_path "$FILE"; then NEEDS_B=1; fi
if [ "$TOOL" = Bash ]; then
  # 리다이렉트는 **대상이 운영 경로일 때만**. `grep app/x.py > /tmp/o` 는 쓰기가 아니다.
  printf '%s' "$CMD" | grep -qE '>>?[[:space:]]*"?'"'"'?(\./)?(app|crawler|tools)/' && NEEDS_B=1
  if printf '%s' "$CMD" | grep -qE '(sed -i|tee |io\.open\(|shutil\.copy|patch )' \
     && printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9_/])(\./)?(app|crawler|tools)/'; then NEEDS_B=1; fi
fi

if [ "$NEEDS_B" = 1 ]; then
  for pair in "01-repro:①재현:repro $FIX -- <결함을 재현하는 명령>" \
              "02-map:②영향지도:map $FIX -- <영향지도.md>"; do
    f="${pair%%:*}"; rest="${pair#*:}"; nm="${rest%%:*}"; how="${rest#*:}"
    if [ "$(step_status "$FIX" "$f")" != GREEN ]; then
      gate_block "edit-before-${f}" "🚫 운영 코드 편집 차단 — 수정 단위 $FIX 의 $nm 가 없다.
   $(step_say "$FIX" "$f" "$nm")
   **재현 없는 수정 금지**(ENGINEERING §3). 이 순서다:
      .claude/hooks/step.sh $how
   ① 은 그 명령이 **실패**해야 GREEN 이다 — 통과하는 명령은 재현이 아니다.
$(esc_hint)"
    fi
  done
fi

# ── (C) 커밋 게이트 ──────────────────────────────────────────────────
# 🔴 벽이 아니라 과속방지턱이다 — 단, **닫는 커밋만은 벽이다.**
#    중간 저장까지 막으면 사람이 STEP_OVERRIDE 를 습관으로 쓰게 되고,
#    그러면 게이트가 사라진다.
if [ "$TOOL" = Bash ] && printf '%s' "$CMD" | grep -qE '\bgit\b[^|;]*\bcommit\b'; then
  CLOSING=0
  printf '%s' "$CMD" | grep -qE '(✅|종결|해결|닫는다|[A-Z]{2,5}-[0-9]+)' && CLOSING=1
  if [ "$CLOSING" = 1 ]; then
    for pair in "04-norepro:④재현불가:norepro $FIX" \
                "05-contract:⑤계약테스트:contract $FIX --node <pytest nodeid>"; do
      f="${pair%%:*}"; rest="${pair#*:}"; nm="${rest%%:*}"; how="${rest#*:}"
      if [ "$(step_status "$FIX" "$f")" != GREEN ]; then
        gate_block "commit-before-${f}" "🚫 커밋 차단 — 결함을 닫는 커밋인데 $nm 가 없다.
   $(step_say "$FIX" "$f" "$nm")
      .claude/hooks/step.sh $how
$(esc_hint)"
      elif ! step_fresh "$FIX" "$f"; then
        gate_block "commit-stale-${f}" "🚫 커밋 차단 — $nm 가 **무효**다 (기록 후 코드가 또 바뀌었다).
      .claude/hooks/step.sh $how  를 다시 돌려라.
$(esc_hint)"
      fi
    done
  else
    WARN="$STATE/step-warn-$SESSION"
    if [ "$(step_status "$FIX" 04-norepro)" != GREEN ] && [ ! -f "$WARN" ]; then
      : > "$WARN"
      log_audit "STEP-WARN commit-wip fix=$FIX session=${SESSION:0:8}"
      [ "$MODE" = observe ] && exit 0
      deny "⏸ 중간 커밋이다 (수정 단위 $FIX 진행 중, ④ 아직 없음).
   $(step_say "$FIX" 04-norepro '④재현불가')
   중간 저장이면 그대로 다시 실행하라 — **이 턴에 다시 막지 않는다.**
   결함을 닫는 커밋이라면 먼저:  .claude/hooks/step.sh norepro $FIX"
    fi
  fi
fi

# ── (D) 배포 게이트 ──────────────────────────────────────────────────
if [ "$TOOL" = Bash ] && printf '%s' "$CMD" | grep -qE \
   '(^|[;&|]|\bbash[[:space:]]+|\bsh[[:space:]]+)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(\./)?(tools/)?deploy\.sh\b|(^|[;&|])[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*railway[[:space:]]+(up|redeploy)\b'; then
  if [ "$(step_status "$FIX" 04-norepro)" != GREEN ]; then
    gate_block "deploy-before-norepro" "🚫 배포 차단 — 수정 단위 $FIX 의 ④ 재현 불가가 없다.
   $(step_say "$FIX" 04-norepro '④재현불가')
   고쳐졌다는 증거 없이 서버를 바꾸는 것이다.  step.sh norepro $FIX
$(esc_hint)"
  elif ! step_fresh "$FIX" 04-norepro; then
    gate_block "deploy-stale-norepro" "🚫 배포 차단 — ④가 **무효**다 (기록 후 코드가 또 바뀌었다).
   지금 배포될 코드는 재현 불가가 확인된 그 코드가 아니다.
$(esc_hint)"
  fi
fi
exit 0
