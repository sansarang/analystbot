"""🔴🔴 **검색어 구성 규칙** — 사용자 수정 ①②③ (2026-10-04).

> 검색어 구성 규칙: `{팀} {상대} {대회명} {종목 낱말} {날짜}` — **나라 이름
> 하나짜리 검색어는 계약으로 금지.** 종목 낱말은 어댑터 `SPORT` 에서, 대회명은
> 슬레이트 행에서, 언어는 Babel likely-subtag 에서.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (북마케도니아 vs 스코틀랜드)
══════════════════════════════════════════════════════════════════

```
Scotland lineup Oct 3   → rottentomatoes.com/tv/succession/… **드라마 출연진** ×8
                          rugby.com.au · florugby.com · skysports.com/rugby-league ×15
North Macedonia lineup  → wiki/{Economy_of_, Flag_of_, naming_dispute}(18만 자)
                          5sim.net(SMS 판매) · telfa.law(법률) · tripadvisor(호스텔)
```
→ 쓰레기 **76건**을 열었고 LLM 60초가 타서 **진짜 프리뷰에 0초**가 남았다.

⚠️ 사용자 규칙의 다섯 조각은 **9낱말**이고 §12-b 상한(6)을 넘는다. 던져서 쟀다
   (`app/queries.PIECE_ORDER` 머리글의 표) — **대회명·날짜를 넣으면 나빠진다.**
   🔴 그래서 우선순위는 `팀 → what → 상대 → 종목 → 날짜` 다.
"""
from __future__ import annotations

from datetime import date

import pytest

from app import queries, rules

DAY = date(2026, 10, 3)


# ══════════════════════════════════════════════════════════════════
# ① 나라 이름 하나짜리 질의 금지
# ══════════════════════════════════════════════════════════════════


def test_대표팀_질의에_상대와_종목이_들어간다():
    """🔴 **계약으로 금지** — 나라 이름 하나로는 안 던진다."""
    got = queries.variants(
        team="North Macedonia", league="UEFA Nations League B Grp. 1", day=DAY,
        what={"en": "lineup"}, opponent="Scotland", sport="soccer",
        langs=("en",))
    assert got, "질의가 0건이면 이 계약은 아무것도 안 본다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **상대는 전부**, 종목 낱말은 **적어도 주 축에**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 여섯 낱말 예산에서 모든 축이 다섯 조각을 다 담을 수는 없다. 그래서
    #     계약은 *"조각이 다 들어갔나"* 가 아니라 **실제 안전 속성**을 본다:
    #
    #  🔴 **상대가 있으면 그 질의는 나라 이름 하나짜리가 아니다** — 그것이 금지
    #     대상이었다. `Scotland` 와 `North Macedonia` 를 **함께** 가진 페이지는
    #     럭비도 드라마 출연진도 아니다(실측: 쓰레기 76건 전부 한쪽만 가졌다).
    #  ⚠️ `시점:전날` 축은 **날짜가 요점**이라(전날 예고 기사) 종목을 버린다 —
    #     그 축에 날짜가 없으면 `lang:` 축과 똑같아져 중복으로 사라진다.
    for v in got:
        assert "Scotland" in v.text, (
            f"🔴 상대가 없다 — **나라 이름 하나짜리 질의**다: {v.text!r} "
            f"(사용자 계약 2026-10-04)")
    assert any("football" in v.text or "soccer" in v.text for v in got), (
        f"🔴 어느 축에도 종목 낱말이 없다 — 실측 +24%: {[v.text for v in got]}")


def test_클럽은_종목_낱말을_안_넣는다():
    """🔴 실측: 클럽에 종목 낱말을 붙이면 **−22%** 다(`LG 트윈스` 는 럭비가 아니다).

    ⚠️ 그리고 6낱말 예산을 먹어 **상대**가 밀려 나간다 — 상대가 +100% 다.
    """
    got = queries.variants(team="LG Twins", league="KBO", day=DAY,
                           what={"ko": "선발 라인업", "en": "lineup"},
                           opponent="Kia Tigers", sport="baseball",
                           langs=("ko", "en"))
    assert got
    assert not any("야구" in v.text or "baseball" in v.text for v in got), [
        v.text for v in got]
    # 🔴 대신 **상대**가 들어간다
    assert any("Kia" in v.text or "기아" in v.text for v in got), [
        v.text for v in got]


def test_모든_질의가_여섯_낱말_상한을_지킨다():
    """§12-b. 🔴 상한은 `llm.query_ok` **하나**가 정한다(사본 금지)."""
    from app import llm
    for kw in ({"team": "North Macedonia", "opponent": "Scotland",
                "sport": "soccer", "langs": ("mk", "en")},
               {"team": "LG Twins", "opponent": "Kia Tigers",
                "sport": "baseball", "langs": ("ko", "en")}):
        got = queries.variants(league="KBO", day=DAY,
                               what={"en": "lineup", "ko": "선발 라인업",
                                     "mk": "состав"}, **kw)
        for v in got:
            assert llm.query_ok(v.text), f"🔴 상한을 넘었다: {v.text!r}"


def test_버린_조각을_이름으로_남긴다():
    """#3 조용한 0 금지 — **무엇을 왜 안 넣었나**가 축 이름에 남는다."""
    got = queries.variants(
        team="North Macedonia", league="x", day=DAY, what={"en": "lineup"},
        opponent="Scotland", sport="soccer", langs=("en",))
    axes = " ".join(v.axis for v in got)
    assert "버림:" in axes, axes


# ══════════════════════════════════════════════════════════════════
# 🔴 날짜가 **그 언어로** 적히나 (모르는 언어에 한국어를 붙이던 자리)
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("lang,want", [
    ("ja", "10月3日"), ("zh", "10月3日"), ("en", "Oct 3"), ("ko", "10월 3일"),
])
def test_실측한_네_언어의_날짜_꼴은_그대로다(lang, want):
    """⚠️ 이 넷은 **검색엔진에 던져 고른 꼴**이다 — Babel 로 바꾸지 않는다."""
    assert queries.month_day(DAY, lang) == want


def test_모르는_언어에_한국어_날짜를_붙이지_않는다():
    """🔴 실측 2026-10-04: `… фудбал **3일**` 이 나갔다 — 한국어다."""
    got = queries.month_day(DAY, "mk")
    assert "월" not in got and "일" not in got, got
    # 🔴 Babel 이 **그 언어의 순서까지** 준다(`3 окт.`)
    assert "окт" in got, got


def test_못_적는_언어는_빈_칸이다():
    """🔴 지어내지 않는다 — 빈 칸이면 `_compose` 가 그 조각을 안 넣는다."""
    assert queries.month_day(DAY, "존재하지않는언어") == ""


# ══════════════════════════════════════════════════════════════════
# ③ 도메인 등급표 · 타종목
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("url", [
    "https://www.rottentomatoes.com/tv/succession/s02/e08/cast-and-crew",
    "https://5sim.net/countries/northmacedonia",
    "https://www.telfa.law/juridictions/north-macedonia/",
    "https://www.tripadvisor.com/ShowUserReviews-g295110-x.html",
])
def test_스포츠가_아닌_호스트는_거부한다(url):
    """🔴 실측 2026-10-04 에 **실제로 열린** 주소들이다."""
    assert rules.not_sport_host(url), url


@pytest.mark.parametrize("url", [
    "https://www.rugby.com.au/wallabies/match-centre/3/2023/93125",
    "https://www.florugby.com/articles/15408451-scotland-vs-england-lineups",
    "https://www.skysports.com/rugby-league/australia-vs-scotland/teams/45299",
    "https://www.bbc.com/sport/rugby-union/live/c2kpgqwd8djt",
])
def test_다른_종목_페이지는_거부한다(url):
    """🔴 스코틀랜드는 **럭비 국가**다 — 15건이 열렸다."""
    assert rules.other_sport(url, "soccer"), url


@pytest.mark.parametrize("url", [
    "https://www.sportsmole.co.uk/football/macedonia/uefa-nations-league/x.html",
    "https://www.theguardian.com/football/live/2026/oct/03/north-macedonia-v-scotland",
])
def test_축구_기사는_통과한다(url):
    assert not rules.not_sport_host(url) and not rules.other_sport(url, "soccer")


def test_우리_종목_낱말이_함께_있으면_안_버린다():
    """⚠️ 종합 매체는 한 기사에 `football` 과 `rugby` 를 같이 적는다."""
    assert not rules.other_sport(
        "https://www.bbc.com/sport/football/articles/x", "soccer",
        title="Rugby and football round-up")


def test_종목을_모르면_막지_않는다():
    """🔴 `queries.asks` 와 같은 처분 — 모른다고 전부 거부하면 새 종목이 벙어리다."""
    assert not rules.other_sport("https://www.rugby.com.au/x", "")


# ══════════════════════════════════════════════════════════════════
# ② 본문 상한
# ══════════════════════════════════════════════════════════════════


def test_본문_상한이_선언돼_있다():
    """🔴 *"본문 5만 자 이상은 안 받는다(위키 18만 자가 예산을 먹었다)."*"""
    from app import cells
    assert cells.EXTRACT_MAX_CHARS == 50_000
    assert cells.EXTRACT_MIN_CHARS < cells.EXTRACT_MAX_CHARS


def test_상한을_넘는_본문은_추출을_안_부른다():
    """🔴 구조 계약 — `_extract` 안에 그 분기가 **있나**."""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "cells.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    used = {ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Compare)}
    assert any("EXTRACT_MAX_CHARS" in u and ">" in u for u in used), (
        "🔴 `EXTRACT_MAX_CHARS` 를 **비교하는 곳이 없다** — 상수만 두면 "
        "없는 코드보다 나쁘다(CLAUDE.md #2 배선)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **현지 표기는 쪽에 따라 뒤집힌다**(실측 2026-10-04)
# ══════════════════════════════════════════════════════════════════


def test_원정_세포에서_상대가_자기_자신이_되지_않는다():
    """🔴 실측 로그 원문: `Scotland manager said **Scotland** фудбал`.

    `game["local"]`·`game["opponent_local"]` 은 **홈 기준**으로 담긴다
    (`ref.home_local`·`ref.away_local`). ⚠️ 원정 팀 세포가 그대로 쓰면 상대가
    자기 자신이 된다 — 그 질의는 아무 데도 없는 문자열이다.

    🔴 구조 계약이다 — `gather` 안에서 `game.get("opponent_local")` 을 **직접**
       쓰면 빨개진다. 쪽을 가린 `other_local` 을 써야 한다.
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "analyze.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    gather = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "gather")
    bad = []
    for node in ast.walk(gather):
        if not isinstance(node, ast.Call):
            continue
        if ast.unparse(node.func) != "game.get":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value in ("local", "opponent_local"):
            bad.append(f"analyze.py:{node.lineno} — {ast.unparse(node)}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **0 이다** — 돌연변이가 이 계약을 한 번 통과했다(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  첫 판은 `allowed = 2` 였다 — *"`my_local`·`other_local` 을 만드는 두 줄은
    #  허용한다"* 는 생각이었다. 🔴 그런데 그 두 줄은 **삼항식**이라
    #  (`game.get("local" if side == "home" else "opponent_local")`) `args[0]` 가
    #  `Constant` 가 아니고 `IfExp` 다 — 이 검사에 **애초에 안 걸린다.**
    #  ⚠️ 그래서 실제 적발 수는 **0** 이었고, `<= 2` 는 **공허한 참**이었다.
    #     돌연변이(상수 접근을 하나 되돌림 → 적발 1)가 그대로 통과했다.
    #  🔴 상수로 꺼내는 자리는 **한 곳도 없어야** 한다. 쪽을 가린 이름을 쓴다.
    assert not bad, (
        "🔴 `gather` 가 홈 기준 현지 표기를 **상수로** 꺼낸다 — 원정 세포에서 "
        "뒤집힌다(실측 2026-10-04: `Scotland manager said Scotland`):\n  "
        + "\n  ".join(bad))


def test_쪽을_가린_이름이_실제로_있다():
    """🔴 위 계약은 *"상수로 안 꺼낸다"* 만 본다 — **대신 무엇을 쓰나**를 본다.

    ⚠️ 둘을 함께 걸어야 한다: 상수 접근만 금지하면 `local` 을 **아예 안 쓰는**
       코드도 초록이 되고, 그러면 현지 표기가 통째로 빠진 것을 못 잡는다.
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "analyze.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    gather = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "gather")
    assigned = {t.id for n in ast.walk(gather) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    for name in ("my_local", "other_local"):
        assert name in assigned, (
            f"🔴 `{name}` 이 `gather` 에 없다 — 쪽을 가린 현지 표기가 사라졌다")
    used = {n.id for n in ast.walk(gather) if isinstance(n, ast.Name)}
    assert {"my_local", "other_local"} <= used
