"""🔴🔴 **v5 §7-3 — 라이브 재판정.** 일곱 규칙이 전부 *거절*에 관한 것이다.

지시문 §7-3 원문:

> 입력은 스코어·경과 분·지표 캡처(또는 어댑터 라이브 피드). 규칙:
> **스코어·경과 분 없이 재판정 금지** / **스코어로는 시나리오를 제거, 지표로는
> 약화만** / **지표 2개 이상이 같은 메커니즘을 가리킬 때만 인정** /
> **"GK 선방 0"은 상대 유효슈팅 부재가 아니다** / **라이브로 새 마켓을 만들지
> 않는다** / **15분 간격**. 라이브 판정은 **등급 승격 없이** 생존 여부만
> 갱신한다. [M29]

══════════════════════════════════════════════════════════════════
🔴 왜 — 라이브는 **고치는 자리가 아니다**
══════════════════════════════════════════════════════════════════

⚠️ 경기 중에 등급을 올리면 *"예측"* 이 아니라 *"따라가기"* 가 된다. 🔴 §3 불변:
   *"맞았나를 예측이 끝난 뒤에 고치지 않는다."* 라이브가 할 수 있는 일은
   **죽은 시나리오를 죽었다고 적는 것**뿐이다.
"""
from __future__ import annotations

import pytest


def test_v5_7_3_스코어와_경과분_없이는_재판정_금지():
    """🔴🔴 *"스코어·경과 분 없이 재판정 금지"* — **둘 다** 있어야 한다."""
    from app import live
    from app.reasons import Reason
    for kw in ({}, {"score": "1-0"}, {"minute": 55}):
        got = live.may_judge(**kw)
        assert got.ok is False, kw
        assert got.reason is Reason.LIVE_NO_INPUT, (kw, got.reason)
    ok = live.may_judge(score="1-0", minute=55)
    assert ok.ok is True and ok.reason is Reason.OK


def test_v5_7_3_간격을_지킨다():
    """🔴 *"15분 간격"* — ⚠️ 수를 코드에 박지 않는다(yaml · 근거 포함)."""
    from app import live, rules
    cfg = rules.live_rules()
    assert int(cfg["interval_min"]) == 15
    assert str(cfg.get("basis") or "").strip(), "🔴 근거가 없다(§5-6)"
    got = live.may_judge(score="1-0", minute=55, since_min=3)
    assert got.ok is False and "15" in got.why, got.why
    assert live.may_judge(score="1-0", minute=55, since_min=20).ok is True


def test_v5_7_3_스코어는_제거_지표는_약화만():
    """🔴🔴 *"스코어로는 시나리오를 **제거**, 지표로는 **약화만**"*.

    ⚠️ 지표(점유율·xG)는 **일어난 일이 아니다** — 경향이다. 🔴 경향으로
       시나리오를 지우면 아직 가능한 결과를 카드에서 없애는 것이다.
    """
    from app import live
    assert live.effect_of("score") == "제거"
    assert live.effect_of("metric") == "약화"
    # 🔴🔴 모르는 입력은 **아무 일도 하지 않는다**(지어내지 않는다 · #4).
    #    ⚠️ 돌연변이 I 가 통과했다 — `or "없음"` 을 `or "제거"` 로 바꿔도
    #       초록이었다. 내가 **표에 있는 값만** 시험했다.
    #    🔴 세 글자 중 **무엇도 아니어야** 한다는 것이 아니라, `제거`·`약화` 가
    #       **아니어야** 한다(그 둘이 일을 하는 값이다).
    for junk in ("느낌", "", "SCORE", "지표", None):
        got = live.effect_of(junk)
        assert got == "없음", (junk, got)
        assert got not in ("제거", "약화"), (junk, got)
    # ⚠️ 그리고 표에 있는 둘은 **서로 달라야** 한다(같으면 구분이 없다)
    assert live.effect_of("score") != live.effect_of("metric")


def test_v5_7_3_지표는_둘_이상_같은_메커니즘일_때만():
    """🔴 *"지표 2개 이상이 **같은 메커니즘**을 가리킬 때만 인정"*."""
    from app import live
    one = live.metrics_ok([{"name": "possession", "mechanism": "압박"}])
    assert one[0] is False and "2" in one[1]
    # ⚠️ 둘인데 **메커니즘이 다르면** 안 된다
    two_diff = live.metrics_ok([{"name": "possession", "mechanism": "압박"},
                                {"name": "xg", "mechanism": "역습"}])
    assert two_diff[0] is False, two_diff
    same = live.metrics_ok([{"name": "possession", "mechanism": "압박"},
                            {"name": "ppda", "mechanism": "압박"}])
    assert same[0] is True, same


def test_v5_7_3_GK_선방_0_은_유효슈팅_부재가_아니다_M29():
    """🔴🔴 지시문이 **이름으로 댄** 함정이다.

    ⚠️ `saves == 0` 은 *"상대가 유효슈팅을 못 냈다"* 가 아니다 — **골이 들어갔을
       때도** 선방은 0 이다. 🔴 그 둘을 같게 보면 수비 시나리오가 살아남는다.
    """
    from app import live
    ok, why = live.reads_as_no_shots({"saves": 0})
    assert ok is False
    assert "유효슈팅" in why, why
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **첫 판이 돌연변이 F 를 통과시켰다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `if "shots_on_target" not in got:` 를 끄면 `int(None)` 이 실패해 *"수가
    #  아니다"* 로 떨어진다 — 🔴 **거짓은 같지만 사유가 다르다.** 그러면 카드가
    #  *"유효슈팅 수를 받아야 한다"*(고칠 곳: 수집) 대신 *"수가 아니다"*(고칠
    #  곳: 파서)를 적는다. ⚠️ §8-6 이 막는 거짓 사유다.
    #  🔴 그래서 **사유 글을 가린다** — 그 둘은 다른 말이어야 한다.
    assert "직접 받아야" in why, (
        f"🔴 *'유효슈팅 수를 받지 않았다'* 와 *'받았는데 수가 아니다'* 가 "
        f"섞였다 — 고칠 곳이 다르다: {why}")
    _, why_bad = live.reads_as_no_shots(
        {"saves": 0, "shots_on_target": "많음"})
    assert "수가 아니다" in why_bad and why != why_bad, (why, why_bad)
    # 🔴 **유효슈팅 수를 직접 받았을 때만** 그렇게 읽는다
    ok2, _ = live.reads_as_no_shots({"saves": 0, "shots_on_target": 0})
    assert ok2 is True
    # ⚠️ 그리고 **골이 들어갔어도 선방은 0 이다** — 그 경기가 이 함정이다
    assert live.reads_as_no_shots(
        {"saves": 0, "shots_on_target": 4})[0] is False


def test_v5_7_3_라이브로_새_마켓을_만들지_않는다():
    """🔴 *"라이브로 새 마켓을 만들지 않는다"* — 있던 것의 생존만 갱신한다."""
    from app import live
    before = ["home", "total 8.5"]
    got = live.keep_markets(before, proposed=["home", "btts", "total 8.5"])
    assert got.kept == ["home", "total 8.5"]
    assert got.refused == ["btts"]
    assert "새 마켓" in got.why, got.why


def test_v5_7_3_등급_승격이_없다():
    """🔴🔴 *"라이브 판정은 **등급 승격 없이** 생존 여부만 갱신한다"*(M29).

    ⚠️ 경기 중에 등급을 올리면 *"예측"* 이 아니라 *"따라가기"* 다.
    """
    from app import live
    # 🔴 내려가는 것은 **된다**
    assert live.cap_verdict(before="name", after="small") == "small"
    # 🔴 올라가는 것은 **안 된다** — 전 등급으로 **묶는다**
    assert live.cap_verdict(before="small", after="name") == "small"
    assert live.cap_verdict(before="none", after="name") == "none"
    assert live.cap_verdict(before="small", after="small") == "small"


def test_v5_7_3_사유가_우리_것인지_가른다():
    """🔴 §8-6 — 라이브 사유도 `fix_where` 가 있어야 한다."""
    from app.reasons import Reason
    # 🔴🔴 **칸을 값으로** 본다 — 돌연변이 J 가 통과했다(분류를 `없음`/`none`
    #    으로 바꿔도 초록이었다. 내가 *"빈 값이 아니다"* 만 봤다).
    #    ⚠️ `fix_where` 가 `없음` 이면 그 사유는 **고칠 곳이 없다**는 뜻이고,
    #       거절한 사유에 그것을 달면 아무도 고치지 않는다(#3).
    want = {
        # 입력이 안 온 것이다 — **다시 물으면 온다**(경기가 진행된다)
        "LIVE_NO_INPUT": ("수집", "ask"),
        # 약한 지표로 지우려 한 것 — 판정의 **결론**이다
        "LIVE_WEAK_METRIC": ("판정", "verdict"),
        # 🔴 라이브로 새 마켓을 만들려 한 것 — **우리 코드의 버그**다
        "LIVE_NEW_MARKET": ("판정", "bug"),
    }
    for name, (where, kind) in want.items():
        assert hasattr(Reason, name), f"🔴 §7-3 사유 `{name}` 이 없다"
        r = getattr(Reason, name)
        assert (r.fix_where, r.kind) == (where, kind), (
            f"🔴 `{name}` 의 분류가 {(r.fix_where, r.kind)} 다 — "
            f"{(where, kind)} 여야 한다(§8-6: 고칠 곳과 종류는 **다른 축**이다)")


def test_v5_7_3_배선_판정_경로가_이것을_지난다():
    """🔴🔴 **안 이어진 라이브 규칙은 없는 규칙이다**(CLAUDE.md #2).

    ⚠️ 라이브 입구가 아직 없다 — 그러면 `NOT_WIRED` 에 **이름과 이어질 단계를**
       적어야 한다. 🔴 둘 중 하나는 참이어야 한다.
    """
    import pathlib
    import re
    wiring = pathlib.Path("tests/test_wiring.py").read_text()
    body = pathlib.Path("app/analyze.py").read_text()
    live_in_analyze = bool(re.search(r"\blive\.", body))
    parked = "app.live." in wiring
    assert live_in_analyze or parked, (
        "🔴 §7-3 을 만들어 두고 **부르는 곳도 `NOT_WIRED` 기록도 없다** — "
        "안 이어진 코드는 없는 코드보다 나쁘다(CLAUDE.md #2)")


@pytest.mark.parametrize("bad", [
    {"score": "", "minute": 10},
    {"score": "1-0", "minute": 0},
    {"score": "1-0", "minute": -5},
])
def test_v5_7_3_빈_값은_있는_것이_아니다(bad):
    """⚠️ `""`·`0`·음수는 *"받았다"* 가 아니다 — fail-closed."""
    from app import live
    assert live.may_judge(**bad).ok is False, bad
