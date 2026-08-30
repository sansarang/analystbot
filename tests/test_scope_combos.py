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
    result = build_tiered_parlays(legs, flat_stake_krw=None)
    combos = result["combos"]
    assert len(combos) == 3
    tiers = [c["tier"] for c in combos]
    assert tiers[0].startswith("안정형") and tiers[1].startswith("균형형")
    assert "고위험 로또형" in tiers[2]
    # 안정형: 저분산 2폴더, 배당 1.8~2.5 (완화 없이 성립: 1.35*1.55=2.09)
    c1 = combos[0]
    assert c1["ok"] and 1.8 <= c1["odds"] <= 2.5 and not c1["relaxed"]
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


def test_tiered_parlays_none_odds_does_not_crash():
    """KBO·NPB는 Odds API를 안 쓴다. 배당 None 레그가 조합에서 파이프라인을 죽이면 안 된다."""
    legs = [
        _leg(1, "A 승", None, 0.62),
        _leg(2, "B 승", None, 0.61),
        _leg(3, "C 승", 1.70, 0.60),
    ]
    result = build_tiered_parlays(legs, None, sport="npb")
    assert result["combos"] == []
    assert "성립 불가" in result["reason"]


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
    result = build_tiered_parlays(legs, flat_stake_krw=None)
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
    # [6] 2-소스 미달·기준 미달은 보드에서 지우지 않고 🔴/🟡로 남긴다.
    #     추천·조합·predictions에서만 빠져야 한다.
    from app.pipeline import qualifies

    rejected = [
        (g, c) for g in analysis["games"]
        for c in g.get("market_board") or []
        if not c.get("approved") or not qualifies(c)
    ]
    assert rejected, "목 데이터에 제외 대상 후보가 있어야 회귀 테스트 성립"
    reasons = " | ".join(
        f"{c.get('reject_reason')} {c.get('grade_note')}" for _, c in rejected)
    # 사유는 실제 사유여야 한다 — 하한 미달 / 근거 축 부족 / 배당 미수집
    assert any(k in reasons for k in ("하한", "근거", "확률 미산출"))
    # [1-2 폐기] 괴리 검증 룰 문구는 더 이상 나오지 않는다
    assert "시장이 아는 정보가 있을 가능성" not in reasons
    reco_keys = {(p["game_id"], p["pick"]) for p in analysis["picks"] if p.get("recommended")}
    combo_keys = {
        (leg["game_id"], leg["desc"])
        for c in (analysis.get("combos") or {}).get("combos", [])
        for leg in c.get("legs", [])
    }
    for g, c in rejected:
        pick_key = f"{c['market']}:{c['side']}" + (
            f":{c['line']:g}" if c.get("line") is not None else "")
        assert (g["game_id"], pick_key) not in reco_keys, (
            f"제외 대상이 추천에 있다: {c['desc']} p={c.get('p')} odds={c.get('odds')} "
            f"grade={c.get('grade')} two_source={c.get('two_source')} "
            f"edge={c.get('edge')} need={c.get('required_prob')}")
        assert (g["game_id"], c["desc"]) not in combo_keys  # 조합 레그에도 없다
    # 카드·심층이 같은 숫자를 인용 (자기모순 금지): 대표 픽과 pick_summary 일치
    for rep in analysis["picks"]:
        jg = next(g for g in analysis["games"] if g["game_id"] == rep["game_id"])
        assert jg["pick_summary"]["ev"] == rep["ev"]
        assert jg["pick_summary"]["p_final"] == rep["p"]
    # [§8-18] predictions에 들어간 픽은 **승률 하한**만 넘으면 된다 (배당 하한 제거)
    from app.config import get_settings

    s = get_settings()
    bad = await db_pool.fetchval(
        "SELECT count(*) FROM predictions "
        "WHERE method = 'performance' AND model_p < $1",
        s.min_win_prob)
    assert bad == 0


def test_ev_flag_removed_but_prob_gap_flag_remains():
    """[3] EV 기반 플래그는 제거됐다 — 승률-배당환산 괴리만 데이터 검증으로 남는다."""
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
    # [3] EV 기반 이상치 플래그 제거 — 승률-배당환산 괴리만 데이터 검증으로 남는다
    assert home["ev"] > 0.20 and not home["flags"]


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
    if "market_board" in jg:
        _graded(jg["market_board"])
    return jg

def _graded(board: list[dict]) -> list[dict]:
    """[A-1] 마켓 보드에 등급을 채워 반환 (신호등이 마켓 단위가 됐다)."""
    from app.engine.markets import grade_candidate

    for c in board:
        c.setdefault("axes_kr", "시장")
        c["grade"], c["grade_note"] = grade_candidate(c)
    return board



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
    # [4] 시장 축은 판정 철학 교체로 제거됐다
    assert home["axes"]["data"] and home["axes"]["expert"]
    assert "market" not in home["axes"]


def test_gap_verification_rule_is_retired():
    """[1-2 폐기] 모델-시장 괴리 검증은 시장 배제 전환으로 삭제됐다.

    시장 확률을 기준점으로 쓰는 규칙이라 시장을 판정에서 빼면 성립하지 않는다.
    남는 위험(시장이 아는 정보를 우리가 못 봄)은 경기력 정보 수집으로 대체 방어한다.
    """
    from app.engine.markets import build_candidates

    jg = _soccer_jg(
        p_model=0.75, p_model3=[0.75, 0.15, 0.10], p_market=0.52,
        judge_confidence="high",
        stats={"home_season": {"form": "WWWWW", "position": 1, "points": 60,
                               "played": 25, "gf": 50, "ga": 12},
               "away_season": {"form": "LLLLL", "position": 18, "points": 12,
                               "played": 25, "gf": 15, "ga": 45}},
        expert_picks=[{"pick": "h2h:Home FC"}],
    )
    cands = build_candidates(jg, "soccer", {"Home FC": 0.70, "Away FC": 0.15})
    home = next(c for c in cands if c["market"] == "h2h" and c["side"] == "Home FC")
    reasons = str(home.get("reject_reason") or "")
    assert "시장이 아는 정보" not in reasons
    assert "market" not in home["axes"]


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
                      "odds": 1.68, "p_final": 0.62, "ev": 0.042, "flags": [],
                      "approved": True, "reject_reason": None, "axes": "전문가+시장"},
        market_board=[
            {"market": "totals", "side": "Under", "line": 2.5, "desc": "언더 2.5",
             "odds": 1.68, "p": 0.62, "ev": 0.042, "basis": "시장+전문가",
             "axes_kr": "전문가+시장", "approved": True, "reject_reason": None},
            {"market": "h2h", "side": "Home FC", "line": None, "desc": "Home FC 승",
             "odds": 1.85, "p": 0.52, "ev": -0.04, "basis": "앙상블",
             "axes_kr": "시장", "approved": False,
             "reject_reason": "근거 부족 — 2-소스 미달 (시장 단독)"},
        ],
    )
    out = render_game_section(jg)
    assert "⑧ 마켓 보드" in out
    # [3-3] 마켓 | 배당 | 승률 | 1만원 수익 | 신호등 | 근거 | ★
    assert "언더 2.5 | 62% | 🟢" in out
    assert "Home FC 승 | 52% | 🔴" in out and "근거 부족" in out


def test_easy_layer_recommends_best_market():
    """[8] 기본층 '걸 만한가?'는 전 마켓 중 최적 하나 — 승패 아닐 땐 대체 화법."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    jg = _soccer_jg(
        p_claude=0.55, verdict="테스트", starts_at_kst="08/24 20:00", status_label="",
        judge_confidence="high",
        pick_summary={"side": "Under", "desc": "언더 2.5", "market": "totals",
                      "odds": 1.68, "p_final": 0.62, "ev": 0.042, "flags": [],
                      "approved": True, "reject_reason": None, "axes": "전문가+시장"},
        market_board=[
            {"market": "totals", "side": "Under", "line": 2.5, "desc": "언더 2.5",
             "odds": 1.68, "p": 0.62, "ev": 0.042, "axes_kr": "전문가+시장",
             "approved": True, "reject_reason": None},
            {"market": "h2h", "side": "Home FC", "line": None, "desc": "Home FC 승",
             "odds": 1.85, "p": 0.52, "ev": -0.04, "axes_kr": "시장",
             "approved": False, "reject_reason": "근거 부족 — 2-소스 미달"},
        ],
    )
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "언더 2.5" in easy and "걸 만합니다" in easy


# --- 단식 후보 풀 = 조합과 같은 마켓 보드 (2026-08-26 실사고) ---

def _game_with_board():
    return {
        "game_id": 1, "home": "Washington Nationals", "away": "Colorado Rockies",
        "league": "MLB", "starts_at_kst": "08/26 07:45", "status": "scheduled",
        "judge_confidence": "high",
        "market_board": [
            # 자격 통과 — 그러나 EV는 낮아 대표 픽이 되지 못한다
            {"market": "h2h", "side": "Washington Nationals", "desc": "워싱턴 내셔널스 승",
             "p": 0.621, "odds": 1.70, "ev": 0.056, "approved": True,
             "two_source": True, "axes_kr": "실데이터+전문가+모델"},
            # [§8-18] 시장 괴리 탈락은 사라졌다 — 살아있는 규율(2-소스)로 바꾼다.
            #   확률·EV는 높지만 근거가 1축뿐이라 추천 자격이 없다.
            {"market": "spreads", "side": "Colorado Rockies", "line": 1.5,
             "desc": "콜로라도 로키스 런라인 +1.5",
             "p": 0.634, "odds": 1.95, "ev": 0.236, "approved": True,
             "two_source": False, "axes_kr": "모델"},
        ],
    }


def test_single_pool_uses_full_market_board():
    """★ 실사고: 단식을 경기당 대표 픽 1건에서만 뽑아 자격 있는 마켓이 빠졌다.

    같은 시스템이 '단식 없음'이라 하면서 그 베팅을 조합 레그로 추천했다.
    """
    from app.config import get_settings
    from app.pipeline import qualified_singles

    out = qualified_singles([_game_with_board()], get_settings())
    assert len(out) == 1
    assert out[0]["desc"] == "워싱턴 내셔널스 승", "자격 통과 마켓이 뽑혀야 한다"


def test_single_pool_caps_one_per_game():
    """같은 경기 두 마켓은 상관돼 있다 — 둘 다 추천하면 노출이 2배가 된다."""
    from app.config import get_settings
    from app.pipeline import qualified_singles

    g = _game_with_board()
    g["market_board"][1]["two_source"] = True   # [§8-18] 둘 다 자격 통과시킨다
    out = qualified_singles([g], get_settings())
    assert len(out) == 1
    assert out[0]["p"] == 0.634, "승률 높은 쪽이 남아야 한다"


def test_single_entry_carries_downstream_contract():
    """추천 엔트리는 DB 적재·속보 비교가 쓰는 필드를 전부 가져야 한다."""
    from app.config import get_settings
    from app.pipeline import qualified_singles

    e = qualified_singles([_game_with_board()], get_settings())[0]
    for key in ("pick", "game_id", "p", "odds", "ev", "kelly",
                "judge_excluded", "lineup_status", "approved"):
        assert key in e, f"{key} 누락 — 다운스트림이 KeyError로 죽는다"


def test_started_game_is_not_a_single_candidate():
    from app.config import get_settings
    from app.pipeline import qualified_singles

    g = _game_with_board()
    g["status"] = "live"
    assert qualified_singles([g], get_settings()) == []


# --- /픽 상세 데이터가 비지 않는다 ---

def test_full_reco_detail_explains_zero_singles():
    """단식 0건일 때 '왜 없는지'가 상세에 남아야 한다 — 헤더만 남으면 '(내용 없음)'."""
    from app.pipeline import DETAIL_SEP, render_full_reco

    g = _game_with_board()
    # [§8-18] 배당 하한이 사라졌다 — 승률 미달로 전부 탈락시킨다
    for c in g["market_board"]:
        c["p"] = 0.51
    analysis = {"sport": "mlb", "date": "2026-08-26", "games": [g], "picks": [],
                "combos": {}, "mode": {"name": "live_conservative"}}
    body = render_full_reco([analysis])
    detail = body.split(DETAIL_SEP, 1)[1]
    assert "단식 0건 사유" in detail
    assert "승률" in detail and len(detail.strip().splitlines()) > 1
