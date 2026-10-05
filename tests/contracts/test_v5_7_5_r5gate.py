"""🔴🔴 **v5 §7-5 — 자료 부족을 *아무 때나* 선언하지 않는다.**

지시문 §7-5 원문:

> **사다리 2단계 이상 · 도구 호출 6회 이상**을 실제로 돈 **로그가 있을 때만**
> R5 자료 부족을 선언한다. 그 전에 선언하면 `premature_insufficient` 실패.

══════════════════════════════════════════════════════════════════
🔴 왜 — *"자료가 안 왔다"* 와 *"우리가 안 찾았다"* 는 다른 말이다
══════════════════════════════════════════════════════════════════

⚠️ 실측 2026-10-02(중국 vs 팔레스타인 친선): 사실 6건 · 변수 **0건** ·
   §7 R5 자료 부족. 🔴 그런데 그 경기의 **자료 주소는 `ext_id` 에 적혀
   있었다**(`fotmob-6280453`) — 깊이 라우팅이 안 돌아 **아예 안 찾은** 것이다.
   그것을 *"자료 부족"* 이라 적으면 **우리 결함이 자료 탓으로 적힌다.**

🔴 §8-6 이 막는 거짓 사유가 바로 이 섞임이다 — `insufficient` 는 `fix_where`
   가 `수집` 이고, `premature_insufficient` 는 `판정`(우리 버그)이다.
"""
from __future__ import annotations

import pytest


def _fun(queries=0, fetched=0, angles=0):
    from app.funnel import Funnel
    f = Funnel()
    if queries:
        f.set("queries", queries)
    if fetched:
        f.set("fetched", fetched)
    if angles:
        f.set_angles(angles)
    return f


def test_v5_7_5_문턱이_yaml_에_근거와_함께_있다():
    """🔴 §5-6 — 두 수(2단계·6회)는 **상수**다. 근거 없이 코드에 박지 않는다."""
    from app import thresholds
    rows = thresholds.all_rows()
    for name in ("r5_min_ladder_steps", "r5_min_tool_calls"):
        assert name in rows, f"🔴 §7-5 문턱 `{name}` 이 yaml 에 없다"
        assert str(rows[name].get("basis") or "").strip(), name
    assert thresholds.value("r5_min_ladder_steps") == 2
    assert thresholds.value("r5_min_tool_calls") == 6


def test_v5_7_5_깔때기가_사다리_단계를_센다():
    """🔴 **안 재는 것은 선언할 수 없다.** 사다리 단계 수가 깔때기에 있어야 한다.

    ⚠️ 종전 깔때기는 `queries`(던진 검색어 수)만 셌다 — **각도가 몇 개였나**는
       세지 않았다. 🔴 같은 각도로 열 번 던진 것과 두 각도로 두 번 던진 것은
       §7-5 에서 **다른 뜻**이다.
    """
    from app.funnel import Funnel
    f = Funnel()
    # 🔴 **안 쟀으면 `None`** — 0 으로 때우지 않는다(#3)
    assert f.angles is None
    f.set_angles(3)
    assert f.angles == 3


@pytest.mark.parametrize(("q", "fe", "ang", "ok"), [
    (6, 0, 2, True),      # 도구 6회(질의만) · 각도 2 → 선언 가능
    (3, 3, 2, True),      # 질의 3 + 받기 3 = 6회
    (5, 0, 2, False),     # 🔴 도구 5회 — 모자라다
    (6, 0, 1, False),     # 🔴 각도 1 — 사다리를 안 올랐다
    (0, 0, 0, False),     # 아무것도 안 했다
])
def test_v5_7_5_증거가_있을_때만_선언한다_R5(q, fe, ang, ok):
    from app import r5gate
    got = r5gate.may_declare(_fun(queries=q, fetched=fe, angles=ang))
    assert got.ok is ok, (q, fe, ang, got.why)


def test_v5_7_5_못_쟀으면_선언하지_않는다():
    """🔴🔴 **fail-closed.** 각도를 **안 쟀으면**(`None`) 선언할 수 없다.

    ⚠️ 0 으로 보고 *"안 돌았다"* 로 읽으면 맞게 보이지만 — 그러면 `None` 과 `0`
       이 한 글자가 된다. 🔴 *"안 쟀다"* 와 *"재 봤는데 0"* 은 고칠 곳이 다르다.
    """
    from app import r5gate
    from app.funnel import Funnel
    f = Funnel()
    f.set("queries", 20)
    f.set("fetched", 20)
    got = r5gate.may_declare(f)
    assert got.ok is False
    assert "못 쟀다" in got.why or "안 쟀다" in got.why, got.why


def test_v5_7_5_거부하면_사유가_우리_버그다_M12():
    """🔴 `premature_insufficient` 는 **`판정`**(우리 버그)이다 — `수집` 이 아니다."""
    from app import r5gate
    from app.reasons import Reason
    got = r5gate.may_declare(_fun(queries=1, angles=1))
    assert got.reason is Reason.PREMATURE_INSUFFICIENT
    assert got.reason.is_our_bug is True
    assert got.reason.fix_where == "판정"
    # ⚠️ 통과하면 그쪽 사유다
    ok = r5gate.may_declare(_fun(queries=6, angles=2))
    assert ok.reason is Reason.OK


def test_v5_7_5_배선_카드가_그_관문을_지난다():
    """🔴🔴 **안 이어진 관문은 없는 관문이다**(CLAUDE.md #2).

    ══════════════════════════════════════════════════════════════════
    🔴 **첫 판이 돌연변이를 통과시켰다**(돌연변이 I · 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    `r5gate.may_declare(fun)` → `r5gate.Verdict(True, …)` 로 바꿔도 **초록**
    이었다 — 내 계약이 `"r5gate" in 코드` 라는 **낱말**만 봤고 그 낱말은 남아
    있었다. 🔴 D46 — **호출 꼴**을 본다(`may_declare` 를 부르나).
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.build)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "may_declare"]
    assert calls, (
        "🔴 §7-5 관문을 만들어 두고 `analyze.build` 가 **안 부른다** — 아무 때나 "
        "*'자료 부족'* 을 적고, 우리 결함이 자료 탓으로 기록된다")
    # 🔴 그리고 **깔때기를** 줘야 한다(빈 것을 주면 늘 거부다)
    assert [a for a in calls[0].args if isinstance(a, ast.Name)], (
        "🔴 `may_declare()` 에 깔때기를 안 넘긴다 — 볼 수가 없다")


def test_v5_7_5_배선_세포가_각도를_센다():
    """🔴🔴 **돌연변이 F 가 통과했다**(2026-10-04).

    `self.funnel.angle(...)` 를 `pass` 로 바꿔도 **초록이었다** — 각도를 세는
    쪽을 아무 계약도 안 봤다. 🔴 그러면 `angles` 가 영원히 `None` 이고 R5 를
    **한 번도 선언할 수 없다**(fail-closed 라 수는 안 틀리지만 규칙이 죽는다).
    """
    import ast
    import inspect
    import textwrap

    from app import cells
    src = textwrap.dedent(inspect.getsource(cells))
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "angle"]
    assert calls, (
        "🔴 `funnel.angle()` 을 부르는 곳이 **없다** — 사다리 단계를 세지 않으면 "
        "§7-5 가 영원히 거부하고 R5 가 죽는다(CLAUDE.md #2)")
    # 🔴 **실물로** 센다 — 같은 각도를 두 번 던져도 **한 단계**다
    from app.funnel import Funnel
    f = Funnel()
    f.angle("npb_schedule")
    f.angle("npb_schedule")
    assert f.angles == 1, f.angle_names
    f.angle("google_news")
    assert f.angles == 2
    # ⚠️ 빈 이름은 **세지 않는다**(각도가 아니다)
    f.angle("")
    assert f.angles == 2


def test_v5_7_5_카드가_둘을_다른_글자로_적는다():
    """🔴 *"자료 부족"* 과 *"우리가 안 찾았다"* 가 **같은 글자면 안 된다.**"""
    from app import r5gate
    bad = r5gate.may_declare(_fun(queries=1, angles=1))
    assert "자료 부족" not in bad.why, bad.why
    assert bad.line(), bad.line()
    # 🔴 **몇 번·몇 각도였나**를 수로 적는다(#3 조용한 0 금지)
    assert "1" in bad.line()
