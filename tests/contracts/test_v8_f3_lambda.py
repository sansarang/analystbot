"""🔴🔴 **F3 — 확률 식: 이중 계산 제거, 홈·원정 분리**(지시서 2026-10-11 §2 F3).

> 규칙 효과는 **축 안에서 한 번만**. ⑪에서 "규칙 λ를 따로 더하는" 항 삭제.
> log λ홈  = 리그 평균(로그) + 홈 이점 + 대회 상수 + Σ_축 β_축 ·(홈 공격_축 − 원정 수비_축)
> log λ원정 = 리그 평균(로그)          + 대회 상수 + Σ_축 β_축 ·(원정 공격_축 − 홈 수비_축)
> 축마다 공격 쪽·수비 쪽 특징을 ⑨에서 **따로** 낸다(축 종합 숫자 하나로 두 λ 를 만들지
> 않는다). 시간대·경기 상태 배율(축3)은 **시뮬 안에서만**.
"""
from __future__ import annotations

import inspect
import math


def test_F3_축이_공격_수비_특징을_따로_든다():
    """🔴 `Axis` 가 `att`·`dfn` 을 **쪽별로** 든다. ⚠️ 돌연변이: 그 칸을 지우면 빨강."""
    import dataclasses

    from app.core import matchup as _mu
    got = {f.name for f in dataclasses.fields(_mu.Axis)}
    assert {"att", "dfn"} <= got, f"🔴 축에 공격·수비 특징이 없다 — {sorted(got)}"


def test_F3_R5_λ홈_식에_원정_공격이_들어가지_않는다():
    """🔴🔴 **계약 R5** — λ홈 식에 **원정 공격 특징**이 들어가면 실패(반대도).

    🔴 실물로 센다 — 원정 **공격**만 올리면 λ홈 은 **그대로**이고 λ원정만 오른다.
    """
    from app.core import probmodel as _pm

    def _mk(**kw):
        box = {"axis0": (0.0, 0.0, 0.0, 0.0), "axis1": (0.0, 0.0, 0.0, 0.0),
               "axis2": (0.0, 0.0, 0.0, 0.0), "axis3": (0.0, 0.0, 0.0, 0.0)}
        box.update(kw)
        return {k: {"att": {"home": v[0], "away": v[1]},
                    "dfn": {"home": v[2], "away": v[3]}}
                for k, v in box.items()}

    flat = _pm.sides_move(_mk(), {"axis0": 1.0}, beta=1.0, cap=10.0)
    assert abs(flat["home"]) < 1e-9 and abs(flat["away"]) < 1e-9, flat
    # 🔴 원정 **공격**만 +1 → λ원정만 오른다
    one = _pm.sides_move(_mk(axis0=(0.0, 1.0, 0.0, 0.0)), {"axis0": 1.0},
                         beta=1.0, cap=10.0)
    assert abs(one["home"]) < 1e-9, f"🔴 원정 공격이 λ홈 을 움직였다 — {one}"
    assert one["away"] > 0.9, one
    # 🔴 홈 **수비**만 +1 → λ원정이 내려간다(그 반대편이다)
    two = _pm.sides_move(_mk(axis0=(0.0, 0.0, 1.0, 0.0)), {"axis0": 1.0},
                         beta=1.0, cap=10.0)
    assert abs(two["home"]) < 1e-9 and two["away"] < -0.9, two


def test_F3_R4_같은_규칙이_λ_경로에_두_번_나오지_않는다():
    """🔴🔴 **계약 R4** — 같은 규칙 id 가 λ 계산 경로에 **두 번** 나오면 실패.

    🔴 규칙(T1~T13)은 **축 안에서** 한 번 센다 — ⑪ 이 `lambda_own`·`lambda_opp`
       으로 λ 를 **또** 미는 항은 지웠다.
    ⚠️ 돌연변이: `probmodel` 이 다시 `sim_input` 의 λ 를 쓰면 빨개진다.
    """
    from app.core import probmodel as _pm
    said = inspect.getsource(_pm.run)
    assert "lam_home=" not in said or "sim_input" not in said, (
        "🔴 ⑪ 이 규칙 λ 를 다시 더한다(이중 계산)")
    # 🔴 시간대·상태 배율은 **시뮬 안에서만** 쓴다(그것은 남는다)
    assert "late_home" in said and "lead_mul" in said, (
        "🔴 시간대·상태 배율이 사라졌다 — 그것은 시뮬 안에서 써야 한다")


def test_F3_홈_이점은_lambda_const_자리_변수만_받는다():
    """🔴 `home_mul`(홈 이점)은 **lambda_const 자리 변수만** 받는다."""
    from app.core import probmodel as _pm
    said = inspect.getsource(_pm.home_mul)
    assert 'of("lambda_const")' in said, "🔴 다른 자리 변수를 본다"
    for ban in ('of("axis0")', 'of("axis1")', 'of("axis2")', 'of("axis3")',
                'of("V1")', 'of("hypo")'):
        assert ban not in said, f"🔴 홈 이점이 `{ban}` 를 본다"


def test_F3_식이_로그에서_더해진다():
    """🔴 λ 는 **로그에서 더한다** — `mean × exp(move)` 가 그 꼴이다.

    ⚠️ 상한(cap)은 그대로 — 임시 계수 표시도 유지한다.
    """
    from app.core import probmodel as _pm
    said = inspect.getsource(_pm.run)
    assert "math.exp" in said, "🔴 로그 합이 아니다"
    assert "cap" in said, "🔴 상한이 사라졌다"
    assert "PROVISIONAL" in said or "provisional" in said, (
        "🔴 임시 계수 표시가 사라졌다")
    # 🔴 두 λ 가 **각자의 이동**을 쓴다(하나의 move 로 둘을 만들지 않는다)
    assert "move[\"home\"]" in said or "move['home']" in said, said[:300]
    assert "move[\"away\"]" in said or "move['away']" in said


def test_F3_축마다_베타를_둘_수_있다():
    """🔴 `Σ_축 β_축` — 축별 계수를 표에서 읽는다(없으면 공통 β · 🔴 임시)."""
    from app.core import probmodel as _pm
    got = inspect.signature(_pm.sides_move).parameters
    assert {"beta", "cap"} <= set(got), sorted(got)
    # 🔴 축별 무게가 곱해진다 — 무게 0 이면 그 축은 λ 를 못 민다
    box = {"axis0": {"att": {"home": 1.0, "away": 0.0},
                     "dfn": {"home": 0.0, "away": 0.0}}}
    off = _pm.sides_move(box, {"axis0": 0.0}, beta=1.0, cap=10.0)
    assert abs(off["home"]) < 1e-9, f"🔴 무게 0 인데 λ 가 움직였다 — {off}"
    on = _pm.sides_move(box, {"axis0": 0.5}, beta=1.0, cap=10.0)
    assert abs(on["home"] - 0.5) < 1e-9, on
    # 🔴 상한이 **양쪽 다** 걸린다
    #    홈 공격 99 − 원정 수비 0 = +99 → 상한 · 원정 공격 0 − 홈 수비 99 = −99 → 상한
    big = _pm.sides_move({"axis0": {"att": {"home": 99.0, "away": 0.0},
                                    "dfn": {"home": 99.0, "away": 0.0}}},
                         {"axis0": 1.0}, beta=1.0, cap=0.35)
    assert math.isclose(big["home"], 0.35) and math.isclose(big["away"], -0.35)
