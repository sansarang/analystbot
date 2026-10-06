"""§7 방아쇠 계약 — **수동 12단계 ⑫** (사용자 지시 2026-10-02).

🔴 **방아쇠의 상한은 지어낸 숫자가 아니다** — 변수를 빼고 §5·§6 을 다시 돌린 값이다.
   그것이 이 파일이 검사하는 전부다. 숫자를 여기 적지 않는다.
⚠️ 단계 8 자리이나 `tests/stage8/` 은 서명이 없어 수집되지 않는다 — 돌아가는 자리에 둔다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app import cells, classify, league, rules, scenarios, triggers
from app.types import Market

ROOT = Path(__file__).resolve().parents[2]
HOME, AWAY = "Sacramento Republic FC", "Las Vegas Lights FC"


class _G:
    def __init__(self, sport="soccer", league_name="USL Championship"):
        self.home, self.away, self.sport = HOME, AWAY, sport
        # 🔴 §5-a C 가 **리그 규정**(무승부 가능 여부)을 읽는다 — 대역도 들고 있어야 한다
        self.league = league_name


def _v(text, vtype, direction, hardness="hard"):
    """변수 하나. 🔴 `classify.Classified` 를 그대로 쓴다(대역이 아니다)."""
    return classify.Classified(text=text, source_url="https://x/1",
                               hardness=hardness, type=vtype,
                               direction=direction, why="시험",
                               dateless_reason="시험 자료", team=None)




# ══════════════════════════════════════════════════════════════════
# "언제 보나" — 🔴 yaml → cells.WAKE 에서 나온다
# ══════════════════════════════════════════════════════════════════


def test_모든_유형에_뒤집는_세포가_적혀_있다():
    """🔴 §9 단계 5 완료 조건 — *"§4 유형표 전 항목에 **세포 질문 매핑**"*.

    ⚠️ 어휘는 `cells.Q_TYPES` 다 — yaml 에서 새 이름을 만들면 여기서 빨개진다.
    """
    types = rules.variable_types()
    miss = [k for k, v in types.items() if not v.get("watch")]
    assert not miss, f"`watch` 가 없는 유형 {miss}"
    bad = [(k, v["watch"]) for k, v in types.items()
           if v["watch"] not in cells.Q_TYPES]
    assert not bad, f"`cells.Q_TYPES` 에 없는 이름 {bad}"


def test_언제_보나를_세포_시각에서_계산한다():
    """🔴 시각을 방아쇠에 적지 않는다 — `cells.WAKE` 가 원본이다(사본 금지)."""
    got = triggers.when_of("individual")
    q = rules.variable_types()["individual"]["watch"]
    mins = cells.WAKE[q][0]
    assert str(mins) in got and q in got, (got, q, mins)
    # 🔴 창이 없는 질문(아침 1회)은 분을 **지어내지 않는다**
    assert "하루 1회" in triggers.when_of("stakes")
    # 🔴 모르는 유형은 **모른다고** 적는다
    assert "모른다" in triggers.when_of("없는유형")


# ══════════════════════════════════════════════════════════════════
# 상한 — 🔴 반사실 재계산이다
# ══════════════════════════════════════════════════════════════════










# ══════════════════════════════════════════════════════════════════
# 🔴🔴 이 계약이 가장 중요하다 — **변수가 생존에 닿지 않는다**
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════════




