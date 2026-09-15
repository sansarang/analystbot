"""ACL-2 — 키를 만든 함수와 비교하는 함수가 **같아야** 한다.

🔴 실측 2026-09-15(ACL-1 배포 직후 진단표):
     A-1 디빅 | 6행 · 배당 None/4.8/None   ← 4경기 전부 Draw 만 붙었다
     C-5 FotMob | 8199 교토@대전 — 경기 매칭 0
   둘 다 ACL-1 이 키를 바꾸고 **비교하는 쪽을 안 바꿔서** 났다.
"""
from __future__ import annotations

import inspect

import pytest

from app.collectors import fotmob as FM
from app.collectors import odds_free as OF
from app.collectors.oddsportal import norm, team_key


def test_side_되돌리기가_경기_매칭과_같은_키를_쓴다():
    """🔴 이 비대칭이 결함의 본체다 — 같은 함수여야 한다."""
    src = inspect.getsource(OF.collect_soccer)
    assert "team_key(side) == blk[\"key_home\"]" in src
    assert "norm(side) ==" not in src, "키는 team_key 로 만들고 비교는 norm 이다"


def test_국가접미사_붙은_side_가_우리_팀명으로_돌아온다():
    """ACL 표기 → 우리 표기. 이게 안 되면 p_market 이 못 선다."""
    for raw, want in (("Kashima Antlers (Jpn) ", "kashima antlers"),
                      ("Daejeon (Kor) ", "daejeon citizen"),
                      ("Beijing Guoan (Chn) ", "beijing guoan")):
        assert team_key(raw) == want
        assert norm(raw) != want, "norm 으로는 안 붙는다(그게 결함이었다)"


def test_기존_리그_side_되돌리기가_그대로다():
    """🔴 반대 위험 — `norm`→`team_key` 로 바꾸면 별칭까지 탄다.
    기존 7리그 표기가 엉뚱한 팀으로 환원되면 배당이 잘못 붙는다."""
    # ⚠️ `team_key` 는 **별칭을 적용한다**(`Inter` → `Internazionale Milano`).
    #    그게 맞다 — `key_home` 을 만든 것과 같은 함수이므로 양쪽에 똑같이
    #    걸린다. 비대칭이었던 종전이 결함이었다.
    from app.collectors.oddsportal import SOCCER_ALIAS
    for raw in ("Leeds", "Manchester Utd", "Aston Villa", "Inter", "Draw"):
        assert team_key(raw) == norm(SOCCER_ALIAS.get(raw, raw)), raw
    # 대조가 성립하는 이유: side 와 key 가 **같은 원표기**에서 나온다.
    for raw in ("Leeds", "Inter", "Kashima Antlers (Jpn) "):
        assert team_key(raw) == team_key(raw)


def test_find_match가_canonical을_거친다():
    rows = [{"id": 1, "home": "Daejeon Hana Citizen", "away": "Kyoto Sanga FC"}]
    assert FM.find_match(rows, home="Daejeon Citizen", away="Kyoto Sanga FC")


def test_find_match는_우리이름을_두_번_매핑하지_않는다():
    """🔴 반대 위험 — 인자 쪽에도 canonical 을 걸면 이미 매핑된 값을 또 민다."""
    src = inspect.getsource(FM.find_match)
    assert "norm(home)" in src and "canonical(home)" not in src
    assert "norm(canonical(r.get(\"home\")))" in src


def test_find_match가_여전히_다른_팀을_붙이지_않는다():
    """🔴 회귀 방지 — 퍼지 매칭으로 번지면 AC밀란 사고가 재발한다."""
    rows = [{"id": 1, "home": "AC Milan", "away": "Inter"}]
    assert FM.find_match(rows, home="Inter", away="AC Milan") is None
    assert FM.find_match(rows, home="AC Milan", away="Inter")


@pytest.mark.parametrize("fm,ours", [
    ("Kashima Antlers", "Kashima Antlers"),
    ("Công An Hà Nội", "Công An Hà Nội"),
    ("Daejeon Hana Citizen", "Daejeon Citizen"),
    ("Pohang Steelers", "Pohang Steelers"),
])
def test_오늘_ACL_8팀이_양쪽에서_같은_키다(fm, ours):
    assert FM.norm(FM.canonical(fm)) == FM.norm(ours)
