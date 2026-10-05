"""🔴🔴 **v5 §5-6 — 문턱 금지.** 근거 없는 상수로 방향을 정하지 않는다. [#23]

§5-6 원문:

> **ERA 차 0.75 같은 임의 상수로 방향을 정하지 않는다.** `pitcher_state` 는 두
> 투수의 사실(시즌 ERA·직전 등판·상대 전적·이닝 제한)을 **변수로 보존**하고,
> 방향은 **시나리오 단계에서 변수 조합으로** 나타난다. 상수가 필요한 자리는
> `config/thresholds.yaml` 에 **근거(원장 통계)와 함께** 적고, **근거 없는 상수는
> 계약 실패.** [#23]

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04(밀워키 vs 샌디에이고)
══════════════════════════════════════════════════════════════════

```
§4 pitcher_state — 선발 방어율 2.47 vs 3.21 (차이 **0.74** < 문턱 **0.75**)
                   · 비슷하다고 본다
```
⚠️ **0.01** 차이로 선발이 배경으로 떨어졌고, 그래서 M18 이 총점·핸디를 거뒀다.
🔴 그 `0.75` 는 **어디서 왔나?** 아무 데도 근거가 없다 — 내가 고른 수다.
   §5-6 이 그런 수를 금지한다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_v5_5_6_문턱_선언에_근거가_있다_R7_M3():
    """🔴 §5-6 — *"근거(원장 통계)와 함께 적고, **근거 없는 상수는 계약 실패**."*"""
    from app import thresholds
    rows = thresholds.all_rows()
    assert rows, "🔴 `config/thresholds.yaml` 이 비었다"
    retired = []
    for name, row in rows.items():
        why = str(row.get("basis") or "").strip()
        assert why, f"🔴 `{name}` 에 **근거가 없다**(§5-6)"
        if row.get("value") is None:
            # 🔴 **걷은 상수**다 — `value: null` 이 *"쓰지 않는다"* 를 뜻한다.
            #    ⚠️ 그 줄을 **지우지 않고 남긴다** — 지우면 다음 세션이 같은 수를
            #       또 고른다(§5-6 이 막으려는 그것이다).
            assert "걷었" in why or "쓰지 않" in why, (name, why[:60])
            retired.append(name)
            continue
        # ⚠️ *"아직 근거가 없다"* 를 근거로 적는 것은 허용한다 — 🔴 **그 사실이
        #    글자로 남아야** 다음 사람이 그것을 측정할 수 있다(#3).
        assert len(why) >= 10, (name, why)
    # 🔴 걷은 상수가 **실제로 있다** — 이 계약이 공허하지 않다는 증거다
    assert "era_gap_min" in retired, retired


def test_v5_5_6_근거_없는_문턱은_거부한다():
    from app import thresholds
    with pytest.raises(ValueError, match="근거"):
        thresholds.check({"value": 0.75, "basis": ""}, name="시험")


def test_v5_5_6_era_문턱이_방향을_정하지_않는다():
    """🔴🔴 §5-6 의 알맹이 — `pitcher_state` 는 **사실을 보존**한다.

    ⚠️ 실측 2026-10-04: ERA 2.47 vs 3.21 이 **0.01** 차로 문턱에 못 미쳐
       배경으로 떨어졌고 M18 이 총점·핸디를 거뒀다.
    🔴 이제 그 사실이 **변수로 선다** — 방향은 §6 시나리오가 변수 조합으로 낸다.
    """
    from app import classify
    g = classify.Game(home="Milwaukee Brewers", away="San Diego Padres",
                      sport="baseball", league="MLB")
    got, why, undecided = classify._dir_pitcher_state(
        {"player": "Logan Henderson", "team": "Milwaukee Brewers",
         "era": 2.47, "opponent_era": 3.21}, g)
    # 🔴 **방향이 선다** — 0.01 차로 사라지지 않는다
    assert got == "home", (got, why, undecided)
    assert not undecided, undecided
    # 🔴 그리고 **수를 그대로 적는다**(사실 보존)
    assert "2.47" in why and "3.21" in why, why
    # ⚠️ **문턱으로 거부하지 않는다.** 🔴 D46 과 같은 결 — *"임의 문턱 없음"* 이라는
    #    **설명**은 괜찮고, *"문턱 X 미만이라 비슷하다고 본다"* 는 **판정**이 문제다.
    assert "비슷하다고 본다" not in why, why
    assert "< 문턱" not in why, why


def test_v5_5_6_같으면_방향이_없다():
    """🔴 **같은 수**에는 방향이 없다 — 그것은 임의 문턱이 아니라 산수다."""
    from app import classify
    g = classify.Game(home="A", away="B", sport="baseball", league="MLB")
    got, why, _ = classify._dir_pitcher_state(
        {"player": "p", "team": "A", "era": 3.00, "opponent_era": 3.00}, g)
    assert got is None, (got, why)
    assert "같다" in why or "차이" in why, why


def test_v5_5_6_하나만_알면_미결정이다():
    """🔴 둘 다 알아야 한다 — 하나만 알고 방향을 고르면 그것이 추측이다."""
    from app import classify
    g = classify.Game(home="A", away="B", sport="baseball", league="MLB")
    got, why, undecided = classify._dir_pitcher_state(
        {"player": "p", "team": "A", "era": 2.0, "opponent_era": None}, g)
    assert got is None and undecided, (got, why, undecided)


def test_v5_5_6_yaml에_근거_없는_상수가_없다():
    """🔴 전수 — `era_gap_min` 처럼 근거 없이 박힌 수가 남아 있나."""
    from app import rules
    bad = []
    vt = rules.variable_types()
    for name, row in vt.items():
        for k, v in (row or {}).items():
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            # ⚠️ 표본 수·일수는 §4·§7 이 원문으로 정한 것이다(그 조항이 근거다)
            if k in ("stale_days", "era_gap_min"):
                if k == "era_gap_min":
                    bad.append(f"{name}.{k} = {v}")
    assert not bad, (
        "🔴 §5-6 — 근거 없는 상수가 `variable_types.yaml` 에 남아 있다. "
        "`config/thresholds.yaml` 로 옮기고 **근거를 적어라**:\n  "
        + "\n  ".join(bad))
