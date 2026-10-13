"""🔴🔴 **§2-3 감독 부임일**(통합 지시서 2026-10-13 밤).

> fotmob 팀 페이지(허용 경로) → 감독 이름·부임일. 없으면 **기사 2매체**.
> 출처·시각 기록. `CoachRow{team_id, coach, since, source}` · `as_of` **이전**만(L1).
> 파생: `coach_games` = 부임 후 리그 경기 수(`as_of` 기준).
> 계약 **CO1**: 부임일 **출처 없으면 ⬜**(추측 금지).

🔴🔴 **실측 2026-10-13** — fotmob 팀 페이지는 **감독 이름·id·나이·국가만** 준다
   (`"coach":{"id":…,"age":…,"name":…}`). 🔴 **부임일(since)이 없다**
   (`since`·`appointed`·`startDate` 전부 0건 · overview·squad 두 쪽 다 확인).
   → 그래서 `since` 는 **기사 2매체**에서만 오고, 못 찾으면 **⬜** 다.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def test_row_from_fotmob_has_no_since() -> None:
    """🔴 fotmob 길은 **이름만** — `since` 는 `None` 이고 사유가 그 말을 한다."""
    from app.collect import coach as co
    got = co.row_of(team_id="245905", payload={
        "props": {"pageProps": {"fallback": {"x": {"coach": {
            "id": 1, "name": "Jeong-Kyu Lee", "age": 44}}}}}})
    assert got.coach == "Jeong-Kyu Lee" and got.team_id == "245905"
    assert got.since is None
    assert "부임일" in got.why and ("⬜" in got.why or "🔴" in got.why)


def test_co1_two_media_are_required_for_a_date() -> None:
    """🔴🔴 **CO1** — 날짜는 **두 매체가 같은 날**을 말할 때만 선다."""
    from app.collect import coach as co
    one = [{"host": "a.com", "date": "2026-07-01"}]
    two = [{"host": "a.com", "date": "2026-07-01"},
           {"host": "b.com", "date": "2026-07-01"}]
    bad = [{"host": "a.com", "date": "2026-07-01"},
           {"host": "b.com", "date": "2026-02-02"}]
    assert co.since_of(one)[0] is None            # 🔴 한 매체로는 안 선다
    assert co.since_of(two)[0] == "2026-07-01"
    assert co.since_of(bad)[0] is None            # 🔴 날짜가 갈리면 안 선다
    assert "매체" in co.since_of(one)[1]


def test_coach_games_counts_league_matches_after_since() -> None:
    """🔴 `coach_games` — 부임 **뒤**, `as_of` **이전** 리그 경기 수."""
    from app.collect import coach as co
    rows = [{"utc": "2026-06-01T12:00:00Z", "home": "A", "away": "B"},
            {"utc": "2026-07-05T12:00:00Z", "home": "A", "away": "C"},
            {"utc": "2026-07-12T12:00:00Z", "home": "D", "away": "A"},
            {"utc": "2026-09-01T12:00:00Z", "home": "A", "away": "E"}]
    got, why = co.games_of(rows, team="A", since="2026-07-01",
                           as_of=datetime(2026, 7, 20, tzinfo=UTC))
    assert got == 2, (got, why)
    # 🔴 부임일이 없으면 **못 센다**(0 이 아니다)
    said, why2 = co.games_of(rows, team="A", since=None,
                             as_of=datetime(2026, 7, 20, tzinfo=UTC))
    assert said is None and "⬜" in why2


def test_co2_coach_term_cannot_touch_lambda_without_a_bias_table() -> None:
    """🔴🔴 **CO2** — 보정표 편향 없이 감독 항이 λ 에 닿으면 **실패**.

    🔴 지금은 `since` 를 못 받으므로 **보정표를 만들 수 없다** → 감독 항은
       **존재하지 않는다**. 그 사실을 코드로 센다(확률 경로에 이름이 없다).
    """
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/sim.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (isinstance(body, list) and body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
        said = ast.unparse(tree)
        for bad in ("coach", "coach_games"):
            assert bad not in said, (rel, bad)
