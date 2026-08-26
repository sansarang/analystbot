#!/usr/bin/env bash
# Railway 배포 — 배포 컨텍스트 검증 + 커밋 정보 주입까지 한 번에.
#
# 손으로 하면 빠뜨린다(실사고 2026-08-26: 커밋 주입을 잊어 /health가
# "코드 unknown"으로 나왔고, 봇만 구버전으로 남아 잡 이름이 옛것으로 보였다).
#
# 사용: tools/deploy.sh [bot|scheduler|all]
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

# ── 3) 커밋 정보 주입 ────────────────────────────────────────────────
# 타르볼 업로드 배포는 RAILWAY_GIT_COMMIT_SHA를 주지 않는다(GitHub 연동 전용).
# 이게 없으면 /health가 "코드 unknown"이 돼 버전 추적이 무력해진다.
SHA=$(git rev-parse HEAD)
SUBJ=$(git log -1 --format=%s)
echo "▶ 배포 커밋 ${SHA:0:7} — $SUBJ"

deploy_one() {
  local svc="$1" cmd="$2"
  railway variables --project "$PROJ" --environment "$ENVIRON" --service "$svc" \
    --set "GIT_COMMIT_SHA=$SHA" --set "RAILWAY_GIT_COMMIT_MESSAGE=$SUBJ" \
    --skip-deploys >/dev/null
  echo "▶ $svc 배포 ($cmd)"
  railway up --project "$PROJ" --environment "$ENVIRON" --service "$svc" --detach
}

case "$TARGET" in
  bot)       deploy_one analystbot-bot "python -m app.bot" ;;
  scheduler) deploy_one analystbot-scheduler "python -m app.scheduler" ;;
  all)       deploy_one analystbot-bot "python -m app.bot"
             deploy_one analystbot-scheduler "python -m app.scheduler" ;;
  *) echo "사용: $0 [bot|scheduler|all]"; exit 1 ;;
esac

echo "✅ 배포 요청 완료 — 상태는 Railway 대시보드나 /health 로 확인하라"
