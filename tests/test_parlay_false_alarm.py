"""조합 0건이 언제 실패인가 — 2026-09-06 NPB 오탐.

🔴 조합은 **정의상 2경기 이상**이다(`parlay.build_tiered_parlays` 가
   `distinct_games < 2` 면 빈 목록을 낸다). 그런데 파이프라인은 배당 있는
   레그가 한 경기분뿐일 때도 🔴 실패로 기록했다:
     "🔴 [NPB] 조합 구성 0/1건 — 데이터 없음 (조합 0건 / 승인 레그 1개)"
   워치독 오탐 한 건이 진짜 고장 하나를 묻는다(실사고 2026-09-02).
"""
from __future__ import annotations

import pathlib

from app.engine.parlay import build_tiered_parlays

SRC = pathlib.Path("app/pipeline.py").read_text(encoding="utf-8")


def _leg(gid, p=0.62, odds=1.8):
    return {"game_id": gid, "p": p, "odds": odds, "side": "home",
            "market": "h2h", "confidence": "medium"}


def test_one_game_cannot_form_a_parlay():
    out = build_tiered_parlays([_leg(1)], None, "npb")
    assert out["combos"] == []
    assert "조합 성립 불가" in out["reason"]


def test_two_legs_from_the_same_game_still_cannot():
    """같은 경기 레그 둘은 조합이 아니다 — 경기 수로 세야 한다."""
    out = build_tiered_parlays([_leg(1), {**_leg(1), "side": "away"}], None, "npb")
    assert out["combos"] == []


def test_two_games_can():
    out = build_tiered_parlays([_leg(1), _leg(2)], None, "npb")
    assert out["combos"], out


def test_pipeline_counts_games_not_legs():
    seg = SRC[SRC.index("_priced_legs = "):]
    seg = seg[:seg.index("from app.research.deep import")]
    assert "_priced_games" in seg, "레그 수로만 판단하고 있다"
    assert "distinct" in seg or "set(" in seg or "{l.get(\"game_id\")" in seg


def test_single_game_is_recorded_as_normal_not_failure():
    seg = SRC[SRC.index("_priced_legs = "):]
    seg = seg[:seg.index("from app.research.deep import")]
    i = seg.index("_priced_games < 2")
    block = seg[i:i + 600]
    assert "zero_ok=True" in block, "한 경기분인데 실패로 기록한다"
    assert "정상" in block
