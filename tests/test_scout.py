"""[정찰층 C2~C5 2026-09-04] 정찰 — 무엇을 아직 모르는가를 센다.

🔴 왜 필요한가 (실사고 2026-09-01): KBO 5경기 판정이 14:00 에 끝나 레저에
   있는데 카드가 한 장도 안 나갔다. 사용자는 "봇이 죽었나"와 "라인업이 안
   떴다"를 구분할 수 없었다. 정찰은 그 구분을 데이터로 만든다.

이 파일이 잠그는 규율
  · 종목 문자열 하드코딩 금지 — `registry.SCOUT_SPORTS` 가 원본
  · 새 크롤 금지 — 이미 수집된 것만 읽는다
  · 시장(배당)은 정찰 기록까지만 — 딥서치·판정으로 흐르지 않는다
  · 새 스케줄 잡 금지 — 기존 폴링에 얹는다
  · 정찰 실패가 발송을 막지 않는다
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import scout


class _Redis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def scan_iter(self, match=None, count=None):
        # ⚠️ 실제 Redis 는 **glob** 이다. 접두사 비교로 흉내 내면
        #    `scout:kbo:*:2026-09-05` 같은 중간 와일드카드가 안 먹고,
        #    가짜가 실제와 다르게 동작해 테스트가 거짓말을 한다.
        import fnmatch

        for k in list(self.store):
            if fnmatch.fnmatch(k, match or "*"):
                yield k


class _Pool:
    def __init__(self, lineup=(), odds=None):
        self._lineup = list(lineup)
        self._odds = odds

    async def fetch(self, q, *a):
        return self._lineup

    async def fetchrow(self, q, *a):
        return self._odds


# ─────────────────── 창 ───────────────────

def test_window_comes_from_the_registry_not_a_literal():
    """🔴 사본 금지 — 창 길이는 ScoutSport.scout_open_h 가 원본이다."""
    import inspect

    from app.registry import scout_sport

    src = inspect.getsource(scout.in_window)
    assert "scout_open_h" in src
    assert "4" not in src.replace("scout_open_h", ""), "숫자를 손으로 적었다"

    kbo = scout_sport("kbo")
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    inside = now + timedelta(hours=kbo.scout_open_h - 0.5)
    outside = now + timedelta(hours=kbo.scout_open_h + 0.5)
    assert scout.in_window("kbo", inside, now=now)
    assert not scout.in_window("kbo", outside, now=now)


def test_unknown_sport_is_not_scouted():
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    assert not scout.in_window("kabaddi", now + timedelta(hours=1), now=now)


def test_started_game_is_out_of_window():
    """이미 시작한 경기는 정찰 대상이 아니다."""
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    assert not scout.in_window("kbo", now - timedelta(minutes=1), now=now)


# ─────────────────── 관측 ───────────────────

@pytest.mark.asyncio
async def test_observe_records_three_axes():
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    pool = _Pool(
        lineup=[{"side": "home", "final": True,
                 "first_seen": now - timedelta(minutes=30)},
                {"side": "away", "final": True,
                 "first_seen": now - timedelta(minutes=20)}],
        odds={"n": 4, "age": 12.0})
    r = _Redis()
    jg = {"sport": "kbo", "game_id": 1705,
          "starts_at": now + timedelta(hours=2),
          "research": {"home_news": [{"t": "a"}], "away_news": []}}
    rec = await scout.observe(pool, r, jg, "2026-09-04", now=now)

    assert rec["lineup"]["state"] == scout.LINEUP_CONFIRMED
    assert rec["market"]["rows"] == 4
    assert rec["factor"]["news"] == 1
    assert rec["hours_to_start"] == 2.0
    assert r.store["scout:kbo:1705:2026-09-04"]


@pytest.mark.asyncio
async def test_missing_research_is_none_not_zero():
    """🔴 "0건"과 "안 봤다"는 다르다. 폴링 경로는 재료를 싣지 않는다."""
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    rec = await scout.observe(_Pool(odds={"n": 0, "age": None}), _Redis(),
                              {"sport": "kbo", "game_id": 1,
                               "starts_at": now + timedelta(hours=1)},
                              "2026-09-04", now=now)
    assert rec["factor"]["news"] is None


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_the_slate():
    now = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)

    class _Boom(_Pool):
        async def fetch(self, q, *a):
            raise RuntimeError("DB")

    games = [{"sport": "kbo", "game_id": i, "starts_at": now + timedelta(hours=1)}
             for i in (1, 2, 3)]
    out = await scout.observe_slate(_Boom(odds={"n": 1, "age": 1.0}), _Redis(),
                                    games, "2026-09-04", now=now)
    assert len(out) == 3, "라인업 조회가 죽어도 나머지 축은 기록한다"


def test_scout_never_calls_a_collector():
    """🔴 새 크롤 금지 — 정찰이 트래픽을 만들면 정찰 때문에 소스가 막힌다."""
    from pathlib import Path

    src = Path("app/engine/scout.py").read_text(encoding="utf-8")
    for banned in ("httpx", "PoliteClient", "fetch_league", "fetch_team",
                   "requests"):
        assert banned not in src, banned


def test_scout_does_not_touch_judgement_or_send():
    from pathlib import Path

    src = Path("app/engine/scout.py").read_text(encoding="utf-8")
    for banned in ("judge_matchup", "send_game_prediction", "p_home",
                   "deepsearch", "value_gate"):
        assert banned not in src, banned


# ─────────────────── 배선 ───────────────────

def test_no_new_scheduler_job_was_created():
    """🔴 새 스케줄 잡 금지 — 기존 폴링에 얹는다."""
    from app.scheduler import _job_specs

    ids = {job_id for job_id, _, _ in _job_specs()}
    assert not any("scout" in i for i in ids), ids


def test_poll_calls_scout_and_survives_its_failure():
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert "from app.engine.scout import observe_slate" in src
    assert "정찰 실패 — 폴링은 계속한다" in src


# ─────────────────── 드리프트 ───────────────────

@pytest.mark.asyncio
async def test_drift_fires_only_when_one_axis_is_empty_across_the_slate():
    import json

    from app.watchdog import _today, check_source_drift

    r = _Redis()
    today = _today("kbo")
    for i in (1, 2, 3):
        r.store[f"scout:kbo:{i}:{today}"] = json.dumps(
            {"hours_to_start": 0.5,            # KBO 공시 관행 1.0h 를 지났다
             "lineup": {"sides": 0}, "market": {"rows": 2}})
    found = await check_source_drift(None, r)
    axes = [t for _, t, _ in found]
    assert "KBO/라인업" in axes
    assert "KBO/배당" not in axes, "들어온 축은 경보하지 않는다"


@pytest.mark.asyncio
async def test_drift_is_silent_before_the_announcement_time():
    """아직 발표 전인 것을 고장이라 부르면 매일 저녁 오탐이 난다."""
    import json

    from app.watchdog import _today, check_source_drift

    r = _Redis()
    today = _today("kbo")
    for i in (1, 2, 3):
        r.store[f"scout:kbo:{i}:{today}"] = json.dumps(
            {"hours_to_start": 3.0,            # 공시 관행 1.0h 전이다
             "lineup": {"sides": 0}, "market": {"rows": 0}})
    assert await check_source_drift(None, r) == []


@pytest.mark.asyncio
async def test_drift_needs_more_than_one_game():
    """표본 1건이면 '하나만 비었다'가 성립하지 않는다."""
    import json

    from app.watchdog import _today, check_source_drift

    r = _Redis()
    today = _today("kbo")
    r.store[f"scout:kbo:1:{today}"] = json.dumps(
        {"hours_to_start": 0.5, "lineup": {"sides": 0}, "market": {"rows": 0}})
    assert await check_source_drift(None, r) == []


def test_lead_hours_read_config_not_a_copy():
    """🔴 워치독 오탐 4건이 전부 사본 때문이었다."""
    import inspect

    from app.config import get_settings
    from app.watchdog import _lineup_lead_h

    src = inspect.getsource(_lineup_lead_h)
    assert "lineup_lead_" in src and "get_settings" in src
    s = get_settings()
    assert _lineup_lead_h("kbo") == s.lineup_lead_kbo
    assert _lineup_lead_h("npb") == s.lineup_lead_npb
    assert _lineup_lead_h("없는종목") == 0.0, "모르는 관행은 감시하지 않는다"


# ─────────────────── 카드 ───────────────────

@pytest.mark.asyncio
async def test_scout_line_is_absent_when_there_is_nothing():
    from app.engine.daily_summary import scout_lines

    assert await scout_lines(_Redis(), ("kbo",)) == []


@pytest.mark.asyncio
async def test_scout_line_counts_but_never_prints_odds_values():
    """🔴 배당 **값**은 싣지 않는다 — 건수만 센다."""
    import json

    from app.engine.daily_summary import scout_lines

    r = _Redis()
    r.store["scout:kbo:1:2026-09-04"] = json.dumps(
        {"lineup": {"state": "확정", "lead_min": 63}, "market": {"rows": 2}})
    r.store["scout:kbo:2:2026-09-04"] = json.dumps(
        {"lineup": {"state": "없음", "lead_min": None}, "market": {"rows": 0}})
    line = (await scout_lines(r, ("kbo",)))[0]
    assert line.startswith("🔭 정찰 KBO:")
    assert "확정 1" in line and "없음 1" in line
    assert "배당 1/2" in line
    assert "1.81" not in line and "odds" not in line.lower()


def test_soccer_is_recorded_but_not_connected():
    """축구는 기록만 — 카드·딥서치에 연결하지 않는다(레지스트리가 원본)."""
    from app.registry import scout_sport, scout_sports

    assert scout_sport("soccer").active is False
    assert scout_sport("soccer").reason
    assert "soccer" not in [x.sport for x in scout_sports(active_only=True)]


def test_every_active_scout_sport_has_a_call_site():
    """🔴 레지스트리에 등록만 하고 호출처가 없으면 그 종목은 영영 정찰 밖이다.

    실사고 2026-09-03: 섀도 패널이 아시아 사이클에만 있어 MLB 가 조용히
    감시 밖에 있었다. 같은 실수를 정찰에서 반복하지 않는다.
    """
    from pathlib import Path

    from app.registry import scout_sports

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    # 정찰을 부르는 잡 두 곳: 아시아 폴링(kbo·npb) · MLB 폴링
    assert src.count("from app.engine.scout import observe_slate") == 2, (
        "정찰 호출처가 둘이 아니다 — 새 종목을 등록했다면 배선도 같이 한다")
    assert '"sport": "mlb"' in src, "MLB 정찰 배선이 없다"
    covered = {"kbo", "npb", "mlb"}
    missing = {x.sport for x in scout_sports(active_only=True)} - covered
    assert not missing, f"배선 없는 활성 종목: {missing}"


def test_scout_records_are_read_with_scan_not_keys():
    """🔴 `KEYS` 는 운영 Redis 전체를 훑는 O(N) 이다. 워치독이 5분마다 그것을
    하면 워치독이 고장의 원인이 된다."""
    from pathlib import Path

    for f in ("app/watchdog.py", "app/engine/daily_summary.py",
              "app/engine/scout.py"):
        src = Path(f).read_text(encoding="utf-8")
        assert "redis.keys(" not in src, f
    src = Path("app/engine/scout.py").read_text(encoding="utf-8")
    assert "scan_iter" in src and "limit" in src, "상한 없는 순회는 폭주한다"


@pytest.mark.asyncio
async def test_drift_ignores_yesterday_records():
    """🔴 실사고 2026-09-05 16:01 — 어제 기록이 오늘 판정에 섞여 오탐이 났다.

    기록 TTL 이 36시간이라 어제 경기가 살아 있다. 어제 경기는 시작 직전에
    관측돼 `hours_to_start` 가 작고 그때 라인업이 없었으면 sides=0 —
    그래서 "전부 0"이 성립해 버린다. 오늘 KBO 는 T-2.5h(공시 전)였다.
    """
    import json

    from app.watchdog import _today, check_source_drift

    r = _Redis()
    today = _today("kbo")
    # 어제 기록 3건 — 시작 직전 관측 · 라인업 0
    for i in (1, 2, 3):
        r.store[f"scout:kbo:{i}:2026-09-04"] = json.dumps(
            {"hours_to_start": 0.2, "lineup": {"sides": 0}, "market": {"rows": 2}})
    # 오늘 기록 2건 — 아직 공시 전(T-2.5h)
    for i in (11, 12):
        r.store[f"scout:kbo:{i}:{today}"] = json.dumps(
            {"hours_to_start": 2.5, "lineup": {"sides": 0}, "market": {"rows": 2}})
    assert await check_source_drift(None, r) == [], "어제 기록으로 오탐이 났다"


def test_today_uses_the_pipeline_rule_not_a_copy():
    """🔴 MLB 는 미국 동부 기준이다 — 날짜 계산을 여기서 다시 쓰지 않는다."""
    import inspect

    from app.watchdog import _today

    src = inspect.getsource(_today)
    assert "mlb_slate_date" in src and "today_kst" in src
    assert "timedelta" not in src and "ZoneInfo" not in src
