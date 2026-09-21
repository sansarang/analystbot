"""[ROB-1] robots 파서 계약 — **재감사를 돌리기 전에 먼저 통과시킨다.**

사용자 지시 2026-09-21: "파서 계약 테스트(실제 robots 10건 + 와일드카드 `*` ·
종결 `$` · Allow/Disallow 최장 일치 우선 · User-agent 그룹 선택)를 먼저
통과시킨 뒤 돌린다."

🔴 **왜 직접 짰나.** 파이썬 표준 `urllib.robotparser` 는 `*`·`$` 를 해석하지
   않는다. `Disallow: /api/*` 를 문자 그대로 읽고 `/api/data/…` 를 **허용**이라
   답한다. 그 버그로 내가 FotMob 을 "robots 명시 허용 — 유일하다"고 **오보**했다.

🔴 **판정 기준은 우리 봇의 UA 문자열이다:**
       AnalystBot/1.0 (+research; respects robots)
   `*` 그룹과 우리 UA 를 지목한 그룹이 다르면 **지목 그룹이 이긴다**(구글 규격).
"""
from __future__ import annotations

import pathlib

import pytest

OUR_UA = "AnalystBot/1.0 (+research; respects robots)"
_FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "robots"


def _txt(host: str) -> str:
    return (_FIX / f"{host}.txt").read_text(encoding="utf-8", errors="replace")


# ── 문법 ──────────────────────────────────────────────────────────
def test_별표는_임의_문자열이다():
    from app.deepsearch.runtime import robots_allows

    t = "User-agent: *\nAllow: /\nDisallow: /api/*\n"
    assert robots_allows(t, "/api/data/matches", ua=OUR_UA) is False
    assert robots_allows(t, "/api/", ua=OUR_UA) is False
    assert robots_allows(t, "/matches", ua=OUR_UA) is True


def test_달러는_끝을_가리킨다():
    from app.deepsearch.runtime import robots_allows

    t = "User-agent: *\nDisallow: /\nAllow: /$\n"
    assert robots_allows(t, "/", ua=OUR_UA) is True
    assert robots_allows(t, "/x", ua=OUR_UA) is False


def test_최장_일치가_이긴다():
    from app.deepsearch.runtime import robots_allows

    t = "User-agent: *\nDisallow: /a/\nAllow: /a/b/\n"
    assert robots_allows(t, "/a/x", ua=OUR_UA) is False
    assert robots_allows(t, "/a/b/x", ua=OUR_UA) is True
    # 반대 방향도 — 더 긴 Disallow 가 짧은 Allow 를 이긴다
    t2 = "User-agent: *\nAllow: /a/\nDisallow: /a/b/\n"
    assert robots_allows(t2, "/a/x", ua=OUR_UA) is True
    assert robots_allows(t2, "/a/b/x", ua=OUR_UA) is False


def test_길이가_같으면_허용이_이긴다():
    from app.deepsearch.runtime import robots_allows

    assert robots_allows("User-agent: *\nDisallow: /x\nAllow: /x\n",
                         "/x", ua=OUR_UA) is True


def test_UA_지목_그룹이_별표를_이긴다():
    """🔴 news.google.com 이 `ClaudeBot`·`anthropic-ai` 를 이렇게 막는다."""
    from app.deepsearch.runtime import robots_allows

    t = "User-agent: *\nAllow: /\n\nUser-agent: AnalystBot\nDisallow: /\n"
    assert robots_allows(t, "/any", ua=OUR_UA) is False
    assert robots_allows(t, "/any", ua="SomeOther/1.0") is True


def test_규칙이_없으면_허용이다():
    from app.deepsearch.runtime import robots_allows

    assert robots_allows("", "/x", ua=OUR_UA) is True
    assert robots_allows("# 주석뿐\n", "/x", ua=OUR_UA) is True


def test_주석과_대소문자를_견딘다():
    from app.deepsearch.runtime import robots_allows

    t = "USER-AGENT: *\nDISALLOW: /a   # 뒤에 주석\n"
    assert robots_allows(t, "/a/b", ua=OUR_UA) is False


# ── 실제 robots 10건 ──────────────────────────────────────────────
#: 🔴 **직접 받은 파일**이다(2026-09-21). 값은 지어내지 않았다.
CASES = [
    ("news.google.com", "/rss/search", False),
    ("news.google.com", "/topics/abc", True),
    ("www.fotmob.com", "/api/data/matches", False),
    ("www.fotmob.com", "/api/matchDetails", False),
    ("www.fotmob.com", "/matches", True),
    ("www.bing.com", "/news/search", True),
    ("www.bing.com", "/search", False),
    ("search.daum.net", "/search", False),
    ("api.open-meteo.com", "/v1/forecast", False),
    ("www.koreabaseball.com", "/ws/Schedule.asmx/GetScheduleList", False),
    ("www.mlb.com", "/news", True),
    ("lite.duckduckgo.com", "/lite/", True),
    ("news.yahoo.co.jp", "/articles/abc", True),
    ("www.transfermarkt.com", "/x/verletztespieler/verein/5", True),
]


@pytest.mark.parametrize("host,path,want", CASES)
def test_실제_robots_판정(host, path, want):
    from app.deepsearch.runtime import robots_allows

    got = robots_allows(_txt(host), path, ua=OUR_UA)
    assert got is want, f"{host}{path} → {got} (기대 {want})"


def test_픽스처가_실물이다():
    """⚠️ 지어낸 파일로 통과하면 이 계약은 아무것도 안 지킨다."""
    assert len(CASES) >= 10
    hosts = {h for h, _, _ in CASES}
    assert len(hosts) == 10
    for h in hosts:
        assert (_FIX / f"{h}.txt").exists(), h
    # 실물이면 이런 것이 들어 있다
    assert "anthropic-ai" in _txt("news.google.com").lower()
    assert "Disallow: /api/*" in _txt("www.fotmob.com")


def test_stdlib_와_갈리는_자리를_적어_둔다():
    """🔴 이 한 줄이 없어서 내가 오보했다. **갈리는 것이 정상**이다."""
    import urllib.robotparser as RP

    from app.deepsearch.runtime import robots_allows

    t = _txt("www.fotmob.com")
    p = RP.RobotFileParser()
    p.parse(t.splitlines())
    stdlib = p.can_fetch(OUR_UA, "https://www.fotmob.com/api/data/matches")
    ours = robots_allows(t, "/api/data/matches", ua=OUR_UA)
    assert stdlib is True and ours is False, \
        "stdlib 가 고쳐졌거나 우리 파서가 망가졌다 — 어느 쪽인지 확인하라"
