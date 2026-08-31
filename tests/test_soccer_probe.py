"""[축구 조사] 프로브가 지켜야 할 계약 — 읽기 전용·예외 격리·서버 주체.

이 프로브는 프로덕션 스케줄러 안에서 돈다. 그러므로 "측정 도구가 본체를
해치지 않는다"를 코드로 잠근다.
"""

import ast
from pathlib import Path

import pytest

PROBE = Path("tools/probe_soccer_lineup.py")
SCHED = Path("app/scheduler.py")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_probe_touches_no_production_state():
    """🔴 읽기 전용이다 — Redis·DB·app 모듈을 건드리지 않는다.

    프로브가 프로덕션 상태를 만지면 '조사'가 아니라 '운영 변경'이 된다.
    승인 조건 ①이며, import 경계로 강제한다.
    """
    banned = {"redis", "asyncpg", "app", "psycopg", "sqlalchemy"}
    leaked = _imports(PROBE) & banned
    assert not leaked, f"프로브가 프로덕션 상태에 접근한다: {sorted(leaked)}"
    src = PROBE.read_text(encoding="utf-8")
    for token in ("get_pool", "aioredis", "redis.asyncio", "DATABASE_URL"):
        assert token not in src, f"프로브에 {token} 흔적이 있다"


def test_probe_exposes_shared_run_for_cli_and_server():
    """CLI와 서버 잡이 같은 코드를 써야 한다 — 갈라지면 숫자를 믿을 수 없다."""
    src = PROBE.read_text(encoding="utf-8")
    assert "async def run(" in src
    assert "emit=None" in src and "log=None" in src


def test_scheduler_probe_job_is_isolated_and_one_shot():
    """프로브 실패가 스케줄러 본연의 잡을 죽이지 않는다 (승인 조건 ②)."""
    src = SCHED.read_text(encoding="utf-8")
    assert "async def soccer_lineup_probe_job()" in src
    # 기동 경로에서 await 하지 않는다 — 본 잡 등록을 지연시키면 안 된다
    assert "asyncio.create_task(soccer_lineup_probe_job())" in src
    assert "await soccer_lineup_probe_job()" not in src
    # 1회성임이 주석에 남아 있어야 한다
    assert "1회성" in src
    body = src[src.index("async def soccer_lineup_probe_job"):]
    body = body[:body.index("\ndef ") if "\ndef " in body else len(body)]
    assert "except Exception" in body, "프로브 잡에 예외 격리가 없다"


def test_scheduler_probe_emits_to_log_not_file():
    """결과는 파일이 아니라 로그로 남긴다 (승인 조건 ③).

    컨테이너 파일시스템은 재배포에 사라진다. railway 로그는 남아 회수할 수 있다.
    """
    src = SCHED.read_text(encoding="utf-8")
    body = src[src.index("async def soccer_lineup_probe_job"):]
    body = body[:body.index("\nasync def ") if "\nasync def " in body else len(body)]
    assert "[soccer-probe]" in body
    assert "json.dumps" in body
    assert "open(" not in body, "프로브 잡이 파일을 연다 — 로그로 남겨야 한다"


async def test_probe_run_handles_no_fixtures(monkeypatch):
    """대상 경기가 없으면 조용히 끝난다 — 예외로 스케줄러를 흔들지 않는다."""
    import tools.probe_soccer_lineup as probe

    async def no_games(client, hours, log=None):
        return []

    monkeypatch.setattr(probe, "upcoming", no_games)
    out = await probe.run(hours=1, log=lambda m: None)
    assert out == {"observed": [], "targets": 0}


def test_probe_distinguishes_predicted_from_confirmed_lineups():
    """🔴 예상 라인업을 확정으로 세면 리드타임 측정이 통째로 틀린다.

    실측 2026-08-31: 킥오프 10시간 전 FotMob이 이미 starters=11을 주는데
    lineupType이 'predicted'였다(종료 경기는 'standard'). 구분 없이 세면
    T-600을 리드타임으로 기록하고 거기서 폴링을 멈춰, 진짜 확정 시점을
    영영 관측하지 못한다.
    """
    import tools.probe_soccer_lineup as probe

    def state(kind):
        return probe._lineup_state({"content": {"lineup": {
            "lineupType": kind, "source": "enetpulse",
            "homeTeam": {"starters": [{}] * 11, "unavailable": []},
            "awayTeam": {"starters": [{}] * 11, "unavailable": [{}, {}]}}}})

    pred = state("predicted")
    assert pred["has_starters"] is True
    assert pred["has_confirmed"] is False, "예상 라인업을 확정으로 셌다"

    conf = state("standard")
    assert conf["has_confirmed"] is True

    # 타입을 모르면 확정이라고 말하지 않는다
    assert state(None)["has_confirmed"] is False


def test_probe_stops_only_on_confirmed():
    """폴링 중단 조건이 확정 라인업이어야 한다 (소스 검사)."""
    from pathlib import Path

    src = Path("tools/probe_soccer_lineup.py").read_text(encoding="utf-8")
    assert 'if rec.get("has_confirmed"):' in src
    assert 'if rec.get("has_starters"):' not in src
