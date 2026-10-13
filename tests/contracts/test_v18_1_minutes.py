"""🔴🔴 **§1 출전 시간(교체 시각)** — 라인업 지시서 2026-10-13 §1.

> `app/collect/minutes.py` — 경기별 선수 출전 구간 `[in, out]` · 득점 분 · 퇴장 분
> (`before_as_of`) · 신원표로 id 매칭(실패율 **경기별 기록**).
> 계약 **MN1**: 킥오프 **이후** 정보로 다른 경기 구간을 채우면 실패.
> 계약 **MN2**: 매칭 **실패 선수를 0분으로** 넣으면 실패(⬜).

🔴 원천(실측 2026-10-13):
   · J리그 — `data.j-league.or.jp/SFMS02/?match_card_id=N` 이 **서버 렌더**이고
     `交代イベント情報エリア` 에 `▽ 나간 선수 / 61' / ▲ 들어온 선수` 가 있다.
     robots 허용 ✅. ⚠️ `www.jleague.jp` 쪽은 **SPA 껍데기**다(같은 HTML 이 모든
     경기에 온다 · `試合経過` 는 **i18n 글자**였다) — 그 길은 쓰지 않는다.
   · K리그 — `www.kleague.com/match` 는 **빈 응답(len 0)** 이다 → 통로 없음.
   · fotmob — `Substitution` 사건이 **없다**(실측 세 번) → 통로 없음.
   🔴 그래서 **K1·그 밖은 "거친 판"**(선발 90분)이고 그 사실을 이름으로 적는다.
"""
from __future__ import annotations

from datetime import UTC, datetime

KICK = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def test_parses_substitution_minutes() -> None:
    """🔴 `▽ … 61' … ▲ …` 를 **나간 선수·들어온 선수·분**으로 읽는다."""
    from app.collect import minutes as mn
    said = ("交代イベント情報エリア Start --> |交代| |&nbsp;| | ▽ | | 三井寺 眞| "
            "|61'| | |&nbsp;| | ▲ | | オナイウ 情滋| || |&nbsp;| | ▽ | | 谷村 海那| "
            "|69'| | |&nbsp;| | ▲ | | 二田 理央| ||")
    got = mn.subs_of_jleague(said)
    assert got == [{"min": 61, "out": "三井寺 眞", "in": "オナイウ 情滋"},
                   {"min": 69, "out": "谷村 海那", "in": "二田 理央"}], got


def test_intervals_from_subs() -> None:
    """🔴 선발·교체 → **구간** `[in, out]`. ⚠️ 못 센 선수는 **구간이 없다**(⬜)."""
    from app.collect import minutes as mn
    got, why = mn.intervals(starters=["A", "B"], subs=[
        {"min": 61, "out": "A", "in": "C"}], bench=["C", "D"])
    assert got["A"] == (0, 61) and got["B"] == (0, 90) and got["C"] == (61, 90)
    # 🔴🔴 **MN2** — 뛰지 않은 벤치 선수는 **0 분으로 넣지 않는다**(칸이 없다)
    assert "D" not in got, got
    assert "D" in why


def test_mn1_no_cross_match_fill() -> None:
    """🔴🔴 **MN1** — 다른 경기(킥오프 이후) 자료로 구간을 채우지 않는다."""
    from app.collect import minutes as mn
    rows = [{"utc": "2026-09-19T10:00:00Z", "subs": [{"min": 61, "out": "A",
                                                      "in": "C"}]},
            {"utc": "2026-09-26T10:00:00Z", "subs": [{"min": 10, "out": "B",
                                                      "in": "D"}]}]
    got = mn.before(rows, as_of=KICK)
    assert len(got) == 0, got           # 🔴 그 경기 자신도 as_of 이전이 아니다
    got2 = mn.before(rows, as_of=datetime(2026, 9, 20, tzinfo=UTC))
    assert len(got2) == 1 and got2[0]["subs"][0]["out"] == "A"


def test_coarse_plate_is_named() -> None:
    """🔴 교체 시각이 없는 리그는 **거친 판**이고 그 사실을 적는다."""
    from app.collect import minutes as mn
    got, why = mn.intervals(starters=["A"], subs=None, bench=["B"])
    assert got["A"] == (0, 90)
    assert "거친 판" in why


def test_match_id_map_is_measured_not_guessed() -> None:
    """🔴 fotmob 경기 ↔ J리그 `match_card_id` 는 **날짜·팀으로 맞춘다**(추측 금지)."""
    from app.collect import minutes as mn
    said = mn.pick_card(rows=[{"card_id": "34517", "day": "2026-08-07",
                               "home": "横浜FM", "away": "鹿島"},
                              {"card_id": "34518", "day": "2026-08-08",
                               "home": "浦和", "away": "FC東京"}],
                        day="2026-08-08", home="Urawa Red Diamonds",
                        away="FC Tokyo")
    assert said == "34518", said
    assert mn.pick_card(rows=[], day="2026-08-08", home="x", away="y") is None


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **경기·선수를 **측정값으로** 맞춘다** — 이름 표를 손으로 쓰지 않는다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-13: 이름으로 맞추니 확보율이 **1.0%(3/290)** 였다 — J리그는
#     `横浜FM`·`鹿島` 로 줄여 쓰고 우리 목록은 fotmob 영어 이름이다.
#  🔴 그래서 **날짜 + 스코어**(둘 다 양쪽이 가진 수)로 경기를 맞추고, 선수는
#     **등번호**(J리그 `NUMBER` ↔ fotmob `shirtNumber`)로 잇는다.


def test_card_is_matched_by_day_and_score() -> None:
    """🔴 경기 맞춤 — **날짜 + 스코어**가 열쇠다(이름이 아니다)."""
    from app.collect import minutes as mn
    rows = [{"card_id": "1", "day": "2026-08-08", "score": (2, 0)},
            {"card_id": "2", "day": "2026-08-08", "score": (1, 3)}]
    assert mn.pick_card(rows=rows, day="2026-08-08", home="x", away="y",
                        score=(1, 3)) == "2"
    # 🔴 같은 날 같은 스코어가 **둘이면 안 맞춘다**(추측 금지)
    rows2 = [{"card_id": "1", "day": "d", "score": (1, 1)},
             {"card_id": "2", "day": "d", "score": (1, 1)}]
    assert mn.pick_card(rows=rows2, day="d", home="x", away="y",
                        score=(1, 1)) is None


def test_squad_numbers_are_parsed() -> None:
    """🔴 `POSITION | NUMBER | NAME` 에서 **이름 → 등번호**를 읽는다."""
    from app.collect import minutes as mn
    said = ("|先発| |POSITION| |NUMBER| |NAME| |TIME| ||GK|| |36| "
            "| ルベン ブランコ| || ||DF|| |13| | 井上 太聖| ||")
    got = mn.squad_of_jleague(said)
    assert got.get("ルベン ブランコ") == 36 and got.get("井上 太聖") == 13, got


def test_subs_become_numbers() -> None:
    """🔴 교체 이름 → **등번호 구간**(이름을 그대로 들고 가지 않는다)."""
    from app.collect import minutes as mn
    nums = {"A선수": 7, "B선수": 21}
    got, why = mn.intervals_by_number(
        starters={7: (0, 90), 9: (0, 90)},
        subs=[{"min": 60, "out": "A선수", "in": "B선수"}], names=nums)
    assert got[7] == (0, 60) and got[21] == (60, 90) and got[9] == (0, 90)
    assert "교체 1건" in why


def test_sides_are_split_and_subs_are_attributed_by_name() -> None:
    """🔴🔴 팀별 명단·교체 — **어느 팀인지는 이름이 말한다**(블록 순서를 안 믿는다).

    ⚠️ 실측 구조(2026-10-13 · `match_card_id=34517`): `先発`×2 → `控え`×2 →
       `交代`×2. 🔴 못 가린 교체는 **사유에 적는다**(조용히 버리지 않는다).
    """
    from app.collect import minutes as mn
    said = ("|先発| |POSITION| |NUMBER| |NAME| |TIME| ||GK|| |1| | 가| "
            "||FW|| |9| | 나|"
            "|先発| |POSITION| |NUMBER| |NAME| ||GK|| |2| | 다| "
            "||FW|| |10| | 라|"
            "|控え| |MF|| |21| | 마|"
            "|控え| |MF|| |22| | 바|"
            "|交代| ▽| | 나| |61'| ▲| | 마|"
            "|交代| ▽| | 라| |70'| ▲| | 바|")
    sides, why = mn.sides_of_jleague(said)
    assert sorted(sides["home"]["starters"].values()) == [1, 9], (sides, why)
    assert sorted(sides["away"]["starters"].values()) == [2, 10], (sides, why)
    assert [s["min"] for s in sides["home"]["subs"]] == [61], why
    assert [s["min"] for s in sides["away"]["subs"]] == [70], why
    # 🔴 어느 팀인지 못 가리면 **사유가 그 수를 적는다**
    _s2, why2 = mn.sides_of_jleague(said.replace("| 나| |61'|", "| 없는| |61'|"))
    assert "못 가린" in why2, why2


def test_squad_blocks_are_required() -> None:
    """⚠️ 명단 블록이 없으면 **빈 결과 + 사유**다(지어내지 않는다)."""
    from app.collect import minutes as mn
    got, why = mn.sides_of_jleague("<html>아무것도 없다</html>")
    assert got == {} and "🔴" in why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **동점 충돌** — 같은 날 같은 스코어가 둘이면 팀명이 깬다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-13: 날짜+스코어만으로는 **90경기 중 72(80.0%)** 다. 못 맞춘
#     18 건은 **전부** "같은 날 같은 스코어 2경기"였다(이름이 다르니 둘 다 버렸다).
#  🔴 그래서 팀명 표를 **맞춘 경기에서 배운다** — 손으로 쓰지 않는다(#1 사본 금지).


def test_names_are_learned_from_matched_games() -> None:
    """🔴 `{일본어: 영어}` 표는 **1:1 로 떨어진 짝만** 배운다(흔들리면 안 배운다)."""
    from app.collect import minutes as mn
    got = mn.learn_names([({"home": "横浜FM", "away": "鹿島"},
                           {"home": "Yokohama F.Marinos", "away": "Kashima"}),
                          ({"home": "横浜FM", "away": "神戸"},
                           {"home": "Yokohama F.Marinos", "away": "Kobe"})])
    assert got["横浜FM"] == "Yokohama F.Marinos"
    # 🔴 한 일본어 이름이 두 영어 이름에 붙으면 **버린다**(추측 금지)
    bad = mn.learn_names([({"home": "A", "away": "B"},
                           {"home": "X", "away": "Y"}),
                          ({"home": "A", "away": "C"},
                           {"home": "Z", "away": "W"})])
    assert "A" not in bad, bad


def test_learned_names_break_the_tie() -> None:
    """🔴 충돌(같은 날 같은 스코어 2경기)을 **배운 이름**이 깬다."""
    from app.collect import minutes as mn
    rows = [{"card_id": "1", "day": "d", "score": (2, 1), "home": "川崎F",
             "away": "清水"},
            {"card_id": "2", "day": "d", "score": (2, 1), "home": "柏",
             "away": "水戸"}]
    names = {"柏": "Kashiwa Reysol", "水戸": "Mito Hollyhock",
             "川崎F": "Kawasaki Frontale", "清水": "Shimizu S-Pulse"}
    assert mn.pick_card(rows=rows, day="d", home="Kashiwa Reysol",
                        away="Mito Hollyhock", score=(2, 1),
                        names=names) == "2"
    # 🔴 표가 없으면 그대로 **안 맞춘다**(없는 것을 지어내지 않는다)
    assert mn.pick_card(rows=rows, day="d", home="Kashiwa Reysol",
                        away="Mito Hollyhock", score=(2, 1)) is None


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **둘째 통로 — fotmob `playerStats` 의 "뛴 분"**(실측 2026-10-13)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 이 실측은 2026-10-12 의 *"fotmob 은 교체 시각을 주지 않는다"* 를 **덮는다**.
#     선수 칸의 `minutesPlayed` 는 비어 있지만 **경기 선수 기록**
#     (`content.playerStats`)에는 `minutes_played` 가 있다(두 리그 다 · 32명).
#  🔴 그것은 **in/out 시각이 아니라 뛴 분**이다 → 선발은 `[0, 분]`, 교체 투입은
#     `[90 − 분, 90]` 으로 읽고 **그 차이를 사유가 적는다**(지어내지 않는다).


def test_intervals_from_played_minutes() -> None:
    from app.collect import minutes as mn
    got, why = mn.intervals_from_minutes(
        starters=["s1", "s2"], bench=["b1", "b2"],
        played={"s1": 90.0, "s2": 60.0, "b1": 30.0})
    assert got["s1"] == (0, 90) and got["s2"] == (0, 60), got
    assert got["b1"] == (60, 90), got
    # 🔴 **MN2** — 안 뛴 벤치(b2)는 **칸이 없다**(0분 금지)
    assert "b2" not in got, got
    assert "뛴 분" in why and "in/out" in why, why


def test_played_minutes_plate_is_named_apart() -> None:
    """🔴 분이 **정확한 시각**인지 **뛴 분**인지 섞어 적지 않는다."""
    from app.collect import minutes as mn
    _got, why = mn.intervals_from_minutes(starters=["s1"], bench=[],
                                          played={})
    assert "🔴" in why and "없다" in why
