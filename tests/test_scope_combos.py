"""리그 범위 라우팅 · 등급제 조합 · 확률 단일화 · 한국어/출처 규율 테스트."""

import pytest

import app.bot.main as botmod
from app.engine.parlay import build_tiered_parlays
from app.leagues import LEAGUES, find_league, find_unsupported_league
from app.pipeline import clean_invisible, contains_english_sentence, render_sources


def test_league_registry_and_aliases():
    assert set(LEAGUES) == {"epl", "la_liga", "serie_a", "bundesliga", "j1", "denmark", "kleague1"}
    assert LEAGUES["kleague1"]["odds_key"] == "soccer_korea_kleague1"
    assert find_league("분데스리가 오늘 분석해줘") == "bundesliga"
    assert find_league("라리가 어때") == "la_liga"
    assert find_league("K리그 순위") == "kleague1"
    assert find_unsupported_league("세리에B 분석") == "세리에b"   # 세리에A 오매칭 방지
    assert find_unsupported_league("리그앙 어때") is not None


def test_route_query_three_level_scope():
    """[5] 범위 유형 고정: 리그→리그만, 팀→1경기, 전체, 미지원 안내."""
    assert botmod.route_query("분데스리가 오늘 분석해줘") == ("league", "bundesliga")
    assert botmod.route_query("유벤투스 어때")[0] == "team"
    assert botmod.route_query("유벤투스 어때")[1] == ("soccer", "Juventus")
    assert botmod.route_query("레알 마드리드 경기 어때")[1] == ("soccer", "Real Madrid")
    assert botmod.route_query("오늘 축구")[0] == "full"
    assert botmod.route_query("세리에B 분석")[0] == "league_unsupported"
    assert botmod.route_query("오늘 추천 픽 줘")[0] == "picks"


def _leg(gid, desc, odds, p, conf="high", league="EPL", kst="08/23 22:00"):
    return {"game_id": gid, "side": desc.replace(" 승", ""), "desc": desc,
            "odds": odds, "p": p, "confidence": conf,
            "league": league, "starts_at_kst": kst}


def test_tiered_parlays_ranges_and_reuse():
    singles = [
        _leg(1, "A 승", 1.5, 0.62), _leg(2, "B 승", 1.7, 0.58),
        _leg(3, "C 승", 2.0, 0.52), _leg(4, "D 승", 2.4, 0.45, conf="medium"),
        _leg(5, "E 승", 3.2, 0.34, conf="medium"),
    ]
    low_var = [
        _leg(6, "F +1.5", 1.35, 0.72), _leg(7, "언더 8.5", 1.55, 0.63),
    ]
    result = build_tiered_parlays(singles, low_var, flat_stake_krw=10_000)
    combos = result["combos"]
    assert len(combos) == 3
    tiers = [c["tier"] for c in combos]
    assert tiers[0].startswith("안정형") and tiers[1].startswith("균형형")
    assert "고위험 로또형" in tiers[2]
    # 안정형: 저분산 2폴더, 배당 1.8~2.5 (완화 없이 성립: 1.35*1.55=2.09)
    c1 = combos[0]
    assert c1["ok"] and 1.8 <= c1["odds"] <= 2.5 and not c1["relaxed"]
    assert c1["stake_note"].startswith("권장 10,000원")
    # 균형형 3~6, 고배당형 8~20 또는 최근접 완화 표시
    for c, lo, hi in ((combos[1], 3.0, 6.0), (combos[2], 8.0, 20.0)):
        if c["ok"] and not c.get("relaxed"):
            assert lo <= c["odds"] <= hi
    # (a) 동일 레그는 최대 2개 조합
    from collections import Counter

    usage = Counter(
        f"{leg['game_id']}:{leg['desc']}" for c in combos if c.get("ok") for leg in c["legs"])
    assert all(v <= 2 for v in usage.values())
    # (b) 실패 확률 표기
    assert result["all_fail_prob"] is not None and 0 <= result["all_fail_prob"] <= 1


def test_tiered_parlays_insufficient_legs():
    result = build_tiered_parlays([_leg(1, "A 승", 1.5, 0.6)], [], None)
    assert result["combos"] == []
    assert "성립 불가" in result["reason"]


async def test_flagged_pick_never_recommended_regression(db_pool, redis_client, monkeypatch):
    """[E] 회귀: 플래그(+20% EV) 픽은 카드 추천·조합·predictions 어디에도 없다."""
    from app.pipeline import run_pipeline

    card = await run_pipeline(db_pool, redis_client, sport="mlb", date="2026-08-22")
    import json as _json

    analysis = _json.loads(await redis_client.get("analysis:mlb:2026-08-22"))
    flagged = [p for p in analysis["picks"] if p["flags"]]
    assert flagged, "목 데이터에 플래그 픽이 있어야 회귀 테스트 성립"
    for p in flagged:
        assert not p["recommended"]
        # 카드·심층이 같은 p_final/EV 숫자를 인용 (자기모순 금지)
        jg = next(g for g in analysis["games"] if g["game_id"] == p["game_id"])
        assert jg["pick_summary"]["ev"] == p["ev"]
        assert jg["pick_summary"]["p_final"] == p["p"]
        # 조합 레그에도 없다
        for c in (analysis.get("combos") or {}).get("combos", []):
            for leg in c.get("legs", []):
                assert leg["game_id"] != p["game_id"] or leg.get("side") != p["side"]
    bad = await db_pool.fetchval("SELECT count(*) FROM predictions WHERE ev > 0.20")
    assert bad == 0


def test_korean_and_invisible_utils():
    assert contains_english_sentence("Covers lists this as their primary prediction today")
    assert not contains_english_sentence("마치다 젤비아가 홈에서 우세하다 (ERA 2.93)")
    assert not contains_english_sentence("확정 라인업: S. Kwan, J. Ramírez 선발")
    dirty = "https://a.com/x￼​https://b.com/y"
    assert clean_invisible(dirty) == "https://a.com/xhttps://b.com/y"


def test_render_sources_one_per_line_plain():
    analysis = {"sources": [
        {"site": "SBR￼", "url": "https://sbr.com/a​"},
        {"site": "Dimers", "url": "https://dimers.com/b"},
    ]}
    out = render_sources(analysis)
    lines = out.splitlines()
    assert lines == ["- SBR: https://sbr.com/a", "- Dimers: https://dimers.com/b"]
    assert "￼" not in out and "​" not in out


def test_kr_team_dictionary():
    from app.bot.aliases import kr_team

    assert kr_team("FC Machida Zelvia") == "마치다 젤비아"
    assert kr_team("Real Madrid") == "레알 마드리드"
    assert kr_team("Bayern Munich") == "바이에른 뮌헨"
    assert kr_team("Ulsan HD FC") == "울산 HD"
    assert kr_team("Brentford FC") == "브렌트포드"          # 퍼지 (fd 표기)
    assert kr_team("Unknown Wanderers XY") == "Unknown Wanderers XY"  # 미등재 → 원문
