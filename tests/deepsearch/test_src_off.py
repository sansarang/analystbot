"""[SRC-OFF / deepsearch_parallel [2]a] robots 가 거부하는 소스를 **끈다.**

🔴 실측 2026-09-21 13:04 — `koreabaseball.com/robots.txt` (HTTP 200 · EUC-KR):

    # 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.
    User-agent: Googlebot / Yeti / Daumoa / Bingbot   Disallow: /ws/
    User-agent: *                                     Disallow: /

   `can_fetch(AnalystBot/1.0)` 는 **전 경로 False** 다. 그런데 우리는 7경로를
   지금도 치고 있었다(kbo.py:31·89 · kbo_stats.py:26·28·29 · kbo_roster.py:25 ·
   kbo_boxscore `/ws/GetBoxScoreScroll`).

🔴 [2026-09-21 사용자 지시 "고 크롤러와 맞춰라"] `api-gw.sports.naver.com` 은
   **다시 켰다.** robots.txt 가 404(판단 불가)지 거부가 아니고, 끈 동안에도
   Go 크롤러가 같은 API 를 10분마다 치고 있어(D36) 모순 상태였다.
   ⚠️ `koreabaseball` 은 **명시 거부**라 그대로 끈다 — 이 둘을 섞지 않는다.

⚠️ **코드를 지우지 않는다.** 기능 플래그로 끈다 — 정식 접근이 허락되면
   플래그 한 줄로 되돌린다.

═══════════════════════════════════════════════════════════════════════
🔴 [KBO-ON 2026-09-23 **사용자 지시 · 규칙 개정**]
   원문: "자동수집.크롤링 복제하는 행위를 허용한다...kbo도 해야한다.."

   `koreabaseball` 을 **켰다.** 위 실측(robots 원문)은 그대로 사실이고 지우지
   않는다 — 바뀐 것은 사실이 아니라 **운영자의 결정**이다.

⚠️ 그 고지는 KBO 가 건 것이라 운영자의 "허용한다"가 그쪽의 *사전 승인*이
   되지는 않는다. 위험은 운영자에게 귀속된다. 이 파일은 그 결정을 기록할 뿐
   정당화하지 않는다.

🔴 **그래서 이 파일이 잠그는 대상이 바뀌었다.**
     종전: "치지 않는다"
     지금: "**정직하게** 친다" — UA 로 봇임을 밝히고, 간격을 두고, 되돌릴
           스위치를 남긴다. 서버를 속이는 쪽(UA 위장·프록시 회전·쿠키 주입·
           CAPTCHA 우회·429 무시)은 **지시가 바꾸지 않았고 그대로 금지다.**
   ⚠️ 계약을 약화시킨 것이 아니다. 약화였다면 단언을 지웠을 것이다 —
      여기서는 **개수가 늘었다**(끔 3건 → 정직성 6건).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import inspect

import pytest


def test_플래그가_config_에_있다():
    """🔴 숫자·스위치는 config 하나가 원본이다(사본 금지)."""
    from app.engine import rules as R

    # 🔴 [KBO-ON 2026-09-23 사용자 지시] 켰다. 종전은 False 였다.
    assert R.get("sources.koreabaseball.enabled") is True
    # 🔴 naver 는 켜져 있어야 한다 — Go 크롤러와 맞췄다(사용자 지시 2026-09-21)
    assert R.get("sources.naver_apigw.enabled") is True


def test_게이트_함수가_한_곳이다():
    from app.collectors.source_gate import enabled

    assert enabled("koreabaseball") is True
    assert enabled("naver_apigw") is True
    # ⚠️ 모르는 이름은 **켜진 것**으로 본다 — 게이트가 기존 소스를 조용히
    #    끄면 그게 더 큰 사고다.
    assert enabled("fotmob") is True
    assert enabled("아무거나") is True


def test_되돌릴_스위치가_살아_있다(monkeypatch):
    """🔴 **끌 수 있어야 켠 것이다.** config 한 줄로 종전 상태로 돌아간다.

    ⚠️ 종전 계약은 "요청을 보내지 않는다"를 실호출로 확인했다. 그 확인을
       **버리지 않고** 스위치를 끈 상태에서 그대로 유지한다.
    """
    from app.collectors import source_gate as SG

    monkeypatch.setattr(SG, "enabled", lambda n: n != "koreabaseball")
    assert SG.blocked_reason("koreabaseball")
    with pytest.raises(SG.SourceDisabled):
        SG.require("koreabaseball")


def test_봇임을_밝힌다():
    """🔴 **서버를 속이지 않는다.** 지시가 바꾼 것은 "수집하느냐"이지
    "봇임을 숨기느냐"가 아니다.

    종전 UA 는 `Mozilla/5.0` 이었다 — 브라우저 위장이다.
    """
    from app.collectors.kbo import UA

    assert "Mozilla" not in UA, "브라우저로 위장한다"
    assert "bot" in UA.lower(), "봇임을 밝히지 않는다"
    assert "@" not in UA, "UA 에 개인정보를 싣지 않는다"


def test_UA_원본이_한_곳이다():
    """🔴 사본 금지 — 네 모듈이 같은 상수를 import 한다. 손으로 적으면
    하나가 뒤처지고, 그때 그 하나만 위장 UA 로 남는다."""
    from app.collectors import kbo, kbo_boxscore, kbo_roster
    from app.collectors.kbo import UA

    assert kbo_boxscore._HEADERS["User-Agent"] == UA
    assert kbo_roster.HEADERS["User-Agent"] == UA
    import inspect

    for mod in (kbo, kbo_boxscore, kbo_roster):
        src = "\n".join(ln.split("#", 1)[0]
                         for ln in inspect.getsource(mod).splitlines())
        assert '"Mozilla/5.0"' not in src, f"{mod.__name__} 에 위장 UA 가 남았다"


@pytest.mark.asyncio
async def test_간격을_둔다(monkeypatch):
    """🔴 상대 서버에 연달아 치지 않는다. 값의 원본은 config 다(사본 금지)."""
    import app.collectors.kbo as K

    slept = []

    async def _fake(sec):
        slept.append(sec)

    monkeypatch.setattr("asyncio.sleep", _fake)
    await K.polite_gap()
    assert slept and slept[0] > 0, "간격이 0 이다"

    from app.engine import rules as R

    assert R.get("sources.koreabaseball.min_interval_sec") == slept[0], \
        "코드가 config 값이 아닌 다른 숫자를 쓴다"


def test_요청_앞마다_간격이_걸린다():
    """🔴 배선의 끝 — HTTP 진입점 수만큼 `polite_gap()` 이 있어야 한다."""
    import inspect

    from app.collectors import kbo_boxscore as KB

    src = "\n".join(ln.split("#", 1)[0]
                     for ln in inspect.getsource(KB).splitlines())
    assert src.count("await polite_gap()") >= src.count('require("koreabaseball")')


def test_naver_apigw_는_켜져_있다():
    """🔴 Go 크롤러와 **맞춘다.** 한쪽만 끄면 모순이고, 모순은 다음 사람이
    "왜 파이썬만 비지?"로 며칠을 태운다(D36).

    ⚠️ 게이트 자체는 그대로 있다 — config 한 줄로 다시 끌 수 있다.
    """
    from app.collectors.source_gate import enabled, require

    assert enabled("naver_apigw") is True
    require("naver_apigw")          # 예외가 나지 않아야 한다


def test_robots_실측이_지워지지_않았다():
    """🔴 **사실은 지우지 않는다.** 결정이 바뀐 것이지 robots 원문이 바뀐 것이
    아니다. 다음 사람이 무엇을 딛고 켰는지 알아야 한다."""
    from app.collectors import source_gate

    src = inspect.getsource(source_gate)
    assert "robots" in src and "koreabaseball" in src


def test_게이트_자리를_지우지_않았다():
    """🔴 켰다고 `require()` 를 빼면 **다시 끌 수 없다.**
    D09a 의 `/ws/GetBoxScoreScroll` 포함, 진입점마다 그대로 있어야 한다."""
    from app.collectors import kbo_boxscore as KB

    src = inspect.getsource(KB)
    assert src.count('require("koreabaseball")') >= 2, \
        "박스스코어 HTTP 진입점에서 게이트가 사라졌다"
