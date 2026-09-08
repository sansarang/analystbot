#!/bin/bash
# 훅 공용 헬퍼. **문서가 아니라 여기가 규칙의 원본이다.**
#
# 종료 코드 규약 (Claude Code):
#   0 = 통과 · 2 = 차단(stderr 가 모델에게 전달됨) · 그 외 = 비차단 오류
# ⚠️ `${BASH_SOURCE[0]}` 는 **zsh 에서 비어 있다.** 그러면 dirname "" → "." 가 되어
#    REPO 가 홈 디렉토리로 잡히고, 훅은 **엉뚱한 곳의 상태를 읽으며 조용히 통과**한다.
#    (실측 2026-09-08: zsh 로 이 파일을 source 해 게이트를 시험했더니 활성 수정
#     단위를 못 봤고, 차단이 0건으로 나왔다. 게이트가 죽은 줄도 몰랐다.)
REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
STATE="$REPO/.claude/state"
GREEN="$STATE/last-green"          # 전체 스위트 통과 시점의 작업트리 서명
AUDIT="$STATE/hook-audit.log"

mkdir -p "$STATE"

log_audit() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$AUDIT"; }

# 작업트리 서명 — **파일 내용만** 본다. 커밋 여부와 무관해야 한다.
#
# 🔴 [2026-09-06] 종전에는 `git rev-parse HEAD` 를 넣었다. 그래서 테스트를
#    통과시키고 **커밋하는 순간** 서명이 바뀌어 마커가 무효가 됐고, 정상
#    워크플로(테스트 → 커밋 → 배포)의 배포가 매번 막혔다. 코드는 한 글자도
#    바뀌지 않았는데 게이트가 "검증 안 됐다"고 한 것이다.
#    막아야 하는 것은 **코드가 바뀐 것**이지 커밋이 생긴 것이 아니다.
#    ⚠️ blob 해시(ls-files -s)와 미추적 내용을 섞어도 안 된다 — 새 파일이
#       커밋되며 **미추적→추적**으로 표현이 바뀌면 서명이 또 달라진다
#       (실측 2026-09-06, 같은 사고를 두 번 겪었다).
#       그래서 추적 여부와 무관하게 **파일 내용만** 해싱한다.
worktree_sig() {
  cd "$REPO" || return 1
  # 추적 여부와 **무관하게** 내용만 해싱한다.
  #   `-c`(추적) + `-o`(미추적), `--exclude-standard`(gitignore 존중).
  #   실측 0.15초 / 파일 전체. 게이트에서만 부르므로 충분하다.
  git ls-files -c -o --exclude-standard -z 2>/dev/null \
    | sort -z | xargs -0 shasum 2>/dev/null | shasum | cut -d' ' -f1
}

# 지금 KST 시각(HHMM, 10진수)
kst_hhmm() { TZ=Asia/Seoul date '+%-H%M' | sed 's/^\([0-9]\)\([0-9][0-9]\)$/\1\2/'; }
kst_hour() { TZ=Asia/Seoul date '+%-H'; }

# 훅 입력 JSON 에서 bash 명령을 꺼낸다.
read_command() { jq -r '.tool_input.command // ""' 2>/dev/null; }

deny() {   # $1 = 사용자에게 보일 사유
  echo "$*" >&2
  exit 2
}

# ─────────────────────────────────────────────────────────────────────
# 단계 게이트 공용 (step.sh · step-gate.sh 가 함께 읽는다)
#
# 🔴 상태는 **모델 밖에** 있다. "①을 했다"는 말로는 통과하지 않는다.
#    통과 판정의 재료는 `step.sh` 가 **실제로 돌린 명령의 종료 코드**뿐이다.
#    (PostToolUse 페이로드에는 종료 코드 필드가 없다 — 실측 2026-09-08,
#     전 세션 toolUseResult 7,533건 키 전수: stdout·stderr·interrupted·
#     isImage·noOutputExpected. 그래서 훅이 사후에 읽는 설계는 불가능하고,
#     명령을 감싼 기록자가 $? 를 직접 써야 한다.)
FIXDIR="$STATE/fix"
MODEFILE="$STATE/step-gate-mode"    # observe | enforce | off
OVRTOKEN="$STATE/step-override"     # Edit/Write 용 1회성 사유 토큰

# 게이트 모드. 파일이 없으면 **observe** — 새 게이트는 관측부터 시작한다.
# env STEP_GATE 가 파일을 이긴다.
step_mode() {
  local m="${STEP_GATE:-}"
  [ -z "$m" ] && m=$(cat "$MODEFILE" 2>/dev/null)
  case "$m" in enforce|observe|off) echo "$m" ;; *) echo observe ;; esac
}

# 활성 수정 단위. 없으면 1 을 돌려준다(= 게이트 무동작).
# ⚠️ 여기서 fail closed 하면 저장소의 모든 편집이 막힌다. **활성 여부를
#    못 읽는 것**은 차단 사유가 아니다. 활성인데 상태를 못 읽는 것이 차단이다.
FIX_MAX_AGE=${FIX_MAX_AGE:-43200}   # 12시간. 잊고 켜둔 단위가 영원히 막지 않게.
fix_active() {
  local f="$FIXDIR/active" id age
  [ -f "$f" ] || return 1
  id=$(head -1 "$f" 2>/dev/null); [ -n "$id" ] || return 1
  age=$(( $(date +%s) - $(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0) ))
  if [ "$age" -gt "$FIX_MAX_AGE" ]; then
    log_audit "STEP fix-expired $id age=${age}s"
    rm -f "$f"; return 1
  fi
  printf '%s' "$id"
}

# 단계 상태 — **세 상태를 뭉개지 않는다**: NONE(미실행) · FAIL · SKIP · GREEN
step_status() {  # $1=FIX $2=단계파일명
  local f="$FIXDIR/$1/$2" s
  [ -f "$f" ] || { echo NONE; return 0; }
  s=$(sed -n 's/^status=//p' "$f" 2>/dev/null | tail -1)
  case "$s" in GREEN|FAIL|SKIP) echo "$s" ;; *) echo NONE ;; esac
}
step_get() {  # $1=FIX $2=단계파일 $3=키
  sed -n "s/^$3=//p" "$FIXDIR/$1/$2" 2>/dev/null | tail -1
}
step_put() {  # $1=FIX $2=단계파일 $3.. = key=value
  mkdir -p "$FIXDIR/$1" 2>/dev/null || return 1
  local f="$FIXDIR/$1/$2"
  : > "$f" 2>/dev/null || return 1
  local kv; for kv in "${@:3}"; do printf '%s\n' "$kv" >> "$f" || return 1; done
  return 0
}

# 사람이 읽을 한 줄. 미실행/실패/건너뜀을 **다른 문장**으로 말한다.
step_say() {  # $1=FIX $2=단계파일 $3=단계이름
  local st; st=$(step_status "$1" "$2")
  case "$st" in
    GREEN) printf '%s: 통과 (%s)' "$3" "$(step_get "$1" "$2" when)" ;;
    FAIL)  printf '%s: **실패로 기록됐다** — %s' "$3" "$(step_get "$1" "$2" why)" ;;
    SKIP)  printf '%s: **사유로 건너뛰었다** — %s' "$3" "$(step_get "$1" "$2" reason)" ;;
    *)     printf '%s: **기록된 적이 없다**' "$3" ;;
  esac
}

# 코드가 바뀌면 무효가 되는 단계인가 (④⑤). 서명 불일치 → 무효.
# ⚠️ worktree_sig 는 커밋 여부를 보지 않는다 (lib.sh:16~28 의 두 번 겪은 사고).
#    그래서 ④ → 전체스위트 → 커밋 → 배포 의 정상 경로는 막히지 않는다.
step_fresh() {  # $1=FIX $2=단계파일 ; GREEN 이면서 서명이 지금과 같아야 0
  [ "$(step_status "$1" "$2")" = GREEN ] || return 1
  local s; s=$(step_get "$1" "$2" sig)
  [ -n "$s" ] && [ "$s" = "$(worktree_sig)" ]
}
