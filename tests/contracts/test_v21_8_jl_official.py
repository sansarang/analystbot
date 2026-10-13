"""🔴🔴 **§6-6 전용 통로 — J리그 출장정지 공시**(지시서 2026-10-13 밤 셋째).

> 징계: 리그·대회 징계 공시(경고 누적·퇴장) → **결장 hard**.

🔴 실측 2026-10-13 — `data.j-league.or.jp/SFIN03/` 표는
   `選手 | チーム | 前回の停止 | 今回の停止 | 出場停止試合` 다(`<tr>` 20줄).
🔴 **L2** — 이 공시는 **현재 값**이다(오늘의 정지 목록) → **운영 전용**이고
   백필·as-of 재현에는 **쓰지 않는다**. 계약이 그 자리를 센다.
"""
from __future__ import annotations

HTML = """
<table><tr><th>選手</th><th>チーム</th><th>前回の停止</th>
<th>今回の停止</th><th>出場停止試合</th></tr>
<tr><td>高 宇洋</td><td>FC東京</td><td></td><td>J1(a)</td>
<td>２０２６／２７明治安田Ｊ１リーグ第９節第２日(10/10)</td></tr>
<tr><td>下田 北斗</td><td>町田</td><td></td><td>J1(b)</td>
<td>２０２６／２７明治安田Ｊ１リーグ第９節第２日(10/10)</td></tr>
<tr><td></td><td></td><td></td><td></td>
<td>２０２６／２７明治安田Ｊ１リーグ第１０節第２日(10/18)</td></tr>
</table>
"""


def test_suspensions_are_parsed() -> None:
    from app.collect import jl_official as jo
    got, why = jo.suspensions(HTML)
    assert len(got) == 2, (got, why)
    assert got[0]["player"] == "高 宇洋" and got[0]["team"] == "FC東京"
    assert got[0]["kind"] == "J1(a)"
    assert got[0]["day"] == "10/10", got[0]
    assert "20줄" in why or "줄" in why


def test_empty_rows_are_not_players() -> None:
    """🔴 선수 칸이 빈 줄은 **선수가 아니다**(라운드 머리글이다)."""
    from app.collect import jl_official as jo
    got, _why = jo.suspensions(HTML)
    assert all(r["player"] for r in got)


def test_for_match_matches_team_and_day() -> None:
    """🔴 그 경기의 결장만 고른다 — 팀 **별칭**과 **날짜**로 가린다."""
    from app.collect import jl_official as jo
    got, why = jo.suspensions(HTML)
    said, why2 = jo.for_match(got, team_names=["FC東京", "FC Tokyo"],
                              day="10/10")
    assert [r["player"] for r in said] == ["高 宇洋"], (said, why2)
    none, why3 = jo.for_match(got, team_names=["FC東京"], day="10/18")
    assert none == [] and "0명" in why3


def test_l2_backfill_tools_do_not_use_this_channel() -> None:
    """🔴🔴 **L2** — 이 공시는 **현재 값**이다 → 백필·재현 도구가 부르면 실패."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    bad = []
    for name in ("backfill_score.py", "compare_paths.py", "season_trial.py",
                 "cup_trial.py", "lineup_trial2.py", "build_grids.py"):
        path = root / "tools" / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if "jl_official" in ast.unparse(tree):
            bad.append(name)
    assert not bad, f"🔴 백필 도구가 **현재 값 공시**를 쓴다: {bad}"


def test_the_docstring_says_it_is_operational_only() -> None:
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/collect/jl_official.py").read_text(encoding="utf-8")
    assert "L2" in said and "운영 전용" in said
