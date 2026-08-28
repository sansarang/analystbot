"""KBO·NPB 17:45 공통 발송 — 라인업 공시 이후 한꺼번에."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.pregame_push import (
    PUSH_HOUR,
    PUSH_MINUTE,
    SPORTS,
    compose_card,
    header_line,
    run_pregame_push,
    sent_key,
    still_upcoming,
)


def test_only_kbo_npb():
    assert SPORTS == ("kbo", "npb")
    assert "mlb" not in SPORTS and "soccer" not in SPORTS


def test_push_clock_is_1745():
    assert (PUSH_HOUR, PUSH_MINUTE) == (17, 45)
    assert header_line("kbo") == "⏰ KBO · 17:45 예측"
    assert header_line("npb") == "⏰ NPB · 17:45 예측"


def test_still_upcoming_skips_started():
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    assert still_upcoming(now + timedelta(minutes=15), now) is True   # NPB 18:00
    assert still_upcoming(now + timedelta(minutes=45), now) is True   # KBO 18:30
    assert still_upcoming(now, now) is False
    assert still_upcoming(now - timedelta(minutes=1), now) is False


def test_compose_card_is_game_prediction():
    jg = {
        "game_id": 11, "sport": "kbo", "home": "LG Twins", "away": "NC Dinos",
        "starts_at_kst": "08/28 18:30", "status": "scheduled", "league": "KBO",
        "p_claude": 0.61, "judge_confidence": "medium", "verdict": "홈 우세",
        "best_odds": {}, "expert_picks": [], "stats": {},
        "research": {
            "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
            "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            "home_pitcher": {"name": "임찬규", "era_season": 3.40},
        },
        "market_board": [],
    }
    text = compose_card(jg, "", "kbo")
    assert "17:45 예측" in text
    assert "LG" in text or "트윈스" in text or "NC" in text


class _Redis:
    def __init__(self, store=None):
        self.store = store if store is not None else {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, val, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = val
        return True

    async def delete(self, key):
        self.store.pop(key, None)


class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def fetch(self, *_a, **_k):
        return self.rows

    async def execute(self, sql, *args):
        self.executed.append((sql, args))



def _row(gid=11, sport="kbo", minutes=45):
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    return now, {
        "id": gid, "sport": sport, "home": "LG Twins", "away": "NC Dinos",
        "starts_at": now + timedelta(minutes=minutes), "league": "KBO",
    }


def _analysis(gid=11):
    import json
    return json.dumps({
        "games": [{
            "game_id": gid, "sport": "kbo", "home": "LG Twins", "away": "NC Dinos",
            "starts_at_kst": "08/28 18:30", "status": "scheduled", "league": "KBO",
            "p_claude": 0.61, "judge_confidence": "medium", "verdict": "홈 우세",
            "best_odds": {}, "expert_picks": [], "stats": {},
            "research": {
                "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
                "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            },
            "market_board": [],
        }],
        "news": "",
    })


@pytest.mark.asyncio
async def test_sends_kbo_and_npb_together(monkeypatch):
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    rows = [
        {"id": 11, "sport": "kbo", "home": "LG Twins", "away": "NC Dinos",
         "starts_at": now + timedelta(minutes=45), "league": "KBO"},
        {"id": 22, "sport": "npb", "home": "Hanshin Tigers", "away": "Yomiuri Giants",
         "starts_at": now + timedelta(minutes=15), "league": "NPB"},
    ]
    rds = _Redis()
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    async def fake_ensure(*_a, **_k):
        return True

    import json
    rds.store["analysis:kbo:2026-08-28"] = _analysis(11)
    rds.store["analysis:npb:2026-08-28"] = json.dumps({
        "games": [{
            "game_id": 22, "sport": "npb", "home": "Hanshin Tigers",
            "away": "Yomiuri Giants", "starts_at_kst": "08/28 18:00",
            "status": "scheduled", "league": "NPB", "p_claude": 0.58,
            "best_odds": {}, "expert_picks": [], "stats": {},
            "research": {}, "market_board": [],
        }],
        "news": "",
    })
    monkeypatch.setattr("app.engine.pregame_push.ensure_analysis_cache", fake_ensure)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await run_pregame_push(_Pool(rows), rds, now)
    assert out["sent"] == 2 and len(sent) == 2
    assert any("KBO" in t and "17:45 예측" in t for t in sent)
    assert any("NPB" in t and "17:45 예측" in t for t in sent)

    out2 = await run_pregame_push(_Pool(rows), rds, now)
    assert out2["sent"] == 0 and out2["skipped"] == 2
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_send_failure_releases_claim(monkeypatch):
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis()

    async def boom(text, **_k):
        return False

    async def fake_ensure(*_a, **_k):
        return True

    monkeypatch.setattr("app.engine.pregame_push.ensure_analysis_cache", fake_ensure)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", boom)

    out = await run_pregame_push(_Pool([row]), rds, now)
    assert out["failed"] == 1
    assert sent_key(11) not in rds.store


@pytest.mark.asyncio
async def test_missing_cache_sends_honest_once(monkeypatch):
    now, row = _row()
    rds = _Redis()
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    async def fake_ensure(*_a, **_k):
        return False

    monkeypatch.setattr("app.engine.pregame_push.ensure_analysis_cache", fake_ensure)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await run_pregame_push(_Pool([row]), rds, now)
    assert out["sent"] == 1
    assert "분석 캐시가 없어" in sent[0]
    assert sent_key(11) in rds.store


@pytest.mark.asyncio
async def test_unjudged_cache_does_not_send_empty_cards_for_later_games(monkeypatch):
    """ensure가 False면 같은 종목 다음 경기도 빈 승률 카드를 쓰지 않는다."""
    now, row1 = _row(11)
    _, row2 = _row(12)
    row2["home"] = "Doosan Bears"
    row2["away"] = "Kia Tigers"
    rds = _Redis({
        "analysis:kbo:2026-08-28": json.dumps({
            "games": [
                {"game_id": 11, "home": "LG Twins", "away": "NC Dinos",
                 "starts_at_kst": "08/28 18:30", "status": "scheduled"},
                {"game_id": 12, "home": "Doosan Bears", "away": "Kia Tigers",
                 "starts_at_kst": "08/28 18:30", "status": "scheduled"},
            ],
        }),
    })
    sent = []
    calls = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    async def fake_ensure(*_a, **_k):
        calls.append(1)
        return False

    monkeypatch.setattr("app.engine.pregame_push.ensure_analysis_cache", fake_ensure)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await run_pregame_push(_Pool([row1, row2]), rds, now)
    assert out["sent"] == 2
    assert len(calls) == 1
    assert all("분석 캐시가 없어" in t for t in sent)
    assert all("승률" not in t for t in sent)


@pytest.mark.asyncio
async def test_cancelled_crawler_game_is_not_sent(monkeypatch):
    """네이버 취소가 Redis에만 있어도 카드는 나가지 않고 DB를 cancelled로 맞춘다."""
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    row = {
        "id": 506, "sport": "kbo", "home": "Lotte Giants", "away": "LG Twins",
        "starts_at": now + timedelta(minutes=45), "league": "KBO",
    }
    rds = _Redis({
        "crawl:kbo:2026-08-28:latest": json.dumps({
            "LG Twins@Lotte Giants": {
                "status": "경기취소", "home_pitcher": "나균안",
            },
        }),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    async def fake_ensure(*_a, **_k):
        return True

    monkeypatch.setattr("app.engine.pregame_push.ensure_analysis_cache", fake_ensure)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    pool = _Pool([row])
    out = await run_pregame_push(pool, rds, now)
    assert out["sent"] == 0 and out["skipped"] == 1
    assert sent == []
    assert pool.executed
    assert sent_key(506) not in rds.store
