"""🔴🔴 **김천–안양이 드러낸 다섯 어긋남** — 사용자 지적 2026-10-10.

> 숫자끼리 서로 맞지 않는 곳이 **다섯 군데** 있고, 그중 하나는 김천상무라는 팀의
> 특성을 봇이 전혀 모르는 데서 나온다.

| # | 어긋남 | 고친 곳 |
|---|---|---|
| ① | `공격 기여 −100%` — **불가능한 숫자**(기록 없는 선수를 0 으로 셌다) | `strategy._shrunk`·`CONTRIB_SANE` |
| ② | `중앙 수비 4명` — 풀백을 CB 로 셌다 | `fotmob.spot_of` → `facts.player_pos`·`strategy.pos_fault` |
| ③ | **김천은 로테이션이 아니라 전역**이다 | `app/core/turnover.py`·`config/squad_turnover.yaml` |
| ④ | 시뮬 52% 인데 최종 38% — **두 답** | `s2e.final_sim` 이 최종을 낸다 |
| ⑤ | `상성 우위: 안양` 인데 확률은 김천 — 규칙 **둘**로 정했다 | `layer1.edge_side` |

🔴 다섯 다 **돌연변이로 되돌리면 빨개진다** — 그것이 이 파일의 일이다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ref(home="Gimcheon Sangmu", away="FC Anyang"):
    from app.core.schema import MatchRef
    return MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                    competition_short="K리그1", home="team:000318",
                    away="team:000320", home_name=home, away_name=away,
                    kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))


def _p(name, spot, flank="중앙"):
    from app.core.schema import Player
    return Player(name=name, pos=("GK" if spot == "GK" else
                                  "DF" if spot in ("CB", "LB", "RB") else
                                  "MF" if spot in ("CM", "DM") else "FW"),
                  spot=spot, flank=flank)


# ══════════════════════════════════════════════════════════════════
# ① 기록 없는 선수 = 0 금지
# ══════════════════════════════════════════════════════════════════

def test_v6_기록없는_선수를_0으로_세지_않는다():
    """🔴🔴 ① — *"기록이 없는 선수는 0이 아니라 '모름'(포지션 평균으로 수축)"*.

    ⚠️ 돌연변이: `_shrunk` 를 `sum(table.get(nm, 0))` 으로 되돌리면 — 기록 있는
       선수 둘이 빠지고 기록 **없는** 선수가 들어온 명단의 ΔA 가 **−100%** 가 되고
       이 줄이 빨개진다(실측 2026-10-10 김천: `공격 기여 -100%`).
    """
    from app.core import strategy as _st
    table = {"A": 10.0, "B": 8.0, "C": 2.0, "D": 1.0}
    pos = {"A": "ST", "B": "ST", "C": "CB", "D": "CB"}
    # 🔴 표에 **없는** 두 명이 들어온 명단
    got, gone = _st._shrunk(["X", "Y"], table, pos)
    assert gone == 2, gone
    assert got > 0.0, "🔴 기록 없는 선수를 0 으로 셌다 — ΔA 가 −100% 가 된다"
    # 🔴 수축값은 **표 전체 평균**(칸을 모르므로) × 2 다
    whole = sum(table.values()) / len(table)
    assert abs(got - whole * 2) < 1e-9, (got, whole)
    # 🔴 칸을 알면 **그 칸 평균**으로 수축한다
    got2, _ = _st._shrunk(["Z"], table, {**pos, "Z": "ST"})
    assert abs(got2 - 9.0) < 1e-9, got2


def test_v6_델타가_상한을_넘으면_안_쓴다():
    """🔴 ① — *"ΔA·ΔD가 ±60%를 넘으면 계산 오류 의심으로 그 지표를 쓰지 않고"*."""
    from app.core import strategy as _st
    assert _st.CONTRIB_SANE == 60.0
    src = (ROOT / "app" / "core" / "strategy.py").read_text(encoding="utf-8")
    assert "da_bad" in src and "CONTRIB_SANE" in src
    # 🔴 버린 사실이 **사실 목록으로** 나간다(#3 조용히 비우지 않는다)
    assert 'add("delta_att", f"{name} {got.da_bad}")' in src


def test_v6_공격기여표가_선수단_전원을_든다():
    """🔴 ① 뿌리 — `key_players`(팀당 2명)만 보던 표가 **선수단 전원**을 든다."""
    from app.core import strategy as _st
    from app.core.schema import Facts
    facts = Facts(player_stats={"A": {"goals": 3, "assists": 2},
                                "B": {"goals": 0, "assists": 0}},
                  standings={"key_players": {"team:000318": [
                      {"name": "C", "value": 11.0}]}})
    got = _st._att_table(facts)
    assert got == {"A": 5.0, "B": 0.0, "C": 11.0}, got


# ══════════════════════════════════════════════════════════════════
# ② 포지션 분류
# ══════════════════════════════════════════════════════════════════

def test_v6_선수_이름을_순서_없이_맞춘다():
    """🔴🔴 ① 뿌리 — **실사고**: fotmob 이 같은 선수를 두 꼴로 준다.

    선수단 페이지 `Park Man-Ho`(성 먼저) ↔ 경기 라인업 `Man-Ho Park`.
    ⚠️ 실측 2026-10-10: 겹치는 이름이 **0명**이어서 선수단 기록이 통째로
       버려지고 카드가 *"기록 없음"* 만 적었다 — ① 의 고침이 한국 선수에게는
       **죽은 코드**였다.
    ⚠️ 돌연변이: `name_key` 를 지우고 글자로 맞추면 이 줄이 빨개진다.
    """
    from app.core import discover as _d
    from app.core import strategy as _st
    from app.core.schema import Facts
    assert _d.name_key("Park Man-Ho") == _d.name_key("Man-Ho Park")
    assert _d.name_key("Si-Hoo Hong") != _d.name_key("Min-Seo Park")
    facts = Facts(player_stats={"Park Man-Ho": {"goals": 2, "assists": 1,
                                                "rating": 7.0}})
    got = _st.stat_of(facts, "Man-Ho Park")
    assert got.get("goals") == 2, "🔴 성 먼저 꼴을 못 찾는다"
    # 🔴 기여표도 같은 열쇠로 맞춘다 — 수축이 아니라 **실제 기록**이 잡힌다
    total, gone = _st._shrunk(["Man-Ho Park"], {"Park Man-Ho": 3.0}, {})
    assert (total, gone) == (3.0, 0), (total, gone)
    # 🔴 사실 묶음도 같은 한 곳을 쓴다(사본 금지)
    src = (ROOT / "app" / "core" / "saybundle.py").read_text(encoding="utf-8")
    assert "_st.stat_of" in src, "🔴 묶음이 자기 식으로 이름을 맞춘다"


def test_v6_평소XI가_없으면_헛_교체를_만들지_않는다():
    """🔴🔴 ③ 뒤처리 — ⚠️ 실측 2026-10-10(재현): 전역으로 평소 XI 가 **0경기**가
    됐는데 카드가 `CB 자리 — 빠짐 [] · 들어옴 [...]` 로 적어 **아무도 안 나간
    것처럼** 읽혔다. 🔴 없는 비교를 사실처럼 내지 않는다.
    """
    from app.core import strategy as _st
    from app.core.schema import Facts, XI
    ref = _ref()
    now = [_p(f"New {i}", "CB") for i in range(11)]
    facts = Facts(xi={ref.home: XI(team=ref.home, state="confirmed",
                                   formation="4-4-2",
                                   players=[x.name for x in now],
                                   lineup=now)},
                  past_xi={ref.home: []})      # 🔴 과거 선발이 없다
    got = _st.read(ref, facts, side="home")
    assert got.swaps == {}, f"🔴 헛 교체를 만들었다 — {got.swaps}"
    assert got.changed is None and got.da is None


def test_v6_풀백을_중앙수비로_세지_않는다():
    """🔴🔴 ② — *"중앙 수비 수가 3을 넘거나 GK가 1이 아니면 분류 오류"*.

    ⚠️ 실측 2026-10-10: 카드가 **"CB 자리 — 빠짐 네 명"** 을 냈다. 🔴 원인은
       `facts.player_pos` 가 묶음 글자(`DF`)만 들어 `slot_of("DF") == "CB"` 였다.
    ⚠️ 돌연변이: `s2_facts` 가 다시 `p.pos` 만 싣게 하면 — 네 명이 CB 가 되고
       `pos_fault` 가 빨개진다.
    """
    from app.core import strategy as _st
    # 🔴 세부 자리를 실으면 네 수비가 RB·CB·CB·LB 로 갈린다
    good = {"a": "GK", "b": "RB", "c": "CB", "d": "CB", "e": "LB",
            "f": "CM", "g": "CM", "h": "LW", "i": "RW", "j": "ST", "k": "ST"}
    assert _st.slot_tally(list(good), good)["CB"] == 2
    assert _st.pos_fault(list(good), good) == ""
    # 🔴 묶음 글자만 실으면(옛 모양) **CB 4명** → 분류 오류로 잡힌다
    bad = dict(good)
    for nm in ("b", "c", "d", "e"):
        bad[nm] = "DF"
    assert _st.slot_tally(list(bad), bad)["CB"] == 4
    said = _st.pos_fault(list(bad), bad)
    assert "중앙 수비 4명" in said, said
    # 🔴 골키퍼가 둘이면 그것도 잡는다
    two = dict(good)
    two["f"] = "GK"
    assert "골키퍼 2명" in _st.pos_fault(list(two), two)


def test_v6_s2_facts가_세부자리를_먼저_싣는다():
    """🔴 ② 배선 — 포지션 표에 `Player.spot` 이 먼저 들어간다(#2)."""
    src = (ROOT / "app" / "core" / "stages"
           / "s2_facts.py").read_text(encoding="utf-8")
    assert 'getattr(p, "spot", "")' in src, "🔴 세부 자리를 안 싣는다"
    assert "pos_fault" in src, "🔴 분류 검사를 안 부른다"


# ══════════════════════════════════════════════════════════════════
# ③ 선수단 대거 변동(전역)
# ══════════════════════════════════════════════════════════════════

def test_v6_군팀은_전역주기팀으로_표에_있다():
    """🔴🔴 ③ — *"김천상무 같은 군 팀은 config에 '전역 주기 팀'으로 표시"*."""
    from app.core import turnover as _turn
    assert _turn.cycle_team("Gimcheon Sangmu"), "🔴 김천상무가 표에 없다"
    assert _turn.cycle_team("김천상무"), "🔴 한글 이름으로 못 찾는다"
    assert not _turn.cycle_team("FC Anyang"), "🔴 아무 팀이나 군 팀이 됐다"


def test_v6_한글_이름이_정규화에서_사라지지_않는다():
    """🔴🔴 ③ 뿌리 — **실사고**: `NFKD` 가 한글을 자모로 쪼개 이름이 빈 글자였다.

    ⚠️ 돌연변이: `norm_name` 의 `NFC` 재결합을 지우면 `norm_name("김천상무")` 가
       `""` 가 되고 **한글끼리 `same_team` 이 영원히 거짓**이 된다(전역 주기 팀
       표를 한글로 적자 드러났다).
    """
    from app.core import discover as _d
    assert _d.norm_name("김천상무") == "김천상무"
    assert _d.same_team("김천상무", "김천 상무")
    # 🔴 라틴 발음기호는 그대로 떼야 한다(그것이 `NFKD` 의 일이었다)
    assert _d.same_team("Unión de Santa Fe", "Union de Santa Fe")
    # 🔴 서로 다른 팀은 여전히 다르다
    assert not _d.same_team("김천상무", "안양")


def test_v6_교체_이후_경기로만_평소XI를_만든다():
    """🔴🔴 ③ — *"전역 뒤 첫 경기들은 평소 XI를 **전역 이후 경기로만**"*."""
    from app.core import turnover as _turn
    from app.core.schema import XI

    def xi(names):
        return XI(team="team:000318", state="confirmed", players=names)

    rows = [xi(["old1", "a", "b"]), xi(["a", "b", "c"]), xi(["a", "b", "d"])]
    keep, why = _turn.past_since(rows, names={"old1"})
    assert len(keep) == 2 and "교체 이후" in why, (len(keep), why)
    # 🔴 전부 옛 선수단이면 **평소 XI 없음**이다(0 으로 메우지 않는다)
    keep2, why2 = _turn.past_since(rows, names={"a"})
    assert keep2 == [] and "평소 XI 없음" in why2, why2


def test_v6_전역팀_판정은_로테이션이_아니다():
    """🔴🔴 ③ — *"전략 판정을 **로테이션으로 하지 않는다**(새 판정값
    `squad_turnover`)"*.

    ⚠️ 돌연변이: `_turn_lines` 를 지우면 — 김천의 6자리 변경이 다시
       `로테이션·체력 관리` 로 나가고 그 판정의 λ·승무패 이동이 걸린다.
    """
    from app.core.schema import StrategyLine, StrategyOut
    from app.core.stages.s2d_strategy import _turn_lines
    from app.core.state import RunState
    ref = _ref()
    lines = [StrategyLine(side="home", strategy="로테이션·체력 관리",
                          fact_refs=["L1", "L2"], why="여섯 자리 바뀌었다"),
             StrategyLine(side="away", strategy="평소 그대로",
                          fact_refs=["A1", "A2"], why="두 자리다")]
    st = RunState(match_key="x:1")
    box: dict = {}
    got = _turn_lines(lines, ref, {"home": {"on": True, "why": "전역 주기 팀"},
                                   "away": {"on": False}},
                      state=st, box=box)
    assert got[0].strategy == "squad_turnover", got[0].strategy
    assert got[1].strategy == "평소 그대로", "🔴 안 켜진 팀을 바꿨다"
    assert "TURN-home" in box, "🔴 사실 묶음에 사유를 안 남겼다"
    # 🔴 카드는 **사람 말로** 적는다
    from app.core import turnover as _turn
    assert _turn.verdict_ko("squad_turnover") == _turn.VERDICT_KO
    assert _turn.verdict_ko("수비 위주") == "수비 위주"
    # 🔴 이동량 표에 그 유형이 있고 **승무패는 안 움직인다**
    from app.core import strategy as _st
    eff, why = _st.move_of("squad_turnover")
    assert eff["own_win_logodds"] == 0.0 and eff["draw_logodds"] == 0.0, eff
    assert "임시값" in why
    # 🔴 StrategyOut 이 그 값을 받는다(열거값에 들어 있다)
    assert StrategyOut(lines=got).lines[0].strategy == "squad_turnover"


def test_v6_팀에_없다는_선수단_명부로_센다():
    """🔴🔴 **실사고 2026-10-10** — `facts.squad` 는 **경기 명단 20명**(선발 11 +
    벤치 9)이다. 그것으로 *"이 팀에 없는 선수"* 를 세니 **그날 안 뽑힌 선수가
    전부** 이적·전역으로 잡혔고, 로테이션뿐인 FC 안양이 `선수단 교체` 판정을
    받았다(실측: 안양 6명 · 김천 12명).

    🔴 기준은 **선수단 명부**(`facts.player_stats` — 선수단 페이지 전원)다.
    ⚠️ 돌연변이: `facts.squad` 로 되돌리면 이 줄이 빨개진다.
    """
    from app.core import strategy as _st
    from app.core.schema import Facts, XI
    ref = _ref()
    now = [_p("Man-Ho Park", "GK"), _p("Si-Hoo Hong", "RB")]
    past = [XI(team=ref.home, state="confirmed",
               players=["Man-Ho Park", "Rotated Out", "Discharged Guy"])]
    # 🔴 명부에 `Rotated Out` 이 **있다** → 그는 팀에 있는 선수다(그날만 안 뽑혔다)
    facts = Facts(xi={ref.home: XI(team=ref.home, state="confirmed",
                                   players=[p.name for p in now],
                                   lineup=now)},
                  past_xi={ref.home: past},
                  squad={ref.home: [p.name for p in now]},
                  player_stats={"Park Man-Ho": {"goals": 0, "assists": 0},
                                "Out Rotated": {"goals": 1, "assists": 0}})
    got = _st._off_squad(facts, ref.home, facts.xi[ref.home], past)
    assert got == {"Discharged Guy"}, f"🔴 로테이션을 이적으로 셌다 — {got}"
    # 🔴 명부가 **없으면 빈 집합**이다(모르면 교체로 읽지 않는다 · #4)
    thin = facts.model_copy(update={"player_stats": {}})
    assert _st._off_squad(thin, ref.home, thin.xi[ref.home], past) == set()


def test_v6_양쪽_다_교체면_양상도_사람_말이다():
    """🔴 ⚠️ 실측 2026-10-10: 양쪽 다 교체일 때 반대쪽이 열거값으로 새어 나왔다
    (`… vs squad_turnover`)."""
    from app.core import strategy as _st
    from app.core import turnover as _turn
    said = _st.shape_of("squad_turnover", "squad_turnover",
                        home_name="김천", away_name="안양")
    assert _turn.VERDICT not in said, said
    assert said == f"양 팀 {_turn.VERDICT_KO}"
    one = _st.shape_of("squad_turnover", "평소 그대로", home_name="김천",
                       away_name="안양")
    assert _turn.VERDICT not in one and "김천" in one


def test_v7_깃발은_오늘_경기_명단_기준이다():
    """🔴🔴 **사용자 결정 2026-10-10 (a)** — 구단 명부 기준 **삭제**. 셋 중 하나:

    > ① 오늘 경기 명단(선발+벤치) 기준: 최근 5경기 선발 중 없는 선수 **≥ 5명**
    > ② 전역 주기 팀 + 최근 30일 전역 새 사실 · ③ 평소 XI 를 만들 수 없다
    > r 도 **오늘 경기 명단 기준**이다. 명부는 **이름 매칭용으로만**.

    ⚠️ 돌연변이: 명부(`player_stats`) 기준으로 되돌리면 — 전역한 선수가 명부에
       남아 있어 깃발이 **꺼지고**(실측 2026-10-10 김천) 이 줄이 빨개진다.
    """
    from app.core import turnover as _turn
    from app.core.schema import Facts, XI
    ref = _ref()
    box = _turn.flags()
    assert int(box["off_matchday"]) == 5 and int(box["look_back"]) == 5
    assert int(box["news_days"]) == 30
    assert "suspect" not in _turn.table(), "🔴 옛 명부 기준이 남아 있다"
    now = [f"New {i}" for i in range(11)]
    past = [XI(team=ref.home, state="confirmed",
               players=[f"Old {i}" for i in range(11)]) for _ in range(5)]
    facts = Facts(xi={ref.home: XI(team=ref.home, state="confirmed",
                                   players=now, bench=["Bench 1"])},
                  past_xi={ref.home: past},
                  # 🔴 명부에 옛 선수가 **그대로 있어도** 깃발은 켜진다
                  player_stats={f"Old {i}": {"goals": 0} for i in range(11)})
    got = _turn.read(ref, facts, side="home")
    assert got["on"] is True, got["why"]
    assert got["reasons"] and got["reasons"][0].startswith("①"), got["reasons"]
    # 🔴 r 은 **오늘 명단 기준**이고 0 쪽이다(옛 선발이 하나도 없다)
    assert got["r"] == 0.0, (got["r"], got["r_why"])
    assert "오늘 명단에 있는 비율" in got["r_why"]
    # 🔴 그대로인 팀은 r 1.0 이고 깃발이 꺼진다
    same = Facts(xi={ref.home: XI(team=ref.home, state="confirmed",
                                  players=[f"Old {i}" for i in range(11)])},
                 past_xi={ref.home: past})
    off = _turn.read(ref, same, side="home")
    assert off["on"] is False and off["r"] == 1.0, off


def test_v7_모델이_코드값을_골라도_그_줄만_덮는다():
    """🔴🔴 **(b) 안전장치**(사용자 결정) — *"그 팀 줄만 버리고 코드 깃발 값으로
    덮는다. **다른 팀 판정은 살린다**"*.

    ⚠️ 실측 2026-10-10: 그것을 **위반**으로 셌더니 양 팀 판정이 **다 버려졌다**.
    """
    from app.core.schema import StrategyLine
    from app.core.stages.s2d_strategy import _turn_lines, check
    from app.core.state import RunState
    ref = _ref()
    lines = [StrategyLine(side="home", strategy="squad_turnover",
                          fact_refs=["L1", "L2"], why="모델이 골랐다"),
             StrategyLine(side="away", strategy="공격 위주",
                          fact_refs=["A1", "A2"], why="살아야 한다")]
    turn = {"home": {"on": False}, "away": {"on": False}}
    # 🔴 이제 **위반이 아니다**(검사가 통과한다)
    assert not [x for x in check(lines, {}, turnover=turn)
                if "코드만 쓰는" in x]
    got = _turn_lines(lines, ref, turn, state=RunState(match_key="x"), box={})
    assert got[0].strategy == "평소 그대로", got[0].strategy
    assert "덮었다" in got[0].why
    assert got[1].strategy == "공격 위주", "🔴 다른 팀 판정을 죽였다"


def test_v7_전역_주기_팀은_고정_질의를_받는다():
    """🔴 사용자 결정 (3) — *"전역 주기 팀은 **고정 질의**를 추가한다 — `{팀} 전역`,
    `{팀} 신병 합류`, 구단·리그 공식 공지"*.

    ⚠️ 실측 2026-10-10: 김천 카드의 새 사실이 **0건**이었다 — 깃발이 꺼진 사이
       질의도 안 나갔다. 🔴 이제 **깃발과 무관하게** 그 팀이면 넣는다.
    """
    from app import rules
    got = [str(x) for x in rules.local_words("squad_turnover", "ko")]
    assert got[:2] == ["전역", "신병 합류"], got
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert "_turn.cycle_team(" in src and "cycle or any(" in src, (
        "🔴 전역 주기 팀일 때 고정 질의를 안 넣는다")


def test_v7_전역_질의가_실제로_나간다():
    """🔴🔴 **실사고 2026-10-10** — 개념을 **뒤에** 붙였더니 질의가 한 번도 안
    나갔다. 질의 계획이 개념을 **둘까지만** 쓴다(하위당 검색 3회 상한)인데
    `squad_turnover` 가 여섯째였다 — 김천 새 사실 **0건**의 원인이다.

    🔴 이제 **맨 앞**에 넣고, 그 개념은 **한 팀 질의**(`{팀} 전역`)로 던진다
    (구단 공지에는 상대 팀 이름이 없다).
    """
    import dataclasses as _dc
    from datetime import datetime, timedelta, timezone

    from app.core.schema import MatchRef
    from app.core.stages import s3_docs
    from app.research import subtasks as _st
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="Gimcheon Sangmu",
                   away_name="FC Anyang",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    subs = [x for x in _st.split(s3_docs._RefShim(ref)) if x.group == "F"]
    assert subs, "🔴 하위 F 가 없다"
    said = _dc.replace(subs[0], words=("squad_turnover",) + tuple(subs[0].words))
    got = s3_docs.queries_for(said, ref)
    ko = [q for q, lang in got if lang == "ko"]
    assert any("전역" in q for q in ko), got
    # 🔴 **한 팀 질의**다 — 상대 팀 이름이 그 줄에 없다
    one = [q for q in ko if "전역" in q][0]
    assert "안양" not in one, one
    # 🔴 s3 가 **앞에** 넣는다(뒤에 붙이면 상한에 걸려 안 나간다)
    src = (ROOT / "app" / "core" / "stages"
           / "s3_docs.py").read_text(encoding="utf-8")
    assert "box[str(sub.group)] + tuple(sub.words)" in src, (
        "🔴 개념을 뒤에 붙이고 있다 — 질의가 안 나간다")


def test_v7_전역_새사실이_깃발을_켠다():
    """🔴 (a)② — 전역 주기 팀 + **전역 새 사실**이면 켠다. ⚠️ 다른 팀은 아니다."""
    from app.core import turnover as _turn
    from app.core.schema import Variable
    ref = _ref()
    var = Variable(id="R7", type="returning", subject=ref.home, favors="home",
                   hardness="hard", weight=2.0,
                   claim="김천 상무 선수 셋이 전역했다", quote="전역", doc_ids=[])
    off = {"on": False, "reasons": [], "why": "문턱 아래", "r": 1.0}
    got = _turn.with_news(ref, off, [var], side="home")
    assert got["on"] is True and got["kind"] == "cycle_news", got
    assert any(x.startswith("②") for x in got["reasons"]), got["reasons"]
    # 🔴 전역 주기 팀이 **아니면** 아무것도 안 한다
    other = _turn.with_news(_ref(home="FC Anyang"), dict(off), [var],
                            side="home")
    assert other["on"] is False, other

def test_v6_교체_의심이면_새사실을_찾는다():
    """🔴 ③ — *"`squad_turnover` 의심으로 **새 사실 검색**(이적·전역·징계)"*."""
    from app import rules
    got = rules.local_words("squad_turnover", "ko")
    assert "전역" in got and "이적" in got, got
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert '{"F": ("squad_turnover",)}' in src, "🔴 s3 에 개념을 안 넘긴다"
    s3 = (ROOT / "app" / "core" / "stages"
          / "s3_docs.py").read_text(encoding="utf-8")
    assert "extra_words" in s3, "🔴 s3 가 개념을 안 받는다"




def test_v6_오버도_시뮬에서_나온다():
    """🔴🔴 ④ — *"확률 한 곳"*. 오버 줄이 **시뮬 분포**에서 나온다.

    ⚠️ 실측 2026-10-10(재현): 한 카드에 `시뮬 오버 1.5 72%` 와 `확률 변화 오버
       1.5 62%` 가 같이 있었다(재가중 분포). 🔴 둘 중 하나만 봇의 말이다.
    """
    from app.core import layer1
    from app.core.schema import Card, Facts, ProbTriple
    sim = {"home": 0.4, "draw": 0.3, "away": 0.3,
           "over": {"1.5": 0.72, "2.5": 0.46, "3.5": 0.24}}
    card = Card(match=_ref(), facts=Facts(),
                matchup={"profile": {"home": 1}, "sim": sim},
                shape={"over": {"1.5": 0.62, "2.5": 0.49, "3.5": 0.19}},
                our_prob=ProbTriple(home=0.4, draw=0.3, away=0.3))
    said = layer1._over_line(card)
    assert "1.5 72%" in said and "시뮬 분포" in said, said
    assert "62%" not in said, f"🔴 재가중 분포를 그대로 적었다 — {said}"
    # 🔴 시뮬이 못 돌면 재가중을 쓰고 **그 사실을 적는다**
    thin = card.model_copy(update={"matchup": {"profile": {"home": 1}}})
    said2 = layer1._over_line(thin)
    assert "1.5 62%" in said2 and "재가중 분포" in said2, said2


def test_v6_예상스코어도_시뮬에서_나온다():
    """🔴🔴 ④ — *"확률 한 곳"*. 예상 스코어도 **같은 분포**에서 나온다.

    ⚠️ 실측 2026-10-10(재현): 최종 확률은 홈 46% 인데 예상 스코어가
       `3-3 · 1-2 · 1-1` 로 나와 카드가 **"방향과 어긋난다"** 고 스스로 적었다 —
       스코어는 재가중 무게에서, 확률은 시뮬에서 왔다(두 생성기).
    """
    from app.core import layer1
    from app.core.schema import Card, Facts, ProbTriple
    sim = {"home": 0.46, "draw": 0.30, "away": 0.24,
           "scores": {(1, 0): 0.11, (2, 1): 0.09, (1, 1): 0.10,
                      (0, 0): 0.05, (3, 3): 0.01}}
    card = Card(match=_ref(), facts=Facts(),
                matchup={"profile": {"home": 1}, "sim": sim},
                our_prob=ProbTriple(home=0.46, draw=0.30, away=0.24))
    said = layer1._scores(card)
    assert "시뮬 분포" in said, said
    # 🔴 무게 큰 순으로 셋 — `1-0`(0.11) · `1-1`(0.10) · `2-1`(0.09)
    assert said.startswith("1-0 · 1-1 · 2-1"), said
    assert "어긋난다" not in said, "🔴 같은 분포에서 왔는데 어긋난다고 적었다"




def test_v6_자리글자가_붙은_이름을_없는_이름이라_하지_않는다():
    """🔴🔴 (r) 거짓 위반 — ⚠️ 실측 2026-10-10(재현): 평이 *"새로 들어온
    **LB Min-Seo Park**"* 이라 적었고 검열이 그 다섯 글자를 통째로 **없는 이름**
    이라 했다(묶음에는 `Min-Seo Park` 이 있다) — 좋은 평이 템플릿으로 떨어졌다.
    """
    from app.core.stages import s9_say
    known = {"Min-Seo Park", "Si-Hoo Hong"}
    assert s9_say._names_in("새로 들어온 LB Min-Seo Park 이", known) == []
    assert s9_say._names_in("RB Si-Hoo Hong 과", known) == []
    # 🔴 지어낸 이름은 여전히 걸린다
    assert s9_say._names_in("Lionel Messi 가", known) == ["Lionel Messi"]


# ══════════════════════════════════════════════════════════════════
# ⑤ 상성 우위
# ══════════════════════════════════════════════════════════════════

def test_v6_상성우위는_세축_합이고_확률과_어긋나면_안_쓴다():
    """🔴🔴 ⑤ — *"세 축을 합친 결과로만 … **최종 확률 방향과 다르면 쓰지
    않는다**"*.

    ⚠️ 실사고 2026-10-10: 규칙 **둘**(T10·T11)로 *"상성 우위 안양"* 을 적었는데
       폼은 김천이 1.1 좋고 확률도 김천이 높았다 — 카드가 두 말을 했다.
    """
    from app.core import form as _form
    from app.core import goals as _g
    from app.core import layer1
    from app.core.schema import Card, Facts, ProbTriple

    def card_of(prob, fired, forms):
        return Card(match=_ref(), facts=Facts(),
                    matchup={"profile": {"home": 1}, "fired": fired,
                             "fired2": [], "form": forms},
                    our_prob=ProbTriple(home=prob[0], draw=prob[1],
                                        away=prob[2]))

    # 🔴 실측 2026-10-10 김천–안양의 그 수다 — 홈 −0.17 · 원정 −1.30
    f_home = _form.TeamForm(team="H", n=10, adj_gf=10.0, adj_ga=11.7)
    f_away = _form.TeamForm(team="A", n=10, adj_gf=10.0, adj_ga=23.0)
    forms = {"home": f_home, "away": f_away}
    fired = [_g.Fired(rule="T10", side="away", effect={"lambda_own": 0.1}),
             _g.Fired(rule="T11", side="away", effect={"draw_logodds": 0.1})]
    # 🔴🔴 **그 경기 그대로** — 축3 규칙 둘은 원정, 축1 폼은 홈(+1.13)이다.
    #    축이 갈렸으니 **안 쓴다**(둘 다 맞을 수는 없다).
    card = card_of((0.38, 0.28, 0.34), fired, forms)
    assert layer1.edge_votes(card.matchup) == {"축1": "home", "축2": "",
                                               "축3": "away"}
    assert layer1.edge_side(card.matchup, card) == "", (
        "🔴 규칙 둘로 상성 우위를 정했다 — 축1 은 반대를 말한다")
    said = layer1._edge_line(card.matchup, card)
    assert "안 쓴다" in said and "축1" in said, said
    # 🔴 축이 **모이면** 그 쪽을 쓴다(원정 폼 + 원정 규칙)
    flip = {"home": f_away, "away": f_home}
    card2 = card_of((0.28, 0.28, 0.44), fired, flip)
    assert layer1.edge_side(card2.matchup, card2) == "away"
    # 🔴 그런데 **확률이 반대면** 못 쓴다 — `반반` 일 때도 그렇다(그 구멍으로
    #    김천–안양이 빠져나갔다: 38% 대 34% 는 `반반` 이다)
    card3 = card_of((0.36, 0.30, 0.34), fired, flip)
    assert layer1.dir_side(card3) == "", "🔴 시험 재료 — `반반` 이어야 한다"
    assert layer1.edge_side(card3.matchup, card3) == "", (
        "🔴 확률이 더 높게 본 팀의 **반대쪽**을 상성 우위로 적었다")


def test_v6_골내용_지표는_분모를_함께_쓴다():
    """🔴 ⑤ — *"'90%(9/10)'처럼 **분모를 함께** 쓰고, 해당 유형 골 5개 미만이면
    '관찰만'"*."""
    from app.core import goals as _g
    mine = _g.Profile(team="A", matches=6,
                      led_first={"지킴": 1, "무": 2, "역전패": 3})
    theirs = _g.Profile(team="B", matches=6,
                        trailed_first={"역전승": 3, "무": 2, "패": 2})
    mine.scored.n = 10
    mine.scored.by_bucket = {"61-90+": 6, "0-30": 4}
    theirs.conceded.n = 10
    theirs.conceded.by_bucket = {"61-90+": 9, "0-30": 1}
    rows = {f.rule: f for f in _g.fire(mine, theirs, rest={})}
    assert "(6/10)" in rows["T10"].text and "(9/10)" in rows["T10"].text
    assert "(1/6" in rows["T11"].text and "(5/7" in rows["T11"].text, (
        "🔴 리드 유지력·추격력에 분모가 없다")
    # 🔴 표본이 얇으면 `관찰만` 이고 **확률을 안 움직인다**
    thin = _g.Profile(team="C", matches=2, led_first={"역전패": 2})
    rows2 = {f.rule: f for f in _g.fire(thin, theirs, rest={})}
    if "T11" in rows2:
        assert rows2["T11"].watch_only and rows2["T11"].moves() == {}


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ④ **다시 쓴 계약** — 확률의 출처가 **상성**으로 바뀌었다
# ══════════════════════════════════════════════════════════════════
#
#  옛 계약 다섯(`final_sim`·`solve_tilt`·`_within_cap`·`기준 약함 ×0.5`)은 상성
#  엔진 지시서 §2 가 **지운 경로**를 세고 있었다. 🔴 그 자리를 새 경로로 바꿨다
#  (§2 마지막 줄: *"옛 기능을 지울 때 그걸 쓰던 계약·테스트는 새 계약으로
#  바꾼다(빨간 채로 두지 않는다)"*).

def _probset():
    """🔴 S2·S3 를 돌릴 **최소 재료** — 가치·XI·리그 평균."""
    from app.core import matchup as _mu
    from app.core import routing
    from app.core.schema import Facts, Variable, XI
    ref = _ref()
    xi = {ref.home: XI(team=ref.home, state="confirmed",
                       players=[f"H{i}" for i in range(11)]),
          ref.away: XI(team=ref.away, state="confirmed",
                       players=[f"A{i}" for i in range(11)])}
    facts = Facts(xi=xi, standings={"match_total_baseline": 2.6},
                  player_value={**{f"H{i}": 1_000_000 for i in range(11)},
                                **{f"A{i}": 700_000 for i in range(11)}})
    vs = routing.place([Variable(id="S03", type="home_field", subject=ref.home,
                                 favors="home", hardness="soft", weight=0.4,
                                 claim="홈 이점 수치 없음", quote="q")])
    box = {"form": {}, "style": {}, "profile": {}, "fired": [], "fired2": [],
           "off": {}, "late": {}}
    return ref, facts, vs, box, _mu.report(ref, facts, box, vs)


def test_v7_C1_S3_입력에_상성_밖_정보가_없다():
    """🔴 C1 — *"S3 입력에 Elo·동기·일정(T2 제외)·감독 발언·맞대결·시장·LLM
    문장이 **없다**"*.

    ⚠️ 돌연변이: `probmodel.run` 이 `base_prob`·`market`·`commentary` 를 읽게
       만들면 이 줄이 빨개진다.
    """
    import ast
    src = (ROOT / "app" / "core" / "probmodel.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "run"]
    assert fn, "🔴 `probmodel.run` 이 없다"
    said = ast.unparse(fn[0])
    for bad in ("base_prob", "adj_prob", "market", "elo", "commentary",
                "coach", "h2h", "stakes", "outlook", "llm"):
        assert bad not in said, f"🔴 S3 가 `{bad}` 를 읽는다(C1)"
    # 🔴 `facts` 에서 읽는 것은 **리그 평균·대회 유형**뿐이다
    whole = ast.unparse(tree)
    assert "match_total_baseline" in whole and "goal_share" in whole


def test_v7_C2_카드_확률이_S3_산출과_같다():
    """🔴 C2 — *"S5 이후 어느 단계도 확률을 바꾸지 않는다(S3 출력 = 카드 확률)"*."""
    from app.core import probmodel as _pm
    from app.core.state import RunState
    ref, facts, vs, _box, mr = _probset()
    got = _pm.run(ref, facts, mr, vs, state=RunState(match_key="x"))
    assert got.ok()
    sim = got.as_sim()
    for key in ("home", "draw", "away"):
        assert sim[key] == getattr(got, key)
    # 🔴 파이프라인이 그 수를 **그대로** 우리 열에 넣는다
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert 'layers["ours"] = _PT(home=prob.home' in src, (
        "🔴 카드 확률이 S3 에서 안 온다")


def test_v7_C4_상성_우위와_확률_방향이_같다():
    """🔴 C4 — *"상성 우위 팀 = S3 확률이 더 높은 팀(강도 '없음' 제외)"*.

    🔴 지금은 **구조로** 보장된다 — 같은 축 합이 λ 기울기를 만든다.
    """
    from app.core import probmodel as _pm
    from app.core.state import RunState
    ref, facts, vs, _box, mr = _probset()
    got = _pm.run(ref, facts, mr, vs, state=RunState(match_key="x"))
    edge = mr.edge_of()
    if edge and dict(mr.verdict).get("strength") != "없음":
        want = "home" if got.home >= got.away else "away"
        assert edge == want, (edge, got.home, got.away)


def test_v7_기여_합이_리그_평균_대비_변화와_같다():
    """🔴 3-4 — *"축0 x · 축1 y · 축2 z · 축3 w — **합 = 리그 평균 대비 변화**"*."""
    from app.core import probmodel as _pm
    from app.core.state import RunState
    ref, facts, vs, _box, mr = _probset()
    got = _pm.run(ref, facts, mr, vs, state=RunState(match_key="x"))
    base = _pm.league_base(ref, facts, vs)
    total = (float(got.home) - float(base["home"])) * 100.0
    assert abs(sum(got.share.values()) - total) < 0.05, (got.share, total)
    assert set(got.share) == {"axis0", "axis1", "axis2", "axis3"}
    # 🔴 축마다 **그 기여를 만든 변수 id**(상위 3개)
    assert set(got.share_refs) == set(got.share)


def test_v7_람다_이동이_상한을_지킨다():
    """🔴 3-6 — λ 이동은 `config/matchup_model.yaml` 의 `cap_pct` 안이다."""
    import math

    from app.core import matchup as _mu
    from app.core import probmodel as _pm
    from app.core.state import RunState
    ref, facts, vs, box, _mr = _probset()
    # 🔴 축0 을 아주 크게 벌려도 상한에서 잘린다
    big = _mu.MatchupReport(axes={"axis0": _mu.Axis(name="axis0", home=50.0,
                                                    away=0.0, gap=50.0)})
    got = _pm.run(ref, facts, big, vs, state=RunState(match_key="x"))
    cap = float(dict(_mu.table()["lambda_model"]).get("cap_pct")) / 100.0
    mean, _why = _pm.league_mean(facts, ref=ref)
    mul, _said = _pm.home_mul(facts, vs)
    # ⚠️ λ 는 소수 넷째 자리로 **반올림**해 담긴다 — 그 폭을 둔다
    assert float(got.lam["home"]) <= mean * mul * math.exp(cap) + 1e-3
    assert "상한" in got.why, got.why


def test_v7_C8_선수단_교체는_r_가중을_받는다():
    """🔴 C8 — *"squad_turnover 팀은 **r 가중**이 적용된다"*.

    ⚠️ 옛 계약은 *"기준 약함 ×0.5"* 를 셌다 — §2 가 그 고정 배율을 **지웠다**.
    """
    from app.core import form as _form
    from app.core import matchup as _mu
    from app.core import routing
    from app.core.schema import Variable
    ref = _ref()
    turn = Variable(id="TURN-home", type="squad_rotation", subject=ref.home,
                    favors="away", hardness="hard", weight=2.0,
                    claim="선수단 교체", quote="q")
    vs = routing.place([turn])
    r = _mu.r_of(vs, ref)
    assert 0.0 < r["home"] < 1.0 and r["away"] == 1.0, r
    # 🔴 축1 이 그 r 로 과거를 깎는다
    box = {"form": {"home": _form.TeamForm(team="H", n=10, adj_gf=20.0,
                                           adj_ga=10.0),
                    "away": _form.TeamForm(team="A", n=10, adj_gf=10.0,
                                           adj_ga=10.0)}}
    axis = _mu.axis1(box, vs, r=r)
    assert abs(float(axis.home) - 1.0 * r["home"]) < 1e-6, axis.home
    assert "r=" in axis.why
    # 🔴 그 r 은 **표**가 든다(코드에 수를 박지 않는다)
    assert "turnover_r" in str(_mu.table().get("axis1"))
