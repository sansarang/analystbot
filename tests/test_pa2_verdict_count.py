"""PA-2 계약 — "판정이 있는가"를 한 곳에서 판정한다.

🔴 PART A 실측(2026-09-16 · ORDER_V3=1): v3 가 승자 2건을 냈는데 같은 실행이
   `게이트·발송 0/2경기 — 판정 0` 이라고 보고했다. 규칙이 세 벌이었고
   파이프라인 집계만 달랐다.
"""
import pathlib

from app.engine import matchup as M
from app.engine import pregame_push as PP

#: v3 가 실제로 만드는 모양 (`matchup.py:618`) — p_home 없음, jg["model"] 없음.
JG_V3 = {"game_id": 8312, "sport": "mlb",
         "home": "Los Angeles Angels", "away": "Seattle Mariners",
         "matchup": {"승자": "Seattle Mariners", "확신": "중",
                     "model": "gemini/gemini-3.5-flash-lite"},
         "winner": "Seattle Mariners", "p_claude": 0.46}

#: v2 모양 — 확률과 model 이 둘 다 있다.
JG_V2 = {"game_id": 1, "matchup": {"p_home": 0.55, "model": "m"},
         "model": "m", "p_claude": 0.55}


def test_판정_기준은_한_곳이다():
    """🔴 사본 금지 — 위임이 아니라 **같은 함수**여야 한다."""
    assert PP._judged is M.has_verdict


def test_v3_판정을_센다():
    """p_home 도 jg['model'] 도 없지만 판정이다."""
    assert M.has_verdict(JG_V3) is True


def test_v2_판정도_센다():
    assert M.has_verdict(JG_V2) is True


def test_판정이_없으면_없음이다():
    """🔴 반대 위험 — 전부 '있음'으로 세면 조용한 0 을 못 잡는다."""
    assert M.has_verdict({"game_id": 2, "matchup": {}}) is False
    assert M.has_verdict({"game_id": 3}) is False
    assert M.has_verdict({}) is False
    # 숫자가 아닌 값도 판정이 아니다
    assert M.has_verdict({"p_claude": "0.5"}) is False
    assert M.has_verdict({"p_claude": None}) is False


def test_발송_규칙_자체는_안_바뀐다():
    """🔴 반대 위험 — 규칙을 바꾸면 카드가 달라진다. 바꾼 것은 **세는 방법**뿐."""
    assert M.has_verdict({"p_claude": 0.0}) is True      # 0.0 도 숫자다
    assert M.has_verdict({"p_claude": 1}) is True


def _pipeline_block() -> str:
    src = pathlib.Path("app/pipeline.py").read_text(encoding="utf-8")
    return src.split('await record("게이트·발송"')[0][-1800:]


def test_집계가_공용_술어를_쓴다():
    blk = _pipeline_block()
    assert "_has_verdict(_g)" in blk, "집계가 공용 술어를 안 쓴다"


def test_집계가_자기_규칙을_안_들고_있다():
    """종전 인라인 조건이 남아 있으면 v3 를 또 못 본다."""
    blk = _pipeline_block()
    assert 'get("p_home") is not None' not in blk
    assert '_g.get("model")' not in blk


def test_원장_기준과는_합치지_않는다():
    """🔴 반대 위험 — '원장에 남길 판정'과 '발송할 판정'은 다른 질문이다.

    ORD-3 는 확률 없이 승자만 있는 판정도 **일부러** 원장에 남긴다.
    그 경기는 발송 대상이 아니다(확률이 없으면 카드를 못 만든다).
    """
    from app.engine import pick_ledger as PL

    winner_only = {"game_id": 9, "sport": "mlb", "home": "A", "away": "B",
                   "matchup": {"승자": "A", "확신": "중"}, "winner": "A"}
    assert PL._row_from_game(winner_only,
                             {"sport": "mlb", "date": "2026-09-16"}, {}) is not None
    assert M.has_verdict(winner_only) is False
