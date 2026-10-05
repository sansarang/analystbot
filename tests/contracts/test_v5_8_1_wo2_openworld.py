"""🔴🔴 **지시서 §2 — 오픈월드 해석기.** 모르는 팀을 그 자리에서 배운다.

작업 지시서(오픈월드) §2 · 계약 **§5 M53~M56**:

> 지금 `resolve()` 는 이름표에 없으면 `name_unresolved` 로 멈춘다. 그 뒤에
> **사다리 한 단(⑥ 오픈월드)** 을 추가한다. **순서는 바꾸지 않는다** — 아는
> 팀은 지금처럼 빠르고 결정적으로 풀리고, **모를 때만** 이 단이 돈다.
>
> ⑥-1 **입력 해석**(Solar, 좁은 질문 하나) — `{teams:[{ko, latin_candidates[],
>      country_guess}], date_hint, competition_hint}` 만 받는다. **Solar 는 경기를
>      고르지 않는다 — 철자 후보만 낸다.** 도구 없음, 출력 1k 토큰 상한.
> ⑥-2 **후보 검색**(코드) — v5 §4 통로. 검색어 규칙(§4-1)은 이 단에서도 적용하되
>      **두 팀명이 요소 둘로** 센다.
> ⑥-3 **경기 페이지 확인**(코드) — (a) 두 팀 이름 일치 (b) 킥오프가 36시간 창 안
>      (c) 대회명 기록. **정확히 하나면 확정.** 둘 이상이면 후보를 사용자에게
>      보여 주고 **멈춘다.** 0개면 `openworld_not_found` + 시도한 검색어·URL.
> ⑥-4 **임시 열쇠 발급** — `provisional: true` · `learned_from` 필수, 별칭은
>      **그 번호 밑에만**.
> ⑥-5 리그·언어 — 리그는 페이지 대회명 그대로, `leagues.yaml` 에 **자동 추가
>      하지 않는다**. 언어는 `['en'] + babel_likely(country)`.

| M | 계약 | 돌연변이(빨개져야) |
|---|---|---|
| M53 | ⑥ 은 이름표 해석이 **실패했을 때만** 돈다 — 아는 팀 질문에서 Solar 호출 0회 | ⑥ 을 사다리 맨 앞으로 |
| M54 | ⑥-1 출력은 **철자 후보만** — 경기 ID·URL·날짜 확정 칸은 무시하고 로그 | Solar 의 `match_url` 을 확정에 쓰기 |
| M55 | 확정은 두 팀 일치 + 36시간 창 + 경기 **정확히 1개**. 2개 이상이면 후보 반환, **자동 선택 금지** | 첫 후보 자동 선택 |
| M56 | 임시 열쇠는 `provisional:true`·`learned_from` 필수, 별칭은 번호 밑에만 | `learned_from` 비우기 |
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

UTC = dt.timezone.utc
FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openworld"


# ══════════════════════════════════════════════════════════════════
# §5 M53 — ⑥ 은 **모를 때만** 돈다
# ══════════════════════════════════════════════════════════════════

def test_wo2_M53_사다리_맨_뒤다():
    """🔴 *"순서는 바꾸지 않는다 — 모를 때만 이 단이 돈다."*"""
    from app import openworld, resolve
    assert hasattr(resolve, "LADDER_LAST"), (
        "🔴 사다리의 **마지막 단**을 선언한 자리가 없다 — `resolve.LADDER_LAST`")
    assert resolve.LADDER_LAST == "openworld", resolve.LADDER_LAST
    assert hasattr(openworld, "read_names"), "🔴 ⑥-1 이 없다"


def test_wo2_M53_아는_팀이면_Solar_를_안_부른다():
    """🔴🔴 **M53** — 아는 팀 질문에서 **Solar 호출 0회**.

    ⚠️ 돈이 든다. 🔴 아는 팀에까지 부르면 모든 질문이 LLM 한 번을 더 쓴다.
    """
    from app import openworld
    calls = []
    ok, why = openworld.may_run(resolved_names=["Portugal", "Norway"],
                                _spy=calls)
    assert ok is False, why
    assert calls == [], f"🔴 아는 팀인데 Solar 를 불렀다: {calls}"
    # ✅ 하나라도 못 풀렸으면 돈다
    ok2, _ = openworld.may_run(resolved_names=["Portugal", ""])
    assert ok2 is True


# ══════════════════════════════════════════════════════════════════
# §5 M54 — ⑥-1 은 **철자 후보만**
# ══════════════════════════════════════════════════════════════════

def test_wo2_M54_경기_확정_칸을_무시한다():
    """🔴🔴 **M54** — Solar 가 낸 `match_url`·`match_id`·`date` 는 **버린다**.

    ⚠️ 금지 사항에 그대로 있다: *"Solar 가 낸 경기 URL·ID 로 경기를 확정하는
       것"*. 🔴 확정은 **코드의 경기 페이지 검사**만이다.
    """
    from app import openworld
    said = {
        "teams": [{"ko": "라네로스 FC", "latin_candidates": ["Llaneros"],
                   "country_guess": "CO"},
                  {"ko": "아메리카 데 칼리",
                   "latin_candidates": ["América de Cali", "America de Cali"],
                   "country_guess": "CO"}],
        "date_hint": "2026-10-05", "competition_hint": "Primera A",
        # 🔴 **모델이 넣어서는 안 되는 칸** — 넣어도 무시해야 한다
        "match_url": "https://www.fotmob.com/matches/x/1",
        "match_id": "fotmob:1", "kickoff": "2026-10-05T23:00:00Z"}
    got, dropped = openworld.parse_names(said)
    assert "match_url" not in got and "match_id" not in got, got
    assert dropped, "🔴 **버린 칸을 로그로 안 남겼다**(#3)"
    assert any("match_url" in d for d in dropped), dropped
    # ✅ 철자 후보는 남는다
    assert got["teams"][0]["latin_candidates"] == ["Llaneros"]


def test_wo2_M54_출력_상한이_1k_다():
    """🔴 *"도구 없음, 출력 1k 토큰 상한"* — ⑥-1."""
    from app import openworld
    assert openworld.MAX_OUT == 1_000, openworld.MAX_OUT
    assert openworld.TOOLS is None, (
        "🔴 ⑥-1 에 **도구를 준다** — 지시서는 *'도구 없음'* 이라고 했다")


# ══════════════════════════════════════════════════════════════════
# §5 M55 — 확정은 **정확히 하나**일 때만
# ══════════════════════════════════════════════════════════════════

def _page(home, away, kick, comp="Categoría Primera A", url="https://x/1"):
    return {"home": home, "away": away, "kickoff": kick,
            "competition": comp, "url": url}


def test_wo2_M55_정확히_하나면_확정한다():
    from app import openworld
    now = dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    pages = [_page("Llaneros", "América de Cali",
                   now + dt.timedelta(hours=10))]
    got, why = openworld.pick(pages, ["Llaneros"], ["América de Cali"],
                              now=now)
    assert got is not None, why
    assert got["competition"] == "Categoría Primera A"


def test_wo2_M55_둘_이상이면_자동_선택하지_않는다():
    """🔴🔴 **M55** — *"2개 이상이면 후보 반환, **자동 선택 금지**"*."""
    from app import openworld
    now = dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    pages = [_page("Llaneros", "América de Cali", now + dt.timedelta(hours=10),
                   url="https://x/1"),
             _page("Llaneros", "America de Cali", now + dt.timedelta(hours=30),
                   url="https://x/2")]
    got, why = openworld.pick(pages, ["Llaneros"],
                              ["América de Cali", "America de Cali"], now=now)
    assert got is None, f"🔴 **첫 후보를 자동 선택했다**: {got}"
    assert "2" in why or "둘" in why, why


def test_wo2_M55_창_밖은_확정하지_않는다():
    """🔴 (b) *"킥오프가 §window 36시간 창 안"*."""
    from app import openworld
    now = dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    pages = [_page("Llaneros", "América de Cali",
                   now + dt.timedelta(hours=50))]
    got, why = openworld.pick(pages, ["Llaneros"], ["América de Cali"],
                              now=now)
    assert got is None and ("창" in why or "지났" in why), why


def test_wo2_M55_두_팀이_다_맞아야_한다():
    """🔴 (a) *"두 팀 이름이 후보와 일치"* — 한쪽만 맞으면 남의 경기다."""
    from app import openworld
    now = dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    pages = [_page("Llaneros", "Junior", now + dt.timedelta(hours=10))]
    got, why = openworld.pick(pages, ["Llaneros"], ["América de Cali"],
                              now=now)
    assert got is None, why


def test_wo2_M55_0개면_사유와_시도를_남긴다():
    """🔴 *"0개면 `openworld_not_found` 와 **시도한 검색어·URL 목록**"*."""
    from app import openworld
    from app.reasons import Reason
    assert hasattr(Reason, "OPENWORLD_NOT_FOUND"), (
        "🔴 `Reason.OPENWORLD_NOT_FOUND` 가 없다")
    now = dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    got, why = openworld.pick([], ["Llaneros"], ["América de Cali"], now=now)
    assert got is None
    assert "0" in why or "없" in why, why


# ══════════════════════════════════════════════════════════════════
# §5 M56 — 임시 열쇠
# ══════════════════════════════════════════════════════════════════

def test_wo2_M56_임시_열쇠가_출처를_든다():
    """🔴🔴 **M56** — `provisional:true` · `learned_from` **필수**."""
    from app import openworld
    page = _page("Llaneros", "América de Cali",
                 dt.datetime(2026, 10, 5, 23, 0, tzinfo=UTC))
    rows = openworld.provision(page, ko=["라네로스 FC", "아메리카 데 칼리"],
                               latin=[["Llaneros"], ["América de Cali"]],
                               country="CO")
    assert len(rows) == 2, rows
    for r in rows:
        assert r["provisional"] is True, r
        assert r["learned_from"], (
            "🔴 `learned_from` 이 비었다 — 어느 경기에서 배웠는지 모르면 "
            "되돌릴 수도 승격할 수도 없다(M56)")
        assert r["key"].startswith("team:"), r
        assert r["league"] == "Categoría Primera A", r
        # 🔴 별칭은 **그 번호 밑에만** — 이름끼리 연결하지 않는다
        assert all(isinstance(a, str) for a in r["aliases"]), r


def test_wo2_M56_별칭에_한국어와_페이지_이름이_다_들어간다():
    """🔴 *"별칭: 경기 페이지의 팀명·외부 ID·사용자가 쓴 한국어 이름"*."""
    from app import openworld
    page = _page("Llaneros", "América de Cali",
                 dt.datetime(2026, 10, 5, 23, 0, tzinfo=UTC))
    rows = openworld.provision(page, ko=["라네로스 FC", "아메리카 데 칼리"],
                               latin=[["Llaneros", "Llaneros FC"],
                                      ["América de Cali"]], country="CO")
    a = rows[0]["aliases"]
    assert "라네로스 FC" in a and "Llaneros" in a, a


def test_wo2_M56_leagues_yaml_에_자동_추가하지_않는다():
    """🔴 ⑥-5 — *"`leagues.yaml` 에 **자동 추가하지 않는다**(사용자 결정)"*."""
    import inspect

    from app import openworld
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(openworld))
    assert "leagues.yaml" not in body, (
        "🔴 코드가 `leagues.yaml` 을 건드린다 — 리그 선언은 **사용자 결정**이다")


def test_wo2_M56_언어가_나라에서_온다():
    """🔴 ⑥-5 — *"`['en'] + babel_likely(country)`"* — 콜롬비아면 `['en','es']`."""
    from app import openworld
    assert openworld.langs_for("CO") == ["en", "es"], openworld.langs_for("CO")
    assert openworld.langs_for("") == ["en"]


# ══════════════════════════════════════════════════════════════════
# 🔴 고정물 — **실측 저장**(라이브 웹에 기대지 않는다 · 지시서 §5)
# ══════════════════════════════════════════════════════════════════

def test_wo2_고정물이_실측이다():
    p = FIX / "llaneros_pages.json"
    if not p.exists():
        pytest.skip("🔴 §6 인수 테스트에서 저장한다 — 아직 안 돌렸다")
    box = json.loads(p.read_text(encoding="utf-8"))
    assert box.get("_출처") and box.get("_받은날"), box.keys()
