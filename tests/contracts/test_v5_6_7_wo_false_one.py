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

@pytest.mark.parametrize("state", ["", "baseline", "predicted", "unknown"])
def test_one_확정_XI_가_아니면_낸다_금지(state):
    """🔴 *"`lineup_state` 가 `confirmed` 가 아니면 **"낸다"(1.0) 금지**"*."""
    from app import survive
    got = survive.cap_for(state)
    # 🔴 **수를 여기 적지 않는다** — 지시 ②가 말한 것은 *"확정이 아니면 `낸다`
    #    (1.0) 금지"* 다. 칸마다의 수는 `scenario_rules.yaml` 이 든다(§6-5).
    #    ⚠️ 실사고 2026-10-05: 여기 `0.8` 을 박아 두어, 표가 `양쪽예상: 0.85`
    #       라고 적은 칸에서 계약이 **표를 틀렸다고** 말했다(사본 금지 #1).
    assert got < 1.0, (
        f"🔴 `lineup_state={state!r}` 인데 상한이 {got} 다 — 확정이 아니면 "
        f"1.0 이 될 수 없다")
    assert survive.word_of(survive.verdict_word(got)) != survive.verdict_words()[0], (
        f"🔴 상한 {got} 인데 등급 어휘가 **최상**이다 — `낸다` 금지(지시 ②)")


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


def test_one_O02_결론_줄이_상한을_따른다():
    """🔴🔴 **카드 글**을 본다 — 상한이 내린 등급이 결론 줄에 그대로 와야 한다."""
    from app import survive
    # 🔴 `verdict` 가 `small` 인데 생존은 1.0 인 줄(pn8 의 그 꼴)
    assert survive.word_of("small") == survive.verdict_words()[1], \
        survive.word_of("small")
    assert survive.word_of("name") == survive.verdict_words()[0]
    # ⚠️ 그리고 **생존 수로 다시 재면** 다른 글자가 된다 — 그 둘이 달라야 이
    #    계약이 뜻을 갖는다(같으면 돌연변이를 못 잡는다)
    assert survive.verdict_word(1.0) != survive.word_of("small"), (
        "🔴 `verdict_word(1.0)` 과 `word_of('small')` 이 같다 — 이 계약이 "
        "O02 를 못 잡는다")


def test_one_O02_카드가_판정_코드를_쓴다():
    """🔴 **배선**(#2) — 결론 줄이 `word_of` 를 쓰고 `verdict_word` 를 안 쓴다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze.render))
    i = body.index("■ 8 결론")
    seg = body[i:i + 1400]
    assert "word_of(" in seg, (
        "🔴 결론 줄이 `survive.word_of(verdict)` 를 **안 쓴다** — 상한을 "
        "무시하고 생존으로 다시 계산한다(pn8 모순)")
    assert "verdict_word(" not in seg, (
        "🔴 결론 줄이 **생존으로 다시 계산한다** — 상한이 내린 등급을 되올린다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **킥오프를 `getattr` 로 더듬지 않는다** — 실측 2026-10-05 (pn12)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: `survive.run(..., kickoff=getattr(card, "kickoff", None))` 이었고
#     `Card` 에 그 칸이 **없어서** 늘 `None` 이었다 — 지시 ③(시작한 경기는 등급
#     없음)이 **조용히 꺼져** 있었다. 카드 머리글은 *"이미 시작"* 을 찍으면서
#     결론 줄은 `소액` 을 적었다. 🔴 `getattr` 기본값은 **없는 칸을 숨긴다.**
def test_카드가_킥오프를_칸으로_든다():
    from app import analyze
    assert "kickoff" in analyze.Card.__dataclass_fields__, (
        "🔴 `Card` 에 `kickoff` 칸이 없다 — `getattr(card,'kickoff',None)` 이 "
        "늘 `None` 이라 지시 ③ 이 조용히 꺼진다")


def test_시작한_경기는_결론_줄에_등급이_없다():
    """🔴 **끝까지** 본다 — 생존 1.0 이어도 시작했으면 등급은 `없음`."""
    import datetime as _dt

    from app import analyze, survive
    kick = _dt.datetime(2026, 10, 5, 3, 45, tzinfo=_dt.timezone.utc)
    now = kick + _dt.timedelta(hours=10)
    gone, said = survive.started(kick, now)
    assert gone and said, "🔴 10시간 지난 경기를 '안 시작했다'고 한다"
    # 🔴 그리고 **`survive.run` 이 그 칸을 받는다**(#2 배선).
    #    ⚠️ 문자열로 보지 않는다 — M97(`getattr(card,"kick2",None)` 로 바꾸기)이
    #       **통과했다**: `body.find("kickoff=")` 가 엉뚱한 첫 자리를 집었다(D46).
    #    🔴 **AST 로** 본다: 그 인자가 `card.kickoff` **칸 읽기**여야 한다.
    import ast
    import inspect
    found = []
    for node in ast.walk(ast.parse(inspect.getsource(analyze))):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "run"
                and isinstance(f.value, ast.Name) and f.value.id == "survive"):
            continue
        for kw in node.keywords:
            if kw.arg == "kickoff":
                found.append(kw.value)
    assert found, "🔴 `survive.run(kickoff=…)` 을 안 넘긴다 — 지시 ③ 이 꺼진다"
    for val in found:
        assert isinstance(val, ast.Attribute) and val.attr == "kickoff", (
            f"🔴 킥오프를 **칸으로** 안 넘긴다({ast.dump(val)[:80]}) — "
            f"`getattr` 기본값은 없는 칸을 숨긴다(실측 pn12)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **등급 0 의 까닭을 적는다** — 실측 2026-10-05 (pn14)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: 지시 ③ 이 등급을 전부 거두자 깔때기가 `markets_graded:0` 을 적고
#     **탈락 사유 칸이 비었다** — 독자가 *"시나리오가 모자랐나, 시작했나"* 를
#     구별할 수 없다(#3 조용한 0 금지).
def test_시작해서_등급을_거둔_것이_깔때기에_남는다():
    import datetime as _dt

    from app import funnel as _f
    from app.reasons import Reason
    assert hasattr(Reason, "KICKOFF_PASSED"), (
        "🔴 `kickoff_passed` 사유가 없다 — 시작해서 거둔 것과 시나리오 부족을 "
        "구별할 수 없다")
    fun = _f.Funnel()
    fun.set("markets_graded", 0)
    fun.drop(Reason.KICKOFF_PASSED, "markets_graded")
    said = fun.drop_line()
    assert "kickoff_passed" in said, said
    # 🔴 **배선**(#2) — 카드가 그 사유를 실제로 붙인다
    import ast
    import inspect

    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    hit = [n for n in ast.walk(tree)
           if isinstance(n, ast.Attribute) and n.attr == "KICKOFF_PASSED"]
    assert hit, (
        "🔴 카드가 `KICKOFF_PASSED` 를 **안 쓴다** — 사유가 깔때기에 안 남는다")
    # 🔴 그리고 그 판단은 `survive.started` 가 남긴 글로 한다(사본 금지)
    import datetime as _dt2

    from app import survive
    _, said2 = survive.started(
        _dt.datetime(2026, 10, 5, 3, 45, tzinfo=_dt2.timezone.utc),
        _dt.datetime(2026, 10, 5, 13, 45, tzinfo=_dt2.timezone.utc))
    assert "지시 ③" in said2, said2
