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




