"""🔴🔴 **P3 — 감독 원천 고정**(후속 지시 2026-10-13 밤 6번).

> 감독은 **경기 페이지 `isCoach`** 를 우선 원천으로 한다(팀 페이지 이력 행
> 금지). 둘이 다르면 경기 페이지 채택 + 🟡 기록.

🔴 **CH1** 경기 페이지의 `isCoach` 줄을 쓴다 · **CH2** `isCoach: false` 는 **안
   쓴다** · **CH3** 팀 페이지 `coachHistory` 는 **대조용**이고 감독 칸이 아니다 ·
   **CH4** 실사고(베이징 궈안)가 코드에 사유로 적혀 있다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ch1_match_page_is_the_source() -> None:
    from app.collect import fotmob as fm
    got = fm._coach({"coach": {"name": "Nick Montgomery", "isCoach": True,
                               "primaryTeamId": 4177}})
    assert got == "Nick Montgomery"
    assert fm._coach({"coach": "Mark Jackson"}) == "Mark Jackson"


def test_ch2_not_a_coach_is_dropped() -> None:
    from app.collect import fotmob as fm
    assert fm._coach({"coach": {"name": "누군가", "isCoach": False}}) is None


def test_ch3_history_row_is_only_for_comparison() -> None:
    from app.collect import fotmob as fm
    page = {"props": {"pageProps": {"fallback": {"team-4177": {"history": {
        "coachHistory": [
            {"name": "Ricardo Soares", "season": "2024",
             "leagueName": "Super League", "win": 16, "draw": 8, "loss": 6},
            {"name": "Ramiro Amarelle", "season": "2025",
             "leagueName": "Super League", "win": 2, "draw": 0, "loss": 2}]}}}}}}
    name, why = fm.coach_history_last(page, 4177)
    assert name == "Ramiro Amarelle"
    assert "현재 감독 칸이 아니다" in why and "2025" in why


def test_ch4_incident_is_written_down() -> None:
    said = (ROOT / "app/collect/fotmob.py").read_text(encoding="utf-8")
    assert "Ramiro Amarelle" in said and "isCoach" in said
    assert "팀 페이지 이력 행 금지" in said or "이력 행" in said
