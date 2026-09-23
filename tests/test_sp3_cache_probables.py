"""[SP-3] NPB 선발이 **캐시에 있는데** `games` 에 안 들어간다.

사용자 2026-09-23: "오늘 kbo.npb 어제 고친 페이블 분석과정으로 처음부터 끝까지
돌려서 예측해보자"

🔴 실측 — 흐름을 돌리자 NPB 6경기가 전부 ⑥에서 멈췄다:
```
[NPB] Hanshin@Yakult   선발 None / None
  n06_verdict  {"starter_recent3": "unknown", "lineup_out": "unknown", …}
               verdict="모름과반"  unknown_ratio 0.667~0.833   → 멈춤
```
그런데 같은 시각 판정 캐시에는 **이름까지 있었다**:
```
analysis:npb:2026-09-23  games[0]
  away_pitcher "髙橋 遥人"   research.away_pitcher.era_season 1.99
  home_pitcher "奥川 恭伸"   research.home_pitcher.era_season 2.75
  research.starter_status "예상"
```
`games.home_pitcher` 에 쓰는 코드는 저장소 전체에서 **`naver_kbo` 하나**뿐이라
(KBO 전용) NPB 는 영원히 비어 있었다 — KBO 와 똑같은 "만들어 놓고 안 이음".

⚠️ ⑤의 `_starter_recent3` 는 `games.home_pitcher` 를 읽는다. 그 칸이 비면
   선발 축이 통째로 미상이고, 핵심 변수 셋 중 둘이 미상이면 ⑥이 멈춘다.

🔴 **종목을 가리지 않는다**(CLAUDE.md "페이블식 흐름은 모든 스포츠에 적용").
   캐시 모양은 종목 공통이라 한 함수가 kbo·npb·mlb 를 다 덮는다.
"""
from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest

from app.collectors import lineups as L

DOC = {"games": [
    {"game_id": "16962", "away": "Hanshin Tigers", "home": "Tokyo Yakult Swallows",
     "away_pitcher": "髙橋 遥人", "home_pitcher": "奥川 恭伸"},
    {"game_id": "16963", "away": "Yomiuri Giants", "home": "Hiroshima Toyo Carp",
     "away_pitcher": "", "home_pitcher": None},          # 예고 전
]}


class _R:
    def __init__(self, doc=DOC):
        self.doc = doc

    async def get(self, k):
        return json.dumps(self.doc, ensure_ascii=False) if self.doc else None


class _Pool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *a):
        self.calls.append((sql, a))
        return "UPDATE 1"


def test_함수가_있다():
    assert hasattr(L, "upsert_probables_from_analysis")


@pytest.mark.asyncio
async def test_캐시의_선발을_games_에_쓴다():
    pool = _Pool()
    out = await L.upsert_probables_from_analysis(pool, _R(), "npb", "2026-09-23")
    assert out["games"] == 1, out
    wrote = [a for sql, a in pool.calls if "home_pitcher" in sql]
    assert wrote, "games 에 선발을 쓰지 않았다"
    assert "奥川 恭伸" in str(wrote) and "髙橋 遥人" in str(wrote)


@pytest.mark.asyncio
async def test_예고_전은_건너뛴다():
    """🔴 빈 값으로 덮지 않는다 — 어제 채운 값이 지워진다."""
    pool = _Pool()
    await L.upsert_probables_from_analysis(pool, _R(), "npb", "2026-09-23")
    args = [a for sql, a in pool.calls if "home_pitcher" in sql]
    assert all("16963" not in str(x[0]) for x in args), args


@pytest.mark.asyncio
async def test_기존_값을_지우지_않는다():
    """🔴 COALESCE 로 덮어쓰기를 막는다."""
    import re

    sql = re.sub(r"\s+", " ", L._SET_STARTERS)
    for col in ("home_pitcher", "away_pitcher"):
        assert f"{col} = COALESCE" in sql, f"{col} 이 덮어쓰기다"


@pytest.mark.asyncio
async def test_캐시가_없으면_조용히_0():
    """⚠️ 크래시하지 않는다(절대 규칙 3)."""
    out = await L.upsert_probables_from_analysis(_Pool(), _R(None), "npb",
                                                 "2026-09-23")
    assert out["games"] == 0


@pytest.mark.asyncio
async def test_어제_캐시로_내려가지_않는다():
    """🔴 **오늘 선발을 어제 것으로 채우면 안 된다.** 날짜를 그대로 쓴다."""
    seen = []

    class _RR(_R):
        async def get(self, k):
            seen.append(k)
            return json.dumps(DOC, ensure_ascii=False)

    await L.upsert_probables_from_analysis(_Pool(), _RR(), "npb", "2026-09-23")
    assert seen == ["analysis:npb:2026-09-23"], seen


def test_종목을_가리지_않는다():
    """🔴 CLAUDE.md — "페이블식 흐름은 모든 스포츠에 적용"."""
    src = inspect.getsource(L.upsert_probables_from_analysis)
    for banned in ('"npb"', "'npb'", '"kbo"', "'kbo'"):
        assert banned not in src, f"종목을 손으로 적었다: {banned}"


def test_스케줄러가_부른다():
    """🔴 배선의 끝 — 프리페치가 캐시를 만든 **뒤에** 옮긴다."""
    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S).splitlines())
    assert "upsert_probables_from_analysis" in src


@pytest.mark.asyncio
async def test_한_경기가_실패해도_나머지가_산다():
    class _Boom(_Pool):
        async def execute(self, sql, *a):
            raise RuntimeError("DB")

    out = await L.upsert_probables_from_analysis(_Boom(), _R(), "npb",
                                                 "2026-09-23")
    assert out["failed"] >= 1 and "games" in out
