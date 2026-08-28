"""[§8-20] Yahoo!スポーツ NPB 크롤러 — LLM 0회로 선발·불펜을 모은다.

실사고(2026-08-26): NPB 6경기 전부 `λ 미확보 입력: 핵심 지표 전무`였다.
지표 소스가 없어 확률이 판정 단독이었고, 지바 롯데 70%처럼 검증할 수 없는 값이 나왔다.
"""

import pytest

from app.collectors.yahoo_npb import (
    MAX_CREDIBLE_ERA,
    MIN_STARTER_APPEARANCES,
    TEAM_TO_ODDS,
    merge_into_research,
    parse_game,
    parse_schedule,
)

_SCHED = '''
<a href="/npb/game/2021039331/index"><span>神宮</span> ヤクルト 巨人 18:00 (予)山野 (予)井上</a>
<a href="/npb/game/2021039335/index"><span>ZOZOマリン</span> ロッテ ソフトバンク 18:00 (先)ロング (先)上沢</a>
<a href="/npb/game/2021039325/index">試合終了</a>
'''

def _tbl(rows):
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{body}</table>"

_PREGAME = "予告先発" + _tbl([["背番号", "投", "選手名"], ["26", "左投", "山野 太一"]]) \
    + _tbl([["", "防御率", "登板", "勝利", "敗戦"],
            ["今季", "2.15", "19", "9", "3"], ["対戦", "1.69", "5", "4", "0"]]) \
    + _tbl([["背番号", "投", "選手名"], ["11", "右投", "井上 温大"]]) \
    + _tbl([["", "防御率", "登板", "勝利", "敗戦"],
            ["今季", "3.38", "18", "10", "7"], ["対戦", "4.20", "2", "0", "2"]])

_FINISHED = _tbl([["投手", "位置", "選手名", "投", "防御率", "調子"],
                  ["先発", "投", "吉村 貢司郎", "右", "4.05", "好調"]]) \
    + _tbl([["投手", "位置", "選手名", "投", "防御率", "調子"],
            ["先発", "投", "則本 昂大", "右", "4.94", "普通"]]) \
    + _tbl([["選手名", "投打", "防御率", "調子"],
            ["清水 昇", "右左", "1.99", "絶不調"], ["星 知弥", "右右", "2.82", "普通"]]) \
    + _tbl([["選手名", "投打", "防御率", "調子"],
            ["赤星 優志", "右右", "2.18", "好調"]])


# ---------------------------------------------------------------- 일정

def test_schedule_extracts_today_games_only():
    """종료·미정 블록은 팀명이 안 잡힌다 — 걸러져야 한다."""
    games = parse_schedule(_SCHED)
    assert len(games) == 2
    assert games[0]["home"] == "Tokyo Yakult Swallows"
    assert games[0]["away"] == "Yomiuri Giants"


def test_projected_vs_confirmed_starters():
    """⚠️ `(予)`는 예상, `(先)`는 확정 — 섞으면 '최종 픽' 자격이 잘못 부여된다."""
    games = parse_schedule(_SCHED)
    assert games[0]["starters_confirmed"] is False      # (予)
    assert games[1]["starters_confirmed"] is True       # (先)


def test_team_mapping_covers_all_twelve():
    assert len(TEAM_TO_ODDS) == 12
    assert TEAM_TO_ODDS["ソフトバンク"] == "Fukuoka SoftBank Hawks"


# ---------------------------------------------------------------- 경기 페이지

def test_parses_pregame_structure():
    """[§8-20] 경기 **전** 페이지는 `予告先発` 블록이다.

    실사고: 종료 경기 구조만 보고 파서를 만들었더니 **오늘 6경기가 전부 실패**했다.
    개발 중 본 한 페이지가 전부라고 가정하면 안 된다.
    """
    d = parse_game(_PREGAME)
    assert d is not None
    assert d["home_pitcher"]["name"] == "山野 太一"
    assert d["home_pitcher"]["throws"] == "L"
    assert d["home_pitcher"]["era_season"] == 2.15
    # 상대전적 ERA — 딥서치가 절대 못 주는 재료
    assert d["home_pitcher"]["era_vs_opponent"] == 1.69
    assert d["away_pitcher"]["era_season"] == 3.38
    # 실측 2026-08-28: 시작 수 시간 전에는 打順 표가 없다. 빈 타순은 정상.
    assert "lineup_home" not in d and "lineup_away" not in d


def test_parses_finished_structure():
    """종료 경기 구조도 그대로 지원한다(과거 경기 검증용)."""
    d = parse_game(_FINISHED)
    assert d["home_pitcher"]["name"] == "吉村 貢司郎"
    assert d["home_pitcher"]["era_season"] == 4.05
    assert len(d["home_bullpen_list"]) == 2
    assert d["home_bullpen_list"][0]["condition"] == "매우 나쁨"   # 絶不調


def test_returns_none_when_structure_changes():
    """⚠️ HTML 파싱이다 — 구조가 바뀌면 조용히 0건이 된다. 검증 후 거부한다."""
    assert parse_game("<html>선발 정보 없음</html>") is None
    assert parse_game("") is None


# ---------------------------------------------------------------- 표본 가드

def test_thin_sample_era_is_discarded():
    """[§8-20] 표본 미달 ERA는 **버린다** — 리그 평균으로 대체하지도 않는다.

    실측(2026-08-26): 齋藤 響介가 **1등판 ERA 189.00**이었다. 0이닝대 대량 실점이면
    산술적으로 나오는 값이고 데이터는 정확하지만, λ의 선발 억제 계수에 넣으면
    그 경기가 통째로 망가진다.
    없는 것을 있는 척하지 않는다 — 판정이 "선발 정보 없음"으로 다루게 한다.
    """
    thin = "予告先発" + _tbl([["背番号", "投", "選手名"], ["1", "右投", "齋藤 響介"]]) \
        + _tbl([["", "防御率", "登板", "勝利", "敗戦"], ["今季", "189.00", "1", "0", "0"]]) \
        + _tbl([["背番号", "投", "選手名"], ["2", "右投", "荘司 康誠"]]) \
        + _tbl([["", "防御率", "登板", "勝利", "敗戦"], ["今季", "4.08", "19", "6", "9"]])
    d = parse_game(thin)
    assert "era_season" not in d["home_pitcher"], "표본 1등판 ERA가 λ로 흘러간다"
    assert "189.00" in d["home_pitcher"]["era_unreliable"]
    # 정상 표본은 그대로 남는다
    assert d["away_pitcher"]["era_season"] == 4.08


def test_guard_thresholds_are_sane():
    assert MIN_STARTER_APPEARANCES >= 2
    assert 8.0 <= MAX_CREDIBLE_ERA <= 30.0


# ---------------------------------------------------------------- 병합

def test_crawl_overrides_deep_search():
    """[§8-20] 크롤링이 딥서치를 덮어쓴다 — 구단 발표가 LLM 산문보다 정확하다."""
    research = {"home_pitcher": {"name": "누구", "era_season": 9.99}}
    filled = merge_into_research(research, {}, parse_game(_PREGAME))
    assert research["home_pitcher"]["era_season"] == 2.15
    assert research["home_pitcher"]["name"] == "山野 太一"
    assert any("era_season" in f for f in filled)


def test_bullpen_roster_becomes_research_material():
    """불펜 전원 방어율·컨디션은 딥서치가 못 주는 재료다."""
    research = {}
    merge_into_research(research, {}, parse_game(_FINISHED))
    assert research["home_bullpen"]["era"] == pytest.approx(2.405, abs=0.01)
    assert "清水 昇" in research["home_bullpen"]["roster"]


def test_merge_is_safe_on_empty():
    research = {}
    assert merge_into_research(research, {}, {}) == []
    assert research == {}


# ---------------------------------------------------------------- [§8-28] 채점 경로

_FINALS = '''
<a href="/npb/game/2021039325/index">神宮 ヤクルト 巨人 6 - 8 試合終了 (敗)吉村 (勝)赤星</a>
<a href="/npb/game/2021039326/index">バンテリンドーム 中日 阪神 4 - 2 試合終了 (勝)大野</a>
<a href="/npb/game/2021039331/index">神宮 ヤクルト 巨人 18:00 (予)山野 (予)井上</a>
<a href="/npb/game/2021039340/index">ZOZOマリン ロッテ ソフトバンク 0 - 0 試合中</a>
'''


def test_parse_finals_extracts_scores():
    """[§8-28] NPB 채점 경로 — Yahoo 일정에 최종 점수가 그대로 있다.

    종전에는 Odds API `/scores`에 의존했는데 완료 경기가 **한 건도 안 잡혀**
    채점이 증명되지 않았다(실측 2026-08-26, daysFrom=3에서 0건).
    """
    from app.collectors.yahoo_npb import parse_finals

    out = parse_finals(_FINALS)
    assert len(out) == 2                       # 예정·진행 중은 제외
    g = out[0]
    assert g["home"] == "Tokyo Yakult Swallows" and g["away"] == "Yomiuri Giants"
    assert g["home_score"] == 6 and g["away_score"] == 8


def test_in_progress_zero_zero_is_not_final():
    """⚠️ 점수만 보고 판단하면 **진행 중 0-0을 종료로 오판**한다.

    KBO 공식 파서에서 겪은 것과 같은 유형의 사고다 — `試合終了`가 있어야 종료다.
    """
    from app.collectors.yahoo_npb import parse_finals

    out = parse_finals(_FINALS)
    assert all(g["game_id"] != "2021039340" for g in out)


def test_finals_home_team_comes_first():
    """표기 순서는 홈 먼저 — 뒤집히면 채점이 통째로 반대가 된다."""
    from app.collectors.yahoo_npb import parse_finals

    g = parse_finals(_FINALS)[1]
    assert g["home_kr"] == "中日" and g["away_kr"] == "阪神"
    assert g["home_score"] == 4 and g["away_score"] == 2


def test_grader_prefers_yahoo_for_npb():
    """[§8-28] 채점기가 Yahoo를 1순위로 부르는지 — 배선이 빠지면 조용히 Odds로 간다."""
    from pathlib import Path

    # [§8-36] 종목 분기는 `ingest_finals` **한 곳**에만 있다. 두 곳에 두었더니
    #   한쪽(reconcile_stale_games)이 갱신되지 않아 KBO·NPB가 축구 수집기로
    #   보내졌고, 8/26 경기가 'scheduled'로 굳어 영원히 미채점이 됐다.
    src = Path("app/grader.py").read_text(encoding="utf-8")
    i = src.index("async def ingest_finals")
    block = src[i:i + 2200]
    assert "yahoo_npb import upsert_final_scores" in block
    assert block.index("yahoo_finals") < block.index('odds_finals(pool, date, days=2, sport="npb")')
    # 분기가 다시 복제되지 않았는지 — reconcile은 ingest_finals를 불러야 한다
    rec = src[src.index("async def reconcile_stale_games"):]
    assert "ingest_finals" in rec, "reconcile이 종목 분기를 다시 갖게 됐다"
    assert "football" not in rec.split("async def ", 2)[0], \
        "reconcile에 축구 전용 경로가 다시 생겼다"


# ---------------------------------------------------------------- [§8-28] 打順 9명 (Yahoo /top)

def _dasen(rows):
    """打順 | 位置 | 選手名 표. rows = [(이름, 포지션), ...]"""
    body = [["打順", "位置", "選手名"]]
    body += [[str(i), p, n] for i, (n, p) in enumerate(rows, 1)]
    return _tbl(body)


_CL9 = [
    ("山田 哲人", "捕"), ("塩見 泰隆", "中"), ("村上 宗隆", "三"),
    ("サンタナ", "右"), ("オスナ", "一"), ("西川 輝矢", "左"),
    ("長岡 秀樹", "遊"), ("山野 太一", "投"), ("山崎 晃大朗", "二"),
]
_PL9 = [
    ("藤原 恭大", "中"), ("藤岡 裕大", "遊"), ("ソト", "一"),
    ("山口 航輝", "左"), ("ポランコ", "右"), ("安田 尚憲", "三"),
    ("佐藤 都志也", "捕"), ("茶谷 健太", "二"), ("石川 慎吾", "指"),
]
# 8명은 불완전 — 평소 기준으로 쓰면 안 된다
_EIGHT = _CL9[:8]


def test_batting_order_nine_each_side():
    """종료 경기 /top 打順은 팀당 선발 9명. 첫 표가 홈(실측 神宮 ヤクルト)."""
    from app.collectors.yahoo_npb import parse_batting_orders

    lu = parse_batting_orders(_dasen(_CL9) + _dasen(_PL9))
    assert [x.split("(")[0] for x in lu["home"]] == [n for n, _ in _CL9]
    assert [x.split("(")[0] for x in lu["away"]] == [n for n, _ in _PL9]
    assert all(x.endswith(")") for x in lu["home"] + lu["away"])


def test_central_keeps_pitcher_pacific_keeps_dh():
    """CL은 투수가 타순에 있고(投), PL은 지명타자(指). 한글 1루수로 바꾸면
    크롤러 게이트가 숫자를 보고 이름을 버린다."""
    from app.collectors.yahoo_npb import parse_batting_orders

    lu = parse_batting_orders(_dasen(_CL9) + _dasen(_PL9))
    assert any(x.endswith("(投)") for x in lu["home"])
    assert any(x.endswith("(指)") for x in lu["away"])
    joined = "-".join(lu["home"] + lu["away"])
    assert "1루수" not in joined and "3루수" not in joined


def test_pregame_has_no_batting_order():
    from app.collectors.yahoo_npb import parse_batting_orders

    assert parse_batting_orders(_PREGAME) == {"home": [], "away": []}


def test_eight_names_are_rejected():
    """9명이 아니면 그 쪽을 버린다. 한쪽만 9명이어도 둘 다 빈다."""
    from app.collectors.yahoo_npb import parse_batting_orders

    lu = parse_batting_orders(_dasen(_EIGHT) + _dasen(_PL9))
    assert lu == {"home": [], "away": []}


def test_parse_game_attaches_lineups_when_both_nines():
    html = _FINISHED + _dasen(_CL9) + _dasen(_PL9)
    d = parse_game(html)
    assert d["lineup_home"].count("-") == 8
    assert d["lineup_away"].count("-") == 8
    assert "山野 太一(投)" in d["lineup_home"]


def test_merge_writes_yahoo_lineup_source():
    research = {}
    merge_into_research(research, {}, parse_game(_FINISHED + _dasen(_CL9) + _dasen(_PL9)))
    assert research["home_lineup"]["source"] == "Yahoo"
    assert len(research["home_lineup"]["order"].split("-")) == 9


def test_score_card_drops_other_days():
    """주간 표의 어제 경기를 오늘 날짜로 적재하면 안 된다."""
    from app.collectors.yahoo_npb import parse_finals, score_card_html

    html = '''
    <div id="gm_card">
      <a href="/npb/game/2021039331/index">神宮 ヤクルト 巨人 6 - 8 試合終了</a>
    </div>
    <div id="week_table">
      <a href="/npb/game/2021039200/index">ZOZOマリン ロッテ ソフトバンク 3 - 1 試合終了</a>
    </div>
    '''
    today = parse_finals(score_card_html(html))
    mixed = parse_finals(html)
    assert [g["game_id"] for g in today] == ["2021039331"]
    assert {g["game_id"] for g in mixed} == {"2021039331", "2021039200"}

