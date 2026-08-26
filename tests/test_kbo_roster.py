"""[A-2단계] KBO 1군 등록 명단 → 결장 판정.

KBO는 **말소로 결장을 알린다.** 그동안 이 정보는 Perplexity 산문에서만 왔는데
(실측: KBO 캐시 5건 중 absences 채움 0), 공식 명단이 공개돼 있다.
"""

from app.collectors.kbo_roster import (
    absent_regulars,
    merge_into_research,
    parse_registered,
)
from app.collectors.kbo_usage import parse_batters, regulars_from

# 실제 응답 구조 축약 (RegisterAll.aspx)
HTML = """
<table><tr><th>구단</th><th>감독(1)</th><th>코치(10)</th><th>투수(14)</th>
<th>포수(4)</th><th>내야수(8)</th><th>외야수(8)</th></tr>
<tr><td>KIA45명</td><td>이범호(71)</td><td>정재훈(72)</td><td>네일(1)황동하(29)</td>
<td>김태군(42)</td><td>김도영(5)나성범(47)</td><td>김호령(30)이우성(4)</td></tr>
<tr><th>구단</th><th>감독(1)</th><th>코치(9)</th><th>투수(15)</th>
<th>포수(3)</th><th>내야수(8)</th><th>외야수(7)</th></tr>
<tr><td>롯데43명</td><td>김태형(88)</td><td>주형광(70)</td><td>로드리게스(43)</td>
<td>손성빈(23)</td><td>나승엽(51)고승민(7)</td><td>황성빈(31)레이예스(27)</td></tr>
</table>"""


def test_parse_registered_reads_batters_by_header_position():
    """열 순서를 상수로 박으면 구조가 바뀔 때 조용히 어긋난다 — 헤더로 찾는다."""
    out = parse_registered(HTML)
    assert set(out) == {"Kia Tigers", "Lotte Giants"}
    assert out["Kia Tigers"] == {"김태군", "김도영", "나성범", "김호령", "이우성"}
    assert "네일" not in out["Kia Tigers"], "투수가 야수 명단에 섞였다"
    assert "이범호" not in out["Kia Tigers"], "감독이 섞였다"


def test_parse_registered_empty_html_is_empty():
    assert parse_registered("<html></html>") == {}


# ---------------------------------------------------------------- 결장 판정

REGULARS = [{"name": f"선수{i}", "pa": 15 - i, "rank": i} for i in range(1, 10)]


def test_absent_regular_is_detected():
    """🔴 핵심 — 주전인데 등록 명단에 없으면 결장이다."""
    registered = {r["name"] for r in REGULARS} - {"선수3"}
    out = absent_regulars(REGULARS, registered)
    assert [a["name"] for a in out] == ["선수3"]
    assert out[0]["reason"] == "1군 말소" and out[0]["rank"] == 3


def test_non_regular_absence_is_ignored():
    """등록 명단에 없어도 주전이 아니면 결장으로 세지 않는다 — 매일 쏟아진다."""
    assert absent_regulars(REGULARS, {r["name"] for r in REGULARS}) == []


def test_empty_roster_never_marks_everyone_absent():
    """🔴 수집 실패를 사실로 바꾸는 최악의 유형 — 명단이 비면 전원 결장이 된다.

    그러면 그 경기 λ가 통째로 무너진다.
    """
    assert absent_regulars(REGULARS, set()) == []


# ---------------------------------------------------------------- 주전 산출

BOX = {"battersBoxscore": {"home": [
    {"name": "김도영", "ab": 4, "bb": 1, "batOrder": 1},
    {"name": "나성범", "ab": 3, "bb": 2, "batOrder": 2},
    {"name": "대타김", "ab": 1, "bb": 0, "batOrder": 2},   # 교체 — 타석이 적다
]}}


def test_regulars_rank_by_plate_appearances():
    """'타석 상위 9명 중 결장 = 주전'이 규칙이다. PA = 타수 + 볼넷으로 센다."""
    games = [{"batters": parse_batters(BOX, "home")} for _ in range(3)]
    reg = regulars_from(games)
    assert [r["name"] for r in reg] == ["김도영", "나성범", "대타김"]
    assert reg[0]["pa"] == 15 and reg[0]["rank"] == 1
    assert reg[2]["pa"] == 3, "교체 선수가 주전 앞에 오면 판정이 뒤집힌다"


def test_regulars_caps_at_nine():
    games = [{"batters": [{"name": f"P{i}", "pa": 20 - i} for i in range(15)]}]
    assert len(regulars_from(games)) == 9


def test_zero_pa_players_are_not_regulars():
    games = [{"batters": [{"name": "안나옴", "pa": 0}]}]
    assert regulars_from(games) == []


# ---------------------------------------------------------------- 병합

def test_merge_appends_and_does_not_overwrite_deep_search():
    """공시는 말소만 안다. 딥서치는 부상·휴식을 알 수 있다 — 배타적이지 않다."""
    research = {"absences": ["딥서치가 준 결장 정보"],
                "home_usage": {"regulars": REGULARS}}
    jg = {"home": "Kia Tigers", "away": "Lotte Giants"}
    roster = {"Kia Tigers": {r["name"] for r in REGULARS} - {"선수2"}}
    filled = merge_into_research(research, jg, roster)
    assert filled == ["absences"]
    assert research["absences"][0] == "딥서치가 준 결장 정보", "딥서치 값을 덮었다"
    assert any("선수2" in x and "1군 말소" in x for x in research["absences"])
    # 중요도가 문장에 들어가야 판정이 무게를 잴 수 있다
    assert any("타석" in x and "주전" in x for x in research["absences"])


def test_merge_is_idempotent():
    research = {"home_usage": {"regulars": REGULARS}}
    jg = {"home": "Kia Tigers", "away": "Lotte Giants"}
    roster = {"Kia Tigers": {r["name"] for r in REGULARS} - {"선수2"}}
    merge_into_research(research, jg, roster)
    n = len(research["absences"])
    merge_into_research(research, jg, roster)
    assert len(research["absences"]) == n, "같은 결장이 중복 기록됐다"
