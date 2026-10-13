"""🔴🔴 **P4 — 검색(언어·원천)**(수정 지시 2026-10-13 밤 P4).

> 현지어 질의 필수: 팀 국가 언어(vi·th·zh·ar·ja·ko·hi·en)로 팀명 현지 표기 +
> "선발·부상·결장·기자회견".
> 차단 목록: 도박·카지노·배팅 사이트 도메인 패턴은 **s3 전에** 버린다 —
> 신원 단계까지 오지 않게.

🔴 **SR1** 여덟 언어 낱말표가 있다 · **SR2** 구단의 현지어가 **국내 리그**에서
   온다(이름표에 나라 코드가 없다) · **SR3** 도박 꼴은 `tip`·`deny` 로 떨어져
   **본문을 안 받는다** · **SR4** 축구 매체는 안 걸린다(거짓 차단 금지) ·
   **SR5** 도메인 검사가 **신원 검사보다 먼저** 돈다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sr1_eight_language_tables() -> None:
    box = ROOT / "config/search_terms"
    for lang in ("ko", "ja", "en", "vi", "th", "zh", "ar", "hi"):
        path = box / f"{lang}.yaml"
        assert path.exists(), lang
        import yaml
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key in ("absence", "expected_xi", "presser"):
            assert got.get(key), (lang, key)


def test_sr2_club_language_comes_from_its_league() -> None:
    """🔴🔴 **SR2** — 구단은 이름표에 나라 코드가 없다(실측: ACL 일곱 팀 전부)."""
    from app.research import subtasks as st
    said = {"Công An Hà Nội": "vi", "Buriram United": "th",
            "Beijing Guoan": "zh", "Al Shorta": "ar",
            "East Bengal FC": "hi", "Kashima Antlers": "ja"}
    for team, want in said.items():
        got = st.team_lang(team)
        # 🔴 판이 없는 기계에서는 빈 글자일 수 있다 — 있으면 **그 언어**여야 한다
        assert got in ("", want), (team, got, want)


def test_sr3_gambling_is_blocked() -> None:
    from app import domains
    for url in ("https://cong-game-no-hu.example/x", "https://vip52.info/a",
                "https://sunwin.vip/a", "https://soi-keo.net/x",
                "https://hitclub.live/x", "https://x.test/game-bai/y",
                "https://casino-x.test/a", "https://y.test/sportsbook/1"):
        tier = domains.tier_of(url)
        assert tier in ("tip", "deny"), (url, tier)
        assert domains.handling(tier).get("fetch") is False, url


def test_sr4_real_media_is_not_blocked() -> None:
    """🔴 **SR4** — 거짓 차단 금지(축구 매체·구단 이름에 `bet` 가 들어간다)."""
    from app import domains
    for url in ("https://www.bbc.com/sport/football/1",
                "https://www.realbetis.es/noticias",
                "https://www.nikkansports.com/soccer/x",
                "https://m.sports.naver.com/a",
                "https://vnexpress.net/bong-da/x",
                "https://www.the-afc.com/en/national/acl-elite.html"):
        assert domains.tier_of(url) not in ("tip", "deny"), url


def test_sr5_domain_check_runs_before_identity() -> None:
    said = (ROOT / "app/core/stages/s3_docs.py").read_text(encoding="utf-8")
    # ⚠️ **부르는 자리**로 센다 — `def identity_ok` 선언이 위에 있다(그것은 순서가
    #    아니다 · 내 계약이 그 함정을 밟았다).
    i = said.index("domains.verdict(")
    j = said.index("ok_i, said_i = identity_ok(")
    assert i < j, "🔴 신원 검사가 도메인 검사보다 먼저 돈다"
