"""[ADJ-1] ⑦ 부호가 근거의 **내용**을 안 봤다 — 내가 만든 버그다.

🔴 실측 2026-09-20 (오늘 MLB 4경기):
     WSH@STL  starter_recent3  pp=3.0 sign=1.0   상대 선발 6.0이닝 1자책 (잘 던짐)
     NYY@ARI  starter_recent3  pp=3.0 sign=1.0   상대 선발 6.7이닝 6자책 (무너짐)
     MIA@SD   starter_recent3  pp=3.0 sign=1.0   상대 선발 4.0이닝 5자책 (무너짐)
     MIN@LAA  starter_recent3  pp=3.0 sign=1.0   상대 선발 4.0이닝 4자책 (무너짐)
   **잘 던진 선발과 무너진 선발에 같은 부호·같은 크기를 줬다.**

🔴 원인은 내 STR-2 다. `sides` 는 "**악재가 어느 쪽인가**"인데 나는 "이 사실이
   누구 얘기인가"로 넣었다(`sides={opp: n}` 고정). `n07._direction` 은 그것을
   보고 언제나 +1.0 을 냈다.
   ⚠️ `_direction` 머리말이 이미 경고하고 있었다 — "한쪽으로 고정하면 근거와
      **반대로** 확률이 움직인다."

🔴 방향은 **리그 평균 방어율**로 가른다. 새 상수를 만들지 않는다 —
   `settings.league_era`(MLB 4.20) · `kbo_league_era` · `npb_league_era` 가
   이미 있고 `scoring._suppression` 이 같은 값을 쓴다.
"""
from __future__ import annotations

import pytest


def test_방어율로_방향을_가른다():
    from app.flow.nodes.n05_evidence import starter_side_of

    # 상대 선발이 리그 평균보다 나쁘다 → 상대 악재 → 우리에게 유리
    assert starter_side_of(era3=6.5, league_era=4.20, opp="home") == {"home": 1}
    # 상대 선발이 리그 평균보다 좋다 → 우리에게 불리
    assert starter_side_of(era3=2.1, league_era=4.20, opp="home") == {"away": 1}


def test_모르면_비운다():
    """🔴 방어율을 못 구하면 `sides` 를 비운다 — `_direction` 이 보수적으로
       불리하게 읽는다. 유리하게 지어내지 않는다."""
    from app.flow.nodes.n05_evidence import starter_side_of

    assert starter_side_of(era3=None, league_era=4.20, opp="home") == {}
    assert starter_side_of(era3=4.0, league_era=None, opp="home") == {}


def test_이닝이_0이면_방어율이_없다():
    from app.flow.nodes.n05_evidence import era_of_rows

    assert era_of_rows([{"innings": 0.0, "er": 0}]) is None
    assert era_of_rows([]) is None
    assert era_of_rows([{"innings": 6.0, "er": 2},
                        {"innings": 3.0, "er": 1}]) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_잘_던진_상대_선발은_불리로_간다():
    """🔴 이 계약이 오늘의 버그 자체를 겨눈다."""
    from datetime import UTC, datetime

    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N
    from app.flow.state import State

    good = [{"d": datetime(2026, 9, 14, tzinfo=UTC).date(), "innings": 6.0,
             "er": 1, "k": 6, "bb": 1, "opponent": "X"},
            {"d": datetime(2026, 9, 8, tzinfo=UTC).date(), "innings": 6.0,
             "er": 1, "k": 4, "bb": 1, "opponent": "Y"}]

    # 🔴 [UND-1 2026-09-23] ⑤가 **양 팀 선발**을 조회하게 바뀌었다. 종전 대역은
    #    투수 인자를 무시하고 두 쪽에 같은 기록을 줘서 양쪽이 똑같이 호재가 되고
    #    부호가 상쇄됐다. **투수별로 다른 기록**을 준다 — 이 시험의 뜻("잘 던진
    #    상대 선발은 불리")은 우리 선발이 평범할 때의 이야기다.
    mid = [{"d": datetime(2026, 9, 15, tzinfo=UTC).date(), "innings": 5.0,
            "er": 3, "k": 4, "bb": 2, "opponent": "Z"},
           {"d": datetime(2026, 9, 9, tzinfo=UTC).date(), "innings": 5.0,
            "er": 2, "k": 3, "bb": 2, "opponent": "W"}]

    class _Pool:
        async def fetch(self, sql, *a):
            if "pitcher_appearances" not in sql:
                return []
            return good if a and a[0] == "Ace" else mid

    st = State(run_id="r", game_id="1", sport="baseball", league="MLB",
               home="HOME", away="AWAY", kickoff_utc="2026-09-20T01:00:00Z")
    st.pick_side = "away"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "starter_recent3", "is_core": True}]}]
    ctx = Ctx(pool=_Pool(), inject={"starter_notes": [], "absences": [],
                                    "extract": {},
                                    "starters": {"home": "Ace", "away": "Joe"}})
    out = await N.run(st, ctx)
    row = [e for e in out.n05_evidence if e["var"] == "starter_recent3"][0]
    # 🔴 [FIXDIR 2026-09-20] 부호의 원본이 `sides` 에서 `direction` 으로 옮겼다.
    #    ERA3 1.50 < 4.20 → 상대(home) **호재** → 우리(away) 픽에 불리.
    d = row["direction"]
    assert d["home"] == +1, d
    # 🔴 우리(away) 선발은 평범해 방향 0 — 그래서 상쇄되지 않는다.
    assert int(d.get("away", 0) or 0) == 0, d
    # 🔴 **부호가 이 시험의 요점이다.** `merge` 는 dev 를 크기(절대값)로 합쳐
    #    부호를 잃는다(⑦은 dev 를 강도에만 쓴다). 부호는 `_direction_of` 가
    #    정하므로 거기서 확인한다 — 단언을 약화시킨 것이 아니라 **제자리**로
    #    옮긴 것이다.
    from app.flow.nodes.n07_adjust import _direction_of

    assert _direction_of(d, "away") == -1.0, d
