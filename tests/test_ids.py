"""1b 선수 식별 계약 — §16-b 게이트: *"이름만으로 매칭하면 실패"*.

DB 없이 도는 것부터 잠근다(`name_key`). 나머지는 대역으로 호출부를 검사한다 —
🔴 운영이 실제로 만드는 모양으로 짠다(빈 칸이 있으면 배선이 끊겨도 초록이다).
"""
from __future__ import annotations

import inspect

import pytest

from app import ids


# ── name_key — 🔴 한글을 지우지 않는다 ─────────────────────────────

def test_한글_이름이_서로_일치하지_않는다():
    """실사고 2026-09-21: ascii 정규화가 한글을 지워 **전부 일치**했다."""
    assert ids.name_key("박건우") != ""
    assert ids.name_key("박건우") != ids.name_key("박건욱")
    assert ids.name_key("김민석") != ids.name_key("김민혁")


def test_일본어_중국어도_살아_있다():
    assert ids.name_key("森下 暢仁") != ""
    assert ids.name_key("涌井") != ids.name_key("味谷")


def test_라틴_발음부호는_벗긴다():
    assert ids.name_key("Stefan Mugoša") == ids.name_key("Stefan Mugosa")
    assert ids.name_key("Brøndby") != ""


def test_공백과_구두점을_무시한다():
    assert ids.name_key("森下 暢仁") == ids.name_key("森下暢仁")
    assert ids.name_key("J.D. Martinez") == ids.name_key("JD Martinez")


# ── 대역 ──────────────────────────────────────────────────────────

class _Conn:
    """운영이 만드는 모양의 대역. rows 는 `players` 행 목록이다."""

    def __init__(self, rows=None, alias=None):
        self.rows = list(rows or [])
        self.alias = dict(alias or {})
        self.updates: list[tuple] = []

    async def fetchrow(self, sql, *a):
        got = await self.fetch(sql, *a)
        return got[0] if got else None

    async def fetch(self, sql, *a):
        if "FROM player_alias" in sql:
            hit = self.alias.get((a[0], str(a[1])))
            return [{"player_id": hit}] if hit else []
        if "AND jersey=$3 AND name_key=$4" in sql:
            league, team, jersey, key = a
            return [r for r in self.rows if r["league"] == league
                    and r["team"] == team and r["jersey"] == jersey
                    and r["name_key"] == key]
        if "AND jersey=$2 AND name_key=$3 AND team<>$4" in sql:
            league, jersey, key, team = a
            return [r for r in self.rows if r["league"] == league
                    and r["jersey"] == jersey and r["name_key"] == key
                    and r["team"] != team]
        if "AND name_key=$3 AND birth_date" in sql:
            league, team, key, bd = a
            return [r for r in self.rows if r["league"] == league
                    and r["team"] == team and r["name_key"] == key
                    and r.get("birth_date") == bd]
        if "AND name_key=$3" in sql:
            league, team, key = a
            return [r for r in self.rows if r["league"] == league
                    and r["team"] == team and r["name_key"] == key]
        if sql.startswith("INSERT INTO players"):
            pid = len(self.rows) + 1
            self.rows.append({"player_id": pid, "league": a[0], "team": a[1],
                              "jersey": a[2], "name": a[3], "name_key": a[4],
                              "birth_date": a[5], "role": a[6]})
            return [{"player_id": pid}]
        return []

    async def execute(self, sql, *a):
        self.updates.append((sql.split()[0] + " " + sql.split()[2], a))
        if sql.startswith("UPDATE players SET team=$2"):
            for r in self.rows:
                if r["player_id"] == a[0]:
                    r["team"] = a[1]


def _row(pid, league, team, name, jersey=None, bd=None):
    return {"player_id": pid, "league": league, "team": team, "name": name,
            "name_key": ids.name_key(name), "jersey": jersey, "birth_date": bd,
            "role": None}


# ── 팀 불명 → 미상 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_팀_불명이면_미상이다():
    """🔴 사용자 지시 — "팀 불명이면 미상"."""
    conn = _Conn([_row(1, "KBO", "NC", "박건우")])
    pid, how = await ids.resolve_by_name(conn, league="KBO", team=None,
                                         name="박건우")
    assert pid is None and how == ids.MATCH_NONE


@pytest.mark.asyncio
async def test_같은_팀_동명이인은_등번호_없이는_미상이다():
    conn = _Conn([_row(1, "KBO", "NC", "박건우", "37"),
                  _row(2, "KBO", "NC", "박건우", "8")])
    pid, how = await ids.resolve_by_name(conn, league="KBO", team="NC",
                                         name="박건우")
    assert pid is None and how == ids.MATCH_NONE


@pytest.mark.asyncio
async def test_등번호가_있으면_동명이인이_갈린다():
    conn = _Conn([_row(1, "KBO", "NC", "박건우", "37"),
                  _row(2, "KBO", "NC", "박건우", "8")])
    pid, how = await ids.resolve_by_name(conn, league="KBO", team="NC",
                                         name="박건우", jersey="37")
    assert (pid, how) == (1, ids.MATCH_HARD)


@pytest.mark.asyncio
async def test_다른_팀_동명이인은_팀으로_갈린다():
    """실존 사례(D28): 박건우 NC/롯데."""
    conn = _Conn([_row(1, "KBO", "NC", "박건우"),
                  _row(2, "KBO", "롯데", "박건우")])
    assert (await ids.resolve_by_name(conn, league="KBO", team="롯데",
                                      name="박건우"))[0] == 2


@pytest.mark.asyncio
async def test_명단에_없는_이름은_미상이다():
    conn = _Conn([_row(1, "KBO", "NC", "박건우")])
    pid, how = await ids.resolve_by_name(conn, league="KBO", team="NC",
                                         name="없는선수")
    assert pid is None and how == ids.MATCH_NONE


# ── alias 가 1순위 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alias가_있으면_이름을_안_본다():
    conn = _Conn([], alias={("statsapi", "660271"): 9})
    assert await ids.resolve_by_alias(conn, "statsapi", "660271") == 9


@pytest.mark.asyncio
async def test_alias가_없으면_None이다():
    assert await ids.resolve_by_alias(_Conn(), "fotmob", "1") is None


# ── 발급·이적 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_id를_봇이_발급한다():
    conn = _Conn()
    pid = await ids.upsert_player(conn, league="KBO", team="KT", name="배제성",
                                  jersey="15")
    assert pid == 1
    again = await ids.upsert_player(conn, league="KBO", team="KT",
                                    name="배제성", jersey="15")
    assert again == pid, "같은 자연키가 두 번 발급됐다"


@pytest.mark.asyncio
async def test_이적하면_행을_옮긴다():
    """🔴 §7-3 — "이적 시 alias 가 따라간다". 새 행을 만들면 안 따라간다."""
    conn = _Conn([_row(5, "KBO", "두산", "김민석", "3")])
    pid = await ids.upsert_player(conn, league="KBO", team="KT",
                                  name="김민석", jersey="3")
    assert pid == 5, "이적인데 새 id 를 발급했다"
    assert conn.rows[0]["team"] == "KT"


@pytest.mark.asyncio
async def test_등번호_00은_0과_다르다():
    """KBO·NPB 에 '00' 이 실재한다."""
    conn = _Conn()
    a = await ids.upsert_player(conn, league="NPB", team="주니치", name="A",
                                jersey="00")
    b = await ids.upsert_player(conn, league="NPB", team="주니치", name="A",
                                jersey="0")
    assert a != b


@pytest.mark.asyncio
async def test_이름이_비면_거부한다():
    with pytest.raises(ValueError):
        await ids.upsert_player(_Conn(), league="KBO", team="KT", name="  ")


# ── 배선 ──────────────────────────────────────────────────────────

def test_이름_정규화가_한_곳이다():
    """🔴 사본 금지 — 다른 모듈이 정규식을 다시 짜면 그것이 사본이다."""
    src = inspect.getsource(ids)
    assert src.count("def name_key") == 1


def test_외부_id_유일키가_스키마에_있다():
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text()
    assert "UNIQUE (source, external_id)" in sql
