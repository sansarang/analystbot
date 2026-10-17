"""🔴🔴 **§3 빠진 주전 항 되살리기 — 공격 기여표의 공백 원인**(지시서 2026-10-13).

> 공격 기여표 공백 원인 보고(**L2 차단인지 수집 실패인지**) → 경기 단위 재합산
> (as_of 이전 득점·도움)으로 채움. 채울 수 없으면 선수 점수(2절)로 대체.

🔴🔴 **실측으로 찾은 원인은 둘 다 아니다 — 신원 불일치다**(2026-10-13):
| 무엇 | 실측 |
|---|---|
| 자료가 없나 | 🔴 **아니다** — `fotmob.player_adv` 가 경기마다 **22~23명**의 xG·xA 를 낸다(J1·K1 둘 다) |
| L2 가 막았나 | 🔴 **아니다** — 1순위 경로(`adv`)는 **경기별**이라 as-of 정합이고 L2 가 막는 것은 2순위(시즌 누계)뿐이다 |
| 그럼 무엇인가 | 🔴🔴 **`adv_players` 가 선수 id 를 버리고 이름으로 표를 만든다** — 그런데 `s2e_matchup` 의 `usual`·`out_today` 는 **신원표를 지난 id** 다(`_pid.resolve`). 그래서 `style._att_share` 의 `box.get(nm)` 이 **언제나 빈손**이고 비중이 **늘 0** 이었다 |

⚠️ 같은 병을 §1 에서도 봤다(일본어 이름 ↔ fotmob id → 확보율 1.0%). 🔴 이름으로
   잇는 자리는 전부 **id 로** 바꾼다.
"""
from __future__ import annotations


def test_adv_players_keys_by_id_and_keeps_the_name() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_adv_players_keys_by_id_and_keeps_the_name)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_att_table_is_id_keyed_when_the_match_table_is_used() -> None:
    """🔴 `_att_table` 이 `adv` 를 쓰면 **id 열쇠**다(이름 열쇠가 아니다)."""
    from app.core import strategy as st
    got = st._att_table(None, adv={"p1": {"name": "가", "xg": 0.4, "xa": 0.1},
                                   "p2": {"name": "나", "xg": 0.0, "xa": 0.2}})
    assert set(got) == {"p1", "p2"}, got
    assert got["p1"] == 0.5, got


def test_the_share_matches_resolved_ids() -> None:
    """🔴🔴 **이 계약이 그 병이다** — 식별자가 id 여도 비중이 잡혀야 한다."""
    from app.core import strategy as st
    from app.core import style as sy
    read = st.TeamRead(team="H")
    read.att_table = st._att_table(
        None, adv={"p1": {"name": "가", "xg": 0.4, "xa": 0.1},
                   "p2": {"name": "나", "xg": 0.3, "xa": 0.2}})
    # 🔴 `s2e_matchup` 이 넘기는 꼴 = **신원표를 지난 id**
    assert sy._att_share(read, ["p1"]) == 0.5, read.att_table
    # ⚠️ 이름만 가진 식별자(`name:…`)도 **이름 열쇠 표**에서는 잡힌다
    read2 = st.TeamRead(team="H")
    read2.att_table = {"가": 1.0, "나": 1.0}
    assert sy._att_share(read2, ["name:가"]) == 0.5, read2.att_table


def test_empty_table_is_named_not_zeroed() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_empty_table_is_named_not_zeroed)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"
