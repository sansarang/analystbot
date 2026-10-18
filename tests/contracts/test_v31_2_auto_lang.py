"""🔴🔴 **리그 언어를 자동으로 찾는다** — 사용자 지시 2026-10-18.

> MLS 는 영어, K리그는 `ko`, J리그는 `ja`. **리그 언어를 사용하게 해라** ..
> 사용자가 물으면 **자동으로 찾아서** 하게 해라 .. **매번 오류 내지 말고**

⚠️ 실사고 2026-10-18(캔자스 vs 솔트레이크): MLS 질의가 **전부 한국어**로 나가
   ③ 문서가 1~2건이었다(영어권인데). 🔴 까닭 둘:
   ① `entities.langs_of` 가 **`ko` 별칭**(한국 사용자가 한글로 물어서 붙은 것)을
      *"그 팀 기사가 한국어"* 로 읽었다.
   ② ③(질의)과 ⑤(회상)이 **서로 다른 언어 판정**을 썼다.

세는 것:
  AL1 `ko` 별칭은 현지어 증거가 아니다 — MLS 는 영어다
  AL2 한국·일본 리그는 **리그 쪽**이 `ko`·`ja` 를 준다(그 길은 그대로다)
  AL3 나라 코드 → 언어가 **자동**이다(FIFA→ISO→CLDR · 손 목록 0)
  AL4 판정은 **한 자리**다(`langs_final`) — 나라 코드가 먼저
  AL5 나라 코드가 사실에 담긴다(`Facts.ccode`) · 배선됐다
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class _R:
    competition = "Major League Soccer"
    home_name, away_name = "Sporting Kansas City", "Real Salt Lake"
    home, away = "team:000912", "team:000913"


class _F:
    def __init__(self, cc: str = "") -> None:
        self.ccode = cc


def test_al1_ko_별칭은_현지어_증거가_아니다() -> None:
    from app import entities, queries
    # 🔴 별칭 선언에는 `ko` 가 **있다**(사용자가 한글로 묻는다)
    assert "ko" in entities.langs_of("Sporting Kansas City")
    # 🔴 그런데 검색 언어는 **영어**다 — 그 별칭을 증거로 쓰지 않는다
    got, why = queries.langs_for("Major League Soccer", "Sporting Kansas City",
                                 "Real Salt Lake")
    assert "ko" not in got, (got, why)
    assert got == ("en",), (got, why)


@pytest.mark.parametrize("league,a,b,want", [
    ("K-League 1", "Gangwon FC", "Bucheon FC 1995", "ko"),
    ("J. League", "Kashiwa Reysol", "Nagoya Grampus", "ja"),
])
def test_al2_리그_쪽_현지어는_그대로다(league, a, b, want) -> None:
    """🔴 한국·일본 리그는 **리그 색인**이 언어를 준다(별칭이 아니다)."""
    from app import queries
    got, why = queries.langs_for(league, a, b)
    assert want in got, (got, why)


@pytest.mark.parametrize("cc,want", [
    ("USA", "en"), ("ITA", "it"), ("KOR", "ko"), ("JPN", "ja"),
    ("ESP", "es"), ("GER", "de"), ("ENG", "en"), ("BRA", "pt"),
])
def test_al3_나라_코드에서_언어가_자동으로_나온다(cc, want) -> None:
    """🔴🔴 **손 목록 0** — FIFA→ISO→CLDR 가 자동으로 찾는다."""
    from app.core import autoleague as al
    rows, why = al.langs_with_why(cc)
    assert rows and rows[0] == want, (cc, rows, why)


def test_al4_판정은_한_자리다() -> None:
    """🔴 ③과 ⑤가 다른 판정을 쓰던 것을 하나로 묶었다(M12)."""
    import inspect

    from app.core.stages import s4b_gapsearch as gs
    got, why = gs.langs_final(_R(), _F("USA"))
    assert got == ["en"], (got, why)
    assert "나라 코드" in why and "자동" in why, why
    got2, why2 = gs.langs_final(_R(), _F("ITA"))
    assert got2[:2] == ["it", "en"], (got2, why2)
    # 🔴 나라 코드가 없으면 이름표 → 모델 → 영어 순서다(퇴로가 셋)
    got3, why3 = gs.langs_final(_R(), _F(""))
    assert got3, why3
    # 🔴 부르는 자리가 **그 함수 하나**다(`langs_of()` 를 직접 쓰지 않는다)
    src = inspect.getsource(gs)
    body = "\n".join(x for x in src.splitlines()
                     if not x.lstrip().startswith("#"))
    assert 'langs_of() or ["en"]' not in body, "🔴 옛 판정이 남아 있다"


def test_al5_나라_코드가_사실에_담기고_배선됐다() -> None:
    from app.core.schema import Facts
    assert "ccode" in Facts.model_fields, "🔴 `Facts.ccode` 가 없다"
    said = (ROOT / "app/core/stages/s2_facts.py").read_text(encoding="utf-8")
    assert "_ccode(raw_pages)" in said, "🔴 ② 가 나라 코드를 안 읽는다"
    assert 'box["ccode"]' in said, "🔴 사실에 안 담는다"
    said_a = (ROOT / "app/core/adapt.py").read_text(encoding="utf-8")
    assert 'ccode=str(box.get("ccode")' in said_a, "🔴 `adapt` 가 안 싣는다"
    # 🔴 읽는 함수는 `fotmob.ccode_of` 하나다(사본 금지)
    assert "fm.ccode_of(j)" in said, "🔴 나라 코드를 따로 파싱한다(사본)"
