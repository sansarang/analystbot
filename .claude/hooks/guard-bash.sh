#!/bin/bash
# [PreToolUse · Bash] 문서 규칙 중 **위반이 치명적인 것만** 기계로 강제한다.
#
# 여기 있는 규칙은 CLAUDE.md 에서 지웠다 — 두 곳에 적으면 사본이 되고,
# 사본은 원본이 바뀔 때 따라가지 않는다.
source "$(dirname "$0")/lib.sh"

CMD=$(cat | jq -r '.tool_input.command // ""' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# 🔴 heredoc 본문은 **실행되는 코드가 아니라 파일에 쓰는 문자열**이다.
#    빼지 않으면 문서·스크립트를 작성하는 것만으로 게이트가 발동한다 —
#    실측 2026-09-05: deploy.sh 의 도움말 문구를 쓰다가 배포 게이트에 걸렸고,
#    훅 테스트를 짜다가 force-push 게이트에 걸렸다.
#    ⚠️ 이건 느슨해지는 것이 아니다. heredoc 안의 글자는 실행되지 않는다.
SCAN=$(printf '%s' "$CMD" | python3 -c '
import re, sys
src = sys.stdin.read().splitlines()
out, pending, term = [], None, None
for line in src:
    if pending is None:
        m = re.search(r"<<-?\s*[\"\x27]?([A-Za-z_][A-Za-z0-9_]*)[\"\x27]?", line)
        out.append(line)
        if m:
            pending, term = True, m.group(1)
        continue
    if line.strip() == term:          # 종료 표시자 — 여기부터 다시 코드다
        pending, term = None, None
    # heredoc 본문은 버린다
print("\n".join(out))
' 2>/dev/null)
[ -z "$SCAN" ] && SCAN="$CMD"

# ── (c) 위험 명령 ────────────────────────────────────────────────────
# rm -rf 로 경로를 통째로 지우는 것. 스크래치패드·빌드 산출물은 예외다.
if printf '%s' "$SCAN" | grep -qE '\brm\b[^|;]*-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\b[^|;]*-[a-zA-Z]*f[a-zA-Z]*[rR]'; then
  if ! printf '%s' "$SCAN" | grep -qE '/(scratchpad|tmp/claude-|node_modules|__pycache__|\.pytest_cache|dist|build)/'; then
    log_audit "DENY rm-rf ${CMD:0:80}"
    deny "🚫 rm -rf 차단 — 되돌릴 수 없다.
   지울 대상을 먼저 ls 로 보고, 개별 파일을 지정하거나 스크래치패드에서 작업하라.
   (스크래치패드·캐시 경로는 이 훅이 막지 않는다)"
  fi
fi

# 🔴 [2026-09-06] `git reset --hard` — **커밋 안 된 작업을 조용히 지운다.**
#    실사고: 훅 자기테스트에 `git reset --hard HEAD~1` 을 썼다가 커밋하지
#    않은 lib.sh 수정을 통째로 날렸다. 되돌릴 방법이 없다(reflog 에도 없다 —
#    커밋된 적이 없으니까).
#    `--soft`(HEAD 만 이동)·`--mixed`(인덱스만)는 작업트리를 건드리지 않는다.
if printf '%s' "$SCAN" | grep -qE '\bgit\b[^|;]*\breset\b[^|;]*--hard'; then
  if [ -n "$(cd "$REPO" && git status --porcelain 2>/dev/null)" ]; then
    log_audit "DENY reset-hard ${CMD:0:80}"
    deny "🚫 git reset --hard 차단 — 커밋 안 된 변경이 있다.
$(cd "$REPO" && git status --short | head -6)
   이 명령은 위 내용을 되돌릴 수 없게 지운다 (커밋된 적이 없어 reflog 에도 없다).
   · HEAD 만 되돌리려면  git reset --soft
   · 인덱스만 되돌리려면  git reset --mixed
   · 정말 버릴 것이면 먼저 git stash 로 대피시켜라."
  fi
fi

# main 강제 push
if printf '%s' "$SCAN" | grep -qE 'git[^|;]*push' \
   && printf '%s' "$SCAN" | grep -qE '(--force([^-]|$)|--force-with-lease|-f( |$))' \
   && printf '%s' "$SCAN" | grep -qE '\b(main|master)\b'; then
  log_audit "DENY force-push ${CMD:0:80}"
  deny "🚫 main 강제 push 차단 — 남의 커밋을 지운다.
   되돌릴 방법이 없다. 브랜치를 따로 만들어 PR 로 가라."
fi

# ── (b) 배포 게이트 ──────────────────────────────────────────────────
# ⚠️ **명령 위치에 있을 때만** 배포로 본다. 종전에는 문자열이 나오기만 하면
#    걸려서 `sed -n 60,95p tools/deploy.sh`(읽기)까지 차단했다 — 실측
#    2026-09-05, 내가 직접 걸렸다. 읽기를 막는 게이트는 곧 꺼진다.
if printf '%s' "$SCAN" | grep -qE '(^|[;&|]|\bbash[[:space:]]+|\bsh[[:space:]]+)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(\./)?(tools/)?deploy\.sh\b|(^|[;&|])[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*railway[[:space:]]+(up|redeploy)\b'; then

  # (c-2) 슬레이트 성역 — KST 17:00~22:00 은 배포 금지 (ENGINEERING §5)
  H=$(kst_hour)
  if [ "$H" -ge 17 ] && [ "$H" -lt 22 ]; then
    if [ -z "$SLATE_OVERRIDE" ] && ! printf '%s' "$SCAN" | grep -q 'SLATE_OVERRIDE='; then
      log_audit "DENY slate-window ${H}시 ${CMD:0:60}"
      deny "🚫 슬레이트 창 배포 차단 — 지금 KST ${H}시다 (금지 17:00~22:00).
   재기동은 진행 중인 판정을 끊고, 카드가 못 나간다.
   실사고 2026-09-05: 17:45 배포로 NPB 재판정이 끊겼다.
   ⚠️ 발송 중단급 P0 라면 사유를 명시해 통과시킬 수 있다:
      SLATE_OVERRIDE='카드 0장 — 사유' tools/deploy.sh <target>
   그 사유는 감사 로그에 남는다. '더 좋아질 것 같다'는 사유가 아니다."
    fi
    log_audit "OVERRIDE slate-window ${H}시 reason=${SLATE_OVERRIDE:-inline}"
  fi

  cd "$REPO" || exit 0
  # 게이트 1 — 미커밋 변경. 타르볼 업로드는 git 추적분만 올라간다.
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    log_audit "DENY deploy-dirty"
    deny "🚫 배포 차단 — 미커밋 변경이 있다.
$(git status --short | head -8)
   배포 업로드는 git 추적 파일만 올린다. 이 변경은 서버에 반영되지 않는다."
  fi
  # 게이트 2 — HEAD 가 임시 커밋인가
  SUBJ=$(git log -1 --format=%s 2>/dev/null)
  if printf '%s' "$SUBJ" | grep -qiE '^(wip|fixup!|squash!|temp|tmp|테스트용)'; then
    log_audit "DENY deploy-wip $SUBJ"
    deny "🚫 배포 차단 — HEAD 가 임시 커밋이다: $SUBJ"
  fi
  # 게이트 3 — 이 코드로 전체 스위트가 통과했는가
  if [ ! -f "$GREEN" ] || [ "$(head -1 "$GREEN")" != "$(worktree_sig)" ]; then
    log_audit "DENY deploy-untested"
    deny "🚫 배포 차단 — 이 코드로 전체 스위트가 통과한 기록이 없다.
   PYTHONPATH=. uv run pytest tests -q
   를 돌려 통과시킨 뒤 다시 배포하라. (부분 실행 -k 는 인정되지 않는다)"
  fi
fi

# ── (a) 커밋 게이트 ──────────────────────────────────────────────────
if printf '%s' "$SCAN" | grep -qE '\bgit\b[^|;]*\bcommit\b'; then
  printf '%s' "$SCAN" | grep -q 'SKIP_TEST_GATE=1' && exit 0
  cd "$REPO" || exit 0
  SIG=$(worktree_sig)
  if [ ! -f "$GREEN" ]; then
    log_audit "DENY commit-no-marker"
    deny "🚫 커밋 차단 — 전체 테스트 스위트 통과 기록이 없다.
   PYTHONPATH=. uv run pytest tests -q
   를 돌려라. 통과하면 이 훅이 자동으로 마커를 남긴다(손으로 못 만든다).
   ⚠️ 문서·설정만 고쳤다면: SKIP_TEST_GATE=1 git commit ... 로 명시적으로 넘겨라."
  fi
  if [ "$(head -1 "$GREEN")" != "$SIG" ]; then
    WHEN=$(sed -n 2p "$GREEN"); WHAT=$(sed -n 3p "$GREEN")
    log_audit "DENY commit-stale marker=$(head -1 "$GREEN") now=$SIG"
    deny "🚫 커밋 차단 — 마지막 통과 이후 코드가 바뀌었다.
   마지막 통과: $WHEN ($WHAT)
   그 뒤 수정한 내용은 검증되지 않았다. 다시 돌려라:
   PYTHONPATH=. uv run pytest tests -q
   ⚠️ 문서·설정만 고쳤다면: SKIP_TEST_GATE=1 git commit ..."
  fi
  # ── [LINT-1 2026-09-16] 버그 급 린트.
  #    🔴 스위트가 못 잡는 종류가 있다. 2026-09-15, 같은 파일에
  #       `record_analysis` 를 두 번 정의해 **원장 저장 본체가 죽을 뻔했는데**
  #       4,395건이 통과했다 — 덮힌 함수를 부르는 테스트가 그 경로까지 안 갔다.
  #    ⚠️ 규칙은 `pyproject.toml [tool.ruff.lint] select` 가 원본이다.
  #       여기에 규칙 이름을 적지 않는다(사본 금지).
  #    ⚠️ ruff 가 없으면 **막지 않는다** — 없는 도구로 막으면 저장소가 잠긴다.
  if [ -x "$REPO/.venv/bin/ruff" ]; then
    if ! LINT=$("$REPO/.venv/bin/ruff" check app tools tests 2>&1); then
      log_audit "DENY commit-lint"
      deny "🚫 커밋 차단 — 린터가 버그 급 위반을 찾았다.
$(printf '%s' "$LINT" | head -20)
   고친 뒤 다시 커밋하라. 규칙은 pyproject.toml [tool.ruff.lint] 이 원본이다."
    fi
  fi
fi
exit 0
