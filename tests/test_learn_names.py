"""🔴🔴 **이름표 자가 성장**(③) · **후보 제시**(④) — 사용자 설계 2026-10-04.

> ③ 조건 셋: 팀 ID 밑에만 · **경기 페이지가 양 팀을 함께 확인한 경우만** ·
>   출처(경기 ID)를 남겨서 되짚어 지울 수 있게.
> ④ 후보를 보여주기만 하고 **절대 자동으로 고르지 않는다.**
>
> 자가 성장은 **오염이 조용히 쌓이는 자리**라 첫 수확을 사람이 봐야 한다.
"""
from __future__ import annotations

import pytest

from app import learn_names, teamref


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **이 파일은 한 작업자가 돈다** — 실측 2026-10-05 (병렬 전환)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ `learn_names.STORE` 는 **고정 경로**(`var/learned_names.json`)다.
#     `-n auto` 로 병렬화하자 작업자들이 그 파일을 서로 덮어 한 계약이
#     빨개졌다(`test_열쇠가_사라진_줄은_버린다`) — 순차로는 통과한다.
#  🔴 `xdist_group` 으로 **같은 작업자에 묶는다** — 파일을 공유하는 계약은
#     병렬로 나눌 수 없다. ⚠️ 경로를 임시로 돌리는 길도 있지만, 그러면
#     운영이 쓰는 그 경로를 **계약이 안 보게** 된다.
pytestmark = pytest.mark.xdist_group("learn_names")


@pytest.fixture(autouse=True)
def _clean():
    """🔴 시험이 **진짜 파일을 더럽히지 않게** — 돌기 전후로 비운다."""
    keep = learn_names.load()
    learn_names.STORE.unlink(missing_ok=True)
    yield
    learn_names.STORE.unlink(missing_ok=True)
    if keep:
        learn_names._save(keep)


def _two_known() -> tuple[str, str]:
    """이름표가 **둘 다 아는** 팀 이름 한 쌍."""
    a = teamref.label_of(teamref.key_of("Arsenal FC")[0], "en")
    b = teamref.label_of(teamref.key_of("Chelsea FC")[0], "en")
    assert a and b and a != b
    return a, b


def test_짝이_하나일_때만_배운다():
    """🔴 아는 쪽이 하나여야 나머지가 **하나로 정해진다**."""
    a, b = _two_known()
    got = learn_names.learn(asked=("모르는우리말", a), page_names=[a, b],
                            match_key="fotmob-1")
    assert len(got) == 1, got
    assert got[0]["key"] == teamref.key_of(b)[0]
    # 🔴 **출처 경기 id 가 붙는다** — 되짚어 지울 수 있어야 한다
    assert got[0]["from_match"] == "fotmob-1"


def test_둘_다_모르면_안_배운다():
    """🔴 어느 쪽인지 알 수 없다 — 거기서 고르면 그것이 추측이다."""
    a, b = _two_known()
    assert learn_names.learn(asked=("모르는하나", "모르는둘"),
                             page_names=[a, b], match_key="x-1") == []


def test_페이지_팀을_모르면_안_배운다():
    """🔴 조건 ② — **경기 페이지가 양 팀을 함께 확인한 경우만**.

    ⚠️ 한쪽을 모르면 그 팀 자체를 모르는 것이고, 그때 만들면 **반쪽짜리 팀**이 생긴다.
    """
    a, _b = _two_known()
    assert learn_names.learn(asked=("모르는우리말", a),
                             page_names=[a, "듣도보도못한FC"],
                             match_key="x-2") == []


def test_새_팀을_만들지_않는다():
    """🔴 배우기는 **별칭을 붙이는 것**이지 팀을 만드는 것이 아니다."""
    before = len(teamref.registry().teams)
    a, b = _two_known()
    learn_names.learn(asked=("모르는우리말", a), page_names=[a, b],
                      match_key="x-3")
    assert len(teamref.registry().teams) == before


def test_되짚어_지울_수_있다():
    """🔴 조건 ③ — 오염이 들어오면 **한 줄로 뺀다**."""
    a, b = _two_known()
    learn_names.learn(asked=("지울이름", a), page_names=[a, b], match_key="x-4")
    assert teamref.norm("지울이름") in learn_names.load()
    assert learn_names.forget("지울이름")
    assert teamref.norm("지울이름") not in learn_names.load()
    assert not learn_names.forget("지울이름")      # 두 번째는 False


def test_배운_것은_출처_등급이_맨_아래다():
    """🔴 사람이 적은 것보다 **낮다** — 오염이 섞이면 대표 표기부터 흔들린다."""
    assert teamref.SOURCE_ORDER[-1] == learn_names.SOURCE


def test_열쇠가_사라진_줄은_버린다():
    """🔴 `key` 가 지금 이름표에 없으면 **새로 만들지 않고 버린다**.

    ⚠️ 열쇠가 바뀌었거나 그 팀이 사라진 것이다 — 그때 만들면 반쪽짜리 팀이 생긴다.
    """
    learn_names._save({teamref.norm("유령"): {
        "name": "유령", "key": "team:999999", "from_match": "x-9", "lang": "ko"}})
    reg, whys = teamref.build()
    assert not reg.index.get(teamref.norm("유령"))
    assert any("버린 것" in w for w in whys), whys


# ══════════════════════════════════════════════════════════════════
# ④ 후보 제시 — 🔴 **고르지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_후보를_보여_주되_고르지_않는다():
    """🔴🔴 사용자 지적 2026-10-04:

    > *"거짓 사유"* 의 **반대 방향 실수**가 *"그럴듯한 후보 자동 채택"* 이다.
    """
    from app.matchref import Reason, say
    near = teamref.suggest("Manchester Cty")
    assert near and "Manchester City FC" in near
    # 🔴 **그래도 `key_of` 는 여전히 못 푼다** — 후보는 제시일 뿐이다
    assert teamref.key_of("Manchester Cty")[0] == ""
    text = say(Reason.NAME_UNRESOLVED, asked="Manchester Cty")
    assert "혹시 이것인가" in text and "고르지 않았다" in text


def test_후보는_사람이_읽는_이름이다():
    """🔴 열쇠를 돌려주면 부르는 쪽이 **그냥 쓰고 싶어진다** — 그 유혹을 없앤다."""
    for n in teamref.suggest("Bayern Munchen"):
        assert not teamref.is_code(n), n
    assert teamref.suggest("") == []
