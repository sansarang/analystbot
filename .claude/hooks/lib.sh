#!/bin/bash
# 훅 공용 헬퍼. **문서가 아니라 여기가 규칙의 원본이다.**
#
# 종료 코드 규약 (Claude Code):
#   0 = 통과 · 2 = 차단(stderr 가 모델에게 전달됨) · 그 외 = 비차단 오류
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE="$REPO/.claude/state"
GREEN="$STATE/last-green"          # 전체 스위트 통과 시점의 작업트리 서명
AUDIT="$STATE/hook-audit.log"

mkdir -p "$STATE"

log_audit() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$AUDIT"; }

# 작업트리 서명 — 커밋 여부와 무관하게 "지금 이 코드"를 가리킨다.
#   추적 변경(diff) + 미추적 파일 내용까지 본다. 새 테스트 파일을 추가하고
#   테스트를 안 돌린 채 커밋하는 것도 막아야 하기 때문이다.
worktree_sig() {
  cd "$REPO" || return 1
  {
    git rev-parse HEAD 2>/dev/null
    git diff HEAD 2>/dev/null
    git ls-files -o --exclude-standard -z 2>/dev/null \
      | xargs -0 -I{} shasum "{}" 2>/dev/null
  } | shasum | cut -d' ' -f1
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
