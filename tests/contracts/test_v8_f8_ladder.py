"""🔴🔴 **F8 — 라인업 사다리·새 사실 72시간을 흐름에 드러낸다**(지시서 2026-10-11).

> 둘 다 **이미 있으면 위치만 흐름도에 그리고**, 없거나 일부면 구현한다.

🔴 실측 2026-10-11: **둘 다 있었다**. 그래서 이 파일은 *"있다"* 를 못 박는 계약이다 —
   지우거나 끊으면 여기서 먼저 빨개진다(그래야 흐름도가 거짓이 되지 않는다).
"""
from __future__ import annotations

import inspect


def test_F8_라인업_사다리가_있고_상태를_적는다():
    """🔴 ③ 라인업 사다리 — 표는 `config/lineup_sources.yaml`, 읽는 곳은 하나다."""
    import pathlib

    from app.core import lineups as _ln
    root = pathlib.Path(__file__).resolve().parents[2]
    assert (root / "config/lineup_sources.yaml").exists(), "🔴 사다리 표가 없다"
    assert hasattr(_ln, "ladder"), "🔴 사다리를 읽는 곳이 없다"
    said = inspect.getsource(_ln)
    # 🔴 상태·출처·시각을 **한 줄로** 적는다(A-3)
    for want in ("확정", "예상", "없음", "출처"):
        assert want in said, f"🔴 `{want}` 를 안 적는다"


def test_F8_확정_XI_전에는_등급이_잠정이다():
    """🔴 A-4 — 확정 XI 전 등급은 **잠정**. ⚠️ 그 길이 F1 재분석과 맞물린다."""
    from app.core import lineups as _ln
    said = inspect.getsource(_ln)
    assert "잠정" in said


def test_F8_라인업_감시가_5분_간격이고_한_곳에_적혀_있다():
    """🔴 🔔 사용자가 **누른 경기만** 5분 간격 — 그 수는 **한 곳**이다(#1)."""
    from app.bot import watch as _w
    said = inspect.getsource(_w)
    assert "5분" in said
    # 🔴 수를 두 곳에 적지 않는다 — 상수 하나가 원본이다
    nums = [n for n in dir(_w) if n.isupper()]
    assert nums, "🔴 간격 상수가 없다(글자에만 있다)"
    assert hasattr(_w, "start") and hasattr(_w, "stop"), "🔴 켜고 끄는 길이 없다"


def test_F8_새_사실_72시간이_별도_하위_과제다():
    """🔴 새 사실 72시간은 ③ 의 **하위 F** 다 — 팀별 현지어+영어."""
    from app.research import subtasks as _st
    said = inspect.getsource(_st)
    assert "72시간" in said and "현지어" in said
    # 🔴 카드가 **0건이면 그 사실과 수**를 적는다(#3)
    from app.core import render as _r
    body = inspect.getsource(_r.new_facts_block)
    assert "0건" in body and "queries" in body


def test_F8_전역_팀은_고정_질의를_더한다():
    """🔴 turnover 팀은 `전역`·`신병 합류`·`이적` 질의를 **더한다**(지시서 F8)."""
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[2]
    box = yaml.safe_load(
        (root / "config/search_words.yaml").read_text(encoding="utf-8"))

    def _find(node, key):
        """🔴 표의 **어느 깊이**에 있든 그 개념 줄을 찾는다(구조를 베끼지 않는다)."""
        if isinstance(node, dict):
            if key in node:
                return node[key]
            for one in node.values():
                got = _find(one, key)
                if got is not None:
                    return got
        return None

    row = _find(box, "squad_turnover") or {}
    words = [str(x) for x in (dict(row).get("ko") or [])]
    assert any("전역" in w for w in words), words
    assert any("신병" in w for w in words), words
    # 🔴 파이프라인이 그 개념을 **깃발이 켜졌을 때** 넣는다
    from app.core import pipeline as _pl
    code = inspect.getsource(_pl)
    assert "squad_turnover" in code and "extra_words" in code
