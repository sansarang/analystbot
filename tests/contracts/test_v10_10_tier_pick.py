"""🔴🔴 **여자팀·2군이 재료로 섞이는 것을 막는다** — 사용자 지시 2026-10-12.

⚠️ 실사고 2026-10-11: fotmob 색인이 **같은 슬러그를 두 번** 준다
   (`crystal-palace` → 614828 여자팀 · 9826 남자팀 · `strasbourg` 도 같다).
   `TIER_WORDS` 는 슬러그 낱말로 가르므로 **못 걸렀고**, `hits[0]` 이 여자팀이라
   팰리스 폼 5경기가 WSL, 스트라스부르 4경기가 여자 Premiere Ligue 로 들어왔다.
   그 목록이 축1 을 만들어 확률(니스 45%)을 밀었고 `squad_turnover` 도 그래서 켜졌다.
🔴 가리는 재료는 **분석 중인 경기가 그 팀 일정에 있나** 하나다.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core import discover as d

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _Ref:
    kickoff_utc: datetime
    home_name: str
    away_name: str


def _ref() -> _Ref:
    return _Ref(datetime(2026, 10, 11, 13, 0, tzinfo=UTC), "Nice", "Strasbourg")


def test_그_경기가_있으면_참이다() -> None:
    rows = [{"utc": "2026-10-11T13:00", "home": "Nice", "away": "Strasbourg"}]
    assert d.has_match(rows, _ref()) is True


def test_여자팀_일정은_거짓이다() -> None:
    # 🔴 실측 줄 — 스트라스부르 여자팀 일정(이 경기가 없다)
    rows = [{"utc": "2026-10-03T13:00", "home": "Strasbourg (W)",
             "away": "Marseille (W)"},
            {"utc": "2026-09-18T18:00", "home": "Strasbourg (W)",
             "away": "Paris FC (W)"}]
    assert d.has_match(rows, _ref()) is False


def test_시각만_같고_상대가_다르면_거짓이다() -> None:
    rows = [{"utc": "2026-10-11T13:00", "home": "Lille", "away": "Lorient"}]
    assert d.has_match(rows, _ref()) is False


def test_킥오프를_모르면_거짓이다() -> None:
    @dataclass
    class _Empty:
        home_name: str = "Nice"
        away_name: str = "Strasbourg"

    rows = [{"utc": "2026-10-11T13:00", "home": "Nice", "away": "Strasbourg"}]
    assert d.has_match(rows, _Empty()) is False


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_두_호출부가_입구를_지난다() -> None:
    """🔴 `hits[0]` 로 과거 경기·선수단을 받는 자리가 **남아 있지 않다**."""
    for rel, fn in (("app/core/stages/s2e_matchup.py", "_history"),
                    ("app/core/stages/s2_facts.py", "_fill_squad")):
        tree = ast.parse(_src(rel))
        got = next(x for x in ast.walk(tree)
                   if isinstance(x, ast.AsyncFunctionDef) and x.name == fn)
        said = ast.unparse(got)
        assert "pick_team" in said, f"🔴 {rel}:{fn} 이 입구를 안 지난다"
        assert "_slug_hit" not in said, f"🔴 {rel}:{fn} 에 `hits[0]` 이 남았다"


def test_입구가_경기로_가린다() -> None:
    tree = ast.parse(_src("app/core/discover.py"))
    got = next(x for x in ast.walk(tree)
               if isinstance(x, ast.AsyncFunctionDef) and x.name == "pick_team")
    said = ast.unparse(got)
    assert "has_match" in said, "🔴 일정으로 가리지 않는다"
    assert "state.note" in said, "🔴 못 가린 사실을 안 적는다(#3)"
