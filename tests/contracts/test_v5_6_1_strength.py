"""🔴🔴 **v5 §6-1·§6-7 — 무게는 변수 합·거짓 1.0.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]




# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_v5_6_1_무게는_늘_변수_합이다_M20`

def test_v5_6_7_거짓_1_0_의_다섯_조건이_있다_M9():
    """🔴 *"변수 5개 미만, 대량득점형 부재, 양 팀 연속 득점 폼인데 난타전 부재,
    시나리오 4개 미만"* 중 하나면 1.0 을 내지 않는다.

    ⚠️ 코드가 그 조건들을 **각각** 들고 있어야 한다(한 가드가 넷을 대신하면
       무엇이 걸렸는지 모른다).
    """
    import inspect

    from app import survive
    src = inspect.getsource(survive)
    for fn in ("_thin_set_guard", "_scoring_streak_guard"):
        assert fn in src, f"🔴 §6-7 가드 `{fn}` 가 없다"
    from app import scenarios
    assert scenarios.MIN_SCENARIOS == 4
    # 🔴 변수 개수 문턱이 **yaml** 에 있다(코드에 박지 않는다)
    assert survive._thin_set_vars() >= 1


# ══════════════════════════════════════════════════════════════════
# §8-7 · §9-5
# ══════════════════════════════════════════════════════════════════


# ── 대역 ──────────────────────────────────────────────────────────




def _draft(sid: str, strength: float):
    from app import scenarios
    return scenarios.Draft(id=sid, scores=["2-1"], strength=strength,
                           template_id="t", why="w", variables=["V1"],
                           added_by="template")




