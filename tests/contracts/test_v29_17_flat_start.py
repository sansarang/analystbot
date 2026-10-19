"""🔴 2026-10-19 — 시험 대역의 유형을 `lineup_intent` →
`squad_ability` 로 바꿨다(그 유형이 확률에서 빠졌다 · 아래 머리말과 같은 까닭).
이 시험들이 지키는 것은 **`flat_prob` 의 기계**(쏠림·무 깎기·두 번 안 세기)이고
유형이 무엇인지는 상관없다.
🔴🔴 **초기 확률은 1/3 균등** — 사용자 지시 2026-10-15.

> 변수 넣기전 **초기 확률 33.3 프로로 동등**하게 해라 … 그외에는 아무 의미 없다

🔴 승무패는 홈 1/3 · 무 1/3 · 원정 1/3 에서 출발하고 **변수만** 움직인다.
   리그 평균 총골·홈 이점·팀별 홈 효과는 **승무패에 안 쓴다**(λ·오버·스코어에만).
"""
from __future__ import annotations

from app.core import probmodel as pm, routing as rt
from app.core.schema import MatchRef, Variable

REF = MatchRef(id="m1", sport="soccer", home="team:100001", away="team:100002",
               home_name="홈팀", away_name="원정팀", competition="ELC",
               competition_short="ELC",
               kickoff_utc="2026-10-15T10:00:00+00:00")


def V(vid: str, kind: str, *, favors: str = "both", goals: str = "none",
      subject: str = "team:100001") -> Variable:
    return Variable(id=vid, type=kind, subject=subject, favors=favors,
                    goals=goals, target=vid, hardness="soft", weight=0.7,
                    claim="x", quote="x", doc_ids=[], from_rule=vid,
                    usable_as_basis=True)


def test_변수가_없으면_정확히_삼분의_일이다() -> None:
    got, why = pm.flat_prob(rt.place([]), ref=REF)
    for side in ("home", "draw", "away"):
        assert abs(got[side] - 1 / 3) < 1e-9, (side, got)
    assert "균등" in why, why


def test_합은_언제나_하나다() -> None:
    got, _ = pm.flat_prob(rt.place([
        V("SL1", "squad_ability", favors="home"),
        V("SL2", "squad_ability", favors="home"),
        V("IR02", "def_absence", favors="away")]), ref=REF)
    assert abs(sum(got.values()) - 1.0) < 1e-9, got


def test_변수가_그_쪽을_민다() -> None:
    got, _ = pm.flat_prob(rt.place([
        V("SL1", "squad_ability", favors="home")]), ref=REF)
    assert got["home"] > 1 / 3 > got["away"], got


def test_폼은_득점_방향으로도_안_센다() -> None:
    """🔴🔴 **뒤집혔다 — 과거 폼은 확률에서 뺐다**(사용자 지시 2026-10-18).

    > 과거 경기력 폼 제외...오로지 변수로만 하자 → **이거 지워라**

    ⚠️ 실측 2026-10-18 저녁 — 과거 층이 **결과와 정반대**였다:
       즈볼러 4-1 고어헤드(우리 원정 40.8% · `FL1`·`ST2`·`IR12`·`TURN` 이 원정을
       밀었다) · 우디네세 0-3 레체(우리 홈 41.8% · `ST2`·`FL2` 가 홈을 밀었다).
    🔴 그래서 `recent_pattern`·`form_streak`·`squad_rotation` 은 **맥락 전용**이다
       (자리도 `hypo` · λ 보정표에도 없다). 카드·⑯ 은 그대로 읽는다.
    🔴 이 시험은 *"되살아나지 않는다"* 를 지킨다 — 지우면 되살아나도 아무도 안 본다.
    """
    got, said = pm.flat_prob(rt.place([
        V("S01-home", "recent_pattern", goals="down")]), ref=REF)
    assert abs(got["away"] - 1 / 3) < 1e-9, (got, said)


def test_표시_전용은_안_센다() -> None:
    """🔴 표시 전용 유형은 확률을 못 민다.

    ⚠️ **`stakes` 는 빠졌다**(사용자 지시 2026-10-18 *"전부다 수정해"*) — 동기
       비대칭이 자리 때문에 버려지던 것을 고쳐 **이제 확률에 닿는다**
       (`test_v10_4_short_names.py` 가 그 뒤집힘을 센다).
    🔴 여기 남는 것은 `mood` 처럼 **자리가 `V*`·가설뿐인** 유형이다.
    """
    got, _ = pm.flat_prob(rt.place([
        V("IR12D", "mood", favors="home"),
        V("R8", "coach_quote", favors="home")]), ref=REF)
    assert abs(got["home"] - 1 / 3) < 1e-9, got


def test_리그_평균과_홈_이점이_승무패에_안_들어간다() -> None:
    """🔴🔴 *"그외에는 아무 의미 없다"* — 같은 변수면 **어느 대회든 같은 수**."""
    import dataclasses as _dc  # noqa: F401
    a, _ = pm.flat_prob(rt.place([V("SL1", "squad_ability", favors="home")]),
                        ref=REF)
    other = REF.model_copy(update={"competition": "UCL",
                                   "competition_short": "UCL"})
    b, _ = pm.flat_prob(rt.place([V("SL1", "squad_ability", favors="home")]),
                        ref=other)
    assert a == b, (a, b)


def test_운영_승무패가_그_수로_덮인다() -> None:
    """🔴 배선 — `run` 이 승무패를 `flat_prob` 로 덮어야 한다."""
    import inspect
    src = inspect.getsource(pm.run)
    assert "flat_prob(varset, ref=ref)" in src, "🔴 안 덮는다"
    assert "got.home = round(float(said_flat[\"home\"]), 6)" in src


def test_λ_는_안_덮는다() -> None:
    """🔴 총골은 리그 실측이 정한다 — 균등 판이 λ 를 건드리면 안 된다."""
    import inspect
    # ⚠️ 글자 `lam` 으로 세면 안 된다 — `lambda_rules`(표 이름)에 들어 있다.
    #    🔴 **쓰는 자리**로 센다: 그 칸에 대입하는 줄이 없어야 한다.
    src = inspect.getsource(pm.flat_prob)
    for bad in ("got.lam", "got.over", "got.scores", ".lam =", ".over ="):
        assert bad not in src, f"🔴 `{bad}` 를 건드린다"


# 🔴 **`test_by_var_를_λ_에서_걷었다` 을 지웠다** — 같은 까닭 — λ 경로 자체가 없다(설정 `by_var` 는 `flat_prob` 가 읽는다).

def test_쏠리면_무가_내려간다() -> None:
    got, said = pm.flat_prob(rt.place([
        V("A", "squad_ability", favors="home")]), ref=REF)
    assert got["draw"] < 1 / 3, got
    assert "쏠림 1단계" in said, said


def test_많이_쏠리면_더_내려간다() -> None:
    one, _ = pm.flat_prob(rt.place([
        V("A", "squad_ability", favors="home")]), ref=REF)
    three, _ = pm.flat_prob(rt.place([
        V(f"A{i}", "squad_ability", favors="home") for i in range(3)]), ref=REF)
    assert three["draw"] < one["draw"] < 1 / 3, (three, one)
    assert three["home"] > one["home"]


def test_상쇄되면_무는_그대로다() -> None:
    """🔴 변수 **수**가 아니라 **쏠림**을 본다 — 양쪽이 같으면 균등 그대로."""
    got, said = pm.flat_prob(rt.place(
        [V(f"A{i}", "squad_ability", favors="home") for i in range(3)]
        + [V(f"B{i}", "def_absence", favors="away") for i in range(3)]),
        ref=REF)
    for side in ("home", "draw", "away"):
        assert abs(got[side] - 1 / 3) < 1e-9, (side, got)
    assert "쏠림" not in said, said


def test_무를_깎는_크기도_새_수가_아니다() -> None:
    """🔴 변수 하나가 쓰는 그 ±5% 를 **거듭제곱**으로만 쓴다."""
    import inspect
    src = inspect.getsource(pm.flat_prob)
    assert 'got["draw"] /= mul ** lean' in src, src[-500:]
