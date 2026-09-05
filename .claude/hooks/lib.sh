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
