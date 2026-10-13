"""🔴🔴 **P1 — 리그 간 전력**(수정 지시 2026-10-13 밤 P1).

> 등록 리그 밖 팀도 국내 리그 과거 경기를 받는다(fotmob 팀 페이지 · 리그 id
> **자동 등록** · kind=domestic_league).
> 리그 오프셋 적합: 최근 3시즌 교차 리그 경기 + 각 국내 리그 Elo(**수축** ·
> 표본 수 표기). 리그 쌍 표본이 얇으면 ⬜ + 🟡.
> 판정 전에는 카드에 **"리그 간 전력 차(표시만)"** 줄로만 낸다 — 확률 경로에
> 안 넣는다.

🔴 **LG1** 자동 등록이 `kind` 를 들고 CP1 을 통과한다 · **LG2** 경기 페이지의 팀
   번호로 과거 경기를 받는다(색인 밖 팀) · **LG3** 오프셋은 **수축**한다 ·
   **LG4** 표본 미달은 판에 값을 안 적는다 · **LG5** 표시 줄이 카드에 있고
   **확률 경로에 안 닿는다** · **LG6** 대륙 대회 판은 국내 리그로 세지 않는다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_lg1_auto_registration_carries_kind() -> None:
    from app.core import autoleague, competition
    box, why = autoleague.build(
        competition_key="league:fotmob999999",
        meta={"league_id": "999999", "ccode": "KOR", "name": "시험 리그",
              "url": "https://x.test/l/999999", "kind": "domestic_league"},
        teams=["가", "나"], baseline={"why": "시험"},
        teams_from="fotmob:999999 일정")
    assert box and box.get("kind") == "domestic_league", why
    # 🔴 `kind_require` 가 자동 등록 파일의 유형을 **읽을 수 있어야** 한다
    said = _src("app/core/competition.py")
    assert "autoleague" in said and "said_auto" in said
    assert "domestic_league" in str(competition.KINDS)


def test_lg2_team_id_path_exists() -> None:
    assert "team_id" in _src("app/collect/fotmob.py")
    assert 'box.setdefault("team_ids"' in _src("app/core/stages/s2_facts.py")
    said = _src("app/core/stages/s2e_matchup.py")
    assert "tid_hint" in said and "team_ids" in said


def test_lg3_offsets_shrink() -> None:
    said = _src("tools/fit_offsets.py")
    assert "ridge" in said and "수축" in said
    # 🔴 벌의 문턱은 **이미 쓰던 수**다(새 계수를 만들지 않는다)
    assert "off.MIN_GAMES / (cnt[k] + off.MIN_GAMES)" in said


def test_lg4_thin_pairs_have_no_value() -> None:
    import yaml
    box = ROOT / "data/league_offsets"
    rows = sorted(box.rglob("*.yaml")) if box.exists() else []
    if not rows:
        return
    got = yaml.safe_load(rows[-1].read_text(encoding="utf-8")) or {}
    from app.core import offsets as off
    for key, one in dict(got.get("leagues") or {}).items():
        n = int(dict(one).get("n") or 0)
        if n < off.MIN_GAMES:
            assert dict(one).get("value") is None, (key, one)


def test_lg5_display_only() -> None:
    assert "league_gap" in _src("app/core/stages/s2_facts.py")
    assert "리그 간 전력 차" in _src("app/core/render.py")
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/legacy/old_engine.py"):
        assert "offsets" not in _src(rel), rel


def test_lg6_continental_plate_is_not_domestic() -> None:
    from app.core import offsets as off
    said = _src("app/core/offsets.py")
    assert "club_continental" in said
    box = off.AUTO_ELO
    if not box.is_dir():
        return
    from app.core import competition as cp
    for path in sorted(box.glob("*.yaml")):
        key = path.stem.replace("league_", "league:")
        assert cp.kind_require(key)[0] != "club_continental", path.name
