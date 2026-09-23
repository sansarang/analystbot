"""[ODN-M] 배당이 **엉뚱한 경기**에 쌓였다 — 매칭에 팀 이름이 없었다.

사용자 2026-09-23: "배당 보류 해제"

🔴 실측 2026-09-23 10:08 운영 — `_match_oddsapinet` 결과:
```
kbo: 이벤트 3 → 매칭 3
  O NC Dinos      @KT Wiz          09-23 09:30Z  game_id=1774
  O Kia Tigers    @Doosan Bears    09-23 09:30Z  game_id=1774   ← 같은 id
  O Lotte Giants  @Hanwha Eagles   09-23 09:30Z  game_id=1774   ← 같은 id
npb: 이벤트 6 → 매칭 6
  4경기 → 16962 · 2경기 → 16963
```
세 경기의 총점·핸디·팀토탈이 **한 경기 행에 겹쳐 쌓였다**(kbo 1경기 7,720행).
그 가격으로 ⑪이 픽을 내면 **다른 경기의 가격**이다.

🔴 원인은 한 줄이다 — 질의에 **팀 조건이 없다**:
```sql
SELECT id, home, away FROM games
 WHERE sport = $1
   AND starts_at BETWEEN $2 - interval '3 hours' AND $2 + interval '3 hours'
```
`fetchrow` 는 그중 **아무거나 하나**를 돌려준다. KBO 5경기가 전부 18:30
시작이라 전건이 첫 행으로 갔다.
⚠️ 바로 위 독스트링은 **"시작 시각(±3시간) + 팀 이름 부분일치로 맞춘다"**
   라고 적고 있었다. 문서가 맞고 **구현이 없었다.**

🔴 팀 대조는 새로 짓지 않는다 — `football.match_team_name`(토큰 교집합 최대 ·
   동점이면 None)이 원본이다. `similar_team` 단독은 위험하다:
   `similar_team("Kia Tigers", "Hanshin Tigers")` 가 **True** 다(둘 다 Tigers).
"""
from __future__ import annotations

import inspect

import pytest

import app.scheduler as S

WHEN = 1790155800          # 2026-09-23 09:30Z — KBO 3경기가 같은 시각


def _evs():
    return [
        {"event_id": "e1", "start_time": WHEN,
         "home_team": "KT Wiz", "away_team": "NC Dinos"},
        {"event_id": "e2", "start_time": WHEN,
         "home_team": "Doosan Bears", "away_team": "Kia Tigers"},
        {"event_id": "e3", "start_time": WHEN,
         "home_team": "Hanwha Eagles", "away_team": "Lotte Giants"},
    ]


class _Pool:
    ROWS = [
        {"id": 1772, "home": "Hanwha Eagles", "away": "Lotte Giants"},
        {"id": 1773, "home": "Doosan Bears", "away": "Kia Tigers"},
        {"id": 1774, "home": "KT Wiz", "away": "NC Dinos"},
    ]

    def __init__(self, rows=None):
        self.rows = self.ROWS if rows is None else rows
        self.n = 0

    async def fetch(self, sql, *a):
        self.n += 1
        return list(self.rows)

    async def fetchrow(self, sql, *a):
        self.n += 1
        return self.rows[0] if self.rows else None


@pytest.mark.asyncio
async def test_세_경기가_세_id_로_간다():
    """🔴 이 단위의 전부 — 종전에는 셋 다 1774 였다."""
    out = await S._match_oddsapinet(_Pool(), "kbo", _evs())
    ids = [gid for _, gid in out]
    assert sorted(ids) == [1772, 1773, 1774], ids
    by = {ev["event_id"]: gid for ev, gid in out}
    assert by["e1"] == 1774 and by["e2"] == 1773 and by["e3"] == 1772, by


@pytest.mark.asyncio
async def test_이름이_달라도_토큰으로_맞춘다():
    """⚠️ 소스 표기가 다르다 — `Yokohama Dena Baystars` · `Fukuoka Hawks`."""
    evs = [{"event_id": "n1", "start_time": WHEN,
            "home_team": "Yokohama Dena Baystars",
            "away_team": "Chunichi Dragons"}]
    pool = _Pool([{"id": 5, "home": "Yokohama DeNA BayStars",
                   "away": "Chunichi Dragons"},
                  {"id": 6, "home": "Hanshin Tigers", "away": "Yomiuri Giants"}])
    out = await S._match_oddsapinet(pool, "npb", evs)
    assert [gid for _, gid in out] == [5], out


@pytest.mark.asyncio
async def test_한쪽만_맞으면_버린다():
    """🔴 **억지로 붙이지 않는다.** `Kia Tigers` 와 `Hanshin Tigers` 는 둘 다
    "Tigers" 라 한쪽 일치는 근거가 못 된다."""
    evs = [{"event_id": "x", "start_time": WHEN,
            "home_team": "Hanshin Tigers", "away_team": "Yomiuri Giants"}]
    pool = _Pool([{"id": 9, "home": "Kia Tigers", "away": "Doosan Bears"}])
    assert await S._match_oddsapinet(pool, "kbo", evs) == []


@pytest.mark.asyncio
async def test_한_id_가_두_번_쓰이지_않는다():
    """🔴 같은 경기에 두 이벤트가 붙으면 그게 오염이다."""
    evs = _evs() + [{"event_id": "dup", "start_time": WHEN,
                     "home_team": "KT Wiz", "away_team": "NC Dinos"}]
    out = await S._match_oddsapinet(_Pool(), "kbo", evs)
    ids = [gid for _, gid in out]
    assert len(ids) == len(set(ids)), ids


@pytest.mark.asyncio
async def test_창_안에_경기가_없으면_빈손():
    assert await S._match_oddsapinet(_Pool([]), "kbo", _evs()) == []


@pytest.mark.asyncio
async def test_질의를_이벤트마다_던지지_않는다():
    """⚠️ 창이 같으면 한 번이면 된다 — 이벤트마다 물으면 N배다."""
    pool = _Pool()
    await S._match_oddsapinet(pool, "kbo", _evs())
    assert pool.n <= len(_evs()), f"질의 {pool.n}회"


def test_대조를_새로_짓지_않았다():
    """🔴 `football.match_team_name` 이 원본이다(사본 금지)."""
    import ast

    # ⚠️ **주석·독스트링을 뗀다.** "similar_team 은 쓰지 않는다"는 설명 자체가
    #    금지 문자열을 담고 있어 원문 grep 은 거짓으로 실패한다(D46, 11회째).
    tree = ast.parse(inspect.getsource(S._match_oddsapinet).strip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if body and isinstance(body, list):
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)
    code = ast.unparse(tree)
    assert "match_team_name" in code
    assert "similar_team" not in code, \
        "similar_team 단독은 위험하다 — Kia/Hanshin 이 둘 다 Tigers 다"
