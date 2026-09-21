"""[RES-1] KBO 결과를 네이버 일정 API 에서 받는다.

🔴 **왜 필요한가.** KBO 결과(점수)를 채우던 것은 `kbo.upsert_games` 이고, 그
   소스는 `koreabaseball.com` 이다. robots 가 거부해서 껐다(D33). 그러면
   **내일 04:01 잡부터 KBO 결과가 안 들어오고 채점이 멈춘다.**
   실측 2026-09-21 13:52: `games(kbo)` 최종 적재 `2026-09-21 04:01` —
   게이트를 켠 13:0x **직전**이다. 아직 안 끊겼을 뿐이다.

🔴 **결과가 다른 곳에 있다.** `api-gw.sports.naver.com/schedule/games` 가 점수를
   같이 준다(실측 2026-09-21 14:10, 로컬):

       homeTeamScore · awayTeamScore · statusCode:'RESULT' · winner ·
       cancel · suspended
       2026-09-20  한화 3 - 4 LG · KIA 8 - 6 NC

   이 소스는 2026-09-21 사용자 지시("고 크롤러와 맞춰라")로 **켜져 있다**.

⚠️ 새 매칭 규칙·새 팀명 표를 만들지 않는다 — `game_match.apply_result` 와
   `naver_kbo.TEAM_TO_ODDS` 가 원본이다(사본 금지). DB 의 KBO 팀명은 이미
   `Hanwha Eagles` 형식이라 그대로 맞는다(실측).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

#: 실측 응답에서 필요한 칸만 뽑은 것. 🔴 키 이름을 지어내지 않았다.
ROWS = [
    {"gameId": "20260920HHLG02026", "gameDateTime": "2026-09-20T18:30:00",
     "homeTeamName": "LG", "awayTeamName": "한화",
     "homeTeamScore": 4, "awayTeamScore": 3,
     "statusCode": "RESULT", "statusInfo": "9회초", "cancel": False,
     "suspended": False, "winner": "HOME"},
    {"gameId": "20260920HTNC02026", "gameDateTime": "2026-09-20T18:30:00",
     "homeTeamName": "NC", "awayTeamName": "KIA",
     "homeTeamScore": 6, "awayTeamScore": 8,
     "statusCode": "RESULT", "statusInfo": "9회말", "cancel": False,
     "suspended": False, "winner": "AWAY"},
    # 우천 취소 — 점수를 넣으면 안 된다
    {"gameId": "20260920SKKT02026", "gameDateTime": "2026-09-20T18:30:00",
     "homeTeamName": "KT", "awayTeamName": "SSG",
     "homeTeamScore": 0, "awayTeamScore": 0,
     "statusCode": "CANCEL", "statusInfo": "우천취소", "cancel": True,
     "suspended": False, "winner": None},
    # 아직 안 끝난 경기 — 건드리지 않는다
    {"gameId": "20260920OBLT02026", "gameDateTime": "2026-09-20T18:30:00",
     "homeTeamName": "롯데", "awayTeamName": "두산",
     "homeTeamScore": 1, "awayTeamScore": 0,
     "statusCode": "STARTED", "statusInfo": "5회말", "cancel": False,
     "suspended": False, "winner": None},
    # 🔴 매핑에 없는 팀(올스타·시범 껍데기). 실측에서 `BMBC1` 이 이렇게 온다.
    {"gameId": "20260920BMBC1", "gameDateTime": "2026-09-20T18:30:00",
     "homeTeamName": "", "awayTeamName": "",
     "homeTeamScore": 0, "awayTeamScore": 0,
     "statusCode": "RESULT", "statusInfo": "", "cancel": False,
     "suspended": False, "winner": None},
]


class _Client:
    def __init__(self, rows):
        self.rows, self.asked = rows, []

    async def games(self, date):
        self.asked.append(date)
        return self.rows


class _Pool:
    """apply_result 가 실제로 부르는 것만 흉내낸다."""

    def __init__(self):
        self.calls = []

    async def fetchval(self, *a):
        return None                      # 기존 행 없음 → insert 경로

    async def execute(self, sql, *a):
        self.calls.append(a)


@pytest.mark.asyncio
async def test_끝난_경기만_점수가_들어간다(monkeypatch):
    from app.collectors import naver_kbo

    seen = []

    async def fake_apply(pool, **kw):
        seen.append(kw)
        return "updated"

    monkeypatch.setattr("app.collectors.game_match.apply_result", fake_apply)
    out = await naver_kbo.upsert_results(_Pool(), "2026-09-20",
                                         client=_Client(ROWS))
    got = {(k["home"], k["away"]): k for k in seen}
    assert ("LG Twins", "Hanwha Eagles") in got
    assert got[("LG Twins", "Hanwha Eagles")]["home_score"] == 4
    assert got[("LG Twins", "Hanwha Eagles")]["away_score"] == 3
    # 🔴 **정수여야 한다.** `4.0 == 4` 가 참이라 값만 보면 통과한다 —
    #    실제로 처음 구현이 `_num`(이닝·방어율용 float 변환)을 써서 4.0 을
    #    넣고 있었고, 이 단언이 없어서 계약이 **거짓 통과**했다(2026-09-21).
    for k in got.values():
        for f in ("home_score", "away_score"):
            assert k[f] is None or type(k[f]) is int, f"{f} 가 {type(k[f])} 다"
    assert got[("LG Twins", "Hanwha Eagles")]["status"] == "final"
    assert got[("NC Dinos", "Kia Tigers")]["away_score"] == 8
    assert out["applied"] == 3           # final 2 + cancelled 1
    assert out["skipped_unmapped"] == 1  # BMBC1


@pytest.mark.asyncio
async def test_취소는_점수를_넣지_않는다(monkeypatch):
    from app.collectors import naver_kbo

    seen = []

    async def fake_apply(pool, **kw):
        seen.append(kw)
        return "updated"

    monkeypatch.setattr("app.collectors.game_match.apply_result", fake_apply)
    await naver_kbo.upsert_results(_Pool(), "2026-09-20", client=_Client(ROWS))
    kt = [k for k in seen if k["home"] == "KT Wiz"][0]
    assert kt["status"] == "cancelled"
    assert kt["home_score"] is None and kt["away_score"] is None


@pytest.mark.asyncio
async def test_진행중_경기는_건드리지_않는다(monkeypatch):
    from app.collectors import naver_kbo

    seen = []

    async def fake_apply(pool, **kw):
        seen.append(kw)
        return "updated"

    monkeypatch.setattr("app.collectors.game_match.apply_result", fake_apply)
    await naver_kbo.upsert_results(_Pool(), "2026-09-20", client=_Client(ROWS))
    assert not [k for k in seen if k["home"] == "Lotte Giants"], \
        "STARTED 경기를 final 로 적었다"


@pytest.mark.asyncio
async def test_시각은_KST_를_UTC_로_바꿔_넣는다(monkeypatch):
    from app.collectors import naver_kbo

    seen = []

    async def fake_apply(pool, **kw):
        seen.append(kw)
        return "updated"

    monkeypatch.setattr("app.collectors.game_match.apply_result", fake_apply)
    await naver_kbo.upsert_results(_Pool(), "2026-09-20", client=_Client(ROWS))
    # 18:30 KST = 09:30 UTC (DB 는 UTC 저장 — 절대 규칙 4)
    assert seen[0]["starts_at"] == datetime(2026, 9, 20, 9, 30, tzinfo=timezone.utc)


def test_팀명_표를_새로_만들지_않았다():
    """🔴 사본 금지 — `TEAM_TO_ODDS` 가 원본이다."""
    import inspect

    from app.collectors import naver_kbo

    src = inspect.getsource(naver_kbo.upsert_results)
    assert "TEAM_TO_ODDS" in src
    for name in ("Hanwha Eagles", "LG Twins", "Doosan Bears"):
        assert name not in src, f"팀명 {name} 을 함수에 손으로 적었다"


def test_매칭_규칙을_새로_만들지_않았다():
    """🔴 `apply_result` 를 쓴다 — 중복 경기 행이 갈라지면 예측이 미채점으로
    남는다(실측 2026-08-27)."""
    import inspect

    from app.collectors import naver_kbo

    src = inspect.getsource(naver_kbo.upsert_results)
    assert "apply_result" in src
    assert "INSERT INTO games" not in src and "UPDATE games" not in src


def test_스케줄러가_실제로_부른다():
    """🔴 **만들어 놓고 안 이으면 없는 것과 같다** — 이 저장소의 반복 결함이다."""
    import inspect

    from app import scheduler

    assert "upsert_results" in inspect.getsource(scheduler.finals_job) or \
        "ingest_kbo_finals" in inspect.getsource(scheduler.finals_job)
    assert hasattr(scheduler, "ingest_kbo_finals")
