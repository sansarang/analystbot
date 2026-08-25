"""[6][7-4][7-5] 버전 추적 · 카드 한계 표시 · /health.

실사고(2026-08-25): 봇이 26커밋 뒤처진 채 돌았고, 스케줄러는 꺼져 있었으며,
결함투성이 리포트가 아무 표시 없이 나갔다. 아래는 그 셋을 각각 막는 장치다.
"""

import json

import pytest

from app import version
from app.pipeline import data_limitation_line


@pytest.fixture(autouse=True)
def _reset_boot():
    version._BOOT = None
    yield
    version._BOOT = None


# ---------------------------------------------------------------- [6] 버전

def test_boot_info_is_frozen_at_first_call(monkeypatch):
    """기동 시점 커밋으로 고정된다 — 이후 git이 움직여도 실행 중 코드는 그대로다."""
    calls = {"n": 0}

    def fake_git(*args):
        if args[0] == "rev-parse":
            calls["n"] += 1
            return f"aaa{calls['n']}"
        if args[0] == "log":
            return "테스트 커밋"
        return ""

    monkeypatch.setattr(version, "_git", fake_git)
    first = version.boot_info().commit
    assert version.boot_info().commit == first, "두 번째 호출에서 값이 바뀌면 안 된다"


def test_commits_behind_counts_gap(monkeypatch):
    def fake_git(*args):
        if args[:2] == ("rev-parse", "--git-dir"):
            return ".git"          # 저장소 안에서 도는 상황
        if args[:2] == ("rev-parse", "--short"):
            return "newhead" if version._BOOT is not None else "oldboot"
        if args[0] == "log":
            return "부팅 당시 커밋"
        if args[0] == "rev-list":
            return "26"
        return ""

    monkeypatch.setattr(version, "_git", fake_git)
    version.boot_info()          # oldboot으로 고정
    assert version.commits_behind() == 26


def test_staleness_line_warns_and_names_count(monkeypatch):
    monkeypatch.setattr(version, "commits_behind", lambda: 26)
    monkeypatch.setattr(version, "boot_info", lambda: version.BuildInfo(
        commit="abc1234", subject="옛 커밋", committed_at="", dirty=False,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
    line = version.staleness_line()
    assert "26커밋 뒤처진" in line and "재시작" in line


def test_staleness_line_is_none_when_current(monkeypatch):
    monkeypatch.setattr(version, "commits_behind", lambda: 0)
    assert version.staleness_line() is None


def test_git_failure_does_not_crash(monkeypatch):
    """git이 없어도 죽지 않는다 — 관측 장치가 본체를 죽이면 안 된다."""
    monkeypatch.setattr(version, "_git", lambda *a: "")
    info = version.boot_info()
    assert info.commit == "unknown"
    assert version.commits_behind() == 0
    assert version.staleness_line() is None


# ---------------------------------------------------------------- [7-4] 카드 한계

def test_limitation_line_absent_when_all_stages_ok():
    analysis = {"stages": [{"name": "판정", "ok": 15, "total": 15, "cause": None},
                           {"name": "λ 산출", "ok": 15, "total": 15, "cause": None}]}
    assert data_limitation_line(analysis) is None


def test_limitation_line_names_judgment_and_lambda():
    analysis = {"stages": [
        {"name": "판정", "ok": 0, "total": 15, "cause": "credit"},
        {"name": "λ 산출", "ok": 0, "total": 15, "cause": "missing"},
    ]}
    line = data_limitation_line(analysis)
    assert line.startswith("⚠️ 이 리포트의 한계")
    assert "판정 미수행(크레딧 부족)" in line
    assert "λ 미산출(데이터 없음)" in line
    assert "시장 배당과 폼 데이터만 반영됨" in line


def test_limitation_line_reports_partial_scope():
    """일부만 실패하면 몇 경기인지 밝힌다."""
    analysis = {"stages": [{"name": "리서치", "ok": 12, "total": 15, "cause": "rate_limit"}]}
    line = data_limitation_line(analysis)
    assert "3경기" in line


def test_card_shows_limitation_at_top():
    """결함이 있으면 카드 **맨 위**에 나와야 한다 — 묻히면 표시하지 않은 것과 같다."""
    from app.pipeline import _render_card

    analysis = {
        "date": "2026-08-26", "sport": "mlb", "games": [], "picks": [],
        "stages": [{"name": "판정", "ok": 0, "total": 15, "cause": "credit"}],
        "mode": {"name": "live_conservative"},
    }
    card = _render_card(analysis)
    head = card.splitlines()[:2]
    assert any("이 리포트의 한계" in line for line in head)


def test_card_clean_when_no_defect():
    from app.pipeline import _render_card

    analysis = {
        "date": "2026-08-26", "sport": "mlb", "games": [], "picks": [],
        "stages": [{"name": "판정", "ok": 15, "total": 15, "cause": None}],
        "mode": {"name": "live_conservative"},
    }
    assert "이 리포트의 한계" not in _render_card(analysis)


# ---------------------------------------------------------------- [7-5] /health

class FakeRedis:
    def __init__(self, store=None, hashes=None):
        self.store = store or {}
        self.hashes = hashes or {}

    async def get(self, k):
        return self.store.get(k)

    async def hgetall(self, k):
        return self.hashes.get(k, {})

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def hset(self, k, f, v):
        self.hashes.setdefault(k, {})[f] = v


@pytest.mark.asyncio
async def test_health_flags_dead_scheduler():
    """하트비트가 없으면 '미실행'이라고 분명히 말해야 한다."""
    from app.health import build_health

    text = await build_health(None, FakeRedis())
    assert "스케줄러" in text and "미실행" in text


@pytest.mark.asyncio
async def test_health_reports_live_scheduler():
    from datetime import datetime, timezone

    from app.health import HEARTBEAT_KEY, build_health

    r = FakeRedis({HEARTBEAT_KEY: datetime.now(timezone.utc).isoformat()})
    text = await build_health(None, r)
    assert "실행 중" in text


@pytest.mark.asyncio
async def test_health_shows_commit_and_staleness(monkeypatch):
    from app.health import build_health

    monkeypatch.setattr("app.health.commits_behind", lambda: 26)
    text = await build_health(None, FakeRedis())
    assert "26커밋 뒤처짐" in text and "재시작 필요" in text


@pytest.mark.asyncio
async def test_health_shows_lambda_and_judge_rates():
    """오늘 λ 가동률·판정 성공률이 나와야 한다 — 이게 없어서 사고를 못 봤다."""
    from app.health import build_health
    from app.pipeline import mlb_slate_date

    games = [
        {"status": "scheduled", "distribution": {"x": 1}, "p_claude": 0.6,
         "research_status": "refreshed"},
        {"status": "scheduled", "distribution": None, "p_claude": None,
         "research_status": "missing"},
    ]
    r = FakeRedis({f"analysis:mlb:{mlb_slate_date()}":
                   json.dumps({"games": games})})
    text = await build_health(None, r)
    assert "λ 1/2" in text and "판정 1/2" in text


@pytest.mark.asyncio
async def test_health_warns_on_quota_exhaustion():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.health import build_health

    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    r = FakeRedis({f"research_calls:{today}": "61", "odds_quota_remaining": "284"})
    text = await build_health(None, r)
    assert "61/60" in text and "상한 초과" in text


def test_boot_info_prefers_deploy_env(monkeypatch):
    """컨테이너에는 .git이 없다 — 배포 플랫폼이 준 커밋을 써야 한다.

    이게 없으면 배포 후 '지금 어떤 코드가 도는가'를 알 수 없어
    [6]의 버전 추적이 통째로 무력해진다.
    """
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_MESSAGE", "배포된 커밋 제목")
    monkeypatch.setattr(version, "_git", lambda *a: "")   # git 없음
    info = version.boot_info()
    assert info.commit == "abcdef1"
    assert info.subject == "배포된 커밋 제목"
    assert info.dirty is False


def test_commits_behind_zero_without_repo(monkeypatch):
    """저장소가 없으면 뒤처짐을 계산할 수 없다 — 0으로 두고 오탐하지 않는다."""
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setattr(version, "_git", lambda *a: "")
    version.boot_info()
    assert version.commits_behind() == 0
    assert version.staleness_line() is None
