"""[§9-6번째 칸] 득점 환경 + 언더오버·핸디캡 매핑.

다섯 칸은 "누가 이기나"만 답한다. 총득점과 점수차는 다른 질문이고 다른 재료를 쓴다.
"""
import asyncio

import pytest

from app.engine import card_markets as M
from app.engine import comparator as C
from app.engine.card import (CELLS, SCORING_CELL, SCORING_LEVELS, build_card,
                             scoring_metrics)
from app.engine.interpreter import scoring_baselines, scoring_direction_check

RESEARCH = {
    "home_usage": {"score_games": 3, "runs_per_game_l3": 10.33, "runs_l3": 31,
                   "runs_allowed_l3": 24, "relief_batters_l3": 69},
    "away_usage": {"score_games": 3, "runs_per_game_l3": 5.67, "runs_l3": 17,
                   "runs_allowed_l3": 27, "relief_batters_l3": 47},
    "home_pitcher": {"name": "양현종", "era_season": 4.19, "whip": 1.44,
                     "ip_avg_recent": 4.81},
    "away_pitcher": {"name": "나균안", "era_season": 4.00, "whip": 1.43,
                     "ip_avg_recent": 5.73},
    "park_factor": 0.902, "park": "광주 — 파크팩터 0.902 (55경기 실측)",
    "weather": "기온 30도, 풍속 1.8m/s",
}
JG = {"game_id": 1, "home": "Kia Tigers", "away": "Lotte Giants",
      "home_kr": "KIA", "away_kr": "롯데"}


# ---------------------------------------------------------------- 칸 구성

def test_scoring_is_one_game_level_cell_not_per_team():
    """🔴 득점이 많은 것은 어느 팀에게도 '유리'가 아니다 — 팀별로 나누지 않는다."""
    card = build_card(JG, RESEARCH)
    assert "scoring" in card and card["scoring"]["key"] == SCORING_CELL[0]
    assert "scoring" not in card["home"] and "scoring" not in card["away"]


def test_scoring_facts_cover_every_requested_source():
    facts = " ".join(build_card(JG, RESEARCH)["scoring"]["facts"])
    for must in ("회당", "ERA", "구원", "파크팩터", "날씨"):
        assert must in facts, f"{must}가 사실 칸에 없다"


def test_metrics_need_both_sides():
    """🔴 한 팀 값으로 경기 전체를 말할 수 없다."""
    one = {k: v for k, v in RESEARCH.items() if not k.startswith("away_")}
    m = scoring_metrics(one)
    assert "runs_per_game_both" not in m and "starter_era_avg" not in m
    assert m.get("park_factor") == 0.902     # 경기 단위 값은 남는다


def test_metrics_combine_both_sides():
    m = scoring_metrics(RESEARCH)
    assert m["runs_per_game_both"] == 16.0
    assert m["starter_era_avg"] == 4.1
    assert m["starter_ip_avg"] == 5.27
    assert m["relief_batters_avg"] == 58.0


def test_no_facts_means_no_cell():
    assert build_card(JG, {})["scoring"]["facts"] == []


# ---------------------------------------------------------------- 방향 검증

def _band(q1, q3):
    return {"q1": q1, "median": (q1 + q3) / 2, "q3": q3}


BASE = {"runs_per_game_both": _band(8.0, 11.0), "starter_era_avg": _band(3.8, 5.0),
        "starter_ip_avg": _band(4.5, 5.6), "relief_batters_avg": _band(40.0, 55.0),
        "park_factor": _band(0.93, 1.09)}


def test_park_factor_below_one_is_low_scoring_not_high():
    """🔴 "파크팩터 0.90"은 투수친화 = 저득점이지 다득점이 아니다."""
    assert scoring_direction_check({"park_factor": 0.88}, BASE, "다득점 예상")
    assert scoring_direction_check({"park_factor": 0.88}, BASE, "저득점 예상") is None


def test_short_starter_means_more_scoring():
    """선발이 짧을수록 불펜 노출이 커진다 — 방향이 뒤집히면 잡아야 한다."""
    assert scoring_direction_check({"starter_ip_avg": 3.2}, BASE, "저득점 예상")


def test_inside_the_band_is_never_a_misread():
    assert scoring_direction_check({"runs_per_game_both": 9.5}, BASE, "다득점 예상") is None


def test_mixed_signals_are_left_alone():
    mixed = {"runs_per_game_both": 14.0, "park_factor": 0.85}
    assert scoring_direction_check(mixed, BASE, "다득점 예상") is None
    assert scoring_direction_check(mixed, BASE, "저득점 예상") is None


def test_baselines_need_four_games():
    cells = [{"metrics": {"park_factor": x}} for x in (0.9, 1.0, 1.1)]
    assert scoring_baselines(cells) == {}
    cells.append({"metrics": {"park_factor": 1.2}})
    assert "park_factor" in scoring_baselines(cells)


# ---------------------------------------------------------------- 언더오버

def test_expected_total_is_card_arithmetic_with_park():
    m = scoring_metrics(RESEARCH)
    assert M.expected_total(m) == round(16.0 * 0.902, 2)


def test_expected_total_is_none_without_material():
    assert M.expected_total({}) is None


BASELINE = {"median": 9.0, "n": 37}     # 실측 2026-08-27 KBO


def test_high_scoring_takes_the_line_at_or_below_the_league_median():
    """"다득점 예상 = 평소보다 많이 난다" → 중앙값 이하 라인에 오버."""
    call = M.totals_call("다득점 예상", [8.5, 9.0, 10.5, 13.5], BASELINE)
    assert call["side"] == "오버" and call["line"] == 9.0
    assert call["basis"] == ["scoring"]
    assert "37경기" in call["note"], "기준의 표본 수를 밝혀야 한다"


def test_low_scoring_takes_the_line_at_or_above_the_median():
    call = M.totals_call("저득점 예상", [7.5, 9.0, 10.5], BASELINE)
    assert call["side"] == "언더" and call["line"] == 9.0


def test_direction_and_line_must_agree():
    """🔴 억지로 고르지 않는다 — 맞는 라인이 없으면 부르지 않는다."""
    assert M.totals_call("다득점 예상", [12.5, 13.5], BASELINE) == {}
    assert M.totals_call("저득점 예상", [6.5, 7.5], BASELINE) == {}


def test_normal_level_makes_no_call():
    assert M.totals_call("보통", [9.5], BASELINE) == {}


def test_no_lines_still_gives_a_direction():
    """라인이 없다고 판정 자체를 버리지는 않는다 — 방향은 카드가 아는 것이다."""
    call = M.totals_call("다득점 예상", [], BASELINE)
    assert call["side"] == "오버" and call["line"] is None


def test_thin_league_sample_blocks_every_totals_call():
    """🔴 얇은 기준으로 라인을 고르면 그 기준의 오차가 판정 오차가 된다."""
    assert M.totals_call("다득점 예상", [8.5], {"median": None, "n": 12}) == {}
    assert M.totals_call("다득점 예상", [8.5], None) == {}


def test_three_game_figure_is_not_used_for_line_comparison():
    """🔴 3경기 표본은 5.86~14.43까지 흔들렸다(실측). 라인 비교에 쓰면 안 된다.

    주석에 언급하는 것은 되고, **호출**하면 안 된다 — AST로 호출만 본다.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(M.totals_call)))
    called = {getattr(n.func, "id", None) for n in ast.walk(tree)
              if isinstance(n, ast.Call)}
    assert "expected_total" not in called, "3경기 산술이 라인 비교로 되돌아왔다"


# ---------------------------------------------------------------- 핸디캡

@pytest.mark.parametrize("won,lost,line", [(5, 0, -1.5), (4, 1, None),
                                           (3, 1, None), (2, 2, None),
                                           (1, 3, +1.5), (0, 4, +1.5)])
def test_handicap_maps_from_the_cell_gap(won, lost, line):
    call = M.handicap_call({"home": won, "away": lost}, "home")
    assert call["line"] == line, call


def test_handicap_needs_a_favored_side():
    assert M.handicap_call({"home": 5, "away": 0}, "none") == {}
    assert M.handicap_call({}, "home") == {}


def test_handicap_basis_lists_the_win_loss_cells():
    call = M.handicap_call({"home": 5, "away": 0}, "home")
    assert call["basis"] == [k for k, _ in CELLS]
    assert SCORING_CELL[0] not in call["basis"], "득점 칸은 승패 근거가 아니다"


# ---------------------------------------------------------------- 근거 표시

def test_every_market_call_names_its_basis_cells():
    """[2] 어느 칸이 그 판정을 만들었는지 반드시 밝힌다."""
    jg = dict(JG, card=build_card(JG, RESEARCH),
              compare={"favored": "home", "counts": {"home": 5, "away": 0}},
              scoring={"level": "다득점 예상", "reason": "회당 10.33득점"},
              total_baseline=BASELINE,
              market_board=[{"desc": "오버 8.5", "line": 8.5},
                            {"desc": "오버 13.5", "line": 13.5}])
    calls = M.market_calls(jg)
    assert calls, "마켓 판정이 하나도 없다"
    assert all(c["basis"] for c in calls)
    rendered = "\n".join(M.render_market_calls(jg))
    assert "근거:" in rendered and "득점 환경" in rendered


def test_no_material_makes_no_market_call():
    """🔴 빈 판정을 '보통'으로 채우면 판정한 것처럼 보인다."""
    assert M.market_calls(dict(JG, card=build_card(JG, {}), compare={},
                               scoring={}, market_board=[])) == []


def test_market_line_is_only_a_reference_not_a_probability():
    """시장 배당은 라인 확인용이지 확률 근거가 아니다 — 확률을 읽지 않는다."""
    import pathlib

    src = (pathlib.Path(M.__file__)).read_text(encoding="utf-8")
    for banned in ('c["p"]', 'get("p")', '"odds"', "p_market"):
        assert banned not in src, f"마켓 매핑이 시장 확률을 본다: {banned}"


# ---------------------------------------------------------------- 채점 [4]

def test_scoring_is_graded_separately_from_win_loss():
    """🔴 "다득점 예상이 맞았나"와 "▲를 준 팀이 이겼나"는 다른 질문이다."""
    import pathlib

    sql = (pathlib.Path(__file__).resolve().parents[1]
           / "db/schema.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW scoring_ledger" in sql
    view = sql[sql.index("VIEW scoring_ledger"):]
    assert "cell = 'scoring'" in view, "승패 칸이 섞인다"
    ledger = sql[sql.index("VIEW cell_ledger"):sql.index("VIEW scoring_ledger")]
    assert "scoring" not in ledger or "cell, sport" in ledger


@pytest.mark.asyncio
async def test_scoring_ledger_scores_over_under_correctly():
    """실 DB에서 방향을 검증한다. 여기가 뒤집히면 집계가 통째로 거짓말이 된다."""
    asyncpg = pytest.importorskip("asyncpg")
    from app.config import get_settings

    try:
        con = await asyncpg.connect(get_settings().database_url)
    except Exception:
        pytest.skip("DB 없음")
    cases = [  # (판정, 기준, 홈, 원정, 기대)
        ("다득점 예상", 9.0, 7, 5, "hit"),     # 실제 12 > 9
        ("다득점 예상", 9.0, 3, 2, "miss"),    # 실제 5 < 9
        ("저득점 예상", 9.0, 3, 2, "hit"),
        ("저득점 예상", 9.0, 7, 5, "miss"),
        ("다득점 예상", 9.0, 5, 4, "push"),    # 정확히 9
        ("다득점 예상", None, 7, 5, None),     # 기준 없음 → 미채점
    ]
    try:
        await con.execute("BEGIN")
        for i, (level, ref, hs, aws, _want) in enumerate(cases):
            gid = await con.fetchval("""
                INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                                   status, home_score, away_score)
                VALUES ('sctest','T',$1, now(),'H','A','final',$2,$3)
                RETURNING id""", f"sctest:{i}", hs, aws)
            await con.execute("""
                INSERT INTO cell_verdicts (game_id, side, cell, symbol, ref_total)
                VALUES ($1,'game','scoring',$2,$3)""", gid, level, ref)
        rows = {r["level"]: dict(r) for r in await con.fetch(
            "SELECT * FROM scoring_ledger WHERE sport='sctest'")}
        hi = rows["다득점 예상"]
        assert hi["decided"] == 2 and hi["hits"] == 1, hi
        assert hi["pushes"] == 1 and hi["ungradable"] == 1, hi
        lo = rows["저득점 예상"]
        assert lo["decided"] == 2 and lo["hits"] == 1, lo
    finally:
        await con.execute("ROLLBACK")
        await con.close()


def test_thin_scoring_sample_hides_the_number():
    from app.engine.cell_grade import format_scoring_ledger

    out = format_scoring_ledger([{"sport": "kbo", "level": "다득점 예상",
                                  "decided": 3, "hits": 3, "pushes": 0,
                                  "ungradable": 0, "avg_actual": 12,
                                  "avg_ref": 9, "hit_rate": 1.0,
                                  "verdict": "표본 부족"}])
    assert "100" not in out and "표본 부족" in out


def test_no_market_line_gives_direction_only_not_a_made_up_line():
    """🔴 시장 라인이 없을 때 λ가 만든 라인에 판정을 붙이면 자기확인이 된다.

    실측 2026-08-27: KBO는 시장 라인 0건이고 λ 후보 라인(8.5~13.5)은
    실제 리그 중앙값 9보다 높았다. 틀린 라인이 근거처럼 읽힌다.
    """
    call = M.totals_call("다득점 예상", [], BASELINE)
    assert call["side"] == "오버" and call["line"] is None
    assert "시장 라인 미수집" in call["note"] and "9점" in call["note"]


def test_market_calls_use_market_lines_not_model_lines():
    jg = dict(JG, card=build_card(JG, RESEARCH), compare={},
              scoring={"level": "다득점 예상", "reason": "x"},
              total_baseline=BASELINE, alt_markets=[],
              market_board=[{"desc": "오버 12.5", "line": 12.5}])
    call = [c for c in M.market_calls(jg) if c["market"] == "totals"][0]
    assert "12.5" not in call["desc"], "λ가 만든 라인을 시장 라인처럼 썼다"
    assert call["desc"] == "오버 쪽"


def test_real_market_line_is_used_when_present():
    jg = dict(JG, card=build_card(JG, RESEARCH), compare={},
              scoring={"level": "다득점 예상", "reason": "x"},
              total_baseline=BASELINE,
              alt_markets=[{"market": "totals", "line": 8.5},
                           {"market": "totals", "line": 12.5}])
    call = [c for c in M.market_calls(jg) if c["market"] == "totals"][0]
    assert call["desc"] == "오버 8.5"
