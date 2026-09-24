"""[PIPE-5 2026-09-25] `lineup_out` 은 **타자만** 센다.

사용자 감사 2026-09-25 모순 5:
```
TB@NYY lineup_out 18건 중 9건이 투수
  "New York Yankees의 Kervin Castro(선발) Injured 60-Day로 결장"
  "New York Yankees의 Fernando Cruz(선발) …"
→ direction 은 BASIS_LINEUP 만 세므로 부호에는 안 들어가지만,
  ⑥의 `_judge` 는 **목록 길이**로 confirmed 를 만들고
  서술·내보내기에는 "결장 18명" 으로 나간다.
```

🔴 잠그는 것 셋:
  (a) 투수 판정의 원본은 `absences.is_pitcher_line` 하나다(사본 금지).
  (b) ⑤가 그것을 불러 `lineup_out` value 에서 투수를 뺀다.
  (c) 뺀 것은 **버리지 않고** `pitcher_il` 칸에 남는다.
"""
from __future__ import annotations

import asyncio
import inspect

from app.collectors import absences as ABS
from app.flow.nodes import n05_evidence as N5


# ── (a) 원본 판정 ──────────────────────────────────────────────────

def test_pipe5_투수_판정의_원본은_absences다():
    il = ABS.from_injured(
        "New York Yankees",
        batters=[{"id": 1}],
        injured=[{"id": 9, "name": "Kervin Castro", "position": "SP",
                  "status": "Injured 60-Day"},
                 {"id": 8, "name": "Tim Hill", "position": "RP",
                  "status": "Injured 15-Day"},
                 {"id": 1, "name": "Aaron Judge", "position": "RF",
                  "status": "Injured 10-Day"}])
    pit = [x for x in il if ABS.is_pitcher_line(x)]
    bat = [x for x in il if not ABS.is_pitcher_line(x)]
    assert len(pit) == 2, pit
    assert len(bat) == 1 and "Aaron Judge" in bat[0], bat
    # 🔴 표지를 테스트에 손으로 적지 않는다 — 상수를 쓴다
    assert all(any(f"({r})" in x for r in ABS.PITCHER_ROLES) for x in pit)
    assert all(any(f"({r})" in x for r in ABS.BATTER_ROLES) for x in bat)


def test_pipe5_역할_표지에_사본이_없다():
    """🔴 `_describe`·`from_injured` 가 상수를 쓴다 — 문자열을 또 적지 않는다."""
    src = inspect.getsource(ABS)
    body = src.split('MARK_IL_DEFAULT = "부상자 명단"', 1)[1]
    for lit in ('role = "주포"', 'role = "주전 타자"', '(불펜)', '(선발)'):
        assert lit not in body, f"역할 문자열을 또 적었다: {lit}"


# ── (b)(c) ⑤ 배선 ─────────────────────────────────────────────────

class _Ctx:
    pool = None
    redis = None

    def __init__(self, absences):
        self.inject = {"absences": absences, "today_order": {}}


class _St:
    game_id = "1"
    sport = "baseball"
    league = "MLB"
    home = "New York Yankees"
    away = "Tampa Bay Rays"
    kickoff_utc = "2026-09-24T23:05:00+00:00"
    hyp_side = "home"
    pick_side = "home"
    n02_market: dict = {}
    n05_evidence = None

    def __init__(self):
        self.n04_hyp = [{"id": "H_break", "vars": [
            {"var": "lineup_out", "is_core": True, "source_hint": ""}]}]


def _lineup_row(absences):
    st = _St()
    s = asyncio.run(N5.run(st, _Ctx(absences)))
    return next(e for e in s.n05_evidence if e["var"] == "lineup_out")


def test_pipe5_lineup_out_excludes_pitchers():
    abs_lines = ABS.from_injured(
        "New York Yankees", batters=[{"id": 1}],
        injured=[{"id": 9, "name": "Kervin Castro", "position": "SP",
                  "status": "Injured 60-Day"},
                 {"id": 8, "name": "Tim Hill", "position": "RP",
                  "status": "Injured 15-Day"},
                 {"id": 1, "name": "Aaron Judge", "position": "RF",
                  "status": "Injured 10-Day"}])
    row = _lineup_row(abs_lines)
    joined = " / ".join(map(str, row["value"] or []))
    assert "Kervin Castro" not in joined, f"투수가 결장 목록에 남았다: {row}"
    assert "Tim Hill" not in joined, f"불펜이 결장 목록에 남았다: {row}"
    # (c) 버리지 않는다
    assert len(row["pitcher_il"]) == 2, row["pitcher_il"]


def test_pipe5_n05_가_원본_판정을_부른다():
    """🔴 배선 — ⑤ 안에서 정규식으로 되짚으면 사본이다."""
    src = inspect.getsource(N5)
    assert "_ABS.is_pitcher_line(" in src, "⑤가 원본 판정을 부르지 않는다"
    assert "(선발)" not in src and "(불펜)" not in src, "⑤가 표지를 손으로 적었다"


def test_pipe5_모든_증거행에_칸이_있다():
    """⚠️ 칸이 일부 행에만 있으면 읽는 쪽이 `.get` 으로 눙치게 된다."""
    row = N5._row("weather", None, source="", status="미실행")
    assert row["pitcher_il"] == []
