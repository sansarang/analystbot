"""🔴🔴 **§6-3 본문 확보 — FT1**(실패를 조용히 버리지 않는다).

> 순서: 원문 → AMP 판 → 구단·리그 RSS → 원천 표에 적힌 대체 경로.
> 실패 사유를 칸별로 기록(robots·4xx·5xx·빈 본문·자바스크립트 렌더 필요).
> 재시도·캐시·속도 제한(도메인당). 계약 **FT1**: 실패를 조용히 버리면 실패.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text: str = "", status: int = 200) -> None:
        self.text, self.status = text, status
        self.ok = 200 <= status < 300


class _Net:
    """🔴 주소마다 정해진 답을 주는 가짜 망(계약용)."""

    def __init__(self, box: dict) -> None:
        self.box, self.seen = dict(box), []

    async def get(self, url: str):
        self.seen.append(str(url))
        got = self.box.get(str(url))
        return got if got is not None else _Resp("", 404)


def test_rung_order_is_fixed() -> None:
    from app.core.search import fetch as ft
    assert ft.RUNGS == ("원문", "AMP", "RSS", "대체 경로")


def test_failure_always_has_a_reason() -> None:
    """🔴🔴 **FT1** — 전부 실패해도 **칸 기록이 비지 않는다**."""
    from app.core.search import fetch as ft
    net = _Net({})
    body, when, rows = asyncio.run(
        ft.body_of(net, "https://nowhere.example/a", league="league:PL",
                   extract=lambda html, url="": ("", None)))
    assert body == "" and when is None
    assert rows, "🔴 FT1 — 칸 기록이 비었다"
    assert all(str(r.get("why") or "") for r in rows), rows
    assert {str(r["rung"]) for r in rows} <= set(ft.RUNGS)
    # 🔴 **네 칸이 다 말을 한다**(통로가 없으면 ⬜ 로)
    assert {str(r["rung"]) for r in rows} == set(ft.RUNGS), rows


def test_amp_rung_comes_from_the_page_not_a_guess() -> None:
    """🔴 AMP 주소는 **원문 HTML 의 `rel=amphtml`** 에서만 온다."""
    from app.core.search import fetch as ft
    html = ('<html><head><link rel="amphtml" '
            'href="https://x.example/a/amp"></head><body></body></html>')
    assert ft.amp_of(html) == "https://x.example/a/amp"
    assert ft.amp_of("<html></html>") == ""


def test_amp_rung_is_actually_tried() -> None:
    from app.core.search import fetch as ft
    # ⚠️ 가짜 주소에 `example` 를 쓰지 않는다 — 그 낱말에 **amp** 가 들어 있어
    #    *"amp 칸인가"* 를 글자로 가릴 수 없다(내 계약이 그 함정을 밟았다).
    html = '<link rel="amphtml" href="https://news.test/a/amp">'
    net = _Net({"https://news.test/a": _Resp(html),
                "https://news.test/a/amp": _Resp("<p>본문이 여기 있다</p>")})
    got, _when, rows = asyncio.run(
        ft.body_of(net, "https://news.test/a", league="league:PL",
                   extract=lambda h, url="": (("본문이 여기 있다"
                                               if "amp" in url else ""), None)))
    assert got == "본문이 여기 있다", rows
    assert [r["rung"] for r in rows if r["ok"]] == ["AMP"], rows


def test_js_render_is_named() -> None:
    """🔴 자바스크립트 렌더 필요를 **이름으로** 적는다."""
    from app.core.search import fetch as ft
    assert ft.needs_render("<p>Please enable JavaScript</p>", "") is True
    assert ft.needs_render("<p>글이 있다</p>", "글이 있다") is False


def test_4xx_is_not_retried() -> None:
    """🔴 4xx 는 다시 받지 않는다(같은 답이 온다 · 상한 낭비)."""
    from app.core.search import fetch as ft
    net = _Net({"https://x.example/a": _Resp("", 404)})
    asyncio.run(ft.body_of(net, "https://x.example/a", league="",
                           extract=lambda h, url="": ("", None)))
    assert net.seen.count("https://x.example/a") == 1, net.seen


def test_rate_limit_exists_per_domain() -> None:
    from app.core.search import fetch as ft
    assert ft.MIN_INTERVAL > 0 and isinstance(ft._LAST, dict)


def test_s3_uses_the_module() -> None:
    """🔴 배선 — ③ 이 `search.fetch.body_of` 로 본문을 받는다(사본 금지)."""
    said = _src("app/core/stages/s3_docs.py")
    assert "body_of(" in said and "why_of(" in said


def test_rss_and_alt_come_from_the_table() -> None:
    """🔴 RSS·대체 경로는 **원천 표**가 든다(코드에 주소를 적지 않는다)."""
    import ast
    import inspect
    from app.core.search import fetch as ft
    for fn in (ft.rss_of, ft.alt_of):
        said = ast.unparse(ast.parse(inspect.getsource(fn)))
        assert "http" not in said.replace('"http"', "").replace(
            "'http'", "") or "startswith" in said, fn.__name__
