"""🔴🔴 **IR13 이동 문턱 계약** — 사용자 지시 2026-10-15.

> 3000 **니 생각이고** 1000km도 가도 힘들다...**과부하 맞다**

🔴 내가 IR13 을 지을 때 `FATIGUE_KM`(3,000km)을 **재사용했다** — 새 수를
   지어내지 않으려고 그랬지만 그 수는 **피로 규칙의 것**이다(지시서 2026-10-06
   7차 §6: *"4일 이내 + (시차 3시간 또는 이동 3,000km)"*). 이동 부담 자체의
   문턱은 그것과 **다르다**.

지키는 것:
  TK1 IR13 은 **자기 문턱**(`TRAVEL_KM`)을 쓴다 — `FATIGUE_KM` 재사용 금지
  TK2 그 수는 **1,000km** 다(사용자가 정했다)
  TK3 `FATIGUE_KM` 은 **그대로 3,000km** 다(IR11 은 지시서가 못 박은 수다)
  TK4 거리를 **실측으로** 센다 — 🔴 로테르담↔코모는 **753km** 다(내가 "약
      1,100km" 라고 적은 것은 짐작이었다). 그 값은 1,000km 문턱을 **못 넘는다**
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s5_verify.py"


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def _body() -> str:
    code = _code(MOD)
    i = code.index("def _ir_travel_away(")
    j = code.find("\ndef ", i + 10)
    return code[i:j if j > i else len(code)]


def test_tk1_own_threshold() -> None:
    """TK1 — IR13 이 `FATIGUE_KM` 을 **재사용하지 않는다**."""
    said = _body()
    assert "TRAVEL_KM" in said, "TK1 🔴 자기 문턱을 안 쓴다"
    assert "FATIGUE_KM" not in said, (
        "TK1 🔴🔴 `FATIGUE_KM`(피로 규칙의 수)을 다시 쓴다 — 사용자가 그 혼동을 "
        "잡았다(2026-10-15). 이동 부담의 문턱은 **따로** 있다")


def test_tk2_is_1000() -> None:
    """TK2 — 1,000km 다(사용자가 정했다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s5_verify import TRAVEL_KM
    assert TRAVEL_KM == 1000, (
        f"TK2 🔴 문턱이 {TRAVEL_KM} 다 — 사용자 지시 2026-10-15 는 **1,000km** 다")


def test_tk3_fatigue_km_untouched() -> None:
    """TK3 — `FATIGUE_KM` 은 그대로 3,000km(지시서가 못 박았다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s5_verify import FATIGUE_KM
    assert FATIGUE_KM == 3000, (
        f"TK3 🔴 `FATIGUE_KM` 이 {FATIGUE_KM} 로 바뀌었다 — 그 수는 지시서 "
        "2026-10-06(7차) §6 이 못 박은 **피로** 문턱이다. 건드리지 않는다")


def test_tk4_distance_is_measured() -> None:
    """TK4 — 거리를 **실측으로** 센다. 🔴 짐작한 수를 계약에 적지 않는다.

    ⚠️ 내가 머리말에 *"로테르담↔코모 약 1,100km"* 라고 적었는데 하버사인으로
       재니 **753km** 였다 — 짐작이었다(규율 #4). 그 수로 고친다.
    🔴 그래서 이 경기는 1,000km 문턱을 **못 넘는다** — IR13 이 안 걸리는 것이
       맞다. 사용자 지시(*"1000km도 가도 힘들다"*)는 **문턱을 1,000 으로**
       정한 것이고, 753km 를 걸리게 하라는 말은 아니다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s5_verify import TRAVEL_KM, _travel

    class _Ref:
        pass
    # 🔴 실제 좌표 — 코모 스타디오 시니갈리아 ↔ 데 카위프(로테르담)
    said = {"last_lat": 45.813856655, "last_lon": 9.072376192,
            "lat": 51.893889, "lon": 4.523056}
    _tz, km, why = _travel(said, _Ref(), "t")
    assert km is not None, f"TK4 🔴 거리를 못 셌다 — {why}"
    assert 740 <= km <= 770, (
        f"TK4 🔴 거리가 {km:,.0f}km 다 — 실측은 **753km** 였다(2026-10-15). "
        "크게 다르면 하버사인이나 좌표가 바뀐 것이다")
    assert km < TRAVEL_KM, (
        f"TK4 🔴 {km:,.0f}km 가 문턱 {TRAVEL_KM:,}km 를 넘는다 — 이 경기는 "
        "안 걸리는 것이 맞다")


def test_tk5_1000km_over_fires() -> None:
    """TK5 — **1,000km 를 넘으면 걸린다**(사용자가 정한 그 문턱)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s5_verify import TRAVEL_KM, _travel

    class _Ref:
        pass
    # 🔴 리스본 ↔ 로테르담(약 1,900km) — 유럽 대항전에 흔한 거리
    said = {"last_lat": 38.7223, "last_lon": -9.1393,
            "lat": 51.893889, "lon": 4.523056}
    _tz, km, _why = _travel(said, _Ref(), "t")
    assert km is not None and km >= TRAVEL_KM, (
        f"TK5 🔴🔴 {km:,.0f}km 가 문턱 {TRAVEL_KM:,}km 를 **못 넘는다** — "
        "1,000km 이상은 걸려야 한다(사용자 지시 2026-10-15)")
