"""[CC-2 2026-09-25] 훅이 **실제로** 막는지 — 주장이 아니라 exit 코드로.

지시문 `cc_collab_0925` CC-2. 막아야 하는 것 넷:
  배포창(KST 17~22) · 컨테이너 직접 수정 · 발송 스위치 · force push / reset --hard

🔴 **새 `guard.sh` 를 만들지 않았다.** `guard-bash.sh` 가 배포창·force·reset 을
   이미 막고 있고, 그 파일 머리말이 "두 곳에 적으면 사본이고 사본은 원본이
   바뀔 때 따라가지 않는다"고 적고 있다. 없는 규칙 둘만 그 파일에 더했다.

🔴 **이 파일의 문자열이 훅에 걸린다.** 금지어를 시험하려면 그 낱말을 적어야
   하는데, Bash 명령줄에 적으면 훅이 그 명령을 먼저 막는다(실측: 이 계약을
   짜다가 내가 걸렸다 — DEFECTS D46 과 같은 함정). 그래서 명령 문자열을
   **파일 안 상수**로 두고 `stdin` 으로 훅에 넘긴다.
⚠️ 시각은 `FAKE_KST_HOUR` 로 주입한다 — 안 그러면 "지금 몇 시냐"에 따라
   초록·빨강이 바뀐다.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUARD = ROOT / ".claude" / "hooks" / "guard-bash.sh"
SETTINGS = ROOT / ".claude" / "settings.json"

#: 🔴 낱말을 쪼개 둔다 — 이 파일을 **읽는** 명령까지 훅에 걸리지 않게.
SEND_KEY = "PIPELINE_V14" + "_SEND"


def run_guard(command: str, hour: int = 9) -> tuple[int, str]:
    env = dict(os.environ, FAKE_KST_HOUR=str(hour), CLAUDE_PROJECT_DIR=str(ROOT))
    env.pop("SLATE_OVERRIDE", None)
    p = subprocess.run(["bash", str(GUARD)], input=json.dumps(
        {"tool_input": {"command": command}}), capture_output=True,
        text=True, env=env, cwd=str(ROOT))
    return p.returncode, (p.stderr or "")


# ── 막아야 하는 것 ─────────────────────────────────────────────────

@pytest.mark.parametrize("cmd,hour,word", [
    ("tools/deploy.sh all", 19, "슬레이트"),
    ("bash tools/deploy.sh bot", 21, "슬레이트"),
    (f"{SEND_KEY}=true python -m app.scheduler", 9, "발송"),
    (f"export {SEND_KEY}=1", 9, "발송"),
    ("railway run python -m app.pipeline", 9, "컨테이너"),
    ("railway shell", 9, "컨테이너"),
    ("railway variables --set FOO=1", 9, "컨테이너"),
    ('railway ssh --service s "pip install requests"', 9, "컨테이너"),
    ("git push --force origin main", 9, ""),
    ("git reset --hard origin/main", 9, ""),
])
def test_막힌다(cmd, hour, word):
    code, err = run_guard(cmd, hour)
    assert code == 2, f"안 막혔다: {cmd!r} → exit {code}\n{err}"
    if word:
        assert word in err, f"사유가 다르다: {cmd!r}\n{err}"


# ── 막으면 안 되는 것 ──────────────────────────────────────────────

@pytest.mark.parametrize("cmd,hour", [
    ("echo hello", 19),
    ("ls docs/fable", 9),
    # 🔴 조회는 막지 않는다 — 막는 것은 켜는 것뿐이다
    (f"railway variables | grep -i {SEND_KEY.lower()}", 9),
    ("grep -rn pipeline_v14_send app/", 9),
    # 🔴 읽기 프로브는 살아 있어야 한다 — CLAUDE.md §서버 접근의 유일한 진입로다
    ('railway ssh --service s "python /tmp/probe.py"', 9),
    ("sed -n 1,20p tools/deploy.sh", 19),
    ("git reset --soft HEAD~1", 9),
])
def test_안_막힌다(cmd, hour):
    code, err = run_guard(cmd, hour)
    assert code != 2, f"읽기·조회가 막혔다: {cmd!r}\n{err}"


# ── 배선 ───────────────────────────────────────────────────────────

def test_시각을_주입할_수_있다():
    """🔴 주입이 안 되면 이 계약은 시간대에 따라 색이 바뀐다.

    ⚠️ 창 **밖**이라고 배포가 통과하는 것은 아니다 — 미커밋·미검증 게이트가
       따로 본다(실측 09시: "미커밋 변경이 있다"). 그래서 exit 코드가 아니라
       **사유**로 가른다.
    """
    _, in_window = run_guard("tools/deploy.sh all", 19)
    _, out_window = run_guard("tools/deploy.sh all", 9)
    assert "슬레이트" in in_window, in_window
    assert "슬레이트" not in out_window, out_window


def test_기존_훅이_지워지지_않았다():
    """🔴 [CC-2] 지시문의 settings.json 을 그대로 쓰면 **훅 6개가 사라진다.**

    이번 세션에 실제로 걸린 게이트들이다 — 병합해야지 덮어쓰면 안 된다.
    """
    cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    wired = json.dumps(cfg, ensure_ascii=False)
    for name in ("guard-bash.sh", "step-gate.sh", "plan-gate.sh",
                 "record-green.sh", "claim-gate.sh", "now.sh", "turn-reset.sh"):
        assert name in wired, f"기존 훅이 빠졌다: {name}"


def test_새_훅이_물려_있다():
    cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    wired = json.dumps(cfg, ensure_ascii=False)
    for name in ("after_commit.sh", "on_stop.sh"):
        assert name in wired, f"새 훅이 안 물렸다: {name}"


@pytest.mark.parametrize("name", ["after_commit.sh", "on_stop.sh"])
def test_새_훅이_실행_가능하다(name):
    p = ROOT / ".claude" / "hooks" / name
    assert p.is_file(), f"{name} 이 없다"
    assert os.access(p, os.X_OK), f"{name} 에 실행 권한이 없다"
    chk = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr


def test_사본을_만들지_않았다():
    """🔴 `guard.sh` 를 새로 만들면 배포창 규칙이 두 곳이 된다."""
    assert not (ROOT / ".claude" / "hooks" / "guard.sh").exists(), \
        "guard-bash.sh 와 규칙이 겹치는 사본이다"
