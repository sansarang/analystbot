"""[전 리그 프로브] 하네스가 **아무것도 바꾸지 않는지**를 잠근다.

🔴 프로브는 진단 도구다. 진단이 대상을 바꾸면 그 진단은 못 믿는다.
"""
import re
from pathlib import Path

import pytest

SRC = Path("tools/probe_league.py").read_text(encoding="utf-8")


def test_probe_never_writes():
    """쓰기·발송 경로를 **부르지** 않는다.

    ⚠️ 문자열 상수까지 잡으면 안 된다 — 이 프로브는 소스를 읽어 슬라이스
       하려고 `"async def judge_matchup"` 같은 문자열을 들고 있다.
       그건 호출이 아니다. **호출 형태**(여는 괄호)만 본다.
    """
    for banned in ("pool.execute(", "pool.executemany(", "redis.set(",
                   "redis.hset(", "redis.hincrby(", "redis.delete(",
                   "send_game_prediction(", "send_message(",
                   "judge_matchup(", "_save_caches(", "run_panel(",
                   "_review_one(", "_shadow_one("):
        assert banned not in SRC, f"프로브가 {banned} 를 부른다"
    # SQL 쓰기문은 형태를 불문하고 없어야 한다
    for sql in ("INSERT INTO", "DELETE FROM"):
        assert sql not in SRC.upper(), f"프로브에 {sql} 이 있다"
    assert not re.search(r'"""\s*UPDATE|\bUPDATE\s+\w+\s+SET\b', SRC)


def test_probe_uses_registry_not_a_copy():
    """담당 provider 는 레지스트리가 원본이다 — 손으로 적지 않는다."""
    assert "from app.registry import" in SRC
    assert not re.search(r'ODDS_PROVIDERS\s*=', SRC), "레지스트리를 베꼈다"


def test_three_values_are_distinct():
    """✅/⚪/🔴 는 서로 다른 뜻이다 — ⚪ 를 ✅ 로 승격하지 않는다."""
    from tools.probe_league import BAD, OK, UNK

    assert len({OK, UNK, BAD}) == 3


def test_monitor_check_reads_call_sites_not_just_grep():
    """🔴 오늘 잡은 유형 — '코드 있음' 이 아니라 '어느 사이클이 부르는가'."""
    assert "_run_shadow_panel(" in SRC
    assert "covered" in SRC, "종목 인자를 실제로 읽어야 한다"


@pytest.mark.asyncio
async def test_monitor_check_flags_a_missing_league(monkeypatch):
    """MLB 호출부를 지운 소스를 주면 MLB 가 🔴 여야 한다."""
    import tools.probe_league as P

    real = P._src

    def fake(path):
        txt = real(path)
        return (txt.replace('await _run_shadow_panel(redis, ("mlb",), date)', "")
                if path == "app/scheduler.py" else txt)

    monkeypatch.setattr(P, "_src", fake)
    row = P.check_monitors()
    assert row.res["mlb"][0] == P.BAD, "MLB 누락을 못 잡는다"
    assert row.res["kbo"][0] != P.BAD


def test_probe_hook_is_flag_gated():
    """플래그 없이는 운영에서 돌지 않는다."""
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'os.getenv("PROBE_LEAGUE") == "1"' in sch
