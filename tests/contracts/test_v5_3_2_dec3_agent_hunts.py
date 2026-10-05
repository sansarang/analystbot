"""🔴🔴 **에이전트가 스스로 찾고 연다** — 결정 ③ 의 필수 조건.

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — 실측 2026-10-04 (5경기 재실행 **첫 경기**)
══════════════════════════════════════════════════════════════════

결정 ③이 세포 검색을 껐다. 🔴 그래서 **찾는 일이 전부 에이전트 몫**이 됐다.
그런데 첫 경기가 **25초**에 끝났고 에이전트는 **0턴**이었다:

```
· 세포 에이전트:Milwaukee Brewers: 🔴 §3 에이전트가 **터졌다** —
    TypeError("'Net' object is not callable")
queries 탈락: cell_search_off 52   ← 세포는 (의도대로) 안 찾았다
verified_vars: 5                   ← 격자 잔재뿐이다
```

⚠️ 까닭: `agentloop.run(net=…)` 은 **이미 쓰이고 있었다** — `solar.chat(_net=…)`
   의 **시험용 대역**(호출 가능한 것)이다. 🔴 거기에 `app.net.Net` 객체를
   넣었다. ⚠️ 쓰기 전에 **`grep` 하지 않았다**(그 이름이 비어 있다고 믿었다).

🔴 **막는 것은 모양이다**(§11-1): *"세포를 껐는데 에이전트도 못 찾는다."*
   그래서 이 계약은 **도구가 실제로 결과를 내나**를 본다 — 이름이 어떻든.
"""
from __future__ import annotations

import pytest


class _Chain:
    """🔴 검색 사슬 대역 — 한 건을 돌려준다."""

    def __init__(self):
        self.asked: list[str] = []

    async def query(self, q: str, **kw):
        self.asked.append(q)

        class H:
            url = "https://example.com/a"
            title = "t"
            published_at = "2026-10-04"
        return [H()]


class _Net:
    """🔴 열기 대역 — `Net` 처럼 **객체**다(호출 가능하지 않다)."""

    def __init__(self):
        self.opened: list[str] = []

    async def get(self, url, **kw):
        self.opened.append(url)

        class R:
            ok = True
            text = ("<html><body><p>" + ("Brewers beat Padres. " * 20)
                    + "</p></body></html>")
        return R()


def _tools(**kw):
    import datetime as dt

    from app import agentloop
    # ⚠️ 킥오프는 **시간대가 있어야** 한다(§8-7) — 처음 `None` 을 줘서 터졌다
    kick = dt.datetime(2026, 10, 4, 23, 0, tzinfo=dt.timezone.utc)
    inp = agentloop.AgentInput(
        match_key="statsapi:1", home="team:1", away="team:2",
        home_names=("Milwaukee Brewers",), away_names=("San Diego Padres",),
        competition="MLB", sport="baseball", kickoff_utc=kick,
        venue="American Family Field", langs=("en",))
    return agentloop.Tools(inp=inp, **kw)


def test_dec3_세포가_없어도_검색이_결과를_낸다():
    """🔴🔴 `seen` 이 **없을 때** 직접 찾아야 한다 — 그것이 ③의 조건이다."""
    chain = _Chain()
    t = _tools(chain=chain)
    got = t.search("Brewers Padres NLDS Game 2 October 4 2026", "en")
    assert got.get("ok") is True, got
    assert got.get("hits"), (
        f"🔴 세포가 없고 사슬이 있는데 **빈손**이다 — 결정 ③ 뒤에는 아무도 "
        f"찾지 않는다: {got}")
    assert chain.asked, "🔴 사슬에 **묻지도 않았다**"


def test_dec3_세포가_없어도_열기가_본문을_낸다():
    """🔴 `fetch` 도 마찬가지다 — 세포가 본문을 받아 두지 않는다."""
    chain, net = _Chain(), _Net()
    t = _tools(chain=chain, net=net)
    t.search("Brewers Padres NLDS Game 2 October 4 2026", "en")
    got = t.fetch("https://example.com/a")
    assert got.get("ok") is True, got
    assert str(got.get("body") or "").strip(), (
        f"🔴 직접 열기가 **빈 본문**을 냈다: {got}")
    assert net.opened == ["https://example.com/a"], net.opened


def test_dec3_수단_이름이_겹치지_않는다():
    """🔴🔴 **`net` 은 두 가지였다** — 그 겹침이 에이전트를 0턴으로 만들었다.

    ⚠️ `run(net=…)` 은 `solar.chat(_net=…)`(시험용 대역)으로 내려가고,
       **열기 수단**은 다른 이름이어야 한다. 🔴 같은 이름이면 하나가 다른 쪽
       자리에 들어가고 `TypeError` 가 난다(실측).
    """
    import inspect

    from app import agentloop
    sig = inspect.signature(agentloop.run)
    assert "fetcher" in sig.parameters, (
        "🔴 열기 수단이 `net` 과 **같은 이름**을 쓴다 — 그 겹침이 "
        "`'Net' object is not callable` 을 만들었다(실측 2026-10-04)")
    # 🔴 `net` 은 **그대로** 시험용 대역이어야 한다(옛 호출부가 살아 있다)
    assert "net" in sig.parameters


def test_dec3_호출부가_올바른_이름으로_넘긴다():
    """🔴🔴 **배선**(#2) — 서명만 고치고 호출부를 안 고치면 그대로 터진다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze._run_agent))
    assert "fetcher=" in body, (
        "🔴 `_run_agent` 가 **열기 수단을 `fetcher=` 로 안 넘긴다**")
    assert "net=net)" not in body, (
        "🔴 아직 `net=net` 으로 넘긴다 — 그것은 `solar.chat` 의 시험용 대역 "
        "자리다(`'Net' object is not callable`)")


@pytest.mark.parametrize("missing", ["chain", "net"])
def test_dec3_수단이_없으면_사유를_남긴다(missing):
    """🔴 **조용한 0 금지**(#3) — 수단이 없으면 *"없다"* 를 글로 남긴다."""
    kw = {"chain": _Chain(), "net": _Net()}
    kw.pop(missing)
    t = _tools(**kw)
    if missing == "chain":
        got = t.search("Brewers Padres NLDS Game 2 October 4 2026", "en")
        assert got.get("hits") == [], got
        assert "없" in str(got.get("why") or ""), got
    else:
        t.chain and t.search("Brewers Padres NLDS Game 2 October 4 2026", "en")
        got = t.fetch("https://example.com/a")
        assert got.get("ok") is False
        assert "못 얻었다" in str(got.get("why") or ""), got
