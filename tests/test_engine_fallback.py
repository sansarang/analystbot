"""🔴🔴 **지정 엔진이 0건이면 지정 없이 한 번 더**(§19-b-4 · 실측 2026-10-04).

══════════════════════════════════════════════════════════════════
🔴 왜 — 이 대체는 **있었는데 영영 안 돌았다**
══════════════════════════════════════════════════════════════════

`SearchChain.query` 의 순차 경로에 `plans = [engines, None]` 이 **이미 있었다.**
🔴 그런데 그 위의 **병렬 합치기**가 한 건이라도 얻으면 거기서 돌아간다 —
   그래서 순차 경로에 **도달하지 못했다.**

실측 2026-10-04(북마케도니아 vs 스코틀랜드) 로그 원문:

```
[searx] 'Северна Македонија lineup Scotland фудбал' → **0건**
        (정지 중인 엔진 {'google news': 'Suspended: access denied'})
[bing-news] 같은 질의 → 2건
[search] 병렬 합계 **2건** → 🔴 여기서 끝났다
```

⚠️ 마케도니아어 질의가 **기회를 못 받았다.** 지정 없이 던지면 **29건**이 온다
   (실측 2026-10-04 · 같은 질의 · 같은 시각대).

🔴 이것은 우회가 **아니다** — 그 엔진이 스스로 `Suspended` 를 알려 왔고, 선언된
   대체(§19-b-4)를 그대로 따르는 것이다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.search import Hit, SearchChain

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Searx:
    """🔴 지정 엔진으로는 0건, 지정 없이는 여럿 — 실측의 그 모양이다."""

    def __init__(self):
        self.calls: list = []

    async def query(self, text, *, lang="ko", engines=None, **kw):
        self.calls.append(engines)
        if engines:
            return []                      # 🔴 그 엔진이 정지 중이다
        return [Hit(url=f"https://sportstation.mk/{i}", title="состав",
                    snippet="") for i in range(5)]


class _Bing:
    """⚠️ **2건을 낸다** — 이것이 종전에 대체를 가로막았다."""

    async def query(self, text, *, lang="ko", **kw):
        return [Hit(url="https://bing.example/1", title="x", snippet=""),
                Hit(url="https://bing.example/2", title="y", snippet="")]


def _chain(**kw):
    ch = SearchChain.__new__(SearchChain)
    ch.searx = kw.get("searx")
    ch.gdelt = None
    ch.bing = kw.get("bing")
    ch.google = None
    ch.tried = []
    return ch


@pytest.mark.asyncio
async def test_지정이_0건이면_지정_없이_다시_던진다():
    """🔴 다른 통로가 2건을 냈어도 **대체는 돈다.**"""
    sx = _Searx()
    ch = _chain(searx=sx, bing=_Bing())
    got = await ch.query("Северна Македонија lineup Scotland фудбал",
                         lang="mk", engines=["google news"])
    # 🔴 두 번 불렸다 — ① 지정 ② 지정 없이
    assert sx.calls == [["google news"], None], sx.calls
    urls = [h.url for h in got]
    assert any(".mk/" in u for u in urls), (
        f"🔴 지정 없이 받은 결과가 합쳐지지 않았다: {urls}")
    # ⚠️ 먼저 온 2건도 **버리지 않는다**(합친다)
    assert any("bing.example" in u for u in urls), urls
    assert len(got) == 7, urls


@pytest.mark.asyncio
async def test_지정이_결과를_내면_다시_던지지_않는다():
    """⚠️ 늘 두 번 던지면 통신이 두 배다 — 0건일 때만이다."""
    class _Ok(_Searx):
        async def query(self, text, *, lang="ko", engines=None, **kw):
            self.calls.append(engines)
            return [Hit(url="https://ok.example/1", title="x", snippet="")]

    sx = _Ok()
    ch = _chain(searx=sx, bing=_Bing())
    await ch.query("x", lang="mk", engines=["google news"])
    assert sx.calls == [["google news"]], sx.calls


@pytest.mark.asyncio
async def test_지정이_없으면_다시_던지지_않는다():
    """🔴 지정이 없었으면 **이미 전체 엔진**이다 — 다시 던질 것이 없다."""
    sx = _Searx()
    ch = _chain(searx=sx, bing=_Bing())
    await ch.query("x", lang="mk")
    assert sx.calls == [None], sx.calls


def test_병렬_경로가_대체를_품는다():
    """🔴 구조 계약 — `_gather` **안에서** 다시 던져야 한다.

    ⚠️ 순차 경로에만 두면 병렬이 한 건을 얻는 순간 영영 안 돈다. 그것이
       2026-10-04 에 실제로 일어난 일이다.
    """
    src = (ROOT / "app" / "search.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_gather")
    calls = [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert sum(1 for c in calls if c.startswith("_one_channel(")) >= 2, (
        "🔴 `_gather` 가 `_one_channel` 을 **한 번만** 부른다 — 지정 0건의 "
        "대체가 병렬 경로에 없다(§19-b-4)")
