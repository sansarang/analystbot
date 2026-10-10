"""🔴🔴 **확정 라인업 전략 → 승률 재계산** — 사용자 지시 2026-10-10(둘째).

> 계약: **예상 XI 로 전략 판정 금지** / **수치와 반대인 판정 버림** / **교체 전문
> 선수 벤치를 결장·약화로 읽지 않음** / **전략 문장이 최종 확률과 같은 방향**.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                    competition_short="K리그1", home="team:000318",
                    away="team:000320", home_name="Gangwon FC",
                    away_name="Bucheon FC 1995",
                    kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))


def _xi(team: str, state: str, names: list[str], *, formation: str = "4-4-2",
        bench: list[str] | None = None):
    from app.core.schema import XI
    return XI(team=team, state=state, formation=formation, players=names,
              bench=[str(x) for x in (bench or [])])


def test_v6_예상_XI_로는_전략을_판정하지_않는다():
    """🔴🔴 §1 — *"예상 XI 로는 전략을 추론하지 않는다"*.

    ⚠️ 돌연변이: `strategy.read` 가 상태를 안 보면 — 예상 XI(우리가 **빈도로 지은
       것**)로 전략을 읽게 되고 *"평소 그대로"* 가 늘 나온다(동어반복).
    """
    from app.core import strategy
    from app.core.schema import Facts
    from app.core.state import RunState
    from app.core.stages import s2d_strategy
    ref = _ref()
    facts = Facts(xi={ref.home: _xi(ref.home, "predicted", [f"P{i}" for i in range(11)]),
                      ref.away: _xi(ref.away, "predicted", [f"Q{i}" for i in range(11)])})
    for side in ("home", "away"):
        got = strategy.read(ref, facts, side=side)
        assert not got.confirmed, side
        assert "확정 XI 전" in got.why, got.why
        assert not got.facts, "🔴 예상 XI 로 사실을 만들었다"
    out = s2d_strategy.run(ref, facts, state=RunState(match_key="x:1"))
    assert out.audit == "확정 XI 전", out.audit
    assert not out.lines, "🔴 예상 XI 로 판정을 냈다"


def test_v6_수치와_반대인_판정은_버린다():
    """🔴🔴 §2-2 — *"판정이 2-1 수치와 반대면 버린다"*(ΔA −15%·3백인데 공격 위주).

    ⚠️ 돌연변이: `check` 의 ΔA·수비 수 검사를 지우면 — 모델이 명단과 **반대되는**
       이야기를 써도 그대로 확률을 움직인다.
    """
    from app.core.schema import StrategyLine
    from app.core.stages.s2d_strategy import check

    class _R:
        def __init__(self, da=None, back=(None, None), changed=1):
            self.da = da
            self.back_usual, self.back_now = back
            self.changed = changed

        def ids(self):
            return ["L1", "L2", "L3"]

    reads = {"home": _R(da=-15.0, back=(4, 3)), "away": _R(da=0.0)}
    bad = check([StrategyLine(side="home", strategy="공격 위주",
                              fact_refs=["L1", "L2"])], reads)
    assert bad and any("공격 위주" in x for x in bad), bad
    # 🔴 수치와 **맞는** 판정은 통과한다
    assert not check([StrategyLine(side="home", strategy="수비 위주",
                                   fact_refs=["L1", "L2"])], reads)
    # 🔴 **근거 2개 미만**도 버린다(§2-2 "근거 없는 판정 금지")
    bad2 = check([StrategyLine(side="home", strategy="수비 위주",
                               fact_refs=["L1"])], reads)
    assert bad2 and "근거" in bad2[0], bad2
    # 🔴 **없는 id** 는 근거로 세지 않는다
    bad3 = check([StrategyLine(side="home", strategy="수비 위주",
                               fact_refs=["Z9", "Z8"])], reads)
    assert bad3, bad3
    # 🔴 로테이션인데 바뀐 자리 0 → 버린다
    bad4 = check([StrategyLine(side="away", strategy="로테이션·체력 관리",
                               fact_refs=["L1", "L2"])],
                 {"away": _R(changed=0)})
    assert bad4 and "로테이션" in bad4[0], bad4


def test_v6_교체전문_벤치는_약화가_아니다():
    """🔴🔴 §2-1·§2-4 — 시즌 선발 비율 **30% 미만** 선수의 벤치는 *평소 운용*.

    실례: **가시와 세가와**(교체로 7골). ⚠️ 돌연변이: 그 검사를 지우면 매 경기
       그 팀에 *"핵심 선수 빠짐"* 변수가 하나 생긴다.
    """
    from app.core import strategy
    from app.core.schema import Facts
    ref = _ref()
    names = [f"P{i}" for i in range(11)]
    past = [_xi(ref.home, "confirmed", names) for _ in range(5)]
    facts = Facts(
        xi={ref.home: _xi(ref.home, "confirmed", names, bench=["세가와"]),
            ref.away: _xi(ref.away, "confirmed", [f"Q{i}" for i in range(11)])},
        past_xi={ref.home: past})
    got = strategy.read(ref, facts, side="home")
    assert got.confirmed
    said = [dict(x) for x in got.bench_regulars]
    assert any(x["name"] == "세가와" for x in said), said
    # 🔴 그 사실이 **"평소 운용"** 이라고 적혀야 한다(약화가 아니다)
    text = " ".join(f.text for f in got.facts if f.kind == "bench_regular")
    assert "평소 운용" in text, text
    assert strategy.starter_share() == 0.30


def test_v6_전략은_표의_계수로만_확률을_움직인다():
    """🔴🔴 §3-2 — *"적합 없는 계수를 **표시 없이** 사용"* 금지.

    ⚠️ 돌연변이 ①: `fit` 칸 검사를 지우면 적합 상태를 모르는 계수가 조용히
       확률을 움직인다. ⚠️ 돌연변이 ②: 상한(±0.5 로그 오즈 · λ ±15%)을 지우면
       전략 하나가 카드를 뒤집는다. 🔴 둘 다 센다.
    """
    from app.core import strategy
    box = strategy.effects()
    assert box.get("source") and box.get("checked_at"), "🔴 출처·확인일이 없다"
    cap_lo, cap_pct = strategy.caps()
    assert cap_lo == 0.5 and cap_pct == 15.0, (cap_lo, cap_pct)
    for kind in strategy.KINDS:
        got, why = strategy.move_of(kind)
        assert got, f"🔴 `{kind}` 의 이동량이 표에 없다"
        assert why, f"🔴 `{kind}` 에 사유가 없다"
        if dict((box.get("effects") or {}).get(kind) or {}).get(
                "fit", {}).get("provisional"):
            assert strategy.PROVISIONAL in why, (kind, why)
    # 🔴 `fit` 칸이 없는 계수는 **쓰지 않는다**
    assert strategy.move_of("없는 전략")[0] == {}
    # 🔴 **λ 상한을 지킨다** — 큰 이동을 넣어도 ±15% 안이다
    got, why = strategy._apply(2.0, 90.0, [], cap_pct)
    assert abs(got / 2.0 - 1.0) <= cap_pct / 100.0 + 1e-9, got
    assert "잘렸다" in why, why


def test_v6_전략_문장이_최종_확률과_같은_방향이다():
    """🔴🔴 §4 — 이유 문단에 **전략 문장 최소 1개** · **최종 확률과 같은 방향**.

    ⚠️ 돌연변이: `(p)` 검열을 지우면 전략이 **이야기로만** 남는다(§금지 첫 줄:
       *"전략을 이야기로만 쓰고 확률 미반영"*).
    """
    from app.core.schema import ReasonLine, StrategyLine, StrategyOut
    from app.core.stages.s9_audit import strategy_check

    class _Card:
        match = _ref()
        strategy = StrategyOut(
            audit="통과",
            lines=[StrategyLine(side="home", strategy="공격 위주",
                                fact_refs=["L1", "L2"])])
        our_prob = None
        variables: list = []

    got = _Card()
    # 🔴 전략을 **안 쓰면** 위반
    bad = strategy_check([ReasonLine(text="날씨가 좋다", fact_refs=[])], card=got)
    assert bad and "(p)" in bad[0], bad
    # 🔴 쓰면 통과(방향을 못 재면 방향 검사는 건너뛴다)
    assert not strategy_check(
        [ReasonLine(text="강원은 공격 위주 명단이다", fact_refs=[])], card=got)
    # 🔴 판정이 **버려졌으면** 아무것도 세지 않는다
    got.strategy = StrategyOut(audit="버렸다")
    assert not strategy_check([ReasonLine(text="x", fact_refs=[])], card=got)


def test_v6_카드가_전략과_확률변화를_확정XI에만_낸다():
    """🔴 §4 — 두 블록은 **확정 XI 일 때만** 나간다.

    ⚠️ 돌연변이: `move_block` 의 판정 검사를 지우면 — 전략이 없는 카드에도
       `잠정 → 최종` 이 찍히고 그 둘은 **늘 같은 수**다(거짓 신호).
    """
    import ast
    from app.core import layer1
    said = (ROOT / "app" / "core" / "layer1.py").read_text(encoding="utf-8")
    for fn in ("plan_block", "move_block"):
        src = [n for n in ast.walk(ast.parse(said))
               if isinstance(n, ast.FunctionDef) and n.name == fn]
        assert src, fn
        assert "audit" in ast.unparse(src[0]), (
            f"🔴 `{fn}` 이 판정 상태를 안 본다 — 예상 XI 카드에도 블록이 나간다")
    assert layer1.PLAN_HEAD.startswith("🧠") and layer1.MOVE_HEAD.startswith("📊")


def test_v6_XI_상태를_영어_칸으로_본다():
    """🔴🔴 **실사고 2026-10-10** — `XI.state` 는 영어인데 코드가 한국어와 비교했다.

    `XI.state` 는 `Literal["confirmed","predicted","none"]` 다. 그런데
    `layer1.xi_confirmed`·`layer1._xi`·`render` 가 **`"확정"`** 과 비교했다 —
    그 비교는 **영원히 거짓**이므로:
      · 라인업 줄이 늘 `예상` 이었고(고정물에서 실제 상태는 `없음` 이었다)
      · 등급이 늘 `잠정` 이었고
      · 새로 넣은 전략 단계가 **한 번도 돌 수 없었다**.

    ⚠️ 돌연변이: `xi_state` 가 영어 칸을 안 보면 — 확정 XI 를 영원히 못 알아본다.
    🔴 옮기는 표는 `layer1.XI_KO` **하나**다(사본 금지).
    """
    from app.core.schema import Facts, XI
    from app.core import layer1
    assert set(XI.model_fields["state"].annotation.__args__) == \
        set(layer1.XI_KO), "🔴 상태 글자 표가 스키마와 안 맞는다"

    class _C:
        def __init__(self, states):
            self.facts = Facts(xi={f"team:00000{i}": XI(
                team=f"team:00000{i}", state=s, players=["x"])
                for i, s in enumerate(states, start=1)})

    assert layer1.xi_state(_C(["confirmed", "confirmed"])) == "확정"
    assert layer1.xi_confirmed(_C(["confirmed", "confirmed"]))
    assert layer1.xi_state(_C(["confirmed", "predicted"])) == "예상"
    assert not layer1.xi_confirmed(_C(["confirmed", "predicted"]))
    assert layer1.xi_state(_C(["none", "none"])) == "없음"
    assert layer1.xi_state(_C([])) == "없음"
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **원본 칸(`.state`)을 한국어와 비교하는 코드가 있으면 빨개진다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 글자로만 찾으면 **옮긴 뒤의 비교**(`xi_state(card) == "확정"`)까지
    #     잡는다 — 그것은 맞는 코드다(실측 2026-10-10: 내 첫 검사가 그랬다).
    #  🔴 그래서 **비교의 왼쪽에 `.state` 나 `state=` 가 있는 것만** 센다(AST).
    import ast
    bad: list[str] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            left = ast.unparse(node.left)
            # 🔴 **칸 접근**(`x.state`·`getattr(x, "state")`)만 센다.
            #    ⚠️ `xi_state(card)` 는 **옮긴 뒤의 글자**라 한국어와 비교하는
            #       것이 맞다(내 첫 검사가 그것까지 잡았다 · 2026-10-10).
            raw = (".state" in left or '"state"' in left or "'state'" in left)
            if not raw or "xi_state(" in left:
                continue
            for one in node.comparators:
                said_r = ast.unparse(one)
                if any(w in said_r for w in ('"확정"', "'확정'", '"예상"',
                                             "'예상'", '"없음"', "'없음'")):
                    bad.append(f"{path.relative_to(ROOT)}: {left} ? {said_r}")
    assert not bad, ("🔴 **원본 상태 칸을 한국어와 비교한다**(그 비교는 영원히 "
                     "거짓이다):\n  " + "\n  ".join(bad))
