"""🔴🔴 **⑥ GDELT 를 아껴 쓴다** — 사용자 지시 2026-10-06.

> GDELT: **경기당 최대 4회**, SearXNG 가 결과를 **5건 이상** 준 하위에서는 **생략**.

══════════════════════════════════════════════════════════════════
🔴 왜 (실측 2026-10-06 · 북아일랜드–조지아)
══════════════════════════════════════════════════════════════════

GDELT 가 매 질의마다 **병렬로** 돌아 세 번째 하위쯤에 스스로 벌점에 들어갔다:

```
[search] 병렬 합계 12건 … (SearXNG:5건 · GDELT:GDELT: 호출 상한에 걸려
         876초 더 쉰다 — 다음 수단으로 간다 · Bing뉴스:8건)
```

🔴 **먼저 쓴 하위가 나중 하위의 통로를 태웠다.** 그리고 그 질의는 SearXNG 가
   이미 5건을 줬다 — GDELT 를 쓸 값이 없는 자리였다.
"""
from __future__ import annotations

import asyncio

import pytest

from app import search as S


class _Ch:
    """🔴 건수만 정해 주는 통로."""

    def __init__(self, n: int, *, tag: str = "x") -> None:
        self.n, self.tag = n, tag
        self.asked = 0

    async def query(self, text, *, lang="ko", engines=None):
        del text, lang, engines
        self.asked += 1
        return [S.Hit(title=f"{self.tag}{i}", url=f"https://{self.tag}/{i}",
                      snippet="", publisher=self.tag, engine=self.tag,
                      published_at=None) for i in range(self.n)]


class _Gdelt(_Ch):
    """🔴 `calls_left` 를 가진 대역 — 사슬이 그것을 **보는지** 센다."""

    def __init__(self, n: int, *, left: int = 4) -> None:
        super().__init__(n, tag="g")
        self._left = left

    def calls_left(self) -> int:
        return self._left


def _chain(searx_n: int, *, left: int = 4):
    sx, bing, gd = _Ch(searx_n, tag="s"), _Ch(1, tag="b"), _Gdelt(2, left=left)
    return S.SearchChain(searx=sx, bing=bing, gdelt=gd, google=None), sx, bing, gd


def test_wo6_SearXNG_가_두텁면_GDELT_를_안_던진다():
    """🔴 5건 이상이면 **생략**이다(사용자 지시 ⑥)."""
    assert S.GDELT_SKIP_IF_HITS == 5, S.GDELT_SKIP_IF_HITS
    chain, sx, bing, gd = _chain(S.GDELT_SKIP_IF_HITS)
    got = asyncio.run(chain.query("q", lang="en"))
    assert got, got
    assert sx.asked == 1 and bing.asked == 1
    assert gd.asked == 0, "🔴 SearXNG 가 5건을 줬는데 GDELT 를 던졌다"


def test_wo6_SearXNG_가_얇으면_GDELT_로_보탠다():
    """🔴 그 통로의 값은 **얇을 때** 나온다 — 그때는 던진다."""
    chain, sx, bing, gd = _chain(S.GDELT_SKIP_IF_HITS - 1)
    got = asyncio.run(chain.query("q", lang="en"))
    assert gd.asked == 1, "🔴 얇은데 GDELT 를 안 던졌다"
    # 🔴 **보탬이다** — 앞 통로 결과를 버리지 않는다
    hosts = {str(h.url).split("/")[2] for h in got}
    assert "s" in hosts and "g" in hosts, hosts


def test_wo6_경기당_횟수를_다_쓰면_안_던진다():
    """🔴 `calls_left() == 0` 이면 **안 묻는다** — 사유를 이름으로 남긴다(#3)."""
    chain, sx, bing, gd = _chain(1, left=0)
    asyncio.run(chain.query("q", lang="en"))
    assert gd.asked == 0, "🔴 경기당 횟수를 다 썼는데 던졌다"
    said = " · ".join(chain.tried)
    assert "GDELT" in said and "다 썼다" in said, said


def test_wo6_상한이_4이고_경기_경계가_있다():
    """🔴🔴 수와 **경계**가 둘 다 있어야 "경기당"이 뜻을 갖는다."""
    assert S.GDELT_MAX_PER_MATCH == 4, S.GDELT_MAX_PER_MATCH
    g = S.GdeltSearch()
    S.GdeltSearch.reset_match()
    assert g.calls_left() == 4
    S.GdeltSearch._state["calls"] = 4.0
    assert g.calls_left() == 0
    # 🔴 그 상한을 `query` 가 **집행한다**(선언만이면 없는 것이다 · #2)
    with pytest.raises(S.SearchUnavailable, match="경기당"):
        asyncio.run(g.query("q"))
    # 🔴 **경계가 0 으로 돌린다** — 그래야 다음 경기가 제 몫을 받는다
    S.GdeltSearch.reset_match()
    assert g.calls_left() == 4
    # ⚠️ 벌점은 **안 건드린다**(GDELT 가 준 것이다 · §14-12)
    S.GdeltSearch._state["rest_until"] = 9e18
    S.GdeltSearch.reset_match()
    assert S.GdeltSearch._state["rest_until"] == 9e18
    S.GdeltSearch._state["rest_until"] = 0.0


def test_wo6_경기_입구가_그_경계를_부른다():
    """🔴 #2 배선 — 경계를 아무도 안 부르면 "경기당"이 "과정당"이 된다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.gather))
    assert "reset_match" in src, (
        "🔴 `analyze.gather` 가 `GdeltSearch.reset_match()` 를 **안 부른다** — "
        "그러면 경기당 4회가 프로세스당 4회가 된다")
