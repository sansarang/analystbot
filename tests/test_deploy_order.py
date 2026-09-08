"""DEP-1 — `deploy.sh all` 이 **스케줄러를 먼저 띄우는 것**을 실제로 보장하는가.

🔴 감사 DEP-1: 주석은 "스케줄러를 먼저 배포한다 — 기동 시 DB 스키마를 적용하므로
   봇이 먼저 새 코드로 뜨면 아직 없는 컬럼을 참조할 수 있다"고 적는데,
   `deploy_one` 은 `railway up --detach` 다 — **업로드만 시작하고 즉시 반환한다.**
   셋의 업로드가 연달아 나가고 SUCCESS 확인은 셋을 다 올린 뒤에 돈다. 그래서
   보장되는 것은 "스케줄러 업로드가 먼저 시작됐다"뿐이고, 빌드 시간이 서비스마다
   다르므로(Go 크롤러는 짧고 파이썬은 uv sync 가 있다) 기동 순서는 뒤집힐 수 있다.

이 테스트는 네트워크를 쓰지 않는다 — `railway`·`docker` 를 PATH 에서 가짜로
바꿔치기하고 **호출 순서를 기록**한다. 임시 git 저장소에서 돈다(운영 무관).
"""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

STUB_RAILWAY = '''#!/bin/bash
sub="$1"; shift
svc=""
while [ $# -gt 0 ]; do
  case "$1" in --service) svc="$2"; shift 2 ;; *) shift ;; esac
done
case "$sub" in
  variable|variables) echo "VARS $svc" >> "$RAILWAY_LOG" ;;
  up)                 echo "UP $svc"   >> "$RAILWAY_LOG" ;;
  deployment)         echo "LIST $svc" >> "$RAILWAY_LOG"
                      printf '[{"status":"%s"}]\\n' "${RAILWAY_STATUS:-SUCCESS}" ;;
esac
exit 0
'''
STUB_OK = "#!/bin/bash\nexit 0\n"


def _sandbox(tmp_path):
    """배포 스크립트만 든 임시 git 저장소 + 가짜 명령들."""
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copy(REPO / "tools" / "deploy.sh", root / "tools")
    os.chmod(root / "tools" / "deploy.sh", 0o755)
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    # 크롤러는 별도 디렉토리에서 올린다(`deploy_one … crawler`) — 없으면 cd 가 죽는다
    (root / "crawler").mkdir()
    (root / "crawler" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "배포 순서 테스트"], cwd=root, check=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("railway", STUB_RAILWAY), ("docker", STUB_OK), ("uv", STUB_OK)):
        p = bin_dir / name
        p.write_text(body, encoding="utf-8")
        os.chmod(p, 0o755)

    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {**os.environ,
           "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "RAILWAY_LOG": str(log),
           "SKIP_STABILITY": "1"}
    return root, log, env


def _run(root, env, target="all"):
    script = str(root / "tools" / "deploy.sh")
    return subprocess.run([script, target], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


def test_스케줄러가_SUCCESS_된_뒤에_봇이_올라간다(tmp_path):
    root, log, env = _sandbox(tmp_path)
    r = _run(root, env)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln]
    i_sched_up = calls.index("UP analystbot-scheduler")
    i_sched_ok = calls.index("LIST analystbot-scheduler")
    i_bot_up = calls.index("UP analystbot-bot")
    assert i_sched_up < i_sched_ok < i_bot_up, (
        f"스케줄러 SUCCESS 확인 전에 봇 업로드가 시작됐다 — 순서: {calls}")
    assert sum(1 for c in calls if c.startswith("UP ")) == 3


def test_스케줄러가_실패하면_봇_크롤러는_올리지_않는다(tmp_path):
    root, log, env = _sandbox(tmp_path)
    env["RAILWAY_STATUS"] = "FAILED"
    r = _run(root, env)
    calls = log.read_text(encoding="utf-8")
    assert "UP analystbot-scheduler" in calls
    assert "UP analystbot-bot" not in calls, "스케줄러가 실패했는데 봇을 올렸다"
    assert "UP analystbot-crawler" not in calls
    assert r.returncode != 0, "실패인데 종료코드가 0이다"


def test_단일_서비스_배포는_그대로_돈다(tmp_path):
    root, log, env = _sandbox(tmp_path)
    r = _run(root, env, target="bot")
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text(encoding="utf-8")
    assert "UP analystbot-bot" in calls
    assert "UP analystbot-scheduler" not in calls


def test_훅이_없는_저장소에서도_배포가_성공으로_끝난다(tmp_path):
    """⚠️ 임시 저장소에는 `.claude/hooks/lib.sh` 가 없다. 배포가 끝난 뒤
    단계 기록을 시도하다 죽으면 **성공한 배포가 실패로 보인다.**"""
    root, log, env = _sandbox(tmp_path)
    r = _run(root, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "배포 완료" in r.stdout
