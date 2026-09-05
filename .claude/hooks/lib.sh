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

# 작업트리 서명 — **파일 내용만** 본다. 커밋 여부와 무관해야 한다.
#
# 🔴 [2026-09-06] 종전에는 `git rev-parse HEAD` 를 넣었다. 그래서 테스트를
#    통과시키고 **커밋하는 순간** 서명이 바뀌어 마커가 무효가 됐고, 정상
#    워크플로(테스트 → 커밋 → 배포)의 배포가 매번 막혔다. 코드는 한 글자도
#    바뀌지 않았는데 게이트가 "검증 안 됐다"고 한 것이다.
#    막아야 하는 것은 **코드가 바뀐 것**이지 커밋이 생긴 것이 아니다.
#      · ls-files -s : 추적 파일의 blob 해시 — 커밋해도 그대로다
#      · diff        : 스테이지되지 않은 수정
#      · ls-files -o : 미추적 파일 내용 (새 테스트를 안 돌리고 커밋하는 것 방지)
worktree_sig() {
  cd "$REPO" || return 1
  {
    git ls-files -s 2>/dev/null
    git diff 2>/dev/null
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
