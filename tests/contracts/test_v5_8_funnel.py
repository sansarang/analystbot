"""🔴🔴 **v5 §8-5 — 깔때기 아홉 칸.** 사유 코드별 개수를 함께 적는다.

§8-5 원문:

> 경기마다 한 줄: `queries → hits → kept_identity → kept_date → fetched →
> agent_vars → verified_vars → scenarios → markets_graded`.
> 단계 간 탈락은 **사유 코드별 개수**를 같이 적는다. 변수가 0 이 되는 자리를
> 숫자로 보기 위한 것이고, 카드 하단에 요약을 붙인다.

══════════════════════════════════════════════════════════════════
🔴 v4 의 일곱 칸과 **무엇이 다른가**
══════════════════════════════════════════════════════════════════

```
v4  queries → hits → kept_identity → kept_date → facts → typed → variables
v5  queries → hits → kept_identity → kept_date → fetched →
                              agent_vars → verified_vars → scenarios → markets_graded
```
⚠️ `facts`·`typed` 가 사라지고 `fetched`·`agent_vars`·`verified_vars`·
   `scenarios`·`markets_graded` 가 들어온다 — **에이전트가 읽기 주체**가 되고
   `typed`(정규식 유형표)가 §1 의 *"버리는 것"* 에 들어갔기 때문이다.
🔴 그래서 *"typed 20 → variables 3"* 같은 진단 대신
   *"agent_vars 9 → verified_vars 2 (quote_not_found 5 · date_missing 2)"* 를 본다.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
V5 = ROOT / "docs" / "fable" / "inbox" / "2026-10-04_v5_solar.md"


def declared_stages() -> list[str]:
    """🔴 문서 §8-5 가 적은 **순서 그대로**의 칸 목록."""
    text = V5.read_text(encoding="utf-8")
    i = text.index("8-5 깔때기")
    seg = text[i:i + 500]
    seg = re.sub(r"Page \d+ of \d+|AnalystBot v5[^\n]*", " ", seg)
    got = re.findall(r"\b(queries|hits|kept_identity|kept_date|fetched|"
                     r"agent_vars|verified_vars|scenarios|markets_graded)\b", seg)
    out: list[str] = []
    for g in got:
        if g not in out:
            out.append(g)
    return out


def test_v5_8_5_문서가_아홉_칸을_들고_있다():
    got = declared_stages()
    assert got == ["queries", "hits", "kept_identity", "kept_date", "fetched",
                   "agent_vars", "verified_vars", "scenarios",
                   "markets_graded"], got


def test_v5_8_5_깔때기가_그_아홉_칸이다():
    """🔴 **순서가 뜻이다** — `broke_at` 이 *"처음으로 0 이 된 칸"* 을 찾는다."""
    from app.funnel import STAGES
    assert list(STAGES) == declared_stages(), list(STAGES)


def test_v5_8_5_칸마다_단위가_있다():
    """🔴 단위를 안 적으면 **문서 수와 사실 수를 같은 자로 잰다**(v4 에서 다쳤다).

    ⚠️ 실측 2026-10-03: `kept_identity`(문서) → `kept_date`(사실) 사이에서
       비율을 세어 *"97% 가 날짜에서 떨어졌다"* 로 읽을 뻔했다.
    """
    from app.funnel import STAGES, UNITS
    for s in STAGES:
        assert UNITS.get(s), f"🔴 `{s}` 의 단위가 없다"


def test_v5_8_5_칸마다_0일_때_무엇을_볼지_있다():
    from app.funnel import STAGES, WHY_ZERO
    for s in STAGES:
        assert str(WHY_ZERO.get(s) or "").strip(), f"🔴 `{s}` 의 진단이 없다"


def test_v5_8_5_사유_코드별_개수를_센다():
    """🔴🔴 §8-5 — *"단계 간 탈락은 **사유 코드별 개수**를 같이 적는다."*

    ⚠️ v4 의 `Funnel.lost` 는 **문장 목록**이었다. 그러면 같은 사유가 몇 건인지
       한눈에 안 보이고, 긴 문장 열일곱 줄이 카드를 덮는다(실측 2026-10-04).
    🔴 §8-5 는 **개수**를 요구한다 — 사유 코드가 열쇠다.
    """
    from app.funnel import Funnel
    from app.reasons import Reason
    f = Funnel()
    f.drop(Reason.QUOTE_NOT_FOUND, "agent_vars")
    f.drop(Reason.QUOTE_NOT_FOUND, "agent_vars")
    f.drop(Reason.DATE_MISSING, "agent_vars")
    got = f.drops.get("agent_vars") or {}
    assert got.get(Reason.QUOTE_NOT_FOUND) == 2, got
    assert got.get(Reason.DATE_MISSING) == 1, got
    line = f.report()
    assert "quote_not_found 2" in line and "date_missing 1" in line, line


def test_v5_8_5_모르는_칸은_조용히_사라지지_않는다():
    """🔴 오타로 칸이 없어지면 그 단계가 **안 센 채로** 지나간다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    첫 판은 `drop()` **하나만** 봤다. 그런데 칸으로 들어오는 문은 **셋**이다 —
    `add`·`set`·`drop`. 🔴 `add` 의 기록을 지운 돌연변이가 **초록이었다.**
    ⚠️ 그래서 세 문을 **전부** 본다.
    """
    from app.funnel import Funnel
    from app.reasons import Reason
    for label, call in (
            ("add", lambda f: f.add("오타난칸", 1)),
            ("set", lambda f: f.set("오타난칸", 5)),
            ("drop", lambda f: f.drop(Reason.DATE_MISSING, "오타난칸")),
    ):
        f = Funnel()
        call(f)
        # ⚠️ 세지 않더라도 **사실은 남는다** — 어디에도 안 남으면 조용한 0 이다
        assert any("오타난칸" in str(x) for x in (f.unknown_stages or [])), \
            f"🔴 `{label}` 이 모르는 칸을 **조용히 버렸다**: {f.unknown_stages}"
        # 🔴 그리고 **아홉 칸을 오염시키지 않았다**
        assert set(f.counts) == set(__import__(
            "app.funnel", fromlist=["STAGES"]).STAGES)


def test_v5_8_5_사유는_enum만_받는다():
    """🔴 §8-6 — 추정 문자열 금지. 날 문자열을 주면 **터진다.**"""
    import pytest

    from app.funnel import Funnel
    f = Funnel()
    with pytest.raises((TypeError, ValueError)):
        f.drop("날짜 창 밖인 것 같다", "agent_vars")
