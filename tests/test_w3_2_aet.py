"""[W3-2] 연장·승부차기 승부를 정규시간 승부처럼 채점하면 안 된다.

🔴 실측 2026-09-21: `games` 에 `result_basis` 칸이 **없다**. FotMob 은
   `reason.short` 로 `FT`·`AET`·`Pen` 을 주고 `status_of` 가 그것을 읽는데,
   저장할 자리가 없어 **버려지고 있었다**. 그러면 연장에 가서 3-2 로 끝난
   경기가 `home_score=3, away_score=2` 로만 남고, 1X2 채점이 그것을
   **정규시간 홈 승**으로 읽는다. 실제로는 90분에 2-2 무승부였을 수 있다.

🔴 지시문 W3-2: "점수는 저장하되 `result_basis` 를 기록하고 **1X2 자동 채점
   에서 제외**한다. 승부차기 득점은 합산 금지."

⚠️ 지금 운영에 AET/Pen 경기는 **0건**이다(09-20·21 적재에서 `needs_90` 0).
   그래도 막아 둔다 — 녹아웃이 시작되면 그때는 이미 틀린 채점이 쌓인 뒤다.
"""
from __future__ import annotations

import inspect

import pytest


def test_스키마에_result_basis_가_있다():
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "result_basis" in sql, "저장할 자리가 없다 — FotMob 이 주는 값을 버린다"


def test_적재가_result_basis_를_쓴다():
    from app.collectors import fotmob as F

    src = inspect.getsource(F.upsert_slate)
    assert "result_basis" in src
    src2 = inspect.getsource(F.apply_result) if hasattr(F, "apply_result") else ""
    from app.collectors import game_match as GM

    assert "result_basis" in inspect.getsource(GM.apply_result), \
        "apply_result 가 result_basis 를 받지 않는다"


def test_채점이_연장경기를_제외한다():
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL.grade_pending)
    assert "result_basis" in src, "1X2 채점이 연장 여부를 보지 않는다"


def test_정규시간_종료는_그대로_채점된다():
    """⚠️ 반대 위험 — 막느라 정상 경기까지 빼면 채점이 통째로 멈춘다."""
    from app.engine.pick_ledger import gradeable_basis

    assert gradeable_basis(None) is True        # 옛 행 · 다른 소스
    assert gradeable_basis("FT") is True
    assert gradeable_basis("") is True


def test_연장_승부차기는_제외된다():
    from app.engine.pick_ledger import gradeable_basis

    for b in ("AET", "Pen", "AP", "PEN"):
        assert gradeable_basis(b) is False, b


def test_모르는_표지는_제외한다():
    """🔴 모르면 채점하지 않는다 — 지어내지 않는다."""
    from app.engine.pick_ledger import gradeable_basis

    assert gradeable_basis("Awarded") is False
    assert gradeable_basis("WO") is False


@pytest.mark.asyncio
async def test_제외된_경기는_조용히_사라지지_않는다():
    """⚠️ 제외는 **보고**된다 — 조용한 0 금지."""
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL.grade_pending)
    assert "needs_90" in src or "연장" in src, "제외 사유를 남기지 않는다"
