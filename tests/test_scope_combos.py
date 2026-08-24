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


def _leg(gid, desc, odds, p, conf="high", league="EPL", kst="08/23 22:00", market="h2h"):
    return {"game_id": gid, "side": desc.replace(" 승", ""), "desc": desc,
            "odds": odds, "p": p, "confidence": conf, "market": market,
            "league": league, "starts_at_kst": kst}


def test_tiered_parlays_ranges_and_reuse():
    legs = [
        _leg(1, "A 승", 1.5, 0.62), _leg(2, "B 승", 1.7, 0.58),
        _leg(3, "C 승", 2.0, 0.52), _leg(4, "D 승", 2.4, 0.45, conf="medium"),
        _leg(5, "E 승", 3.2, 0.34, conf="medium"),
        _leg(6, "F 핸디 +1.5", 1.35, 0.72, market="spreads"),
        _leg(7, "언더 8.5", 1.55, 0.63, market="totals"),
    ]
    result = build_tiered_parlays(legs, flat_stake_krw=10_000)
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
    """[9] 성립 불가는 전 마켓 검토 후에만 — 사유에 검토 범위 명시."""
    result = build_tiered_parlays([_leg(1, "A 승", 1.5, 0.6)], None)
    assert result["combos"] == []
    assert "성립 불가" in result["reason"]
    assert "전 마켓 검토" in result["reason"]        # 어떤 마켓까지 봤는지 명시


def test_tiered_parlays_blocks_correlated_same_game_legs():
    """[9] 같은 경기 상관 마켓 2개(홈승+홈-1.5)는 한 조합에 못 들어간다."""
    legs = [
        _leg(1, "A 승", 1.9, 0.62),
        _leg(1, "A 핸디 -1.5", 3.1, 0.61, market="spreads"),  # 같은 경기 상관 레그
        _leg(2, "B 더블찬스(승/무)", 1.30, 0.75, market="dc"),
    ]
    result = build_tiered_parlays(legs, None)
    for c in result["combos"]:
        if not c.get("ok"):
            continue
        games = [leg["game_id"] for leg in c["legs"]]
        assert len(games) == len(set(games)), "같은 경기 레그 2개가 조합에 포함됨"


def test_tiered_parlays_forms_from_non_h2h_only():
    """[9] 회귀: 승패 픽이 없어도 더블찬스·토탈 레그만으로 조합 1이 성립한다.

    (어제 슬레이트 소급: 마치다 언더 2.5 + 마치다 더블찬스 + AGF 더블찬스 시나리오)"""
    legs = [
        _leg(101, "마치다 더블찬스(승/무)", 1.36, 0.80, market="dc", league="J1 리그"),
        _leg(102, "AGF 오르후스 더블찬스(승/무)", 1.44, 0.78, market="dc", league="덴마크 수페르리가"),
        _leg(101, "언더 2.5", 1.70, 0.63, market="totals", league="J1 리그"),
        _leg(103, "언더 3.5", 1.30, 0.74, market="totals", league="EPL"),
    ]
    result = build_tiered_parlays(legs, flat_stake_krw=10_000)
    c1 = result["combos"][0]
    assert c1["tier"] == "안정형" and c1["ok"], "저분산 레그만으로 안정형이 성립해야 한다"
    assert 1.8 <= c1["odds"] <= 2.5 or c1.get("relaxed")
    games = [leg["game_id"] for leg in c1["legs"]]
    assert len(games) == len(set(games))


async def test_flagged_pick_never_recommended_regression(db_pool, redis_client, monkeypatch):
    """[E] 회귀: 플래그·괴리 미검증·2-소스 미달 후보는 추천·조합·predictions에 없다."""
    from app.pipeline import run_pipeline

    await run_pipeline(db_pool, redis_client, sport="mlb", date="2026-08-22")
    import json as _json

    analysis = _json.loads(await redis_client.get("analysis:mlb:2026-08-22"))
    rejected = [
        (g, c) for g in analysis["games"]
        for c in g.get("market_board") or [] if not c.get("approved")
    ]
    assert rejected, "목 데이터에 미승인 후보가 있어야 회귀 테스트 성립"
    # [2] 괴리 미검증 라벨과 [1] 2-소스 미달 사유가 실제로 발생한다
    reasons = " | ".join(str(c.get("reject_reason")) for _, c in rejected)
    assert "시장이 아는 정보가 있을 가능성" in reasons
    assert "2-소스 미달" in reasons
    reco_keys = {(p["game_id"], p["pick"]) for p in analysis["picks"] if p.get("recommended")}
    combo_keys = {
        (leg["game_id"], leg["desc"])
        for c in (analysis.get("combos") or {}).get("combos", [])
        for leg in c.get("legs", [])
    }
    for g, c in rejected:
        pick_key = f"{c['market']}:{c['side']}" + (
            f":{c['line']:g}" if c.get("line") is not None else "")
        assert (g["game_id"], pick_key) not in reco_keys   # 추천에 없다
        assert (g["game_id"], c["desc"]) not in combo_keys  # 조합 레그에도 없다
    # 카드·심층이 같은 숫자를 인용 (자기모순 금지): 대표 픽과 pick_summary 일치
    for rep in analysis["picks"]:
        jg = next(g for g in analysis["games"] if g["game_id"] == rep["game_id"])
        assert jg["pick_summary"]["ev"] == rep["ev"]
        assert jg["pick_summary"]["p_final"] == rep["p"]
    bad = await db_pool.fetchval("SELECT count(*) FROM predictions WHERE ev > 0.20")
    assert bad == 0


def test_ev_flag_still_fires_on_pathological_odds():
    """플래그 가드 유닛 회귀: 수축 후에도 EV +20% 초과 후보는 플래그·미승인."""
    from app.engine.markets import build_candidates

    jg = {
        "game_id": 1, "home": "A", "away": "B", "league": "MLB",
        "status": "scheduled", "model_valid": True, "p_model": 0.62, "p_model3": None,
        "p_market": 0.60, "market_probs": {"A": 0.60, "B": 0.40},
        "best_odds": {"A": 2.30, "B": 1.60},   # 병리적 배당: p 0.6 × 2.3 → EV +38%
        "stats": {"home_win_pct": 0.6, "away_win_pct": 0.45,
                  "home_pitcher_era": 3.0, "away_pitcher_era": 4.5},
        "expert_picks": [{"pick": "h2h:A"}], "judge_confidence": "high",
    }
    cands = build_candidates(jg, "mlb", {"A": 0.60, "B": 0.40})
    home = next(c for c in cands if c["market"] == "h2h" and c["side"] == "A")
    assert home["ev"] > 0.20 and home["flags"] and not home["approved"]


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


# ---------------------------------------------------------------- 적중 품질 패치 (2-소스·괴리·수축)

def _soccer_jg(**over):
    jg = {
        "game_id": 50, "home": "Home FC", "away": "Away FC",
        "league": "덴마크 수페르리가", "status": "scheduled",
        "model_valid": True, "p_model": 0.55, "p_model3": [0.55, 0.25, 0.20],
        "p_market": 0.52, "market_probs": {"Home FC": 0.52, "Draw": 0.25, "Away FC": 0.23},
        "best_odds": {"Home FC": 1.85, "Draw": 3.80, "Away FC": 4.20},
        "stats": {}, "expert_picks": [], "judge_confidence": "medium",
        "research": {  # [2] 심층 분석은 재료가 있을 때만 생성된다
            "home_recent_form": {"form": "WWDLW", "gf5": 9, "ga5": 4, "rank": 3},
            "away_recent_form": {"form": "LDLWL", "gf5": 4, "ga5": 9, "rank": 11},
            "absences": ["Away FC의 John Smith 햄스트링 결장"],
        },
    }
    jg.update(over)
    return jg


def test_two_source_rule_model_only_rejected():
    """[1] 회귀: 빌라·AGF형(모델 단독 지지) 픽은 어떤 EV라도 추천 금지."""
    from app.engine.markets import build_candidates

    # 모델만 원정 우세(0.55), 시장은 홈 우세, 실데이터·전문가 없음 → 원정 픽은 모델 단독
    jg = _soccer_jg(
        p_model=0.25, p_model3=[0.25, 0.20, 0.55], p_market=0.52,
        best_odds={"Home FC": 1.85, "Draw": 3.80, "Away FC": 3.20},
        judge_confidence="high",
    )
    cands = build_candidates(jg, "soccer", {"Home FC": 0.48, "Away FC": 0.32})
    away = next(c for c in cands if c["market"] == "h2h" and c["side"] == "Away FC")
    assert not away["approved"]
    assert "2-소스 미달" in away["reject_reason"] or "시장이 아는" in away["reject_reason"]


def test_two_source_rule_machida_style_passes():
    """[1] 회귀: 마치다형(실데이터+전문가+시장 동방향) 픽은 통과한다."""
    from app.engine.markets import build_candidates

    jg = _soccer_jg(
        league="J1 리그", judge_confidence="high",
        p_model=0.55, p_market=0.55,
        market_probs={"Home FC": 0.55, "Draw": 0.25, "Away FC": 0.20},
        stats={"home_season": {"form": "WWWDW", "position": 2, "points": 50,
                               "played": 25, "gf": 40, "ga": 18},
               "away_season": {"form": "LLDLW", "position": 15, "points": 20,
                               "played": 25, "gf": 22, "ga": 35}},
        expert_picks=[{"pick": "h2h:Home FC"}],
    )
    cands = build_candidates(jg, "soccer", {"Home FC": 0.58, "Away FC": 0.18})
    home = next(c for c in cands if c["market"] == "h2h" and c["side"] == "Home FC")
    assert home["approved"], home["reject_reason"]
    assert home["axes"]["data"] and home["axes"]["expert"] and home["axes"]["market"]


def test_gap_unverified_label():
    """[2] 모델-시장 괴리 ≥10%p + 전문가 미지지 → '시장이 아는 정보' 라벨 제외."""
    from app.engine.markets import build_candidates

    jg = _soccer_jg(
        judge_confidence="high", p_model=0.68, p_model3=[0.68, 0.20, 0.12], p_market=0.52,
        stats={"home_season": {"form": "WWWWW", "position": 1, "points": 60,
                               "played": 25, "gf": 50, "ga": 10},
               "away_season": {"form": "LLLLL", "position": 18, "points": 10,
                               "played": 25, "gf": 15, "ga": 45}},
    )
    cands = build_candidates(jg, "soccer", {"Home FC": 0.60, "Away FC": 0.18})
    home = next(c for c in cands if c["market"] == "h2h" and c["side"] == "Home FC")
    assert not home["approved"]
    assert "시장이 아는 정보가 있을 가능성" in home["reject_reason"]


def test_soccer_h2h_requires_high_confidence():
    """[3] 축구 승패 단식은 신뢰도 high에서만 — medium이면 더블찬스는 살고 승패는 제외."""
    from app.engine.markets import build_candidates

    jg = _soccer_jg(
        judge_confidence="medium", p_model=0.55, p_market=0.55,
        market_probs={"Home FC": 0.55, "Draw": 0.25, "Away FC": 0.20},
        stats={"home_season": {"form": "WWWDW", "position": 3, "points": 45,
                               "played": 25, "gf": 38, "ga": 20},
               "away_season": {"form": "DLLWL", "position": 12, "points": 25,
                               "played": 25, "gf": 25, "ga": 33}},
        expert_picks=[{"pick": "h2h:Home FC"}],
    )
    cands = build_candidates(jg, "soccer", {"Home FC": 0.58, "Away FC": 0.18})
    h2h = next(c for c in cands if c["market"] == "h2h" and c["side"] == "Home FC")
    dc = next(c for c in cands if c["market"] == "dc" and c["side"] == "Home FC")
    assert not h2h["approved"] and "저분산 우선" in h2h["reject_reason"]
    assert dc["approved"], dc["reject_reason"]


def test_synth_dc_odds():
    """[3] 더블찬스 배당 미수집 시 3-way h2h 합성: 1/o_dc = 1/o1 + 1/oX."""
    from app.engine.markets import synth_dc_odds

    assert synth_dc_odds(2.0, 4.0) == 1.33
    assert abs(1 / synth_dc_odds(1.85, 3.8) - (1 / 1.85 + 1 / 3.8)) < 0.01


def test_data_zero_downgrades_confidence():
    """[4d] 올 시즌 실데이터 0건 경기는 신뢰도 자동 '낮음' + 추천 자격 박탈."""
    from app.pipeline import _enforce_data_rules

    jg = _soccer_jg(p_claude=0.55, verdict="테스트", judge_confidence="high")
    _enforce_data_rules([jg])
    assert jg["judge_confidence"] == "low" and jg.get("data_zero")
    assert "자동 강등" in jg["verdict"]

    jg2 = _soccer_jg(
        p_claude=0.55, verdict="테스트", judge_confidence="high",
        stats={"home_season": {"form": "WWDLW", "position": 5, "points": 40,
                               "played": 24, "gf": 30, "ga": 20},
               "away_season": {"form": "LDWLL", "position": 10, "points": 28,
                               "played": 24, "gf": 24, "ga": 30}},
    )
    _enforce_data_rules([jg2])
    assert jg2["judge_confidence"] == "high"     # 실데이터 있으면 유지


def test_shrinkage_lambda():
    """[5] p_final = λ*p_market + (1-λ)*p_ensemble — 성숙 리그 0.3, 빈약 리그 0.6."""
    from app.engine.markets import shrink, shrink_lambda

    assert shrink_lambda("MLB") == 0.3 and shrink_lambda("EPL") == 0.3
    assert shrink_lambda("덴마크 수페르리가") == 0.6 and shrink_lambda("J1 리그") == 0.6
    assert abs(shrink(0.70, 0.50, "EPL") - (0.3 * 0.5 + 0.7 * 0.7)) < 1e-9
    assert abs(shrink(0.70, 0.50, "덴마크 수페르리가") - (0.6 * 0.5 + 0.4 * 0.7)) < 1e-9
    assert shrink(0.70, None, "EPL") == 0.70     # 시장 없으면 수축 불가


def test_market_board_rendered_in_deep_section():
    """[8] 심층 상세에 '⑧ 마켓 보드'가 마켓별 판정과 함께 표기된다."""
    from app.pipeline import render_game_section

    jg = _soccer_jg(
        p_claude=0.55, verdict="테스트 판정", starts_at_kst="08/24 20:00",
        status_label="",
        pick_summary={"side": "Home FC", "desc": "언더 2.5", "market": "totals",
                      "odds": 1.85, "p_final": 0.62, "ev": 0.09, "flags": [],
                      "approved": True, "reject_reason": None, "axes": "전문가+시장"},
        market_board=[
            {"market": "totals", "side": "Under", "line": 2.5, "desc": "언더 2.5",
             "odds": 1.85, "p": 0.62, "ev": 0.09, "basis": "시장+전문가",
             "axes_kr": "전문가+시장", "approved": True, "reject_reason": None},
            {"market": "h2h", "side": "Home FC", "line": None, "desc": "Home FC 승",
             "odds": 1.85, "p": 0.52, "ev": -0.04, "basis": "앙상블",
             "axes_kr": "시장", "approved": False,
             "reject_reason": "근거 부족 — 2-소스 미달 (시장 단독)"},
        ],
    )
    out = render_game_section(jg)
    assert "⑧ 마켓 보드:" in out
    assert "언더 2.5 @1.85 (✅추천후보" in out
    assert "제외 — 근거 부족" in out


def test_easy_layer_recommends_best_market():
    """[8] 기본층 '걸 만한가?'는 전 마켓 중 최적 하나 — 승패 아닐 땐 대체 화법."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    jg = _soccer_jg(
        p_claude=0.55, verdict="테스트", starts_at_kst="08/24 20:00", status_label="",
        judge_confidence="high",
        pick_summary={"side": "Under", "desc": "언더 2.5", "market": "totals",
                      "odds": 1.85, "p_final": 0.62, "ev": 0.09, "flags": [],
                      "approved": True, "reject_reason": None, "axes": "전문가+시장"},
    )
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "승패보다는 언더 2.5" in easy and "걸 만한 자리" in easy
