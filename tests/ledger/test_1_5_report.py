"""[RPT-1] 원장 성적표 — 축별·판정자별.

🔴 09-17 [149] "report.py 는 사람이 부른다 — 원장에서 행을 뽑아 넣는 도구가 없다".
   실제로 `tools/report.py` 가 없었다(P0-C).
🔴 **계수기 규율**(09-08): 세기 전에 그 계수기가 무엇을 세는지 확인한다.
   `hit` 은 True/False/None 셋이고, `void` 행이 따로 있다. 분모에서 무엇을
   뺐는지 **찍지 않으면** 적중률이 조용히 부풀거나 줄어든다.
"""
from __future__ import annotations

import pytest


def test_도구가_있다():
    from tools import report

    assert hasattr(report, "main")


def test_by_는_허용목록이다():
    """🔴 임의 문자열을 SQL 에 넣지 않는다 — 컬럼명은 화이트리스트다."""
    from tools.report import BY_COLUMNS

    assert "judge_by" in BY_COLUMNS
    assert "main_axis" in BY_COLUMNS
    assert "market" in BY_COLUMNS
    assert "sport" in BY_COLUMNS


def test_모르는_축은_거부한다():
    from tools.report import check_by

    with pytest.raises(SystemExit):
        check_by("judge_by; DROP TABLE pick_ledger")
    assert check_by("judge_by") == "judge_by"


def test_적중률_분모가_무엇을_뺐는지_센다():
    """🔴 분모에서 뺀 것을 세지 않으면 그 숫자는 검증할 수 없다."""
    from tools.report import summarize

    rows = [
        {"k": "fable_chat", "hit": True,  "void": False, "clv": 0.02},
        {"k": "fable_chat", "hit": False, "void": False, "clv": -0.01},
        {"k": "fable_chat", "hit": None,  "void": False, "clv": None},   # 미채점
        {"k": "fable_chat", "hit": True,  "void": True,  "clv": None},   # 무효
        {"k": "bot_v14",    "hit": None,  "void": False, "clv": None},
    ]
    out = summarize(rows)
    f = out["fable_chat"]
    assert f["n"] == 4
    assert f["graded"] == 2          # hit 이 True/False 이고 void 가 아닌 것만
    assert f["hit"] == 1
    assert f["rate"] == pytest.approx(0.5)
    assert f["ungraded"] == 1
    assert f["void"] == 1
    assert f["clv_n"] == 2
    assert f["clv_avg"] == pytest.approx(0.005)
    b = out["bot_v14"]
    assert b["graded"] == 0 and b["rate"] is None   # 표본 0 → 비율을 지어내지 않는다


def test_표본_0_이면_그렇게_찍는다():
    from tools.report import render

    text = render({"fable_chat": {"n": 3, "graded": 0, "hit": 0, "rate": None,
                                  "ungraded": 3, "void": 0,
                                  "clv_n": 0, "clv_avg": None}}, by="judge_by")
    assert "표본 0" in text, text
    assert "%" not in text.split("표본 0")[0].splitlines()[-1], text


def test_전체가_비면_조용히_끝내지_않는다():
    from tools.report import render

    text = render({}, by="judge_by")
    assert "표본 0" in text
