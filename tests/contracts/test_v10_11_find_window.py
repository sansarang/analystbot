"""🔴🔴 **경기 찾기 — 창이 둘이어서 찾은 경기를 버렸다**(사용자 지시 2026-10-12).

⚠️ 실사고(아스널): 사다리 ② 가 `Arsenal vs Lille`(10-13 19:00Z)를 **찾았는데**
   `fotmob.slate_row` 가 버려 `match_not_found` 로 끝났다. 🔴 까닭은 창이 둘:
   경기 찾기 `discover.window`(오늘~+3일 ≈ 96시간) vs 슬레이트 `window.HOURS`(36시간).
   ⚠️ 그리고 그 사유가 `tried` 에 **빈 괄호**로 적혀(`page.reason` 만 썼다) 카드·
   로그 어디에도 "창 밖"이 안 보였다(#3 위반).
🔴 고침: 물어서 온 길은 `asked=True` 로 창을 **사유로만** 남긴다(수집기는 36시간 그대로) ·
   경기 주소는 **번호**(`/match/{번호}`)로 받는다(일정이 주는 조각 주소는 옛 경기다).
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class _Got:
    """🔴 `net.get` 이 돌려주는 모양만 흉내 낸다(텍스트는 실물 페이지 꼴)."""

    def __init__(self, url: str, text: str) -> None:
        self.ok, self.url, self.text, self.reason = True, url, text, ""


def _page_text(when: datetime) -> str:
    import json
    j = {"props": {"pageProps": {"content": {}, "general": {
        "matchId": "6106260",
        "homeTeam": {"name": "Arsenal"}, "awayTeam": {"name": "Lille"},
        "matchTimeUTCDate": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "leagueName": "Champions League"}}}}
    return ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(j) + "</script>")


def test_물어서_온_경기는_슬레이트_창_밖이어도_행이_된다() -> None:
    from app import window as _w
    from app.collect import fotmob as fm
    far = _w.now_utc() + timedelta(hours=_w.HOURS + 7)
    got = _Got("https://www.fotmob.com/match/6106260", _page_text(far))
    assert fm.slate_row(got) is None, "🔴 수집기 경로는 창을 지켜야 한다"
    row = fm.slate_row(got, asked=True)
    assert row and row["home"] == "Arsenal" and row["away"] == "Lille"


def test_이미_지난_경기는_물어도_행이_아니다() -> None:
    """⚠️ 창을 푸는 것은 **앞으로**다 — 지난 경기는 그대로 버린다(§1-3)."""
    from app import window as _w
    from app.collect import fotmob as fm
    past = _w.now_utc() - timedelta(hours=3)
    got = _Got("https://www.fotmob.com/match/6106260", _page_text(past))
    assert fm.slate_row(got, asked=True) is None


def test_찾기_경로가_번호_주소로_받는다() -> None:
    tree = ast.parse(_src("app/findgame.py"))
    fn = next(x for x in ast.walk(tree)
              if isinstance(x, ast.AsyncFunctionDef) and x.name == "_by_index")
    said = ast.unparse(fn)
    assert "match_url(said_id)" in said, "🔴 번호 주소를 안 쓴다"
    assert "asked=True" in said, "🔴 슬레이트 창을 그대로 맞고 있다"


def test_행을_못_만든_사유를_이름으로_남긴다() -> None:
    """🔴 #3 — 빈 괄호로 적던 자리다."""
    tree = ast.parse(_src("app/findgame.py"))
    fn = next(x for x in ast.walk(tree)
              if isinstance(x, ast.AsyncFunctionDef) and x.name == "_by_index")
    said = ast.unparse(fn)
    assert "why_out" in said, "🔴 창 사유를 안 적는다"
    assert "킥오프" in said


def test_수집기들은_창을_그대로_쓴다() -> None:
    """⚠️ `asked=True` 가 수집기로 새면 슬레이트가 넓어진다(호출·비용)."""
    for rel in ("app/collect/espn.py", "app/collect/nhl.py",
                "app/collect/fdorg.py"):
        assert "asked=True" not in _src(rel), rel
