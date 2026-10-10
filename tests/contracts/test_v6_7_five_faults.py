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


def test_v6_일반화_문턱이_표에_있다():
    """🔴 ③ 일반화 — *"7자리 이상 바뀌고 빠진 선수가 명단에도 없으면"*."""
    from app.core import turnover as _turn
    box = dict(_turn.table().get("suspect") or {})
    assert int(box.get("changed")) == 7 and int(box.get("off_squad")) == 2
    assert _turn.suspect(changed=7, off_squad=2)
    assert not _turn.suspect(changed=6, off_squad=5)
    assert not _turn.suspect(changed=9, off_squad=1)
    assert not _turn.suspect(changed=None, off_squad=9), "🔴 못 센 칸을 의심했다"


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


def test_v6_교체팀은_기준_약함을_표시한다():
    """🔴 ③ — *"기준(Elo)·폼·골 내용은 전역 이전 기록이므로 '선수단 교체 — 기준
    약함' 표시, 가중을 낮춘다(적합 전 임시값 표시)"*."""
    from app.core import turnover as _turn
    w = _turn.weaken()
    assert 0.0 < w["elo"] < 1.0, w
    assert w["provisional"] and w["why"], w
    src = (ROOT / "app" / "core" / "stages"
           / "s2e_matchup.py").read_text(encoding="utf-8")
    assert "WEAK_MARK" in src and "weaken()" in src, "🔴 약화를 안 쓴다"
    # 🔴 1겹 카드가 그 표시를 낸다
    l1 = (ROOT / "app" / "core" / "layer1.py").read_text(encoding="utf-8")
    assert '.get("weak")' in l1, "🔴 1겹이 기준 약함을 안 적는다"


# ══════════════════════════════════════════════════════════════════
# ④ 확률은 한 곳
# ══════════════════════════════════════════════════════════════════

def test_v6_최종확률은_시뮬레이션_결과다():
    """🔴🔴 ④ — *"최종 확률 = **시뮬레이션(묶인 분포) 결과**. 카드의 '시뮬' 줄과
    최종 숫자가 **다르면 계약 실패**"*.

    ⚠️ 실사고 2026-10-10: 시뮬 **52%** · 최종 **38%** — 한 카드가 두 답을 냈다.
    """
    from app.core import layer1
    from app.core.schema import Card, Facts, ProbTriple
    sim = {"home": 0.41, "draw": 0.27, "away": 0.32,
           "over": {"1.5": 0.7, "2.5": 0.45, "3.5": 0.24},
           "first_wins": 0.66, "why": "시험"}
    card = Card(match=_ref(), facts=Facts(),
                matchup={"profile": {"home": 1, "away": 1}, "sim": sim},
                our_prob=ProbTriple(home=0.41, draw=0.27, away=0.32))
    said = layer1._sim_line(card.matchup)
    # 🔴 시뮬 줄의 세 수가 **최종 확률과 같아야** 한다
    for want in (f"{sim['home']:.0%}", f"{sim['draw']:.0%}",
                 f"{sim['away']:.0%}"):
        assert want in said, (want, said)
    probs = layer1._probs(card)
    for want in ("41%", "27%", "32%"):
        assert want in probs, (want, probs)
    # 🔴 파이프라인이 **시뮬 결과로 `ours` 를 덮는다**(그래야 둘이 같다)
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert 'layers["ours"] = _PT(home=said_sim["home"]' in src, (
        "🔴 최종 확률이 시뮬에서 안 온다")


def test_v6_시뮬_기울기가_확률에서_나온다():
    """🔴🔴 ④ — λ 기울기를 **확률층의 홈/원정 비를 맞춰** 푼다(계수가 없다).

    ⚠️ 돌연변이: `solve_tilt` 를 지우고 폼 차만 쓰면 — 시뮬이 ①②③(Elo·라인업·
       변수·전략)을 **전혀 모르는** 수를 내고 최종과 갈라진다.
    """
    from app.core.stages import s2e_matchup as _s2e
    box: dict = {"fired": [], "fired2": [], "form": {}}
    base = 2.6
    for want in (1.0, 1.6, 0.6):
        t = _s2e.solve_tilt(box, base, want)
        got, _ = _s2e._sim_at(box, base, t, axis2=False, axis3=False)
        assert abs((got.home / got.away) - want) < 0.02, (want, t,
                                                          got.home / got.away)
    # 🔴 비가 1 이면 기울기는 0 쪽이다(홈 이점을 지어내지 않는다)
    assert abs(_s2e.solve_tilt(box, base, 1.0)) < 0.01


def test_v6_기여분해_합이_잠정에서_최종까지와_같다():
    """🔴🔴 ④ — *"잠정→최종 변화는 축별 기여(폼·전술·골 내용)로 분해해 **합이
    맞게**"*. 🔴 단계를 쌓아 재므로 잔차가 **0** 이다."""
    from app.core.schema import Facts, ProbTriple
    from app.core.stages import s2e_matchup as _s2e
    from app.core.state import RunState
    facts = Facts(standings={"match_total_baseline": 2.6})
    box: dict = {"fired": [], "fired2": [], "form": {}}
    st = RunState(match_key="x:1")
    got = _s2e.final_sim(_ref(), facts, box, state=st,
                         ours=ProbTriple(home=0.45, draw=0.27, away=0.28),
                         before=ProbTriple(home=0.40, draw=0.28, away=0.32))
    share = dict(got["share"])
    total = (float(got["home"]) - float(got["before"]["home"])) * 100.0
    assert abs(sum(share.values()) - total) < 0.03, (share, total)
    assert set(share) == {"폼", "전술", "골 내용"}, share


def test_v6_얹는_몫이_상한_반_로그오즈를_넘지_않는다():
    """🔴🔴 ④ — 폼·축2·축3 을 **합친 몫**이 경기당 ±0.5 로그 오즈 안이다.

    ⚠️ 실측 2026-10-10(재현): 폼 기울기를 그냥 얹으니 홈 승이 42% → **58%**
       (+0.72 로그 오즈)로 움직였다 — 상한의 한 배 반이다.
    ⚠️ 돌연변이: `_within_cap` 을 지우면 이 줄이 빨개진다.
    """
    import math

    from app.core import form as _form
    from app.core import strategy as _st
    from app.core.schema import Facts, ProbTriple
    from app.core.stages import s2e_matchup as _s2e
    from app.core.state import RunState
    cap, _pct = _st.caps()
    facts = Facts(standings={"match_total_baseline": 2.5})
    # 🔴 그 경기 그대로 — 폼 차 1.13(홈 −0.17 · 원정 −1.30)
    box: dict = {"fired": [], "fired2": [],
                 "form": {"home": _form.TeamForm(team="H", n=10, adj_gf=10.0,
                                                 adj_ga=11.7),
                          "away": _form.TeamForm(team="A", n=10, adj_gf=10.0,
                                                 adj_ga=23.0)}}
    ours = ProbTriple(home=0.42, draw=0.27, away=0.31)
    got = _s2e.final_sim(_ref(), facts, box, state=RunState(match_key="x"),
                         ours=ours, before=ours)

    def logit(x):
        return math.log(x / (1 - x))

    # 🔴 확률층만 쓴 시뮬과의 차가 상한 안이다
    t = _s2e.solve_tilt(box, 2.5, 0.42 / 0.31)
    ref_got, _ = _s2e._sim_at(box, 2.5, t, axis2=False, axis3=False)
    moved = logit(float(got["home"])) - logit(ref_got.home)
    assert abs(moved) <= cap + 1e-6, (moved, cap)
    assert got["cut"], "🔴 잘렸는데 그 사실을 안 적었다(#3)"
    assert "상한" in got["cut"]


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


def test_v6_시뮬_스코어는_무게_큰_순으로_든다():
    """🔴 ④ — ⚠️ 열쇠 순으로 40칸을 자르면 **상위 스코어가 사라진다**."""
    from app.core.schema import Facts, ProbTriple
    from app.core.stages import s2e_matchup as _s2e
    from app.core.state import RunState
    facts = Facts(standings={"match_total_baseline": 2.6})
    got = _s2e.final_sim(_ref(), facts, {"fired": [], "fired2": [], "form": {}},
                         state=RunState(match_key="x"),
                         ours=ProbTriple(home=0.45, draw=0.27, away=0.28),
                         before=ProbTriple(home=0.45, draw=0.27, away=0.28))
    rows = list(dict(got["scores"]).items())
    assert rows, "🔴 스코어 분포가 비었다"
    vals = [float(v) for _k, v in rows]
    assert vals == sorted(vals, reverse=True), "🔴 무게 순이 아니다"
    # 🔴 가장 무거운 스코어가 **한 자리 수 득점**이다(열쇠 순이면 `0-0` 쪽만 남는다)
    (h, a), top = rows[0]
    assert (h + a) <= 4, (h, a, top)


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
