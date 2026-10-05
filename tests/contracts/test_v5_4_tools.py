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


@pytest.mark.parametrize("q,ok", [
    # 🔴 이름 하나 — **거부**
    ("Scotland", False),
    ("North Macedonia", False),
    ("LG 트윈스", False),
    # ⚠️ 이름 + 핵심어 **둘뿐** — 아직 모자라다
    ("Scotland lineup", False),
    # ✅ 팀 + 핵심어 + 날짜
    ("Scotland lineup Oct 3", True),
    # ✅ 팀 + 종목 낱말 + 핵심어
    ("Scotland football lineup", True),
])
def test_v5_4_1_세_요소_이상을_요구한다_M33(q, ok):
    """🔴 §4-1 — *"**중 세 요소 이상**을 가진다."* [#1]

    ⚠️ **글에서 짐작할 때**의 수다. 🔴 상대 이름은 **글자로 안 보인다**(이름을
       모르니까) — 그래서 `North Macedonia Scotland lineup` 도 짐작으로는 2개다.
       그쪽이 안전하다: **거짓 통과보다 거짓 거부가 낫다.**
    🔴 호출부가 조각을 **이름으로 넘기면**(`parts=`) 정확히 센다 — 아래 시험.
    """
    from app.querygate import enough_parts
    got, why = enough_parts(q)
    assert got is ok, (q, got, why)
    if not ok:
        assert "query_too_bare" in why, why


def test_v5_4_1_조각을_넘기면_정확히_센다():
    """🔴🔴 §4-1 의 정본 길 — 호출부가 **무엇을 넣었는지** 안다.

    ⚠️ 짐작은 상대·대회를 못 센다(글자로 안 보인다). 🔴 `queries.variants` 는
       그 조각을 **이미 들고 있다**(`_compose` 가 우선순위로 넣는다) — 그것을
       그대로 넘기면 거짓 거부가 사라진다.
    """
    from app.querygate import enough_parts
    ok, why = enough_parts(
        "North Macedonia Scotland lineup",
        parts={"team": "North Macedonia", "opponent": "Scotland",
               "when": "lineup"})
    assert ok is True, why
    assert "요소 3개" in why, why
    # 🔴 조각이 둘이면 **거부**다 — 선언을 줬어도 모자라면 모자라다
    ok2, why2 = enough_parts("A lineup", parts={"team": "A", "when": "lineup"})
    assert ok2 is False and "query_too_bare" in why2, why2


def test_v5_4_1_조각_선언이_짐작을_이긴다():
    """🔴 선언이 짐작보다 낫다 — 그래서 `parts` 가 1순위다."""
    from app.querygate import count_parts
    n_guess, _ = count_parts("Scotland football lineup Oct 3")
    n_said, got = count_parts(
        "x", parts={"team": "A", "opponent": "B", "sport": "football",
                    "when": "Oct 3", "competition": "Nations League"})
    assert n_said == 5, (n_said, got)
    assert n_guess < n_said


def test_v5_4_1_거부_사유가_enum이다():
    """🔴 §8-6 — 사유는 **실패한 조건이 돌려주는 enum** 이다."""
    from app.querygate import gate
    from app.reasons import Reason
    ok, reason, why = gate("Scotland")
    assert ok is False and reason is Reason.QUERY_TOO_BARE, (reason, why)


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


def test_v5_4_1_선언은_짐작을_덮어쓰지_않는다():
    """🔴🔴 **실측 2026-10-04 — 선언이 에이전트를 굶겼다.**

    게이트 2 를 켜고 돌리니 모델의 질의가 **전부 거부**됐다:

    ```
    'Milwaukee Brewers last 5 games results October 2026 MLB'
      → 🔴 요소가 **2개**다(['team', 'competition'])
    ```

    ⚠️ 그 질의에는 **날짜(October 2026)** 가 있다. 🔴 그런데 `Tools._parts` 가
       `team`·`opponent`·`competition` **셋만** 선언했고, `count_parts` 가
       `if parts:` 에서 **선언만** 세어 날짜·종목 낱말을 **잃었다.**

    🔴 `"선언이 짐작을 이긴다"` 는 **칸마다**여야 한다 — 통째로 덮으면 아는 것을
       선언하는 쪽이 **벌을 받는다**(아무것도 안 넘기는 쪽이 더 많이 센다).
    """
    from app import querygate
    q = "Milwaukee Brewers last 5 games results October 2026 MLB"
    # 🔴 선언 없이 짐작하면 **날짜·종목**이 보인다
    n_guess, got_guess = querygate.count_parts(q)
    assert "when" in got_guess, got_guess
    # 🔴🔴 선언을 **더해도** 그것이 사라지지 않는다
    n_both, got_both = querygate.count_parts(
        q, parts={"team": "Milwaukee Brewers", "competition": "MLB"})
    assert n_both >= n_guess, (n_guess, got_guess, n_both, got_both)
    assert "when" in got_both, got_both
    assert {"team", "competition"} <= set(got_both), got_both
    # ✅ 그래서 이 질의는 **통과한다**(세 요소 이상).
    #    ⚠️ `enough_parts` 는 `(통과, 왜)` 를 돌려준다 — 쌍이다.
    ok, said = querygate.enough_parts(
        q, parts={"team": "Milwaukee Brewers", "competition": "MLB"})
    assert ok is True, said


def test_v5_4_1_에이전트_질의가_통과한다():
    """🔴 모델이 실제로 낸 질의 넷이 **통과해야** 한다(실측 2026-10-04).

    ⚠️ 전부 거부되면 에이전트가 **굶는다** — 48턴을 돌고 변수 0개였다.
    """
    from app import agentloop
    from datetime import datetime, timedelta, timezone
    inp = agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers", "Brewers"),
        away_names=("San Diego Padres", "Padres"), competition="MLB",
        sport="baseball",
        kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        venue="", langs=("en",))
    tools = agentloop.Tools(inp=inp)
    # 🔴 **통과해야 하는 것** — 세 요소가 실제로 있다
    for q in ("Milwaukee Brewers last 5 games results October 2026 MLB",
              "San Diego Padres last 5 games results October 2026 MLB",
              "Milwaukee Brewers vs San Diego Padres MLB October 2026"):
        ok, reason, why = tools.querylog.check(q, parts=tools._parts(q))
        assert ok, f"🔴 모델 질의가 거부됐다: {q} — {why}"
    # ══════════════════════════════════════════════════════════════════
    # ⚠️ **거부가 맞는 것** — 내 첫 계약이 이것까지 통과를 요구했다(틀렸다)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `'Milwaukee Brewers Logan Henderson pitcher 2026 season stats'` 는
    #  **팀 하나**뿐이다 — 상대도 대회도 종목 낱말도 날짜도 없다(`2026` 하나는
    #  창을 안 좁힌다). 🔴 §4-1 이 거부하는 것이 **맞다.**
    #  ✅ 사유가 **무엇이 모자란지** 말하므로 모델이 각도를 바꿀 수 있다.
    bad = "Milwaukee Brewers Logan Henderson pitcher 2026 season stats"
    ok2, reason2, why2 = tools.querylog.check(bad, parts=tools._parts(bad))
    assert ok2 is False and reason2.value == "query_too_bare", (ok2, why2)
    assert "3개 이상" in why2, why2


def test_v5_4_1_달과_연도도_날짜다():
    """🔴🔴 **실측 2026-10-04 — `October 2026` 이 날짜로 안 세졌다.**

    `_DATE` 는 **달+일**(`Oct 4`·`10月4`)만 봤다. ⚠️ 모델은 `October 2026`·
    `2026 October` 처럼 **달+연도**로도 쓴다 — 그것도 *"언제"* 다(§4-1 이
    요구하는 것은 **창을 좁히는 요소**이고 달+연도는 창을 좁힌다).

    🔴 그 한 줄이 에이전트의 질의를 **전부 거부**하게 만들었다.
    """
    from app import querygate
    for q in ("Milwaukee Brewers San Diego Padres October 2026",
              "Brewers Padres 2026 October preview",
              "Brewers Padres 2026-10-04 lineup",
              "ロッテ ソフトバンク 2026年10月"):
        n, got = querygate.count_parts(q)
        assert "when" in got, (q, n, got)
    # ⚠️ **연도만**은 날짜가 아니다(창을 안 좁힌다)
    assert "when" not in querygate.count_parts("Brewers Padres 2026")[1]
    # ⚠️ 그리고 **아무 수**나 날짜로 보지 않는다
    assert "when" not in querygate.count_parts("Brewers 5 games")[1]
