"""[SP-1] KBO 예고선발이 **손에 있는데 `games` 에 안 들어간다.**

사용자 2026-09-23: "1,2,3,4 전부다 승인" (④ 라인업 회수) · "완료를 해놓거라"

🔴 실측 2026-09-23 01:55 운영 — `naver_kbo.refresh(redis, "2026-09-23")`:
```
refresh → {'games': 3, 'failed': 4}
load    → 3건
  Kia Tigers@Doosan Bears   home_pitcher {"name": "잭로그", "throws": "L",
                                          "era_season": 4.09, …}
  Lotte Giants@Hanwha Eagles home_pitcher {"name": "박준영", …}
  NC Dinos@KT Wiz            home_pitcher {"name": "로건",  …}
  stadium 칸도 함께 온다
```
그런데 같은 시각 `games` 는:
```
KBO 예정 26경기 · home_pitcher 채워진 것 0
```
⑤의 `starter_recent3` 는 `games.home_pitcher` 를 읽는다. 그래서 **오늘 KBO
경기는 선발 축이 통째로 미상**이었다 — 자료가 없어서가 아니라 옮기는 코드가
없어서다("만들어 놓고 안 이음").

⚠️ 이름은 이미 맞는다 — `games` 선발 52종이 `pitcher_appearances` 에 52종
   전부 있다(NPB 80/81 · MLB 173/176). 옮기기만 하면 최근 3등판이 붙는다.

🔴 **매칭을 새로 짓지 않는다.** `upsert_results` 와 같은 규약으로 `games` 의
   그 날짜 행을 팀 표기로 찾는다 — 같은 경기가 두 행으로 갈리면 그 행에 붙은
   예측이 영원히 미채점으로 남는다.
"""
from __future__ import annotations

import inspect

import pytest

from app.collectors import naver_kbo as N

SNAP = {
    "Kia Tigers@Doosan Bears": {
        "stadium": "잠실",
        "home_pitcher": {"name": "잭로그", "era_season": 4.09},
        "away_pitcher": {"name": "네일", "era_season": 2.91},
    },
    "NC Dinos@KT Wiz": {
        "stadium": "수원",
        "home_pitcher": {"name": "로건"},
        "away_pitcher": {},                     # 아직 미발표
    },
}


class _Pool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return 7


def test_함수가_있다():
    assert hasattr(N, "upsert_probables")


@pytest.mark.asyncio
async def test_선발을_games_에_쓴다():
    pool = _Pool()
    out = await N.upsert_probables(pool, "2026-09-23", snap=SNAP)
    assert out["games"] >= 1, out
    wrote = [a for sql, a in pool.calls if "home_pitcher" in sql]
    assert wrote, "games 에 선발을 쓰지 않았다"
    flat = str(wrote)
    assert "잭로그" in flat and "네일" in flat


@pytest.mark.asyncio
async def test_이름이_없으면_안_쓴다():
    """🔴 **빈 값으로 덮지 않는다.** 내일 경기는 예고 전이라 이름이 없다 —
    None 으로 덮으면 어제 채운 값이 지워진다."""
    pool = _Pool()
    await N.upsert_probables(pool, "2026-09-23",
                             snap={"A@B": {"home_pitcher": {},
                                           "away_pitcher": {}}})
    assert not [a for sql, a in pool.calls if "home_pitcher" in sql]


@pytest.mark.asyncio
async def test_구장도_함께_쓴다():
    """[VEN-1 이어받기] `venue_name` 이 KBO 361경기 전건 비어 있었다."""
    pool = _Pool()
    await N.upsert_probables(pool, "2026-09-23", snap=SNAP)
    assert [a for sql, a in pool.calls if "venue_name" in sql], "구장을 안 썼다"


def test_기존_값을_지우지_않는다():
    """🔴 `COALESCE` 로 덮어쓰기를 막는다 — 늦게 오는 빈 값이 이긴 적이 있다.

    ⚠️ 질의는 **모듈 상수**다. 함수 본문에서 찾으면 거짓 실패한다.
    """
    import re

    sql = re.sub(r"\s+", " ", N._SET_PROBABLE)
    for col in ("home_pitcher", "away_pitcher", "venue_name"):
        assert f"{col} = COALESCE" in sql, f"{col} 이 덮어쓰기다"


def test_매칭을_새로_짓지_않는다():
    """🔴 팀 표기 대조표를 **여기서 만들지 않는다.** 스냅샷 키가 이미 Odds
    표기다(`refresh` 가 `TEAM_TO_ODDS` 로 만든다) — `games` 와 같은 문자열이라
    그대로 쓴다. 새 dict 를 만들면 그것이 사본이다."""
    src = inspect.getsource(N.upsert_probables)
    assert "partition(" in src, "스냅샷 키를 안 쓴다"
    # ⚠️ `= {` 로 찾으면 카운터(`out = {...}`)에 걸린다 — 처음에 그랬다.
    #    금지할 것은 **팀 이름 문자열**이 함수 안에 나타나는 것이다.
    for team in ("Doosan", "두산", "KT Wiz", "Lotte", "LG"):
        assert team not in src, f"함수 안에 팀 표기를 적었다: {team}"
    assert "TEAM_TO_ODDS" in inspect.getsource(N), "원본이 사라졌다"


@pytest.mark.asyncio
async def test_한_경기가_실패해도_나머지가_산다():
    class _Boom(_Pool):
        async def fetchval(self, sql, *args):
            raise RuntimeError("DB")

    out = await N.upsert_probables(_Boom(), "2026-09-23", snap=SNAP)
    assert out["failed"] >= 1 and "games" in out


def test_스케줄러가_부른다():
    """🔴 배선의 끝 — 새 잡을 만들지 않고 KBO 결과 잡에 얹는다."""
    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0] for ln in inspect.getsource(S).splitlines())
    assert "upsert_probables" in src, "스케줄러가 안 부른다"
