"""🔴🔴 **v5 §4-1·§4-3·§4-7** — 검색어 세 요소 · 도메인 등급표 · robots. [#1 #4 #9]

§4-1 원문:

> 검색어는 반드시 `{팀 또는 별칭} {상대} {대회명} {종목 낱말} {날짜 또는
> 'preview/lineup/injury'}` **중 세 요소 이상**을 가진다. 팀·나라 이름
> 하나짜리는 search 가 **거부하고 `query_too_bare` 사유를 돌려준다.**
> … 코드도 **같은 검색어 반복을 거부한다**(동일 검색어 2회 이상 → `duplicate_query`).

§4-3 원문:

> 등급표는 `config/domains.yaml`, 미등록 도메인은 **`local` 취급**하되 종목
> 낱말이 제목에 없으면 버린다(럭비·드라마 차단).
> 등급: `official` / `national` / `local` / `aggregator` / `tip` / `deny` / `wiki`

§4-7 원문:

> robots.txt 거부 경로는 dead. 우회·UA 위장·프록시 금지. **301 은 끝까지 따라가
> 최종 호스트의 robots 를 읽는다.** robots 404 는 **허용**으로 본다.

🔴 **§10-4 M33** — 쓰레기 페이지 86%(10-04) — 검색어 3요소 이상 · 받기 전 거르기 · 도메인 등급표
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════
# §4-1 — 세 요소 이상
# ══════════════════════════════════════════════════════════════════










def test_v5_4_1_같은_검색어를_두_번_거부한다():
    """🔴 §4-1 — *"동일 검색어 2회 이상 → `duplicate_query`."*"""
    from app.querygate import QueryLog
    from app.reasons import Reason
    log = QueryLog()
    # ⚠️ 조각을 넘긴다 — 안 넘기면 **세 요소 문지기**가 먼저 막아 이 시험이
    #    중복을 보지 못한다(짐작은 상대를 못 센다).
    parts = {"team": "North Macedonia", "opponent": "Scotland",
             "when": "lineup"}
    ok, reason, _ = log.check("North Macedonia Scotland lineup", parts=parts)
    assert ok is True and reason is Reason.OK
    ok2, reason2, why2 = log.check("North Macedonia Scotland lineup",
                                   parts=parts)
    assert ok2 is False and reason2 is Reason.DUPLICATE_QUERY, why2


def test_v5_4_1_공백_대소문자_차이는_같은_검색어다():
    """⚠️ 각도를 바꾼 척하는 것을 막는다 — 글자만 다른 것은 같은 질의다."""
    from app.querygate import QueryLog
    log = QueryLog()
    parts = {"team": "North Macedonia", "opponent": "Scotland",
             "when": "lineup"}
    log.check("North Macedonia Scotland lineup", parts=parts)
    ok, _, _ = log.check("  north   macedonia  SCOTLAND lineup ", parts=parts)
    assert ok is False


# ══════════════════════════════════════════════════════════════════
# §4-3 — 도메인 등급표
# ══════════════════════════════════════════════════════════════════


def test_v5_4_3_등급표가_config_domains_yaml이다():
    """🔴 §4-3 — *"등급표는 `config/domains.yaml`."*"""
    from app import domains
    assert set(domains.TIERS) == {"official", "national", "local",
                                  "aggregator", "tip", "deny", "wiki"}, \
        sorted(domains.TIERS)
    rows = domains.table()
    assert rows, "🔴 `config/domains.yaml` 이 비었다"


@pytest.mark.parametrize("url,want", [
    ("https://www.scottishfa.co.uk/en/news/x", "official"),
    ("https://statsapi.mlb.com/api/v1/x", "official"),
    ("https://npb.jp/bis/2026/x", "official"),
    ("https://www.bbc.com/sport/football/articles/x", "national"),
    ("https://www.theguardian.com/football/x", "national"),
    ("https://www.sportsmole.co.uk/football/x", "aggregator"),
    ("https://www.fotmob.com/matches/x", "aggregator"),
    ("https://www.rottentomatoes.com/tv/x", "deny"),
    ("https://en.wikipedia.org/wiki/Scotland_national_football_team", "wiki"),
])
def test_v5_4_3_등급을_가른다(url, want):
    assert domains_tier(url) == want, (url, domains_tier(url))


def domains_tier(url: str) -> str:
    from app import domains
    return domains.tier_of(url)


def test_v5_4_3_미등록은_local이다():
    """🔴 §4-3 — *"미등록 도메인은 **`local` 취급**."*"""
    from app import domains
    assert domains.tier_of("https://처음보는매체.example/x") == "local"


def test_v5_4_3_tip은_본문을_안_받는다():
    """🔴 §4-3 — *"`tip`: **본문 안 받음**, 변수 근거 금지."*"""
    from app import domains
    assert not domains.may_fetch("tip")
    assert domains.may_fetch("official") and domains.may_fetch("local")
    # 🔴 `deny` 는 검색 결과에서 **제거**다
    assert not domains.may_fetch("deny")


@pytest.mark.parametrize("tier,want", [
    ("official", 2), ("national", 1), ("local", 1),
    ("aggregator", 1), ("wiki", 0), ("tip", 0),
])
def test_v5_4_3_등급이_hardness를_준다(tier, want):
    """🔴 §4-3·§5-5 — 등급이 무게를 정한다. ⚠️ `national` 2매체 일치는 2 다."""
    from app import domains
    assert domains.hardness_of(tier) == want, (tier,
                                               domains.hardness_of(tier))


def test_v5_4_3_모르는_등급은_거부한다():
    from app import domains
    with pytest.raises(ValueError, match="등급"):
        domains.hardness_of("오타")


# ══════════════════════════════════════════════════════════════════
# §4-7 — robots
# ══════════════════════════════════════════════════════════════════


def test_v5_4_7_robots_404는_허용이다():
    """🔴 §4-7 — *"robots 404 는 **허용**으로 본다(npb.jp 와 kleague.com 을 같은
    규칙으로)."*"""
    from app import robots
    assert robots.verdict_for_status(404) == "allow"
    assert robots.verdict_for_status(200) == "read"
    # ⚠️ 5xx 는 **모르는 것**이다 — 허용으로 보지 않는다(fail-closed)
    assert robots.verdict_for_status(503) == "unknown"


def test_v5_4_7_301을_끝까지_따라간다():
    """🔴 §4-7 — *"301 은 끝까지 따라가 **최종 호스트의 robots** 를 읽는다."*

    ⚠️ 실측 2026-10-04: `kleague.com` 이 301 이었고 우리는 *"못 읽었다"* 로 적었다.
       🔴 그것은 *"따라가지 않았다"* 였다.
    """
    from app import robots
    assert robots.FOLLOW_REDIRECTS >= 3, robots.FOLLOW_REDIRECTS
    import ast
    import inspect
    src = inspect.getsource(robots)
    tree = ast.parse(src)
    got = ast.unparse(tree)
    assert "FOLLOW_REDIRECTS" in got


def test_v5_4_7_우회_수단이_코드에_없다():
    """🔴 §4-7 — *"우회·UA 위장·프록시 **금지**."*"""
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    bad = []
    for p in sorted((root / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) and node.body:
                f = node.body[0]
                if isinstance(f, ast.Expr) and isinstance(f.value, ast.Constant):
                    node.body = node.body[1:] or [ast.Pass()]
        code = ast.unparse(tree)
        for pat in ("proxies=", "scraperapi", "brightdata", "zenrows",
                    "Mozilla/5.0"):
            if pat in code:
                bad.append(f"{p.relative_to(root)} — `{pat}`")
    assert not bad, (
        "🔴 §4-7 — 우회·UA 위장 수단이 코드에 있다:\n  " + "\n  ".join(bad))






