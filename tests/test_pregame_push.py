"""KBO·NPB 경기마다 1차 발송 · 변동 시 재발송. Judge는 호출하지 않는다."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.pregame_push import (
    HARD_TARGET_MIN,
    NPB_FINISH_MIN,
    SEND_OPEN_MIN,
    SPORTS,
    STAGE1_DEADLINE_MIN,
    analysis_open,
    card_sig_key,
    card_signature,
    compose_card,
    header_line,
    in_send_window,
    roster_signature,
    run_pregame_push,
    send_game_prediction,
    still_upcoming,
)


def test_only_kbo_npb():
    assert SPORTS == ("kbo", "npb")
    assert "mlb" not in SPORTS and "soccer" not in SPORTS


def test_deadlines_are_30_and_15():
    assert STAGE1_DEADLINE_MIN == 30
    assert HARD_TARGET_MIN == 15
    assert NPB_FINISH_MIN == 15
    assert SEND_OPEN_MIN == {"kbo": 70, "npb": 40}


def test_header_is_stage_not_clock():
    assert header_line("kbo") == "⏰ KBO · 1차"
    assert header_line("npb", revision=True) == "⏰ NPB · 변동"


def test_still_upcoming_skips_started():
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    assert still_upcoming(now + timedelta(minutes=15), now) is True   # NPB 18:00
    assert still_upcoming(now + timedelta(minutes=45), now) is True   # KBO 18:30
    assert still_upcoming(now, now) is False
    assert still_upcoming(now - timedelta(minutes=1), now) is False


def test_send_window_opens_at_1720():
    now = datetime(2026, 8, 28, 8, 20, tzinfo=UTC)  # KST 17:20
    kbo = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)  # 18:30, T-70
    npb = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)   # 18:00, T-40
    assert in_send_window("kbo", kbo, now) is True
    assert in_send_window("npb", npb, now) is True
    assert in_send_window("kbo", kbo, now - timedelta(minutes=1)) is False  # T-71
    assert in_send_window("npb", npb, now - timedelta(minutes=1)) is False  # T-41
    assert in_send_window("kbo", now - timedelta(minutes=1), now) is False


def test_npb_analysis_closes_at_1745_send_does_not():
    """18:00 NPB: 17:45에 크롤·분석 종료. 이미 판정된 카드는 시작 전까지 보낸다."""
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    npb = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)   # 18:00
    kbo = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)  # 18:30
    assert analysis_open("npb", npb, now) is False
    assert analysis_open("npb", npb, now - timedelta(minutes=1)) is True  # 17:44
    assert analysis_open("kbo", kbo, now) is True
    assert in_send_window("npb", npb, now) is True
    assert still_upcoming(npb, now) is True


def test_roster_signature_ignores_status_clock():
    a = roster_signature("Takahashi", "Takinaka", "A-B-C", "D-E-F")
    b = roster_signature("Takahashi", "Takinaka", "A-B-C", "D-E-F")
    c = roster_signature("Takahashi", "Takinaka", "A-B-X", "D-E-F")
    assert a == b
    assert a != c
    assert "confirmed" not in a and "predicted" not in a


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
    assert "1차" in text
    assert "17:45" not in text
    assert "LG" in text or "트윈스" in text or "NC" in text
    assert "변동" in compose_card(jg, "", "kbo", revision=True)


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


def _game(gid=11, sport="kbo", p=0.61, pitcher="임찬규", nine="김현수"):
    return {
        "game_id": gid, "sport": sport, "home": "LG Twins", "away": "NC Dinos",
        "starts_at_kst": "08/28 18:30", "status": "scheduled", "league": "KBO",
        "p_claude": p, "judge_confidence": "medium", "verdict": "홈 우세",
        "best_odds": {}, "expert_picks": [], "stats": {},
        "research": {
            "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
            "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            "home_pitcher": {"name": pitcher},
            "home_lineup": {"order": nine},
        },
        "today_nine": {
            "home": {"order": [{"slot": 1, "name": nine, "pos": "LF", "status": "usual"}]},
            "away": {"order": []},
        },
        "compare": {"favored": "home"},
        "scoring": {"level": "보통"},
        "market_board": [],
    }


def _analysis(gid=11, **kw):
    return json.dumps({"games": [_game(gid, **kw)], "news": ""})


def _block_claude(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("Claude 분석은 이 경로에서 호출되면 안 된다")

    async def boom_async(*_a, **_k):
        raise AssertionError("Claude 분석은 이 경로에서 호출되면 안 된다")

    monkeypatch.setattr("app.pipeline.ensure_analysis_cache", boom_async)
    monkeypatch.setattr("app.engine.judge.Judge.judge", boom_async)
    monkeypatch.setattr("app.pipeline.Judge.judge", boom_async)


@pytest.mark.asyncio
async def test_sends_kbo_and_npb_per_game(monkeypatch):
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

    rds.store["analysis:kbo:2026-08-28"] = _analysis(11)
    rds.store["analysis:npb:2026-08-28"] = json.dumps({
        "games": [{
            **_game(22, sport="npb", p=0.58, pitcher="村上", nine="佐藤"),
            "home": "Hanshin Tigers", "away": "Yomiuri Giants",
            "starts_at_kst": "08/28 18:00", "league": "NPB",
        }],
        "news": "",
    })
    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await run_pregame_push(_Pool(rows), rds, now)
    assert out["sent"] == 2 and len(sent) == 2
    assert any("KBO" in t and "1차" in t for t in sent)
    assert any("NPB" in t and "1차" in t for t in sent)

    out2 = await run_pregame_push(_Pool(rows), rds, now)
    assert out2["sent"] == 0 and out2["revised"] == 0
    assert out2["skipped"] == 2
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_lineup_change_resends_as_revision(monkeypatch):
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis(pitcher="임찬규", nine="김현수")
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    rds.store["analysis:kbo:2026-08-28"] = _analysis(pitcher="켈리", nine="오스틴")
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "revised"
    assert "변동" in sent[1]
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "skipped"
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_send_failure_does_not_mark_sent(monkeypatch):
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis()

    async def boom(text, **_k):
        return False

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", boom)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "failed"
    assert card_sig_key(11) not in rds.store


@pytest.mark.asyncio
async def test_missing_cache_does_not_send_empty_card(monkeypatch):
    now, row = _row()
    rds = _Redis()
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "skipped"
    assert sent == []
    assert card_sig_key(11) not in rds.store


@pytest.mark.asyncio
async def test_unjudged_cache_does_not_send(monkeypatch):
    now, row = _row()
    rds = _Redis({
        "analysis:kbo:2026-08-28": json.dumps({
            "games": [{
                "game_id": 11, "home": "LG Twins", "away": "NC Dinos",
                "starts_at_kst": "08/28 18:30", "status": "scheduled",
            }],
        }),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "skipped"
    assert sent == []


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
        "analysis:kbo:2026-08-28": _analysis(506),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    pool = _Pool([row])
    out = await run_pregame_push(pool, rds, now)
    assert out["sent"] == 0 and out["skipped"] == 1
    assert sent == []
    assert pool.executed
    assert card_sig_key(506) not in rds.store


def test_card_signature_moves_when_nine_changes():
    a = _game(nine="김현수")
    b = _game(nine="오스틴")
    assert card_signature(a) != card_signature(b)
    assert card_signature(a) == card_signature(_game(nine="김현수"))
