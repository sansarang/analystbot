"""🔴🔴 **v5 §4-2 — 언어는 Babel 이 준다** · **§3-5 초안은 입력일 뿐이다**.

§4-2 원문:

> `langs = ['en'] + babel_likely(team.country)`. Babel 의 **likely-subtag**
> (`Locale.parse('und_HR')` → `hr`)로 나라→언어를 **자동으로** 얻는다. 다국어
> 나라(CH·BE·CA 등)만 `config/langs_override.yaml`. 클럽은 리그의 현지어
> (J리그 ja, KBO ko…). 리그가 미상이면 팀의 나라. **한국어 질문은 입력에만 쓰고
> 검색어에는 팀 현지어·영어만** 쓴다(한국어 매체는 KBO·K리그·대표팀일 때만).

§3-5 원문:

> 가설·시나리오는 에이전트가 쓴다, **그러나 코드가 다시 만든다.** 에이전트
> 초안은 §6-2 의 자동 보강(필수형 추가·단일 방향 금지) **입력일 뿐이다.**
> 초안에 없는 필수형은 코드가 템플릿으로 추가하고 `added_by:code` 를 단다.

══════════════════════════════════════════════════════════════════
🔴 왜 Babel 인가 — **손으로 적으면 늘 모자란다**
══════════════════════════════════════════════════════════════════

⚠️ 사용자 지적 2026-10-04: *"C는 손으로 안 적어도 된다"* — 나라→언어는 **CLDR**
   이 이미 안다. 🔴 손으로 적은 표는 54개 대표팀 중 몇 개만 덮는다.
"""
from __future__ import annotations

import pytest


def test_v5_4_2_babel_이_나라에서_언어를_준다():
    """🔴 `Locale.parse('und_HR')` → `hr`. ⚠️ 우리가 적지 않는다."""
    from app import queries as language
    assert language.babel_likely("HR") == "hr"
    assert language.babel_likely("JP") == "ja"
    assert language.babel_likely("KR") == "ko"
    assert language.babel_likely("MK") == "mk"
    # 🔴 **모르는 나라는 빈 문자열**이다(지어내지 않는다)
    assert language.babel_likely("ZZ") == ""
    assert language.babel_likely("") == ""


def test_v5_4_2_영어가_늘_먼저다():
    """🔴 *"`langs = ['en'] + babel_likely(...)`"* — 영어가 **앞**이다."""
    from app import queries as language
    got = language.langs_from_country("HR")[0]
    assert got[0] == "en", got
    assert "hr" in got, got
    # ⚠️ 같은 언어를 두 번 넣지 않는다
    assert len(got) == len(set(got)), got


def test_v5_4_2_다국어_나라만_선언으로_덮는다():
    """🔴 *"다국어 나라(CH·BE·CA 등)만 `config/langs_override.yaml`"*.

    ⚠️ 그 파일이 **작아야** 한다 — 커지면 Babel 을 안 쓰고 손으로 적는 것이다.
    """
    from app import queries as language
    over = language.lang_overrides()
    assert over, "🔴 다국어 나라 선언이 비었다"
    # 🔴 스위스는 하나가 아니다
    assert len(over.get("CH") or []) >= 2, over.get("CH")
    # ⚠️ **스물 미만**이어야 한다(그 이상이면 손으로 적는 것이다)
    assert len(over) < 20, f"🔴 선언이 {len(over)}개다 — Babel 을 쓰지 않고 있다"


def test_v5_4_2_이름표_접두를_떼어_읽는다():
    """🔴 이름표는 `iso:HR`·`fa:SCO` 로 적는다 — **두 글자만** Babel 이 안다.

    ⚠️ 실측 2026-10-04: 내 첫 판이 `und_ISO:HR` 를 사유에 적었다(글자는
       맞았지만 **거짓 사유**였다 — Babel 에 들어간 것은 `HR` 이다).
    🔴 `fa:SCO`(FIFA 세 글자)는 **못 읽는다** — 그 사실이 사유에 남는다.
    """
    from app import queries
    assert queries.country_code("iso:HR") == "HR"
    assert queries.country_code("fa:SCO") == ""
    assert queries.country_code("") == ""
    got, why = queries.langs_from_country("fa:SCO")
    assert got == ["en"]
    assert "FIFA" in why or "못 읽었다" in why, why


def test_v5_4_2_대표팀이_선언_없이_현지어를_얻는다():
    """🔴🔴 **54개 대표팀이 한 길로 덮인다** — 손으로 적은 적이 없다.

    ⚠️ 종전에 이 자리는 **영어만**으로 끝났다(*"그 팀 기사가 현지어로만 나오면
       못 찾는다"*). 🔴 나라는 이름표가 알고, 나라→언어는 CLDR 이 안다.
    """
    from app import queries
    for team, want in (("Croatia", "hr"), ("North Macedonia", "mk")):
        got, why = queries.langs_for("Friendlies", team)
        assert got[0] == "en" and want in got, (team, got, why)
        assert "Babel" in why, why


def test_v5_4_2_한국어는_검색어에_안_쓴다():
    """🔴🔴 *"한국어 질문은 입력에만 쓰고 검색어에는 팀 현지어·영어만"*.

    ⚠️ 실측 2026-10-04(밀워키 vs 샌디에이고): 카탈로그 템플릿이 **한국어**라
       *"건너뜀 — 템플릿 언어 `ko` 가 이 경기 언어 ['en'] 에 없다"* 가 다섯 줄
       나왔다. 🔴 그것이 **맞는 동작**이다.
    """
    from app import queries as language
    # 🔴 MLB 팀에 한국어가 **없다**
    got, _ = language.langs_for("MLB", "Milwaukee Brewers")
    assert "ko" not in got, got
    # ✅ KBO 는 한국어다(지시문이 이름 댔다)
    kbo, _ = language.langs_for("KBO", "LG Twins")
    assert "ko" in kbo, kbo


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_v5_3_5_초안은_입력일_뿐이다`

def test_v5_3_5_초안이_없어도_코드가_만든다():
    """🔴 초안이 **0개**여도 코드는 할 일을 한다(그 사실을 사유로 남긴다)."""
    from app import scenarios
    res = scenarios.Result()
    scenarios.require_set(res, _game(), [_var(), _var("x", "away")])
    assert res.incomplete is True
    assert any("최소" in w for w in res.incomplete_why), res.incomplete_why


@pytest.mark.parametrize("country", ["CH", "BE", "CA"])
def test_v5_4_2_지시문이_이름_댄_나라가_선언에_있다(country):
    """🔴 §4-2 가 **이름으로 댄** 셋. ⚠️ 빠지면 그 나라 검색이 한 언어로 돈다."""
    from app import queries as language
    assert country in language.lang_overrides(), language.lang_overrides()


def _game(sport: str = "soccer"):
    from app import classify
    return classify.Game(home="A", away="B", sport=sport, league="L")


def _var(vtype: str = "recent_pattern", direction: str = "home"):
    from app import classify
    return classify.Classified(
        text=f"{vtype} 사실", source_url="https://x/y", hardness="hard",
        type=vtype, direction=direction, team="A", why="§4")


def test_v5_4_2_접두를_떼지_않으면_못_읽는다():
    """🔴🔴 **돌연변이 B 가 통과했다**(2026-10-04).

    `babel_likely` 에서 `country_code` 를 빼도 **초록이었다** — 내 계약이
    `country_code` 를 **직접만** 시험하고 `babel_likely("iso:HR")` 를 안 넣어
    봤다. 🔴 그 둘이 이어져 있어야 이름표 꼴이 Babel 에 닿는다.
    """
    from app import queries
    # 🔴 **이름표 꼴 그대로** 넣는다(그것이 실제로 오는 모양이다)
    assert queries.babel_likely("iso:HR") == "hr"
    assert queries.babel_likely("iso:JP") == "ja"
    # ⚠️ 세 글자 FIFA 코드는 **못 읽는다**(그 사실이 뜻이다)
    assert queries.babel_likely("fa:SCO") == ""
    assert queries.babel_likely("ISO:MK") == "mk"


def test_v5_4_2_다국어_나라도_영어가_먼저다():
    """🔴🔴 **돌연변이 C 가 통과했다**(2026-10-04).

    다국어 선언 경로에서 `["en"] +` 를 지워도 **초록이었다** — 내 계약이
    `langs_from_country("HR")`(Babel 경로)만 순서를 봤고 **선언 경로**는
    안 봤다.
    🔴 §4-2 원문이 `langs = ['en'] + …` 다 — 영어가 **공통**이고 예산(검색
       3회)을 쓰는 순서가 그 순서여야 한다(사용자 지시 2026-10-02).
    """
    from app import queries
    for cc in sorted(queries.lang_overrides()):
        got, why = queries.langs_from_country(cc)
        assert got and got[0] == "en", (cc, got, why)
        # ⚠️ 같은 언어를 두 번 넣지 않는다
        assert len(got) == len(set(got)), (cc, got)

