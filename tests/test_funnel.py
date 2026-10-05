"""🔴🔴 **깔때기** — 어느 칸에서 0 이 되는지 숫자로 본다(사용자 기술 지시 2026-10-03).

⚠️ **v5 §8-5 로 칸이 바뀌었다**(2026-10-04). 칸 목록·순서를 지키는 것은 이제
   `tests/contracts/test_v5_8_funnel.py` 이고(문서에서 읽어 대조한다),
   이 파일은 **동작**(한 줄·끊긴 자리·합치기·배선)을 지킨다.

```
v4  queries → hits → kept_identity → kept_date → facts → typed → variables
v5  queries → hits → kept_identity → kept_date → fetched
                  → agent_vars → verified_vars → scenarios → markets_graded
```

> **고치기 전에 진단.**

⚠️ **종목을 가리지 않는다**(사용자 지시: *"야구뿐만 아니라 전경기다"*) — 이 계약이
   종목 분기가 없다는 것을 검사한다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app import analyze, funnel

ROOT = Path(__file__).resolve().parents[1]


def test_칸마다_진단과_단위가_있다():
    """🔴 칸 목록 자체는 `tests/contracts/test_v5_8_funnel.py` 가 문서와 대조한다.

    ⚠️ 같은 사실을 두 곳에서 지키면 한쪽이 늘 늦는다 — 여기서는 **빠진 칸이
       없는지**만 본다.
    """
    assert set(funnel.WHY_ZERO) == set(funnel.STAGES)
    assert set(funnel.UNITS) == set(funnel.STAGES)


def test_한_줄로_찍는다():
    f = funnel.Funnel()
    for k, n in (("queries", 12), ("hits", 40), ("kept_identity", 9),
                 ("kept_date", 9), ("fetched", 9)):
        f.set(k, n)
    # 🔴 **안 잰 칸은 `-`** 다 — 0 과 다르다(v5 §8-5 · 안 잰 것을 0 이라 하면 거짓)
    assert f.line() == ("queries:12 → hits:40 → kept_identity:9 → "
                        "kept_date:9 → fetched:9 → agent_vars:- → "
                        "verified_vars:- → scenarios:- → markets_graded:-")


def test_처음으로_0_이_된_칸만_짚는다():
    """🔴 앞 칸이 0 이면 뒤는 **당연히** 0 이다 — 처음 자리만이 뜻이 있다."""
    f = funnel.Funnel()
    f.set("queries", 12); f.set("hits", 40)
    # ⚠️ **안 잰 칸은 짚지 않는다**(v5 §8-5) — 그 구분이 없으면 매 카드가
    #    거짓 경고를 낸다. 🔴 그래서 `kept_identity` 를 **0 으로 재야** 짚는다.
    assert f.broke_at == "", f.broke_at
    assert "안 잰 칸" in f.report(), f.report()
    f.set("kept_identity", 0)
    assert f.broke_at == "kept_identity"
    assert "신원 필터" in f.report()

    g = funnel.Funnel()
    for k in ("queries", "hits", "kept_identity", "kept_date", "fetched"):
        g.set(k, 5)
    g.set("agent_vars", 0)
    assert g.broke_at == "agent_vars"
    # ⚠️ v5 §8-5 — 그 자리의 진단이 *"유형표"* 에서 **에이전트**로 바뀠다
    assert "에이전트" in g.report(), g.report()

    h = funnel.Funnel()
    for k in funnel.STAGES:
        h.set(k, 1)
    assert h.broke_at == "" and "0 이 됐다" not in h.report()


def test_0_이_된_칸의_바로_앞을_보여_준다():
    """🔴 수만 내면 못 고친다 — **무엇이 거기까지 왔나**가 진단의 재료다."""
    f = funnel.Funnel()
    for k in ("queries", "hits", "kept_identity", "kept_date"):
        f.set(k, 3)
    f.add("fetched", 1, sample="전민재 … 선발 라인업에 제외")
    f.set("agent_vars", 0)
    assert f.broke_at == "agent_vars"
    assert "전민재" in f.report()


def test_합쳐도_새지_않는다():
    """🔴 경기 하나에 세포가 수십 개다 — 합치기가 틀리면 수가 거짓이 된다."""
    a, b = funnel.Funnel(), funnel.Funnel()
    a.set("hits", 3); b.set("hits", 4); b.set("fetched", 2)
    a.merge(b)
    assert a.counts["hits"] == 7 and a.counts["fetched"] == 2


def test_모르는_칸은_조용히_사라지지_않는다():
    f = funnel.Funnel()
    f.add("오타", 5)
    assert sum(f.counts.values()) == 0          # 세지 않았다
    # ⚠️ 그리고 **경고가 난다**(로그) — 조용히 지나가지 않는다


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **배선** — 만든 것은 부르는 곳이 있어야 한다(CLAUDE.md #2)
# ══════════════════════════════════════════════════════════════════


def test_파이프라인이_일곱_칸을_전부_센다():
    """🔴 칸 하나라도 안 세면 그 자리의 진단이 **영원히 0** 으로 보인다."""
    src = (ROOT / "app" / "cells.py").read_text(encoding="utf-8")
    src += (ROOT / "app" / "analyze.py").read_text(encoding="utf-8")
    for stage in funnel.STAGES:
        assert f'"{stage}"' in src, f"`{stage}` 를 세는 코드가 없다"


def test_세포가_같은_그릇을_쓴다():
    """🔴 세포마다 따로 만들면 **합치기를 빠뜨린 세포가 조용히 빠진다**.

    ⚠️ 같은 그릇을 넘기면 빠질 수가 없다 — 그것이 이 설계의 요점이다.
    """
    src = inspect.getsource(analyze.gather)
    assert "fun = _funnel.Funnel()" in src
    # 🔴 `Cell` 을 만드는 **모든** 자리가 그 그릇을 받는다 — 세어 본다
    made = src.count("Cell(")
    wired = src.count("funnel=fun") + src.count("cell.funnel = fun")
    assert wired >= made, f"세포 {made}곳 중 깔때기를 받은 곳이 {wired}곳이다"


def test_종목_분기가_없다():
    """🔴🔴 사용자 지시 2026-10-03: *"야구뿐만 아니라 **전경기**다."*

    ⚠️ 깔때기 안에 `baseball`·`soccer` 같은 이름이 생기면 그 순간 종목마다 다른
       진단이 되고, 새 종목은 **아무것도 안 세는** 상태로 시작한다.
    """
    src = (ROOT / "app" / "funnel.py").read_text(encoding="utf-8")
    code = "\n".join(
        ast.unparse(n) for n in ast.parse(src).body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)))
    for bad in ("baseball", "soccer", "hockey", "KBO", "NPB", "MLB"):
        assert bad not in code, f"깔때기에 종목·리그 이름이 있다: {bad}"


def test_카드_블록1_맨_위에_적는다():
    """🔴 스무 줄 사유 **아래**에 묻히면 못 본다 — 진단이 먼저다."""
    src = inspect.getsource(analyze.render)
    i = src.index("■ 1 자료 한계")
    j = src.index("card.limits")
    assert src.index("card.funnel", i) < j, "깔때기가 사유 줄 아래에 있다"
