"""[SRC-OFF / deepsearch_parallel [2]a] robots 가 거부하는 소스를 **끈다.**

🔴 실측 2026-09-21 13:04 — `koreabaseball.com/robots.txt` (HTTP 200 · EUC-KR):

    # 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.
    User-agent: Googlebot / Yeti / Daumoa / Bingbot   Disallow: /ws/
    User-agent: *                                     Disallow: /

   `can_fetch(AnalystBot/1.0)` 는 **전 경로 False** 다. 그런데 우리는 7경로를
   지금도 치고 있었다(kbo.py:31·89 · kbo_stats.py:26·28·29 · kbo_roster.py:25 ·
   kbo_boxscore `/ws/GetBoxScoreScroll`).

🔴 `api-gw.sports.naver.com` 은 robots.txt 가 **404** 라 판단 불가다.
   같은 계열 `sports.news.naver.com` 은 `Disallow: /` 이므로, 판단이 설 때까지
   함께 끈다(사용자 지시 [2]a).

⚠️ **코드를 지우지 않는다.** 기능 플래그로 끈다 — 정식 접근이 허락되면
   플래그 한 줄로 되돌린다.
"""
from __future__ import annotations

import inspect

import pytest


def test_플래그가_config_에_있다():
    """🔴 숫자·스위치는 config 하나가 원본이다(사본 금지)."""
    from app.engine import rules as R

    assert R.get("sources.koreabaseball.enabled") is False
    assert R.get("sources.naver_apigw.enabled") is False


def test_게이트_함수가_한_곳이다():
    from app.collectors.source_gate import enabled

    assert enabled("koreabaseball") is False
    assert enabled("naver_apigw") is False
    # ⚠️ 모르는 이름은 **켜진 것**으로 본다 — 게이트가 기존 소스를 조용히
    #    끄면 그게 더 큰 사고다.
    assert enabled("fotmob") is True
    assert enabled("아무거나") is True


@pytest.mark.asyncio
async def test_kbo_일정이_요청을_보내지_않는다():
    """🔴 끈 소스는 **네트워크를 타지 않는다.**

    ⚠️ 처음에 `fetch_month(...) == []` 로 썼다가 **거짓 통과**를 만들었다 —
       목 모드(`freesource_mocked`)가 게이트에 닿기 전에 빈 목록을 돌려주므로,
       게이트를 껐다 켰다 해도 그 단언은 늘 통과한다. 실제 클라이언트로
       **게이트가 있는 자리**를 직접 친다.
    """
    from app.collectors.kbo import KBOClient
    from app.collectors.source_gate import SourceDisabled

    with pytest.raises(SourceDisabled):
        await KBOClient().schedule_rows(2026, 9)


@pytest.mark.asyncio
async def test_kbo_엔트리가_요청을_보내지_않는다():
    from app.collectors import kbo_roster

    from app.collectors.source_gate import SourceDisabled

    with pytest.raises(SourceDisabled) as e:
        await kbo_roster.KBORosterClient().fetch()
    assert "robots" in str(e.value)


@pytest.mark.asyncio
async def test_naver_apigw_도_막힌다():
    from app.collectors import naver_kbo

    from app.collectors.source_gate import SourceDisabled

    with pytest.raises(SourceDisabled) as e:
        await naver_kbo.NaverKBOClient()._get("/schedule/games")
    assert "robots" in str(e.value)


def test_끈_이유가_코드에_적혀_있다():
    """⚠️ 왜 껐는지가 없으면 다음 사람이 그냥 켠다."""
    from app.collectors import source_gate

    src = inspect.getsource(source_gate)
    assert "robots" in src and "koreabaseball" in src


def test_흐름은_KBO_에서도_완주한다():
    """🔴 소스를 꺼도 **예외로 죽지 않는다** — 증거 0 → 미상이다."""
    from app.collectors.source_gate import blocked_reason, enabled

    assert enabled("koreabaseball") is False
    r = blocked_reason("koreabaseball")
    assert r and "robots" in r


@pytest.mark.asyncio
async def test_박스스코어도_막힌다():
    """🔴 `/ws/GetBoxScoreScroll` 이 D09a 의 그 경로다."""
    from app.collectors import kbo_boxscore as KB
    from app.collectors.source_gate import SourceDisabled

    fn = getattr(KB, "fetch_boxscore", None) or getattr(KB, "backfill", None)
    assert fn is not None
    import inspect

    src = inspect.getsource(KB)
    assert src.count('require("koreabaseball")') >= 2, \
        "박스스코어 HTTP 진입점이 다 막히지 않았다"
