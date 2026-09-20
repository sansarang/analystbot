"""[LGA-1b / STEP 1-i-1b] 기능 플래그의 **역방향 잠금.**

🔴 `features` 는 "덜 켜는" 장치다. 그런데 반대 방향이 비어 있었다 —
   **판정·라우터가 켜져 있는데 결과 적재가 없는 리그**를 아무도 막지 않는다.
   그런 리그는 판정을 하고 카드를 낼 수 있지만 **영원히 채점되지 않는다.**
   실측 2026-09-20: ACL 8건이 정확히 그 상태였다(판정 8 · 채점 0 · 결과 0).

🔴 "작동"의 정의는 **설정**이다 — `fd_names` 가 비어 있지 않거나 `fotmob_id`
   가 있으면 적재 경로가 있는 것이다.
   ⚠️ DB 행 수를 보지 않는다. 테스트가 DB 상태에 의존하면 그날그날 달라진다.
"""
from __future__ import annotations

import pytest

from app.leagues import LEAGUES, features_of

#: 결과 적재가 **없는** 채로 판정·라우터가 켜진 리그. 🔴 고치는 것은 1-i-2 다.
#  ⚠️ 이 목록이 비어야 1-i-2 가 닫힌다 — xfail 이 남은 채로 닫지 않는다.
_PENDING = {"j1", "denmark", "kleague1", "acl"}


def _has_result_source(key: str) -> bool:
    """그 리그에 결과를 넣을 **경로가 설정돼 있나.**

    🔴 설정만 본다(지시 1-i-1b). `fd_names` → football-data ·
       `fotmob_id` → FotMob(1-i-2 가 추가한다).
    """
    cfg = LEAGUES.get(key) or {}
    return bool(cfg.get("fd_names")) or bool(cfg.get("fotmob_id"))


@pytest.mark.parametrize("key", sorted(LEAGUES))
def test_judge_requires_results(key, request):
    """🔴 판정·라우터를 켰으면 **결과 적재도 켜져 있어야** 한다.

    안 그러면 그 리그는 판정만 쌓이고 **영원히 채점되지 않는다.**
    """
    if key in _PENDING:
        request.node.add_marker(pytest.mark.xfail(
            reason="1-i-2 에서 fotmob_id 로 해소", strict=True))
    feats = set(features_of(key))
    if not (feats & {"judge", "router"}):
        return                      # 결과만 켠 리그는 대상이 아니다
    assert "results" in feats, f"{key}: 판정/라우터가 켜졌는데 results 가 없다"
    assert _has_result_source(key), \
        f"{key}: results 가 켜졌는데 적재 경로(fd_names·fotmob_id)가 없다"


def test_pending_목록이_비면_1i2가_닫힌다():
    """⚠️ 1-i-2 완료 조건 — 이 목록이 비어야 한다.

    비었는데 이 테스트가 남아 있으면 **지우라는 신호**다(xfail 도 함께).
    """
    still = {k for k in _PENDING if not _has_result_source(k)}
    assert still == _PENDING, (
        f"해소된 리그가 있다 — _PENDING 에서 빼고 xfail 을 떼라: {_PENDING - still}")
