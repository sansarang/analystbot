"""[D 2026-09-02] 타선 시즌 라인 — 수집·정규화·배선.

규율 개정(타선 시즌 지표 금지 해제)과 함께 들어간 테스트다.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.collectors.lineup_season import (
    attach, fill_ops, is_pitcher_slot, lookup, norm_jp, slim_bat, split_order,
    strip_pos, team_line,
)


# ─────────────────── 이름 처리 ───────────────────

def test_split_order_rejoins_hyphenated_names():
    """실측 2026-09-02: `Ha-Seong Kim` 이 두 조각으로 잘려 6명이 미매칭이었다."""
    known = {"Ha-Seong Kim", "Pete Crow-Armstrong", "Hao-Yu Lee", "Elly De La Cruz"}
    order = "Ha-Seong Kim-Elly De La Cruz-Pete Crow-Armstrong-Hao-Yu Lee"
    assert split_order(order, known) == [
        "Ha-Seong Kim", "Elly De La Cruz", "Pete Crow-Armstrong", "Hao-Yu Lee"]


def test_split_order_without_dictionary_does_not_guess():
    """사전이 없으면 재결합하지 않는다 — 추측으로 이름을 만들지 않는다."""
    assert split_order("Ha-Seong Kim-Elly De La Cruz") == [
        "Ha", "Seong Kim", "Elly De La Cruz"]


def test_is_pitcher_slot_covers_all_locales():
    """센트럴리그 `(投)` · KBO `(투수)` · 영문 `(P)`. 하나라도 놓치면 8명을 9명으로 센다."""
    assert is_pitcher_slot("戸郷 翔征(投)")
    assert is_pitcher_slot("오원석(투수)")
    assert is_pitcher_slot("Smith(P)")
    assert not is_pitcher_slot("丸 佳浩(左)")
    assert not is_pitcher_slot("홍창기(중견수)")
    assert not is_pitcher_slot("Elly De La Cruz")


def test_norm_jp_matches_fullwidth_space():
    """라인업은 반각 공백, 성적표는 전각 U+3000 이다."""
    assert norm_jp("浦田 俊輔(二)") == norm_jp("浦田　俊輔") == "浦田俊輔"
    assert norm_jp("*アルメンタ") == "アルメンタ"


def test_strip_pos_keeps_hyphenated_name():
    assert strip_pos("Pete Crow-Armstrong") == "Pete Crow-Armstrong"
    assert strip_pos("홍창기(우익수)") == "홍창기"


# ─────────────────── 라인 정규화 ───────────────────

def test_slim_bat_omits_empty_cells():
    """없는 칸은 만들지 않는다."""
    assert slim_bat(pa=537, avg=".271", obp=None, ops="", hr=21) == {
        "PA": 537, "AVG": ".271", "HR": 21}


def test_fill_ops_synthesizes_only_when_absent():
    """npb.jp 는 OPS 칸이 없다. 있으면 원값을 건드리지 않는다."""
    assert fill_ops({"OBP": ".338", "SLG": ".325"})["OPS"] == "0.663"
    assert fill_ops({"OBP": ".4", "SLG": ".6", "OPS": ".999"})["OPS"] == ".999"
    assert "OPS" not in fill_ops({"OBP": ".338"})


def test_team_line_is_plate_appearance_weighted():
    """대타 표본이 주전과 같은 무게를 가지면 팀 타선 수준이 왜곡된다."""
    bs = [{"OPS": "1.000", "PA": 10}, {"OPS": "0.600", "PA": 590}]
    out = team_line(bs)
    assert out["합계타석"] == 600 and out["인원"] == 2
    # 단순 평균이면 0.800. 가중이면 0.607 근처.
    assert out["가중OPS"] == pytest.approx(0.607, abs=0.002)


def test_team_line_empty_when_no_material():
    """재료가 없으면 0.000 을 지어내지 않는다."""
    assert team_line([]) == {}
    assert team_line([{"이름": "A"}]) == {}


def test_lookup_rejects_wrong_team():
    """동명이인이 다른 팀에 있으면 그 값을 쓰지 않는다."""
    tbl = {"홍길동": {"team": "LG Twins", "OPS": "0.800"}}
    assert lookup(tbl, "kbo", "홍길동(좌익수)", "LG Twins")["OPS"] == "0.800"
    assert lookup(tbl, "kbo", "홍길동(좌익수)", "Doosan Bears") == {}
    assert "team" not in lookup(tbl, "kbo", "홍길동", "LG Twins")


# ─────────────────── 배선 가드 ───────────────────

def test_replay_suppresses_season_line():
    """🔴 시즌 값은 언제나 '지금' 값이다 — 끝난 경기를 재현하면 그 경기가 들어간다."""
    jg = {"sport": "mlb", "research": {"home_lineup": {"order": "A-B"}}}
    asyncio.run(attach(jg, replay=True))
    assert jg["research"]["home_lineup_season"] == {}
    assert jg["research"]["away_lineup_season"] == {}
    assert jg["lineup_season_suppressed"] is True


def test_soccer_is_untouched():
    """축구는 이번 개편 대상이 아니다."""
    jg = {"sport": "soccer", "research": {}}
    asyncio.run(attach(jg))
    assert "home_lineup_season" not in jg["research"]


def test_no_lineup_means_no_call(monkeypatch):
    """타순이 없으면 외부를 때리지 않는다."""
    called = []
    from app.collectors import lineup_season as ls

    monkeypatch.setattr(ls, "fetch_mlb", lambda *a, **k: called.append(1))
    jg = {"sport": "mlb", "research": {}}
    asyncio.run(attach(jg))
    assert called == []


def test_mock_mode_makes_no_external_call(monkeypatch):
    """목 모드에서 외부를 때리면 스위트가 네트워크에 나간다 (딥서치에서 이미 겪었다)."""
    from app.collectors import lineup_season as ls
    from app.config import Settings

    monkeypatch.setattr(ls, "_mem", {})
    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, force_mock=True))
    boom = lambda *a, **k: pytest.fail("목 모드에서 외부 호출")   # noqa: E731
    monkeypatch.setattr(ls, "fetch_mlb", boom)
    monkeypatch.setattr(ls, "fetch_kbo", boom)
    monkeypatch.setattr(ls, "fetch_npb", boom)
    jg = {"sport": "kbo", "research": {"home_lineup": {"order": "홍창기(우)-오스틴(1)"}}}
    asyncio.run(attach(jg, redis=None))
    assert jg["research"]["home_lineup_season"] == {}


def test_header_mismatch_yields_nothing():
    """기록실 HTML 구조가 바뀌면 조용히 틀린 값을 만들지 않고 0건이 된다."""
    from app.collectors.lineup_season import parse_kbo

    assert parse_kbo("<table><th>딴것</th><td>1</td></table>", "Basic1") == []


# ─────────────────── 프롬프트·페이로드 ───────────────────

def test_payload_omits_side_without_material():
    """한쪽만 있으면 없는 쪽은 넣지 않는다 — '없음'과 '나쁨'을 섞지 않는다."""
    from app.engine.matchup import lineup_season_payload

    jg = {"research": {"home_lineup_season": {"타자": [{"이름": "A"}], "팀": {}},
                       "away_lineup_season": {}}}
    out = lineup_season_payload(jg)
    assert set(out) == {"home"}


def test_prompt_exposes_batting_season_and_drops_the_ban():
    """규율 개정이 프롬프트에 실제로 반영됐는가."""
    from app.engine.prompts import MATCHUP

    assert "{{LINEUP_SEASON_JSON}}" in MATCHUP
    assert "타선 시즌:" in MATCHUP
    assert "타선·팀 지표의 시즌 값은 여전히 쓰지 않는다" not in MATCHUP
    # 완화하면 안 되는 것들은 그대로여야 한다.
    assert "0.32~0.68" in MATCHUP
    assert "±3%p" in MATCHUP


def test_every_placeholder_is_supplied():
    """🔴 치환되지 않은 `{{...}}` 가 남으면 모델이 그 자리표시자를 그대로 읽는다.

    프롬프트에서 자리표시자를 **직접 뽑아** 검사한다 — 목록을 손으로 적으면
    자료를 새로 추가할 때 이 테스트가 조용히 뒤처진다.
    """
    import re
    from pathlib import Path

    from app.engine.prompts import MATCHUP

    names = set(re.findall(r"\{\{(\w+)\}\}", MATCHUP))
    assert names, "자리표시자를 하나도 못 찾았다 — 정규식이 깨졌다"
    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    missing = [n for n in sorted(names) if f"{n}=" not in src]
    assert not missing, f"판정이 채우지 않는 자리표시자: {missing}"


def test_matchup_render_leaves_no_placeholder():
    """실제 렌더 1회 — 빈 경기로도 `{{` 가 남지 않아야 한다."""
    import json
    import re
    from pathlib import Path

    from app.engine import matchup as M
    from app.engine.prompts import MATCHUP, fill

    jg = {"research": {
        "home_usage": {"games": [{"runs": 3, "opp_runs": 2}]},
        "away_usage": {"games": [{"runs": 1, "opp_runs": 5}]},
        "home_lineup_season": {"타자": [{"이름": "A", "OPS": ".800"}],
                               "팀": {"가중OPS": 0.8}}}}
    J = lambda x: json.dumps(x, ensure_ascii=False, default=str)   # noqa: E731
    out = fill(MATCHUP,
               BOXSCORE_JSON=J(M.boxscore_payload(jg)),
               NEWS_JSON=J(M.news_payload({}, {})),
               LINEUPS_JSON=J(M.lineups_payload(jg)),
               STARTERS_RECENT_JSON=J(M.starters_recent_payload(jg)),
               PREV_VERDICT_JSON="null",
               LINEUP_INTENT_JSON=J(M.intent_payload(jg)),
               STARTER_SEASON_JSON=J(M.starters_season_payload(jg)),
               LINEUP_SEASON_JSON=J(M.lineup_season_payload(jg)),
               BULLPEN_JSON=J(M.bullpen_payload(jg)))
    assert "{{" not in out
    assert "가중OPS" in out
    assert '"runs": 3' in out, "원본 숫자가 그대로 실려야 한다"


def test_boxscore_payload_passes_numbers_untouched():
    """수집기가 준 숫자를 가공하지 않는다 — 있는 그대로 넘긴다."""
    from app.engine.matchup import boxscore_payload

    g = {"date": "2026-08-30", "runs": 1, "opp_runs": 5, "starter_ip": 3.0,
         "starter_pitches": 73, "errors": 3, "opponent_rank": 5}
    jg = {"research": {"home_usage": {"games": [g], "results_l3": "LWL"},
                       "away_usage": {"games": [g]}}}
    out = boxscore_payload(jg)
    assert out["home"]["경기"][0] == g, "한 칸도 바꾸거나 빠뜨리지 않는다"
    assert out["home"]["results_l3"] == "LWL"


def test_boxscore_payload_omits_side_without_games():
    """재료가 없으면 그 쪽을 만들지 않는다 — 판정 게이트가 이걸 보고 탈락시킨다."""
    from app.engine.matchup import boxscore_payload

    assert boxscore_payload({"research": {"home_usage": {"games": []}}}) == {}


def test_lineup_payload_uses_slots_when_available():
    """today_nine 이 있으면 타순 번호·포지션을 붙인다."""
    from app.engine.matchup import lineups_payload

    jg = {"research": {"today_nine": {"home": {"order": [
        {"slot": 1, "name": "長岡 秀樹", "pos": "遊"},
        {"slot": 2, "name": "赤羽 由紘", "pos": "三"}]}}}}
    out = lineups_payload(jg)
    assert out["home"]["타순"][0] == {"타순": 1, "이름": "長岡 秀樹", "포지션": "遊"}


def test_lineup_payload_falls_back_to_order_string():
    """today_nine 이 없으면 종전 문자열로 간다 — 없다고 빈 칸을 만들지 않는다."""
    from app.engine.matchup import lineups_payload

    jg = {"research": {"home_lineup": {"order": "A-B-C"}}}
    assert lineups_payload(jg)["home"]["타순"] == "A-B-C"


def test_no_odds_import_boundary():
    """🔴 배당은 판정 입력에 절대 흐르지 않는다 — 새 수집기도 같은 경계 안이다."""
    src = Path("app/collectors/lineup_season.py").read_text(encoding="utf-8")
    for banned in ("market_edge", "odds", "pick_ledger", "calibration"):
        assert banned not in src, f"{banned} 를 import 하면 안 된다"


def test_process_cache_expires():
    """🔴 스케줄러는 며칠씩 도는 프로세스다. 만료 없는 dict 에 넣으면
    시즌 성적이 기동 시점 값으로 영원히 굳는다 (redis 는 26시간인데)."""
    import time

    from app.collectors import lineup_season as ls

    ls._mem.clear()
    ls._mem_put("k", {"a": 1})
    assert ls._mem_get("k") == {"a": 1}
    ls._mem["k"] = (time.time() - 1, {"a": 1})       # 만료시킨다
    assert ls._mem_get("k") is None
    assert "k" not in ls._mem, "만료된 항목은 지워야 메모리가 새지 않는다"
