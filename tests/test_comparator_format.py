"""[§9-3단] 출력 형식 — **결론이 눈에 들어와야 한다.**

🔴 실사고 2026-08-27: 3단 결론이 200자 문단 안에 파묻혀 사용자가 못 읽었다.
   그리고 슬레이트 첫 화면에는 아예 없어서 경기별 드릴다운을 눌러야 보였다.
"""
import pytest

from app.engine import comparator as C
from app.engine.card import CELLS, compare_lines, slate_compare_row

LONG = ("KIA는 타선 OPS .792 ▲·최근 3경기 31득점 ▲·포스트시즌 경쟁권 내 무게 ▲로 "
        "세 칸이 유리하고, 롯데는 최근 3경기 LLL 17득점 27실점 ▼로 불리하며, "
        "선발도 양현종 ▼ 대 나균안 =으로 KIA가 열세이나 뒤집기 어렵다")


def _jg(cells, compare):
    return {"home": "Kia Tigers", "away": "Lotte Giants",
            "home_kr": "KIA 타이거즈", "away_kr": "롯데 자이언츠",
            "cells": cells, "compare": compare, "cells_status": "판정"}


KIA_CELLS = {
    "home": {"batting": {"symbol": "▲", "reason": "팀 OPS .792로 리그 상위권 수준이다"},
             "recent3": {"symbol": "▲", "reason": "최근 3경기 WWL·31득점 24실점"},
             "weight": {"symbol": "▲", "reason": "4위·선두와 5.5게임차·잔여 30경기"},
             "starter": {"symbol": "▼", "reason": "양현종 시즌 ERA 4.19·평균 4.81이닝"},
             "bullpen": {"symbol": "▼", "reason": "직전 경기 투수 9명·구원 37타자"}},
    "away": {"batting": {"symbol": "=", "reason": "팀 OPS 0.727 중위권"},
             "recent3": {"symbol": "▼", "reason": "최근 3경기 LLL·17득점 27실점"},
             "weight": {"symbol": "▼", "reason": "6위·선두와 16.5게임차"},
             "starter": {"symbol": "=", "reason": "나균안 ERA 4.00·평균 5.73이닝"},
             "bullpen": {"symbol": "▼", "reason": "직전 경기 투수 6명·구원 25타자"}},
}


# ------------------------------------------------------------ [1] 3줄 형식

def test_conclusion_is_three_short_lines():
    jg = _jg(KIA_CELLS, {"favored": "home", "confidence": "보통",
                         "counts": {"home": 3, "away": 1, "even": 1, "unknown": 0},
                         "reason": LONG})
    out = compare_lines(jg)
    assert len(out) == 3
    assert out[0].startswith("🟡 KIA 타이거즈 우세")
    assert "3칸 대 1칸" in out[0] and "확신 보통" in out[0]
    assert out[1].startswith("▲") and out[2].startswith("▼")
    assert "롯데 자이언츠 우위" in out[2], "반대 방향 칸을 숨기면 안 된다"


def test_long_reason_never_reaches_the_headline():
    """🔴 문단이 결론 줄에 실리면 결론이 파묻힌다."""
    jg = _jg(KIA_CELLS, {"favored": "home", "confidence": "보통",
                         "counts": {"home": 3, "away": 1}, "reason": LONG})
    for line in compare_lines(jg):
        assert len(line) < 80, f"결론 줄이 너무 길다({len(line)}자): {line}"
        assert LONG[:30] not in line


def test_headline_carries_no_probability():
    jg = _jg(KIA_CELLS, {"favored": "home", "confidence": "높음",
                         "counts": {"home": 4, "away": 0}, "reason": "x"})
    assert "%" not in "\n".join(compare_lines(jg))


def test_undecidable_is_one_line():
    out = compare_lines(_jg(KIA_CELLS, {"favored": "none", "confidence": "낮음",
                                        "counts": {"home": 2, "away": 2}}))
    assert len(out) == 1 and "우열을 가리기 어렵다" in out[0]


def test_no_verdict_makes_no_lines():
    assert compare_lines(_jg(KIA_CELLS, {})) == []


# ------------------------------------------------------------ [3][4] 확신도

@pytest.mark.parametrize("won,expect", [(5, "높음"), (4, "높음"), (3, "보통"),
                                        (2, "보통"), (1, "낮음"), (0, "낮음")])
def test_confidence_follows_the_cell_gap(won, expect):
    """🔴 LLM이 매번 다르게 부르지 않도록 **코드가 정한다.**"""
    counts = {"home": won, "away": 0, "even": 5 - won, "unknown": 0}
    assert C.confidence_from(counts, "home") == expect


def test_uncollected_majority_demotes_one_level():
    """🔴 3칸이 비었는데 남은 2칸이 갈려 '2:0 = 보통'이면 얇은 카드가 두껍게 보인다."""
    thin = {"home": 2, "away": 0, "even": 0, "unknown": 3}
    assert C.confidence_from(thin, "home") == "낮음"
    thick = {"home": 2, "away": 0, "even": 3, "unknown": 0}
    assert C.confidence_from(thick, "home") == "보통"


def test_demotion_is_one_step_not_a_floor():
    high_but_thin = {"home": 4, "away": 0, "even": 0, "unknown": 3}
    assert C.confidence_from(high_but_thin, "home") == "보통"


def test_no_favored_side_is_lowest():
    assert C.confidence_from({"home": 3, "away": 0}, "none") == "낮음"


# ------------------------------------------------------------ 칸 셈

def test_cell_counts_compare_both_sides():
    """한쪽만 ▲인 것과 양쪽 다 ▲인 것은 다르다 — 후자는 차이가 아니다."""
    payload = C.build_payload(_jg(KIA_CELLS, {}))
    c = C.cell_counts(payload)
    assert c == {"home": 3, "away": 1, "even": 1, "unknown": 0}


def test_unjudged_cell_counts_for_neither_side():
    """🔴 모르는 것을 유리·불리로 세면 얇은 카드가 두꺼워 보인다."""
    one_sided = {"home": {"batting": {"symbol": "▲", "reason": "OPS .792"}},
                 "away": {}}
    c = C.cell_counts(C.build_payload(_jg(one_sided, {})))
    assert c["home"] == 0 and c["away"] == 0 and c["unknown"] == len(CELLS)


# ------------------------------------------------------------ [2][5] 슬레이트

def test_slate_row_is_one_compact_line():
    row = slate_compare_row(_jg(KIA_CELLS, {
        "favored": "home", "confidence": "보통",
        "counts": {"home": 3, "away": 1}, "reason": LONG}))
    assert row == "· 롯데 자이언츠 @ KIA 타이거즈 — KIA 타이거즈 우세 (3:1, 보통)"


def test_unjudged_game_stays_in_the_list():
    """🔴 조용히 빠지면 분석된 것으로 오인된다 — 몇 경기가 빠졌는지 알아야 한다."""
    jg = _jg({"home": {}, "away": {}}, {})
    jg["cells_status"] = "판정 미수행"
    row = slate_compare_row(jg)
    assert "판정 미수행" in row and "LLM 응답 없음" in row


def test_card_compare_failure_is_named_differently():
    """2단은 됐는데 3단이 실패한 경우를 구분한다 — 원인이 다르면 대응도 다르다."""
    jg = _jg(KIA_CELLS, {})
    row = slate_compare_row(jg)
    assert "카드 대조 실패" in row


def test_slate_summary_is_wired_into_the_card():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/pipeline.py").read_text(encoding="utf-8")
    assert "slate_compare_row" in src, "슬레이트 요약이 배선되지 않았다"


# ------------------------------------------------- 실응답에서 나온 결함 3건

def test_label_is_not_repeated_in_the_snippet():
    """🔴 "최근 3경기 최근 3경기 WWL"이 나갔다."""
    jg = _jg({"home": {"recent3": {"symbol": "▲", "reason": "최근 3경기 WWL·31득점"}},
              "away": {"recent3": {"symbol": "▼", "reason": "최근 3경기 LLL"}}},
             {"favored": "home", "counts": {"home": 1, "away": 0}})
    up = [l for l in compare_lines(jg) if l.startswith("▲")][0]
    assert up.count("최근 3경기") == 1, up


def test_snippet_never_cuts_inside_a_paren():
    """🔴 "2경기 연속 등판자 2명(김민"처럼 읽을 수 없는 조각이 나갔다."""
    long_paren = "2경기 연속 등판자 2명(김민수·박정훈)으로 불펜이 얇다"
    jg = _jg({"home": {"bullpen": {"symbol": "▲", "reason": long_paren}},
              "away": {"bullpen": {"symbol": "▼", "reason": "x"}}},
             {"favored": "home", "counts": {"home": 1, "away": 0}})
    up = [l for l in compare_lines(jg) if l.startswith("▲")][0]
    assert up.count("(") == up.count(")"), f"괄호가 열린 채 잘렸다: {up}"


def test_both_sides_down_is_not_an_opponent_advantage():
    """🔴 양쪽 다 ▼인 칸이 "상대 우위"로 둔갑했다 (실측: 한화·SSG 선발 둘 다 ▼).

    한쪽 부호만 보고 고르면 거짓말이 된다 — 칸 기울기로 골라야 한다.
    """
    both_down = {"home": {"starter": {"symbol": "▼", "reason": "ERA 5.95"},
                          "recent3": {"symbol": "▲", "reason": "WWL 14득점"}},
                 "away": {"starter": {"symbol": "▼", "reason": "ERA 13.5"},
                          "recent3": {"symbol": "▼", "reason": "LLL 5득점"}}}
    jg = _jg(both_down, {"favored": "home", "counts": {"home": 1, "away": 0}})
    out = "\n".join(compare_lines(jg))
    assert "우위" not in out or "선발" not in out.split("▼")[-1], \
        f"양쪽 다 ▼인 칸을 상대 우위로 썼다: {out}"


def test_tilt_needs_both_sides():
    """한쪽 판정이 없으면 기울기를 모른다 — 모름을 우위로 세지 않는다."""
    from app.engine.card import tilt_by_cell

    t = tilt_by_cell({"home": {"starter": {"symbol": "▲"}}, "away": {}})
    assert t["starter"] is None


def test_symbol_values_have_one_definition():
    """부호 수치값이 두 곳에 있으면 한쪽만 고쳐 어긋난다."""
    from app.engine.card import SYM_VALUE
    from app.engine.comparator import _SYM_VALUE

    assert SYM_VALUE is _SYM_VALUE


def test_snippet_ends_on_a_number_not_a_dangling_particle():
    """🔴 "5실점으로"·"OPS .792로"가 말이 끊긴 것처럼 읽혔다."""
    from app.engine.card import _snippet

    assert _snippet("팀 OPS .792로 리그 상위권 수준의 타선이다", "타선") == "OPS .792"
    assert _snippet("최근 3경기 WWL·14득점 5실점으로 살아났다", "최근 3경기") \
        == "WWL 14득점 5실점"


def test_snippet_keeps_meaning_over_a_bare_number():
    """🔴 "2경기 연속 등판 없음"이 "2경기"만 남으면 뜻이 사라진다."""
    from app.engine.card import _snippet

    out = _snippet("‘2경기 연속 등판 없음’과 여유가 있다", "불펜 가용")
    assert len(out.split()) >= 2, out


def test_parenthetical_is_dropped_not_glued():
    """🔴 기호만 지우면 "득점력(회당 10.33점)" → "득점력회당"이 된다."""
    from app.engine.card import _snippet

    out = _snippet("31득점 24실점으로 득점력(회당 약 10.33점)이 활발하다", "최근 3경기")
    assert "득점력회당" not in out and "(" not in out
