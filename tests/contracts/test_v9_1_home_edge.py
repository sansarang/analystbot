"""🔴🔴 **① 홈 이점은 그 리그 결과로 실측한다**(사용자 지시 2026-10-11).

> 리그 홈 이점은 그 리그 경기 결과로 실측한다(자동 등록 리그 포함, fotmob 결과).
> 이번 시즌 30경기 미만이면 직전 시즌까지.
> **"실측 없음 → 1.0" 경로 삭제.** lambda_const 자리 변수(S03)와 λ에 쓴 값이 다르면
> **계약 실패**.
"""
from __future__ import annotations

import inspect


def test_v9_실측_없음이면_1_0_으로_가지_않는다():
    """🔴 **조용한 1.0 금지** — 못 쟀으면 `None` 과 사유다(#3).

    ⚠️ 돌연변이: `home_mul_default` 로 돌아가면 빨개진다.
    """
    from app.core import probmodel as _pm
    said = inspect.getsource(_pm.home_mul)
    code = "\n".join(x for x in said.splitlines()
                     if not x.strip().startswith("#"))
    assert "home_mul_default" not in code, (
        "🔴 실측이 없을 때 **1.0** 으로 간다 — 그 경로는 삭제다")
    # 🔴 못 쟀으면 **`None`** 을 준다(호출부가 크게 실패한다)
    class _Facts:
        standings = {}
        match_format = ""
    got, why = _pm.home_mul(_Facts(), None, ref=None)
    assert got is None, f"🔴 못 쟀는데 수를 냈다 — {got} · {why}"
    assert "실측" in why


def test_v9_MLS_홈_이점이_표에_있다():
    """🔴 자동 등록 리그(MLS)도 **표에 실측이 있다**(fotmob 결과 414경기)."""
    from app import rules
    box = dict(rules.goal_baseline("league:MLS") or {})
    assert box.get("home_share"), f"🔴 MLS 홈 몫이 없다 — {box}"
    assert int(box.get("n") or 0) >= 30, box
    assert "fotmob" in str(box.get("source") or ""), box


def test_v9_S03_변수_값과_λ_값이_같다():
    """🔴🔴 **계약** — `lambda_const` 자리 변수(S03)와 λ 에 쓴 값이 **같아야** 한다.

    ⚠️ 종전에는 S03 이 *"홈 **승률** 표가 없다"* 라고 적고 λ 는 **득점 실측**을 썼다 —
       한 카드가 두 수를 말했다. 🔴 두 자리가 **같은 함수**를 보게 한다.
    """
    from app.core import probmodel as _pm
    from app.core.stages import s5_verify as _s5
    said = inspect.getsource(_s5)
    # 🔴 S03 글을 만드는 자리가 **득점 실측**(`goal_baseline`)을 읽는다
    assert "goal_baseline" in said, "🔴 S03 이 λ 와 다른 표를 본다"
    # 🔴 λ 쪽도 같은 함수다
    assert "goal_baseline" in inspect.getsource(_pm.home_mul)


def test_v9_fotmob_리그_결과_파서가_선다():
    """🔴 그 실측의 재료 — `fotmob.league_results`(끝난 경기만·점수를 읽은 줄만)."""
    from app.collect import fotmob as _fm
    j = {"props": {"pageProps": {"fixtures": {"allMatches": [
        {"home": {"name": "A"}, "away": {"name": "B"},
         "status": {"finished": True, "scoreStr": "2 - 0", "utcTime": "x"}},
        {"home": {"name": "C"}, "away": {"name": "D"},
         "status": {"finished": False, "scoreStr": "", "utcTime": "y"}},
        {"home": {"name": "E"}, "away": {"name": "F"},
         "status": {"finished": True, "scoreStr": "", "utcTime": "z"}}]}}}}
    got = _fm.league_results(j)
    assert len(got) == 1, got          # 🔴 안 끝난 줄·점수 못 읽은 줄은 **버린다**
    assert got[0]["gh"] == 2 and got[0]["ga"] == 0
