"""[CLV-S] CLV 통계가 **같은 판단을 32번 세고 있었다.**

사용자 2026-09-23: "지금 안되는것만 딥서치 해서 고치라고"

🔴 **딥서치 근거** (→ docs/FORKS.md F-21):
> "베팅 시점에 받은 **가격은 고정된 스냅샷**이고 **재평가하지 않는다.**"
> "마감 기준을 일관되게 정의하라 — 예: T−5분."
CLV 는 **한 선택당 한 번** 재는 것이다. 같은 경기를 여러 번 평가하고 그
CLV 들을 평균 내면 "늦은 재평가"가 표본을 지배한다.

🔴 실측 2026-09-23 16:50 운영:
```
행 590 · CLV 정확히 0 인 행 200 (33.9%)
킥오프까지 남은 시간(분)  최소 4 · 중앙 287 · 최대 769
시간대별
  0~30분    33행 · CLV0 27 · 양수   0 · 평균 -0.00172
  30~90분   68행 · CLV0 50 · 양수   0 · 평균 -0.00221   ← 양수가 0건
  90~180분  88행 · CLV0 34 · 양수  28 · 평균 -0.00011
  180분+   401행 · CLV0 89 · 양수 166 · 평균 +0.00273
```
킥오프 직전 재평가는 **정의상 CLV≈0 또는 음수**다(그 가격이 이미 종가다).
그것을 섞어 평균 내면 일찍 내린 판단의 값어치가 지워진다.

⚠️ 자료를 지우는 것이 아니다 — 원장은 그대로 두고 **세는 법**을 고친다.
"""
from __future__ import annotations

import pytest

from app.learning import decisions as D


def test_요약_함수가_있다():
    assert hasattr(D, "clv_summary")


def test_선택당_첫_판단만_센다():
    """🔴 이 단위의 전부 — 딥서치가 말한 "고정된 스냅샷"이다."""
    assert "DISTINCT ON" in D._CLV_SUM_SQL
    assert "game_id, side" in D._CLV_SUM_SQL
    # 첫 판단 = ts_decided 가 가장 이른 행
    assert "ts_decided" in D._CLV_SUM_SQL
    assert "DESC" not in D._CLV_SUM_SQL.split("ORDER BY")[-1].split(")")[0]


class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.sql = []

    async def fetch(self, sql, *a):
        self.sql.append(sql)
        return self.rows


@pytest.mark.asyncio
async def test_요약이_비율과_평균을_낸다():
    pool = _Pool([{"clv": 0.02}, {"clv": -0.01}, {"clv": 0.0}, {"clv": 0.03}])
    got = await D.clv_summary(pool)
    assert got["n"] == 4
    assert got["beat"] == 2, got          # 종가를 이긴 것: +0.02, +0.03
    assert abs(got["avg"] - 0.01) < 1e-9, got


@pytest.mark.asyncio
async def test_움직이지_않은_행을_따로_센다():
    """🔴 CLV 0 은 "졌다"가 아니라 **"시장이 안 움직였다"**다.
    섞어서 한 숫자로 내면 30.8% 같은 거짓 비관이 나온다."""
    pool = _Pool([{"clv": 0.0}, {"clv": 0.0}, {"clv": 0.02}, {"clv": -0.01}])
    got = await D.clv_summary(pool)
    assert got["flat"] == 2, got
    # 움직인 것만 보면 2건 중 1건이 이겼다
    assert got["moved"] == 2 and got["beat_of_moved"] == 1, got


@pytest.mark.asyncio
async def test_표본이_없으면_None_을_낸다():
    """⚠️ 0 으로 적지 않는다 — "못 쟀다"와 "0 이다"는 다르다."""
    got = await D.clv_summary(_Pool([]))
    assert got["n"] == 0 and got["avg"] is None, got


@pytest.mark.asyncio
async def test_엔진을_고를_수_있다():
    pool = _Pool([{"clv": 0.01}])
    await D.clv_summary(pool, engine="flow_v14")
    assert "engine" in pool.sql[0]


@pytest.mark.asyncio
async def test_표본이_적으면_말해준다():
    """🔴 딥서치: CLV 도 **200~500건**은 있어야 실력이라 말할 수 있다.
    적은 표본에 결론을 붙이지 않는다."""
    got = await D.clv_summary(_Pool([{"clv": 0.02}] * 10))
    assert got["enough"] is False, got
    got2 = await D.clv_summary(_Pool([{"clv": 0.02}] * 250))
    assert got2["enough"] is True, got2
