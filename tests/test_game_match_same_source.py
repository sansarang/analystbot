"""GM-4 — 같은 소스의 다른 경기 id 를 같은 경기로 합쳤다.

🔴 **실사고 2026-09-13.** 오늘 13:30 JST 소프트뱅크 경기가 DB에 안 들어가고,
   **어제 18:00 행이 갱신**됐다. 그 행을 봇이 판정했다. 사용자 지적:
     "빗나간 게 아니라 봇이 어제(9/12) 경기를 판정한 겁니다.
      판단이 갈린 게 아니라 입력이 틀렸어요."

   실측(운영):
     Yahoo 원문 2026-09-13  `2021039419` 지바롯데@소프트뱅크 13:30 scheduled
     DB                     `yahoo:20210394**14**` 09-12 09:00Z (KST 18:00)
     두 경기 간격 19.5h → `MATCH_WINDOW_HOURS=20` 안이라 같은 경기로 봤다.

🔴 `_FIND` 는 **ext_id 를 보지 않는다** — 종목·홈·원정·시각창으로만 찾는다.
   그 설계 의도는 "소스가 달라 ext_id 가 다른 같은 경기"를 잇는 것이다
   (실사고 2026-08-27: odds:… 행과 kbo:… 행이 남남이라 채점이 막혔다).
   그런데 **같은 소스의 다른 id** 는 정반대다 — 연전의 다음 경기다.

⚠️ 소스가 다른 경우의 병합은 **그대로 둔다.** 그것이 이 모듈의 존재 이유다.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import game_match as GM

UTC = timezone.utc


class _Pool:
    def __init__(self, found=None):
        self.found = found
        self.calls = []

    async def fetchval(self, sql, *a):
        self.calls.append(("find", sql, a))
        return self.found

    async def execute(self, sql, *a):
        self.calls.append(("exec", sql, a))


def _args(**kw):
    base = dict(sport="npb", league="NPB", ext_id="yahoo:2021039419",
                starts_at=datetime(2026, 9, 13, 4, 30, tzinfo=UTC),
                home="Fukuoka SoftBank Hawks", away="Chiba Lotte Marines",
                status="scheduled", home_score=None, away_score=None)
    base.update(kw)
    return base


def test_찾을_때_ext_id를_넘긴다():
    """🔴 ext_id 를 안 넘기면 같은 소스인지 판단할 방법이 없다."""
    src = inspect.getsource(GM.apply_result)
    assert "ext_id" in src.split("_FIND", 1)[1][:200], src


def test_같은_소스_다른_id는_같은_경기가_아니다():
    """🔴 실사고의 핵심. `yahoo:...419` 가 `yahoo:...414` 를 갱신했다."""
    assert "split_part" in GM._FIND or "같은 소스" in GM._FIND, GM._FIND


@pytest.mark.asyncio
async def test_기존_행을_못_찾으면_새로_넣는다():
    p = _Pool(found=None)
    out = await GM.apply_result(p, **_args())
    assert out == "inserted", out
    assert p.calls[-1][0] == "exec"


@pytest.mark.asyncio
async def test_같은_경기를_찾으면_갱신한다():
    """⚠️ 반대 위험 — 소스가 다른 같은 경기는 **계속 합쳐져야** 한다.
    실사고 2026-08-27: 합치지 못해 예측이 붙은 행이 영영 미채점이었다."""
    p = _Pool(found=770)
    out = await GM.apply_result(p, **_args(ext_id="odds:36cb8879"))
    assert out == "updated", out
    assert p.calls[-1][1] is GM._UPDATE


def test_창_크기_사유가_적혀_있다():
    """⚠️ 20h 는 하루 1경기 종목 기준이다. 연전이면 겹친다 — 그 사실을 남긴다."""
    src = inspect.getsource(GM)
    i = src.index("MATCH_WINDOW_HOURS = ")
    assert "연전" in src[max(0, i - 400):i + 200], src[i - 400:i + 200]
