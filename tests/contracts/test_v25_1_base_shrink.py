"""🔴🔴 **두 팀 총골 기준을 표본으로 수축한다** — 수정 지시 2026-10-13 4번.

> λ 2.818 / 2.170 · 총골 4.99 는 ACL Elite 실측 2.82 의 1.77배 → 이상값으로 보고
> 원인부터 찾는다.

🔴 **찾은 원인** — λ 바닥은 `facts.standings["match_total_baseline"]`(두 팀의
   경기당 총골 평균)이고, ACL 리그 단계는 그때 **2경기**뿐이었다. 상하이–대전의
   그 수는 **5.5** 였고(대회 실측 2.8213 의 1.95배) 대회 기준은 **한 번도 안
   쓰였다**(좁은 출처가 먼저이므로 설계대로지만, 표본 2경기는 잡음이다).
🔴 **BS1** 표본 칸(`match_total_played`)이 함께 실린다 · **BS2** 표본 < 8경기면
   대회 실측 평균으로 **수축**한다(가중 `min(1, n/8)`) · **BS3** 표본 ≥ 8이면
   종전과 **같은 수**다 · **BS4** 대회 실측이 없으면 수축하지 않고 그 사실을 적는다.
⚠️ 새 계수를 만들지 않았다 — 문턱 8 은 `TEAM_HOME_FULL` 과 **같은 수**다.
"""
from __future__ import annotations


class _Facts:
    """🔴 `comp_kind` 가 보는 칸만 들고 있는 최소 모양."""

    def __init__(self, box: dict) -> None:
        self.standings = dict(box)
        self.league_id = ""
        self.competition = ""
        self.match_format = ""
        self.xi = {}
        self.national = False


class _Ref:
    sport = "soccer"
    league = "league:ACLE"
    competition = "AFC Champions League Elite"
    competition_short = "ACLE"
    league_id = ""
    # ⚠️ 실제 이름표에 있는 **구단** 열쇠를 쓴다 — 대표팀 코드(iso:·fa:)가
    #    붙은 열쇠면 `comp_kind` 가 `national_*` 로 떨어진다(실측).
    home = "team:999901"
    away = "team:999902"
    home_name = "HOME"
    away_name = "AWAY"


def test_bs1_played_is_carried() -> None:
    """🔴 **BS1** — s2 가 표본 칸과 **수축 결과**를 싣는다."""
    said = __import__("pathlib").Path(
        "app/core/stages/s2_facts.py").read_text(encoding="utf-8")
    assert 'std["match_total_played"]' in said
    for key in ("match_total_raw", "match_total_why", "goalbase"):
        assert key in said, key


def test_bs2_small_sample_shrinks() -> None:
    """🔴🔴 **BS2** — 표본 2경기면 대회 실측으로 **크게** 수축한다."""
    from app.core import goalbase as gb
    got, why = gb.shrink(5.5, played=2, comp_total=2.8213)
    assert got is not None and got < 4.0, (got, why)
    assert "수축" in why, why


def test_bs3_full_sample_unchanged() -> None:
    """🔴 **BS3** — 표본 8경기면 두 팀 수 그대로(회귀 방지)."""
    from app.core import goalbase as gb
    got, why = gb.shrink(3.0, played=8, comp_total=2.8213)
    assert got == 3.0 and "그대로" in why, (got, why)


def test_bs4_unknown_sample_does_not_shrink() -> None:
    """🔴 **BS4** — 표본·대회 실측을 모르면 **수축하지 않는다**(사유를 적는다)."""
    from app.core import goalbase as gb
    got, why = gb.shrink(5.5, played=None, comp_total=2.8213)
    assert got == 5.5 and "표본 칸이 없다" in why
    got2, why2 = gb.shrink(5.5, played=2, comp_total=None)
    assert got2 == 5.5 and "수축 못 했다" in why2


def test_bs5_league_mean_quotes_the_reason() -> None:
    """🔴 **BS5** — ⑯ 은 **다시 수축하지 않고** 그 사유를 인용한다."""
    import inspect

    from app.core import probmodel as pm
    # ⚠️ **D46** — 독스트링·주석을 뺀 **코드만** 본다(주석이 *"수축은 ③ 에서
    #    한다"* 고 설명하는 것은 호출이 아니다).
    import ast
    tree = ast.parse(inspect.getsource(pm.league_mean))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    said = ast.unparse(tree)
    assert "match_total_why" in said
    assert "goalbase" not in said, "🔴 수축을 두 곳에서 하면 두 번 걸린다"
    assert "shrink" not in said


def test_threshold_is_the_existing_one() -> None:
    from app.core import goalbase as gb
    from app.core import probmodel as pm
    assert gb.FULL == pm.TEAM_HOME_FULL == 8
