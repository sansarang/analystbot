"""🔴🔴 **M109 — `date_missing` 전에 htmldate 가 반드시 돈다**.

지시서 `docs/fable/inbox/2026-10-05_workorder_idn_tha_fixes.md` §4-1·M109.

> `date_missing` 판정 전에 `htmldate` 가 **반드시 호출된다**(호출 기록 없이
> `date_missing` 이 찍히면 실패).

══════════════════════════════════════════════════════════════════
🔴 §4-1 진단 — 재서 찾은 것 (2026-10-05)
══════════════════════════════════════════════════════════════════

it5 로그에서 `[cell] 발행일 —` 줄이 **0건**이었다. 두 가지가 겹쳤다:

| 자리 | 무엇 |
|---|---|
| 세포 경로 | 결정 ③으로 **꺼져 있다**(`cell_search_off 74`) — `pick_published` 가 거기 있어 안 돈다 |
| 하위 에이전트 경로 | `Tools._open` 이 `readtext.read` 의 발행일을 **`_when` 으로 버린다** |
| 변수 조립 | `published_at` 을 **모델이 적은 값**에서만 읽는다 — ③층이 뽑은 날짜가 안 쓰인다 |

🔴 그래서 `htmldate` 는 **돌았지만 그 결과가 검증층에 닿지 않았다** —
   배선 끊김이다(지시서가 의심한 그대로).
"""
from __future__ import annotations

import ast
import inspect


def test_M109_본문_날짜가_버려지지_않는다():
    """🔴 `_open` 이 `readtext.read` 의 발행일을 **들고 있어야** 한다."""
    import textwrap

    from app import agentloop
    src = textwrap.dedent(inspect.getsource(agentloop.Tools._open))
    tree = ast.parse(src)
    # 🔴 `read(...)` 의 **둘째 반환값**(발행일)을 `_` 로 버리지 않는다
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Attribute)
                and n.value.func.attr == "read"):
            continue
        names = [x.id for x in ast.walk(n.targets[0])
                 if isinstance(x, ast.Name)]
        assert len(names) >= 2, names
        assert not names[1].startswith("_"), (
            f"🔴 발행일을 `{names[1]}` 로 **버린다** — ③층이 뽑은 날짜가 "
            f"검증층에 닿지 않는다(실측 it5: `date_missing` 7건)")
        return
    raise AssertionError("🔴 `readtext.read` 호출을 못 찾았다")


def test_M109_본문_날짜를_칸으로_든다():
    from app import agentloop
    assert "dates" in agentloop.Tools.__dataclass_fields__, (
        "🔴 `Tools` 에 `dates` 칸이 없다 — 받은 본문의 발행일을 둘 곳이 없다")


def test_M109_변수가_본문_날짜를_받는다():
    """🔴 모델이 안 적어도 **우리가 뽑은 날짜**가 쓰인다."""
    from app import agentloop
    src = inspect.getsource(agentloop)
    at = src.find('row.get("published_at")')
    assert at > 0, "🔴 그 자리를 못 찾았다 — 이 계약을 고쳐라"
    seg = src[max(0, at - 400):at + 400]
    assert "dates" in seg or "pick_published" in seg, (
        "🔴 변수가 **모델이 적은 값만** 본다 — ③층이 뽑은 발행일을 쓰지 "
        "않는다(지시서: `htmldate` 가 `published_at` 의 **원본**이다)")


def test_M109_날짜를_정하는_곳이_하나다():
    """🔴 본문 ↔ 검색 날짜 우선순위는 `net.pick_published` **한 곳**이다(#1)."""
    from app import agentloop
    tree = ast.parse(inspect.getsource(agentloop))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "pick_published" in called, (
        "🔴 에이전트 경로가 `pick_published` 를 안 부른다 — 어느 쪽이 원본인지 "
        "자리마다 달라진다")
