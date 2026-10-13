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
    """🔴 표의 열쇠는 **선수 id** 다 — 이름은 값 안에 남는다(표시용)."""
    from app.core.stages import s2e_matchup as s2e
    rows = [{"mine_home": True, "side_ids": ("T1", "T2"),
             "player_adv": {"p1": {"name": "가", "team_id": "T1",
                                   "xg": 0.4, "xa": 0.1},
                            "p9": {"name": "남", "team_id": "T2",
                                   "xg": 0.9, "xa": 0.0}}}]
    got = s2e.adv_players(rows)
    assert set(got) == {"p1"}, got            # 🔴 우리 팀만
    assert got["p1"]["name"] == "가" and got["p1"]["xg"] == 0.4, got


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
    """⚠️ 표가 비면 **그 사실**이 남는다(0 으로 메우지 않는다 · #3)."""
    from app.core import matchup as mu
    got, why = mu.key_miss(shares={}, keys=set(), table=0)
    assert got == 0.0 and "비었다" in why, why
