"""[D61-2] 크롤러가 만든 **선발·타순**을 DB 로 옮기는 다리.

사용자 2026-09-24: "전부다 하나씩 수정해라..수정후 다시 확인해라"

🔴 실측이 잡은 자리 — 크롤러는 둘 다 갖고 있는데 DB 에는 없었다:
```
crawl:kbo:2026-09-24:latest  home_pitcher '대니엘' · away_pitcher '송명기'
games.home_pitcher           오늘 8경기 전부 NULL   → ⑤ starter_recent3 6/6 미상
crawl:kbo:2026-09-23:latest  lineup_home 정수빈(중견수)-… 9명
lineups 표 KBO               최근 14일 0행          → ⑤ lineup_out 6/6 미상
                             (같은 기간 NPB 22행 · MLB 670행)
```
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.collectors import crawler_feed as CF

_ORDER_H = ("정수빈(중견수)-안재석(3루수)-김민석(좌익수)-양의지(포수)-"
            "세베리노(1루수)-손아섭(지명타자)-박찬호(유격수)-오명진(2루수)-"
            "조수행(우익수)")
_ORDER_A = ("김호령(중견수)-김민규(좌익수)-김선빈(2루수)-카스트로(1루수)-"
            "나성범(우익수)-한준수(지명타자)-박민(유격수)-김태군(포수)-"
            "변우혁(3루수)")


class _Pool:
    def __init__(self):
        self.exec: list = []

    async def execute(self, sql, *args):
        self.exec.append((" ".join(str(sql).split()), args))


def _row(**kw):
    base = {"id": 1775, "home": "KT Wiz", "away": "NC Dinos",
            "home_pitcher": None, "away_pitcher": None}
    base.update(kw)
    return base


def _code_only(fn) -> str:
    """주석·독스트링을 뗀 코드 본문 — 원문 grep 은 내 설명에 걸린다(D46)."""
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


@pytest.mark.asyncio
async def test_예고선발을_games_에_옮긴다():
    """🔴 오늘 실물 그대로 — 스냅샷에 있고 DB 가 비어 있는 상태."""
    pool = _Pool()
    got = await CF.persist_game_facts(
        pool, _row(), {"home_pitcher": "대니엘", "away_pitcher": "송명기"})
    assert got["starters"] == 2, got
    sqls = [e[0] for e in pool.exec]
    assert any("UPDATE games SET home_pitcher" in q for q in sqls), sqls
    assert any("UPDATE games SET away_pitcher" in q for q in sqls), sqls
    assert ("대니엘",) == pool.exec[0][1][1:], pool.exec[0]


@pytest.mark.asyncio
async def test_빈_값으로_덮지_않는다():
    """⚠️ 반대 위험 — 크롤러가 못 읽은 칸이 DB 값을 지우면 자료가 사라진다."""
    pool = _Pool()
    got = await CF.persist_game_facts(
        pool, _row(home_pitcher="대니엘", away_pitcher="송명기"),
        {"home_pitcher": "", "away_pitcher": None})
    assert got["starters"] == 0
    assert pool.exec == []


@pytest.mark.asyncio
async def test_같은_값이면_다시_쓰지_않는다():
    pool = _Pool()
    got = await CF.persist_game_facts(
        pool, _row(home_pitcher="대니엘"), {"home_pitcher": "대니엘"})
    assert got["starters"] == 0 and pool.exec == []


@pytest.mark.asyncio
async def test_확정_타순만_lineups_에_넣는다(monkeypatch):
    saved: list = []

    async def fake(pool, gid, side, status, source, parsed, *, caller="?"):
        saved.append((gid, side, status, source, parsed, caller))

    monkeypatch.setattr("app.collectors.lineups.save_lineup", fake)
    pool = _Pool()
    got = await CF.persist_game_facts(
        pool, _row(), {"home_pitcher": "대니엘", "away_pitcher": "송명기",
                       "lineup_home": _ORDER_H, "lineup_away": _ORDER_A})
    assert got["lineups"] == 2, got
    sides = {s[1] for s in saved}
    assert sides == {"home", "away"}
    gid, side, status, source, parsed, caller = saved[0]
    assert gid == 1775 and status == "confirmed" and source == "크롤러"
    assert caller == "persist_game_facts"
    assert len(parsed["batting_order"]) == 9
    assert parsed["batting_order"][0] == "정수빈", parsed["batting_order"]
    assert parsed["starter"] == "대니엘"


@pytest.mark.asyncio
async def test_한쪽만_오면_넣지_않는다(monkeypatch):
    """🔴 확정의 정의는 `pregame_push.lineup_confirmed` 하나다 — 여기서
    다시 짓지 않는다. 한쪽만 온 것은 확정이 아니다."""
    saved: list = []

    async def fake(*a, **k):
        saved.append(a)

    monkeypatch.setattr("app.collectors.lineups.save_lineup", fake)
    got = await CF.persist_game_facts(
        _Pool(), _row(), {"lineup_home": _ORDER_H, "lineup_away": ""})
    assert got["lineups"] == 0 and saved == []


@pytest.mark.asyncio
async def test_쓰기_실패가_폴링을_막지_않는다():
    class _Boom:
        async def execute(self, *a):
            raise RuntimeError("DB 없음")

    got = await CF.persist_game_facts(_Boom(), _row(), {"home_pitcher": "대니엘"})
    assert got == {"starters": 0, "lineups": 0}
    assert await CF.persist_game_facts(None, _row(), {"home_pitcher": "x"}) \
        == {"starters": 0, "lineups": 0}


def test_판정_규약을_다시_짓지_않았다():
    """🔴 사본 금지 — 확정·파싱·쓰기의 원본은 각각 하나다."""
    code = _code_only(CF.persist_game_facts)
    assert "lineup_confirmed" in code
    assert "parse_order" in code
    assert "save_lineup" in code
    # 자기 손으로 9를 세거나 이름을 자르지 않는다
    assert ".split(\"-\")" not in code and "'-'" not in code


def test_폴링이_실제로_부른다():
    """🔴 **배선의 끝.** 만든 것에 부르는 곳이 없으면 없는 코드보다 나쁘다.

    ⚠️ 주석을 뗀 본문에서 본다 — 원문 grep 은 내 설명에 걸린다(D46).
    """
    from app import scheduler as S

    code = _code_only(S.crawler_lineup_poll)
    assert "persist_game_facts" in code, "폴링이 다리를 부르지 않는다"
    i_snap = code.index("snapshot_for_game")
    i_call = code.index("persist_game_facts")
    assert i_snap < i_call, "스냅샷을 읽기 전에 부른다"
