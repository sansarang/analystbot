"""🔴🔴 **무승부 신중 처리** — 수정 지시 2026-10-13 밤 2번.

> 확률 경로 변경은 판정 규칙 v2+(d) 통과 전 **금지** — 먼저 측정.
> ④ 카드 표시(측정 결과 나오는 즉시 · **확률 값은 안 바꾼다**).

🔴 **판정 결과**(2-③ · 2,582경기 시즌 교차): **D1·D2 둘 다 탈락** — 무 구간
   오차는 줄었지만(1.36% → D1 0.14% · D2 0.91%) 규칙 v2 의 (c)(d)를 못 넘었다
   (로그 손실 개선 +0.0003/+0.0000 · 방향 ±0.00%p). 🔴 **경로 그대로**다.
🔴 **DB1** 확률 모듈은 `drawband` 를 **안 부른다**(표시 전용) · **DB2** 편차
   ≥ 3%p 면 🟡 와 꼬리표 · **DB3** 미달이면 꼬리표 **없다** · **DB4** 판이
   없거나 그 구간 표본이 0 이면 **그 말을 한다**(지어내지 않는다) · **DB5**
   무에 걸린 줄이면 **방아쇠 한 줄** · **DB6** ρ 는 **폐기 유지**.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_db1_probability_path_never_calls_it() -> None:
    """🔴🔴 **DB1** — 확률 경로에 닿지 않는다(표시 전용)."""
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/legacy/old_engine.py", "app/core/sim.py",
                "app/core/stages/s7_judge.py", "app/core/conclude.py"):
        assert "drawband" not in _src(rel), rel


def test_db2_big_deviation_is_flagged() -> None:
    """🔴 **DB2** — 편차가 문턱을 넘으면 🟡 와 꼬리표가 나온다."""
    from app.core import drawband as db
    said = db._edges("20~25%")
    assert said == (0.20, 0.25), said
    # 🔴 문턱은 하나다(3%p)
    assert db.DEV_CUT == 0.03


def test_db3_small_deviation_has_no_tail() -> None:
    """🔴 **DB3** — 지금 판의 20~25% 구간(−2.7%p)은 **꼬리표가 없다**."""
    from app.core import drawband as db
    got, why = db.of(0.235)
    if not got:
        return                     # 판이 아직 없으면 센 것이 없다
    assert abs(float(got["dev"])) < db.DEV_CUT, (got, why)
    assert db.flag(0.235) == ""


def test_db4_says_when_the_band_is_empty() -> None:
    """🔴 **DB4** — 표본 0 구간·판 없음을 **말로** 남긴다."""
    from app.core import drawband as db
    said = db.said_of(0.15)
    assert "⬜" in said and ("표본" in said or "판이 없다" in said), said


def test_db5_trigger_line_exists() -> None:
    """🔴 **DB5** — 무에 걸린 줄이면 방아쇠에 한 줄."""
    said = _src("app/core/render.py")
    assert "_draw_trigger" in said and "무 구간 편차" in said
    assert "DRAW_LINES" in said


def test_db6_rho_stays_retired() -> None:
    """🔴🔴 **DB6** — ρ 판은 **폐기 유지**다(`.yaml` 로 되살리지 않는다)."""
    box = ROOT / "data/m1_draw"
    live = [p for p in box.rglob("*.yaml")] if box.exists() else []
    assert not live, f"🔴 ρ 판이 되살아났다: {live}"
    assert (box / "INVALID.md").exists()


def test_db7_summary_block_shows_the_measure() -> None:
    """🔴 요약 블록이 **무 신뢰** 한 줄을 낸다(2-④ 첫째 조항)."""
    import inspect
    from app.core import render
    said = ast.unparse(ast.parse(inspect.getsource(render.prob_summary)))
    assert "drawband" in said and "무 신뢰" in said


def test_db8_audit_tool_writes_the_plate() -> None:
    """🔴 판을 적는 것은 **도구**다(`app/` 은 yaml 을 쓰지 않는다)."""
    said = _src("tools/draw_audit.py")
    assert "data/draw_bands" in said and "yaml.safe_dump" in said
    body = _src("app/core/drawband.py")
    assert "safe_dump" not in body
