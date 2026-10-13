"""🔴🔴 **머리 §0 — 선택 신호 기록(확률 불변)**(통합 지시서 2026-10-13 밤).

> 선택 신호 기록(확률 불변): 운영 카드마다 **|L9| 구간(상위 10% 여부)**을 저장 →
> `score_cards` **30경기마다** |L9| 상위 10% 경기의 **방향 적중률(운영 판)** 따로
> 보고. 백필 62경기에서 **51.6%**(전체 45.7%)였다 — 실전에서 유지되면 **판정
> 문턱 후보**로 올린다.

🔴 **확률 불변** — 이 구간은 **기록·보고용**이다. λ·격자·등급에 닿으면
   `test_v19_2_lineup_view.py` 와 이 파일이 함께 빨개진다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_band_threshold_is_measured_and_says_so() -> None:
    """🔴 문턱 0.945 는 **측정값**이다(630경기 · 2026-10-13) — 출처가 코드에 있다."""
    from app.core import lineupfix as lf
    assert lf.L9_TOP10 == 0.945
    said = (ROOT / "app/core/lineupfix.py").read_text(encoding="utf-8")
    assert "630" in said and "상위 10%" in said


def test_band_of_splits_at_the_threshold() -> None:
    from app.core import lineupfix as lf
    assert lf.band_of(1.2) == "상위 10%"
    assert lf.band_of(-1.2) == "상위 10%"      # 🔴 **절댓값**으로 가른다
    assert lf.band_of(0.1) == "그 밖"
    assert lf.band_of(None) == ""              # ⚠️ 못 쟀으면 **빈 글자**다


def test_card_writes_the_band() -> None:
    """🔴 카드가 그 구간을 **글자로** 적는다(`score_cards` 가 그것을 읽는다)."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "|L9| 구간" in said


def test_score_cards_reads_and_reports_the_band() -> None:
    """🔴 채점기가 그 구간을 읽고 **30경기마다** 따로 보고한다."""
    said = (ROOT / "tools/score_cards.py").read_text(encoding="utf-8")
    assert "L9_BAND" in said and "상위 10%" in said
    assert "REPORT_EVERY" in said
