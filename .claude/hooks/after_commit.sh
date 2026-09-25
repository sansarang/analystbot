#!/bin/bash
# [PostToolUse · Bash · CC-2 2026-09-25] 커밋 직후 **보고서 초안 재료**를 남긴다.
#
# 🔴 왜 필요한가. 보고서(`docs/fable/reports/`)는 "커밋 해시 + pytest 마지막
#    20줄"을 요구한다. 그것을 사람이 기억해 옮기면 틀린다 — 기계가 찍는다.
# 🔴 `record-green.sh` 와 **역할이 다르다.** 그쪽은 "전체 스위트가 실제로
#    통과했다"는 마커(커밋 게이트의 근거)이고, 이쪽은 보고서 재료다.
#    같은 자리에 둘이 물려 있어도 서로 간섭하지 않는다.
# ⚠️ **막지 않는다.** 테스트가 실패해도 경고만 낸다(exit 0) — 이 훅은 관측이고,
#    관측이 작업을 죽이면 안 된다.
# ⚠️ 산출물 이름은 `_` 로 시작한다. 보고서 형식 계약이 그것을 제외한다.
set -u

IN=$(cat)
CMD=$(printf '%s' "$IN" | jq -r '.tool_input.command // ""' 2>/dev/null)

# `git commit` 이 **명령 위치**에 있을 때만. 문자열이 나오기만 해서 도는 훅은
# 곧 꺼진다(guard-bash.sh 가 같은 이유로 위치를 본다).
printf '%s' "$CMD" \
  | grep -qE '(^|[;&|]|&&)[[:space:]]*git[[:space:]]+commit\b' || exit 0

REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$REPO" ] && [ -d "$REPO/.git" ] || exit 0
cd "$REPO" || exit 0

OUT="docs/fable/reports/_last_commit.md"
mkdir -p "$(dirname "$OUT")" || exit 0

LOG=$(git log -1 --oneline 2>/dev/null)
# 커밋이 없으면(=커밋이 실패했다) 재료를 남기지 않는다 — 거짓 재료가 더 나쁘다.
[ -n "$LOG" ] || exit 0

TESTS=$(cd "$REPO" && PYTHONPATH=. timeout 600 uv run pytest -q 2>&1 | tail -20)
STAMP=$(TZ=Asia/Seoul date '+%F %T KST')

{
  printf '# 커밋 직후 재료 (자동 생성 · 보고서가 아니다)\n\n'
  printf '생성 %s · 훅 `after_commit.sh`\n\n' "$STAMP"
  printf '## git log -1 --oneline\n\n```\n%s\n```\n\n' "$LOG"
  printf '## pytest 마지막 20줄\n\n```\n%s\n```\n' "$TESTS"
} > "$OUT" 2>/dev/null

# 🔴 실패는 **알리되 막지 않는다.**
if printf '%s' "$TESTS" | grep -qE '[0-9]+ (failed|error)'; then
  printf '⚠️ 커밋 뒤 테스트가 초록이 아니다 — %s\n' "$OUT" >&2
  printf '%s\n' "$(printf '%s' "$TESTS" | tail -3)" >&2
fi
exit 0
