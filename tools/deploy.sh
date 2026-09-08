#!/usr/bin/env bash
# Railway 배포 — 배포 컨텍스트 검증 + 커밋 정보 주입까지 한 번에.
#
# 손으로 하면 빠뜨린다(실사고 2026-08-26: 커밋 주입을 잊어 /health가
# "코드 unknown"으로 나왔고, 봇만 구버전으로 남아 잡 이름이 옛것으로 보였다).
#
# 사용: tools/deploy.sh [bot|scheduler|crawler|all]
set -euo pipefail

PROJ=d29edc63-4309-4656-a8af-543b8b773437
ENVIRON=production
TARGET="${1:-all}"
cd "$(dirname "$0")/.."

# ── 1) 커밋되지 않은 변경이 있으면 멈춘다 ─────────────────────────────
# 배포 업로드는 git 추적 파일만 올라가므로, 미커밋 변경은 반영되지 않는다.
if [ -n "$(git status --porcelain)" ]; then
  echo "❌ 커밋되지 않은 변경이 있다. 배포 업로드에 반영되지 않는다:"
  git status --short
  exit 1
fi

# ── 2) 배포될 파일만으로 빌드가 되는지 확인 ───────────────────────────
# 로컬 docker build는 .gitignore를 보지 않아 이 결함을 못 잡는다.
# (실사고: data/ 와 uv.lock 이 업로드에서 빠져 빌드가 두 번 깨졌다)
echo "▶ 배포 컨텍스트 검증 중..."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git archive --format=tar HEAD | tar -x -C "$TMP"
if ! docker build -q -t analystbot:ctx "$TMP" >/dev/null; then
  echo "❌ 배포 컨텍스트로 빌드 실패 — .gitignore에 필요한 파일이 있는지 확인하라"
  exit 1
fi
echo "✅ 배포 컨텍스트 빌드 성공"

# ── 2.5) 판정 안정성 스모크 ──────────────────────────────────────────
# [P0 2026-09-05] 같은 재료가 같은 숫자를 내는가. 같은 프롬프트 3회를 실제
# 판정 모델에 보내 **우세가 갈리면 배포를 막는다.**
#   실사고: KBO game=1713 이 같은 재료로 기아 0.440 → 0.590 → KT 0.450 으로
#   50% 선을 두 번 넘었고, 그 사이 수정 카드가 나갔다.
# ⚠️ 인프라 장애(503)는 막지 않는다 — 유효 응답 2건 미만이면 SKIP 이다.
#    503 이 배포를 막으면 이 게이트는 곧 꺼지고, 꺼진 게이트는 없는 게이트다.
# ⚠️ SKIP_STABILITY=1 로 끌 수 있다. 끄면 그 사실이 로그에 남는다.
if [ "${SKIP_STABILITY:-0}" = "1" ]; then
  echo "⏭  판정 안정성 스모크 건너뜀 (SKIP_STABILITY=1)"
else
  echo "▶ 판정 안정성 스모크..."
  if ! PYTHONPATH=. TELEGRAM_BOT_TOKEN="" uv run python -m tools.stability_smoke; then
    echo "❌ 같은 재료가 다른 답을 냈다 — 배포 중단"
    echo "   (인프라 장애가 아니라 판정 불안정이다. 원인을 고치거나,"
    echo "    의도한 배포라면 SKIP_STABILITY=1 로 명시적으로 넘겨라)"
    exit 1
  fi
fi

# ── 3) 커밋 정보 주입 ────────────────────────────────────────────────
# 타르볼 업로드 배포는 RAILWAY_GIT_COMMIT_SHA를 주지 않는다(GitHub 연동 전용).
# 이게 없으면 /health가 "코드 unknown"이 돼 버전 추적이 무력해진다.
SHA=$(git rev-parse HEAD)
SUBJ=$(git log -1 --format=%s)
echo "▶ 배포 커밋 ${SHA:0:7} — $SUBJ"

# 🔴 [2026-09-06] **초기화를 빠뜨려 배포가 중간에 죽었다.** `set -u` 아래서
#    첫 `DEPLOYED="$DEPLOYED $svc"` 가 unbound 로 터졌다 — 스케줄러 업로드는
#    이미 나간 뒤라, 봇·크롤러가 구버전으로 남고 아무도 모를 뻔했다.
#    (실측 15:15: "tools/deploy.sh: line 71: DEPLOYED: unbound variable")
DEPLOYED=""

# 🔴 [DEP-2 2026-09-08] 실행 명령을 **여기 손으로 적지 않는다.** 종전에는
#    `deploy_one analystbot-crawler "crawler -interval 10m"` 처럼 적어 화면에
#    찍었는데, 그 값은 `railway up` 에 전달되지 않는다 — 배포할 때마다 **틀린
#    값**이 사람에게 보고됐고, 그걸 믿고 CRW-6 항목이 닫혔다.
#    크롤러의 원본은 이미지 CMD 이므로 거기서 읽어 찍는다.
crawler_cmd() {
  sed -n 's/^CMD \[\(.*\)\]/\1/p' crawler/Dockerfile | tr -d '"' | sed 's/, */ /g'
}

deploy_one() {
  local svc="$1" cmd="$2" path="${3:-.}"
  railway variables --project "$PROJ" --environment "$ENVIRON" --service "$svc" \
    --set "GIT_COMMIT_SHA=$SHA" --set "RAILWAY_GIT_COMMIT_MESSAGE=$SUBJ" \
    --skip-deploys >/dev/null
  echo "▶ $svc 배포 ($cmd)"
  ( cd "$path" && railway up --project "$PROJ" --environment "$ENVIRON" \
      --service "$svc" --detach )
  DEPLOYED="$DEPLOYED $svc"
}

# 🔴 [2026-09-05] **"배포 요청 완료"는 배포된 것이 아니다.** 종전에는 요청만
#    보내고 "대시보드나 /health 로 확인하라"고 사람에게 떠넘겼다.
#    실사고: 요청은 갔는데 마지막 SUCCESS 는 하루 전이었다 — 아무도 몰랐다.
#    이제 기계가 확인한다. 사람의 다짐이 아니라 종료 코드다.
wait_success() {
  local svc="$1" st="" i
  for i in $(seq 1 40); do
    st=$(railway deployment list --project "$PROJ" --environment "$ENVIRON" \
         --service "$svc" --json 2>/dev/null \
         | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["status"])' 2>/dev/null)
    case "$st" in
      SUCCESS) echo "  ✅ $svc SUCCESS ($(date '+%H:%M:%S'))"; return 0 ;;
      FAILED|CRASHED) echo "  🔴 $svc $st — 빌드 로그를 확인하라"; return 1 ;;
    esac
    sleep 12
  done
  echo "  🔴 $svc 8분 안에 SUCCESS 가 안 떴다 (마지막 상태: ${st:-unknown})"
  return 1
}

# ⚠️ [DEP-3] 봇·스케줄러의 실제 실행 명령은 **저장소에 없다** — Railway 대시보드의
#    startCommand 다(스케줄러는 preDeployCommand 로 DB 스키마도 적용한다).
#    그래서 여기서는 명령이 아니라 **어디서 오는지**를 찍는다. 아는 척하지 않는다.
SCHED_CMD="대시보드 startCommand (저장소 밖 · DEP-3)"
BOT_CMD="대시보드 startCommand (저장소 밖 · DEP-3)"

# ⚠️ **스케줄러를 먼저** 배포한다 — 기동 시 DB 스키마를 적용하므로,
#    봇이 먼저 새 코드로 뜨면 아직 없는 컬럼을 참조할 수 있다.
case "$TARGET" in
  bot)       deploy_one analystbot-bot "$BOT_CMD" ;;
  scheduler) deploy_one analystbot-scheduler "$SCHED_CMD" ;;
  crawler)   deploy_one analystbot-crawler "$(crawler_cmd)  ← crawler/Dockerfile CMD" crawler ;;
  all)       # 🔴 [DEP-1 2026-09-08] **스케줄러가 SUCCESS 에 닿을 때까지 기다린 뒤**
             #    나머지를 올린다. 종전에는 셋을 연달아 `railway up --detach` 로
             #    올리고(업로드만 시작하고 즉시 반환) SUCCESS 확인은 그 뒤에 했다 —
             #    보장되는 것은 "스케줄러 **업로드**가 먼저 시작됐다"뿐이었다.
             #    빌드 시간이 서비스마다 다르므로(Go 크롤러는 짧고 파이썬은
             #    uv sync 가 있다) 기동 순서는 얼마든지 뒤집힐 수 있었다.
             #    주석이 막으려던 상황이 정확히 그것이다.
             deploy_one analystbot-scheduler "$SCHED_CMD"
             if ! wait_success analystbot-scheduler; then
               echo "❌ 스케줄러가 SUCCESS 에 도달하지 못했다 — 봇·크롤러는 올리지 않는다."
               echo "   (봇이 새 스키마 없이 뜨는 것보다 옛 코드로 도는 편이 낫다)"
               exit 1
             fi
             DEPLOYED=""          # 확인이 끝났으므로 아래 루프에서 다시 기다리지 않는다
             deploy_one analystbot-bot "$BOT_CMD"
             deploy_one analystbot-crawler "$(crawler_cmd)  ← crawler/Dockerfile CMD" crawler ;;
  *) echo "사용: $0 [bot|scheduler|crawler|all]"; exit 1 ;;
esac

echo "▶ SUCCESS 확인 중 (요청 ≠ 배포)..."
RC=0
for svc in $DEPLOYED; do wait_success "$svc" || RC=1; done
if [ $RC -ne 0 ]; then
  echo "❌ 배포가 SUCCESS 에 도달하지 못했다 — 서버는 옛 코드로 돌고 있다"
  exit 1
fi
echo "✅ 배포 완료 — 커밋 ${SHA:0:7} 이 서버에서 돈다"

# ── ⑧ 단계 기록 ─────────────────────────────────────────────────────
# 🔴 **SUCCESS 를 확인한 뒤에만** 남긴다. 요청 ≠ 배포 ≠ 단계 통과.
#    활성 수정 단위가 있을 때만 기록하고, 없으면 아무 일도 하지 않는다.
#    (활성 여부 판단은 lib.sh 의 fix_active 원본을 쓴다 — 여기에 규칙을
#     다시 적으면 그것이 곧 사본이 된다.)
# ⚠️ 훅이 없는 저장소(테스트 샌드박스·클론)에서도 배포는 성공으로 끝나야 한다.
#    `set -e` 아래서 없는 파일을 source 하면 **성공한 배포가 실패로 보인다.**
FIXNOW=""
if [ -f .claude/hooks/lib.sh ]; then
  source .claude/hooks/lib.sh
  FIXNOW=$(fix_active || true)
fi
if [ -n "${FIXNOW:-}" ]; then
  .claude/hooks/step.sh record deploy "$FIXNOW" "$(echo $DEPLOYED)" || true
  echo "   다음은 ⑨ 첫 사이클 실측이다 — 새 코드가 **처음 실행되는** 로그 라인을 잡아라:"
  echo "   .claude/hooks/step.sh cycle $FIXNOW -- '<확인 명령>'"
fi
