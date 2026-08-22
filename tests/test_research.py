"""딥서치 모듈 목 모드 검증 + 실키 통합 테스트(skip 마커)."""

import os

import pytest

from app.collectors.mlb import MLBClient, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds
from app.research.grok import GrokClient
from app.research.normalize import normalize_pick
from app.research.perplexity import (
    PerplexityClient,
    extract_json_array,
    fetch_expert_picks,
    save_expert_picks,
)

DATE = "2026-08-22"
HOME, AWAY = "New York Yankees", "Athletics"


def test_normalize_pick_formats():
    assert normalize_pick("Yankees ML", HOME, AWAY) == "h2h:New York Yankees"
    assert normalize_pick("Over 8.5", HOME, AWAY) == "totals:Over:8.5"
    assert normalize_pick("under 9", HOME, AWAY) == "totals:Under:9"
    assert normalize_pick("Athletics +1.5", HOME, AWAY) == "spreads:Athletics:+1.5"
    assert normalize_pick("Yankees -1.5", HOME, AWAY) == "spreads:New York Yankees:-1.5"
    assert normalize_pick("Dodgers ML", HOME, AWAY) is None  # 경기 무관 팀


def test_extract_json_array_variants():
    assert extract_json_array('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert extract_json_array('picks: [{"a": 1}] done') == [{"a": 1}]
    with pytest.raises(ValueError):
        extract_json_array("no json here")


async def test_perplexity_mock_returns_structured_picks():
    picks, citations = await fetch_expert_picks(
        [{"home": HOME, "away": AWAY}], DATE, client=PerplexityClient(mock=True)
    )
    assert len(picks) == 6
    for p in picks:
        assert {"expert", "site", "source_url", "game", "pick", "reasoning", "record"} <= set(p)
    assert citations and all(c.startswith("http") for c in citations)


async def test_perplexity_retries_once_on_bad_json(monkeypatch):
    client = PerplexityClient(mock=True)
    calls = {"n": 0}
    good = client.load_mock("perplexity_picks.json")

    async def fake_chat(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"choices": [{"message": {"content": "sorry, no data"}}]}
        return good

    monkeypatch.setattr(client, "chat", fake_chat)
    picks, _ = await fetch_expert_picks([{"home": HOME, "away": AWAY}], DATE, client=client)
    assert calls["n"] == 2 and len(picks) == 6


async def test_save_expert_picks_normalized_with_odds(db_pool):
    await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    await snapshot_odds(db_pool, "mlb", client=OddsClient(mock=True))
    picks, _ = await fetch_expert_picks([], DATE, client=PerplexityClient(mock=True))
    saved = await save_expert_picks(db_pool, picks)
    assert saved == 6
    rows = await db_pool.fetch("SELECT * FROM expert_picks")
    assert all(r["pick"].split(":")[0] in ("h2h", "spreads", "totals") for r in rows)
    # h2h 픽은 API 배당이 붙어야 한다 (LLM 수치가 아니라 odds_snapshots에서)
    h2h = [r for r in rows if r["pick"].startswith("h2h:")]
    assert h2h and all(r["odds"] is not None for r in h2h)


async def test_grok_mock_briefing():
    text = await GrokClient(mock=True).live_briefing([], DATE)
    assert "LINE MOVE" in text and "INJURY" in text


@pytest.mark.skipif(not os.getenv("PPLX_API_KEY"), reason="PPLX_API_KEY 필요 (실키 통합)")
async def test_perplexity_live_integration():
    picks, _ = await fetch_expert_picks(
        [{"home": HOME, "away": AWAY}], DATE, client=PerplexityClient(mock=False)
    )
    assert isinstance(picks, list)


@pytest.mark.skipif(not os.getenv("XAI_API_KEY"), reason="XAI_API_KEY 필요 (실키 통합)")
async def test_grok_live_integration():
    text = await GrokClient(mock=False).live_briefing(
        [{"home": HOME, "away": AWAY}], DATE
    )
    assert isinstance(text, str) and text
