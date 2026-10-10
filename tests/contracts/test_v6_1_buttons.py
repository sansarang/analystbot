"""🔴🔴 **버튼이 실제 버튼인가** — 사용자 지시 2026-10-10(재작성) §1-3·§2-3.

> 후보 2개 이상 → **텔레그램 버튼으로 고르게 한다**. 고르기 전에 분석하지 않는다.
> 카드에 버튼 `[🔔 라인업 나오면 다시 분석]` — **사용자가 누른 경기만** 돈다.

⚠️ 실측 2026-10-10: 봇에 인라인 키보드가 **하나도 없었다**(`grep InlineKeyboard`
   → 0건). 카드 밑 `[📖 자세히]` 는 **글자**였고 누를 수 없었다. 🔴 이 계약이
   그 상태로 되돌아가는 것을 막는다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def test_v6_카드가_인라인_키보드와_함께_나간다():
    """🔴 §1-3 — 카드를 보내는 자리가 `reply_markup` 을 **실제로** 싣는다.

    ⚠️ 돌연변이: `_send_card` 에서 `reply_markup=kb` 를 지우면 버튼이 **조용히
       사라진다**(글자는 그대로라 사람이 못 알아챈다). 이 계약이 잡는다.
    """
    said = (ROOT / "app" / "bot" / "main.py").read_text(encoding="utf-8")
    assert "reply_markup=kb" in said, (
        "🔴 카드를 보낼 때 버튼을 안 싣는다 — §1-3 의 '버튼으로 고르게 한다'가 "
        "글자로만 남는다")
    calls = {ast.unparse(n.func) for n in ast.walk(_tree(
        ROOT / "app" / "bot" / "main.py")) if isinstance(n, ast.Call)}
    for want in ("keys.pick_keys", "keys.card_keys"):
        assert want in calls, f"🔴 `{want}` 를 안 부른다"


def test_v6_콜백_핸들러가_등록돼_있다():
    """🔴 버튼을 눌러도 **아무 일도 안 일어나는** 상태를 막는다.

    ⚠️ 돌연변이: `@dp.callback_query()` 데코레이터를 지우면 버튼은 보이는데
       눌러도 반응이 없다(그 쪽이 **더 나쁘다** — 사용자가 기다린다).
    """
    said = _tree(ROOT / "app" / "bot" / "main.py")
    hit = [fn.name for fn in ast.walk(said)
           if isinstance(fn, ast.AsyncFunctionDef)
           and any("callback_query" in ast.unparse(d) for d in fn.decorator_list)]
    assert hit, "🔴 콜백 핸들러가 **없다** — 버튼이 눌려도 아무 일도 안 한다"


def test_v6_콜백_글자가_64바이트를_넘지_않는다():
    """🔴 텔레그램 한계. ⚠️ 넘으면 버튼이 **만들어지지 않는다**(조용히 사라진다).

    🔴 그래서 긴 열쇠는 **토큰**으로 줄인다(`app/bot/pending.py`).
    """
    from app.bot import keys
    said = keys.pack("pick", "a" * 200)
    assert len(said.encode()) <= keys.CB_CAP, len(said)
    # 🔴 판 번호가 다른 옛 버튼은 **안 받는다**
    assert keys.unpack("0|pick|x") == ("", "")
    assert keys.unpack(keys.pack("pick", "a1:2")) == ("pick", "a1:2")


def test_v6_고른_경기는_다시_찾지_않는다():
    """🔴🔴 §1-3 — 고른 뒤에는 `pick_key` 로 **못 박는다**.

    ⚠️ 돌연변이: `pipeline.analyze` 가 `pick_key` 를 무시하면 — 다시 찾아 또
       여럿이 나오고 **같은 자리에서 멈춘다**(사용자가 고른 것이 무의미해진다).
    """
    import inspect
    from app.core import pipeline
    from app.core.stages import s1_resolve
    for fn in (pipeline.analyze, s1_resolve.run):
        assert "pick_key" in inspect.signature(fn).parameters, fn
    calls = {ast.unparse(n.func) for n in ast.walk(_tree(
        ROOT / "app" / "core" / "stages" / "s1_resolve.py"))
        if isinstance(n, ast.Call)}
    assert "slate.by_key" in calls, (
        "🔴 고른 경기를 **표에서 집지 않는다** — 열쇠로 다니라는 규율(3단계)이다")


def test_v6_감시는_사용자가_누른_경기만_돈다():
    """🔴🔴 §2-3 — *"누르지 않으면 돌지 않는다(자동 분석 아님)"*.

    ⚠️ 돌연변이: `watch.start` 를 카드 렌더링이나 스케줄러에서 부르면 — 그것은
       **자동 분석**이고 지시서 전제를 어긴다. 🔴 부르는 곳이 **버튼 핸들러
       하나**여야 한다.
    """
    hits: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        if p.name == "watch.py":
            continue
        for node in ast.walk(_tree(p)):
            if isinstance(node, ast.Call) and \
                    ast.unparse(node.func).endswith("watch.start"):
                hits.append(str(p.relative_to(ROOT)))
    assert hits == ["app/bot/main.py"], (
        f"🔴 라인업 감시를 버튼 밖에서 켠다 {hits} — 그것은 **자동 분석**이다"
        f"(지시서 전제: 묻지 않은 경기는 돌리지 않는다)")
    from app.bot import watch
    assert watch.EVERY_SEC == 300, "🔴 §2-3 은 **5분 간격**이라고 적었다"
