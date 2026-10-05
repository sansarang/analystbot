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


def _inp():
    """🔴 계약이 쓰는 최소 `AgentInput` — 값은 이 계약과 무관하다."""
    import datetime as dt

    from app import agentloop
    return agentloop.AgentInput(
        match_key="fotmob:1", home="team:000268", away="team:000085",
        home_names=("Northern Ireland",), away_names=("Georgia",),
        competition="UEFA Nations League B Grp. 2", sport="soccer",
        kickoff_utc=dt.datetime(2026, 10, 5, 18, 45,
                                tzinfo=dt.timezone.utc),
        venue="Windsor Park", langs=("en",))


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


def test_M109_저장소가_하나다():
    """🔴🔴 **본문과 날짜는 한 저장소다** — 사용자 지시 2026-10-06.

    > 본문 캐시를 `url → {body, published_at, date_source}` 로 바꿔 **Seen
    > 하나**에 담는다. `bodies` 와 `dates` 를 **따로 들고 다니는 경로를 없앤다.**

    ⚠️ 종전 계약은 *"`Tools` 에 `dates` 칸이 있어야 한다"* 였다 — 🔴 그 칸이
       바로 결함이었다(하위마다 새로 생겨 다른 하위의 날짜를 못 봤다).
    """
    from app import agentloop
    from app.cells import Seen
    # 🔴 ① `Tools` 는 그 둘을 **칸으로 들지 않는다**(따로 들고 다니는 길이 없다)
    for gone in ("bodies", "dates"):
        assert gone not in agentloop.Tools.__dataclass_fields__, (
            f"🔴 `Tools.{gone}` 가 **칸으로** 돌아왔다 — 하위마다 새로 생겨 "
            f"다른 하위가 받아 둔 것을 못 본다(실측 `date_missing` 6건)")
    # 🔴 ② `Seen` 이 한 저장소를 든다
    assert "docs" in Seen.__dataclass_fields__, "🔴 `Seen.docs` 가 없다"
    s = Seen()
    s.add_doc("https://x/1", "본문", published_at="2026-10-05",
              date_source="본문")
    for key in ("body", "published_at", "date_source"):
        assert key in s.docs["https://x/1"], (key, s.docs)
    # 🔴 ③ 뷰는 **사본이 아니다** — 쓰면 원본에 들어간다
    t = agentloop.Tools(inp=_inp(), seen=s)
    t.bodies["https://x/2"] = "뷰로 쓴 본문"
    assert s.docs["https://x/2"]["body"] == "뷰로 쓴 본문", s.docs
    assert t.bodies.get("https://x/1") == "본문"
    assert t.dates.get("https://x/1") == "2026-10-05"


def test_M109_다른_하위가_받은_본문의_날짜도_변수에_붙는다():
    """🔴🔴 **이것이 실측된 결함이다** — 사용자 지시 2026-10-06 ②의 계약.

    > 계약: **다른 하위가 받은 본문을 인용한 변수도 날짜를 가진다.**

    ⚠️ 실측 2026-10-06(북아일랜드–조지아): 받은 문서 **24건 전부** 발행일이
       있었는데(`발행일 — 없다` 0건) 검증층이 `date_missing` **6건**을 냈다.
       🔴 본문은 하위를 가로지르는 `seen` 에서 오고 날짜는 하위마다 새로 생기는
          `Tools.dates` 에만 있었기 때문이다.
    """
    import datetime as dt

    from app import agentloop
    from app.cells import Seen
    shared = Seen()
    # ── 하위 A 가 받았다(본문 + 발행일)
    a = agentloop.Tools(inp=_inp(), seen=shared)
    a.store.add_doc("https://news/1", "Bradley is unavailable.",
                    published_at="2026-10-04T10:00:00+00:00",
                    date_source="본문")
    # ── 하위 B 는 **그 URL 을 받지 않았다** — 저장소에서 재사용할 뿐이다
    b = agentloop.Tools(inp=_inp(), seen=shared)
    assert b.dates.get("https://news/1"), (
        "🔴 다른 하위가 받은 날짜가 **안 보인다** — 저장소가 갈려 있다")
    # 🔴 그 하위가 만든 변수에 날짜가 **실제로 붙는가**
    box = {"variables": [{"id": "v3", "type": "def_absence",
                          "team": "team:000268", "claim": "x",
                          "quote": "Bradley is unavailable.",
                          "url": "https://news/1"}]}
    got, why = agentloop._vars_from(box, dates=b.dates)
    assert got, why
    when = getattr(got[0], "published_at", None)
    assert isinstance(when, dt.datetime), (
        f"🔴 날짜가 안 붙었다({when!r}) — 검증층이 `date_missing` 으로 버린다")
    assert when.tzinfo is not None, when


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
