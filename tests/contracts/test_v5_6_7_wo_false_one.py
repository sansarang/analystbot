"""🔴🔴 **거짓 1.0 세 자리** — 사용자 지시 2026-10-05 (pn8 카드 모순).

> pn8 카드 결론이 모순이다: *"낸다: 언더 3.5 (생존 1.0) — 죽는 시나리오
> G(3-1·2-2)"*. 두 스코어 모두 **합계 4골**이라 언더 3.5 는 G 에서 **죽는다.**
>
> **1.** 계약: **죽는 시나리오가 하나라도 있는 마켓의 생존율은 1.0 이 될 수
>    없다.** **strength 0 시나리오도 생존 계산에서 빠지지 않는다.**
> **2.** 계약: **`lineup_state` 가 `confirmed` 가 아니면 "낸다"(1.0) 금지.**
> **3.** **킥오프가 지난 경기는 등급을 내지 않는다**(카드에 *"이미 시작 — 예측
>    아님"* + 결론 줄 **등급 없음**).

══════════════════════════════════════════════════════════════════
🔴 원인 — `strength 0` 이 **분모에서 사라진다**(실측 2026-10-05)
══════════════════════════════════════════════════════════════════

```
survive.weights([A(strength 9.6), G(strength 0.0)])
  → {'A': 9.6, 'G': 0.0} · 합 **9.6**
  🔴 G 의 무게가 0 → 분자·분모에서 **통째로 사라진다**
  → `언더 3.5` 는 A 에서만 살아 **9.6/9.6 = 1.0**
```

⚠️ 그런데 카드 표는 `○ ○ ○ ○ ○ ○ **✗**` 로 **G 에서 죽는다고 그렸다** —
   **그림과 수가 어긋났다.** 🔴 §6-7 이 막으려는 거짓 1.0 이 바로 이 꼴이다.
"""
from __future__ import annotations

import datetime as dt

import pytest

UTC = dt.timezone.utc


def _game():
    from app import classify
    return classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UNL", home_id="team:1", away_id="team:2")


def _drafts():
    from app import scenarios
    return [
        scenarios.Draft(id="A", scores=["2-1", "1-0"], strength=9.6,
                        template_id="t", why="홈", variables=["V"],
                        added_by="template"),
        # 🔴 **strength 0** — 실측 pn8 의 그 시나리오(대량득점형)
        scenarios.Draft(id="G", scores=["3-1", "2-2"], strength=0.0,
                        template_id="code", why="대량득점형", variables=["V"],
                        added_by="required")]


# ══════════════════════════════════════════════════════════════════
# ① 죽는 시나리오가 있으면 **1.0 이 될 수 없다**
# ══════════════════════════════════════════════════════════════════

def test_one_strength_0_도_분모에_남는다():
    """🔴🔴 *"strength 0 시나리오도 생존 계산에서 **빠지지 않는다**"*."""
    from app import survive
    w, mode = survive.weights(_drafts())
    assert w.get("G"), (
        f"🔴 `G` 의 무게가 **0** 이다 — 분자·분모에서 사라지고 그 시나리오에서 "
        f"죽는 마켓이 **1.0** 을 받는다: {w}")
    assert sum(w.values()) > w["A"], w


def test_one_죽는_갈래가_있으면_1_0_이_아니다():
    """🔴🔴 **지시서가 이름 댄 계약** — 그림과 수가 어긋나지 않는다."""
    from app import survive
    # ⚠️ `board` 는 **`Market` 목록**이다 — 문자열을 주면 터진다(재서 고쳤다).
    #    🔴 안 주면 §6-c-3 **우리 기준선**으로 센다(그 줄에 토탈 3.5 가 있다).
    got = survive.run(_drafts(), _game())
    under = [m for m in (got.markets or [])
             if "언더" in survive.name_of(m) and "3.5" in survive.name_of(m)]
    assert under, [survive.name_of(m) for m in (got.markets or [])]
    m = under[0]
    dead = list(getattr(m, "dead_scenarios", []) or [])
    assert "G" in dead, (
        f"🔴 `언더 3.5` 가 `G`(3-1·2-2 = 합계 4골)에서 **죽지 않는다고** 적혔다: "
        f"{dead}")
    assert float(m.survival or 0) < 1.0, (
        f"🔴 **죽는 갈래가 있는데 생존 {m.survival}** 이다 — 지시 ① 위반"
        f"(죽는 갈래: {dead})")


def test_one_모든_마켓에_그_불변이_선다():
    """🔴 한 마켓만이 아니다 — **죽는 갈래가 있는 모든 마켓**이 1.0 미만이다."""
    from app import survive
    got = survive.run(_drafts(), _game())
    bad = [(survive.name_of(m), m.survival, list(m.dead_scenarios or []))
           for m in (got.markets or [])
           if (m.dead_scenarios or []) and float(m.survival or 0) >= 1.0]
    assert not bad, f"🔴 죽는 갈래가 있는데 생존 1.0 인 마켓: {bad}"


# ══════════════════════════════════════════════════════════════════
# ② 확정 XI 가 아니면 **"낸다" 금지**
# ══════════════════════════════════════════════════════════════════



def test_one_확정이면_상한이_없다():
    """⚠️ 반대쪽 — 확정이면 막지 않는다."""
    from app import survive
    assert survive.cap_for("confirmed") >= 1.0


def test_one_상한이_실제_판정에_걸린다():
    """🔴🔴 **배선**(#2) — pn7 에서는 걸렸고 pn8 에서는 **안 걸렸다**."""
    from app import survive
    got = survive.run(_drafts(), _game(),
                      xi_state={"Portugal": "baseline", "Norway": "baseline"})
    for m in (got.markets or []):
        assert str(m.verdict or "") != survive.verdict_words()[0], (
            f"🔴 확정 XI 가 아닌데 **`낸다`** 를 냈다: {survive.name_of(m)} "
            f"{m.survival}")


# ══════════════════════════════════════════════════════════════════
# ③ 킥오프가 지난 경기는 **등급을 내지 않는다**
# ══════════════════════════════════════════════════════════════════

def test_one_시작한_경기는_등급이_없다():
    """🔴 *"킥오프가 지난 경기는 등급을 내지 않는다"* — 지시 ③.

    ⚠️ 카드는 그대로 낸다(분석은 보여 준다) — **결론 줄만** 등급 없음이다.
    """
    from app import survive
    kick = dt.datetime(2026, 10, 4, 18, 45, tzinfo=UTC)
    now = kick + dt.timedelta(hours=8)
    got = survive.run(_drafts(), _game(),
                      kickoff=kick, now=now)
    assert got.markets, "⚠️ 마켓 자체는 그린다(분석은 보여 준다)"
    named = [survive.name_of(m) for m in got.markets
             if str(m.verdict or "") in survive.verdict_words()[:3]]
    assert not named, (
        f"🔴 **이미 시작한 경기**에 등급을 냈다: {named} — 예측이 아니다")
    assert any("시작" in x or "지났" in x for x in (got.notes or [])), got.notes


def test_one_시작_전이면_등급을_낸다():
    """⚠️ 반대쪽 — 시작 전에는 막지 않는다(막는 일이 목적이 아니다)."""
    from app import survive
    kick = dt.datetime(2026, 10, 4, 18, 45, tzinfo=UTC)
    now = kick - dt.timedelta(hours=3)
    got = survive.run(_drafts(), _game(),
                      kickoff=kick, now=now,
                      xi_state={"Portugal": "confirmed",
                                "Norway": "confirmed"})
    assert got.markets


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **O02 가 통과했다** — 결론 줄을 재는 계약이 없었다 (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ `word = survive.verdict_word(float(r["survival"]))` 로 되돌려도 이 파일은
#     초록이었다 — **카드 글을 아무도 보지 않았다.**
#  🔴 그것이 pn8 모순의 자리다: 상한이 `small` 로 내렸는데 결론 줄이 생존
#     1.0 으로 **다시 계산해 `낸다`** 를 적었다.






# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **킥오프를 `getattr` 로 더듬지 않는다** — 실측 2026-10-05 (pn12)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: `survive.run(..., kickoff=getattr(card, "kickoff", None))` 이었고
#     `Card` 에 그 칸이 **없어서** 늘 `None` 이었다 — 지시 ③(시작한 경기는 등급
#     없음)이 **조용히 꺼져** 있었다. 카드 머리글은 *"이미 시작"* 을 찍으면서
#     결론 줄은 `소액` 을 적었다. 🔴 `getattr` 기본값은 **없는 칸을 숨긴다.**




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **등급 0 의 까닭을 적는다** — 실측 2026-10-05 (pn14)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: 지시 ③ 이 등급을 전부 거두자 깔때기가 `markets_graded:0` 을 적고
#     **탈락 사유 칸이 비었다** — 독자가 *"시나리오가 모자랐나, 시작했나"* 를
#     구별할 수 없다(#3 조용한 0 금지).
