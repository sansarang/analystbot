"""🔴🔴 **충돌·단독 갈래 판정** — 사용자 지시 2026-10-16.

> 충돌되는 것·한쪽만 나오는 것도 **버리는 게 아니라 어느 쪽이 맞는지 확인**해야
> 한다 … 충돌 갈래 — 각 LLM 이 낸 내용을 **다른 LLM 이 서치해서 검증**하는
> 걸로, **옳다 그르다를 판단**한다

🔴 잠금 다섯(`app/core/branchjudge.py` 머리말):
  ① 근거(잰 수·접지된 인용) 없이 **승격 금지**
  ② **자기 주장을 자기가 판정 금지**(교차 강제)
  ③ LLM 은 **글자만** — 방향은 부등호 표, 가중은 코드
  ④ 검증에 쓴 **주소·인용이 변수 글에 남는다**
  ⑤ **갈래 수 상한**이 있다(카드 상한 안)
"""
from __future__ import annotations

import inspect
import pathlib

from app.core import branchjudge as bj
from app.core import strategy_llm as sl

ROOT = pathlib.Path(__file__).resolve().parents[2]


class _XI:
    def __init__(self, form: str = "", rows: list | None = None) -> None:
        self.formation = form
        self.players: list = []
        self.lineup = list(rows or [])
        # 🔴 운영은 `XI.bench` 를 **이름 글자 목록**으로 싣는다(번호가 없다 ·
        #    실측 2026-10-17) — 그래서 벤치 능력치는 못 받는다.
        self.bench: list[str] = []


class _P:
    """🔴 선발 한 명 — ⚠️ `flank` 는 **운영이 만드는 글자**여야 한다.

    실사고 2026-10-17: 여기 `flank="L"` 을 써서 `_flank_n` 의 거짓 수
    (`("L","R")` 로 세어 **영구히 0명**)를 **초록으로 덮고 있었다**.
    🔴 운영이 싣는 글자는 `fotmob.FLANKS`(`왼`·`중앙`·`오른`)뿐이고,
       좌표가 없으면 **빈 글자**다(CLAUDE.md #5 — 대역은 운영 모양으로).
    """

    def __init__(self, pos: str = "", flank: str = "", name: str = "x",
                 pid: int | None = None) -> None:
        from app.collect import fotmob as _fm
        assert flank in ("", *_fm.FLANKS), f"🔴 운영에 없는 측면 글자: {flank!r}"
        self.name, self.pos, self.flank = name, pos, flank
        # 🔴 운영은 `Player.pid`(fotmob 선수 번호)를 싣는다 — 능력치의 열쇠다
        self.pid = pid


class _R:
    home, away = "team:000001", "team:000002"
    home_name, away_name, competition = "A팀", "B팀", "리그"


class _F:
    def __init__(self, xi: dict | None = None, recent: dict | None = None
                 ) -> None:
        self.xi = dict(xi or {})
        self.recent = dict(recent or {})
        self.schedule: dict = {}


class _Plan:
    def __init__(self, facts: dict | None = None) -> None:
        self.facts = dict(facts or {})


def _branch(kind: str, mode: str = "충돌",
            claims: list | None = None) -> bj.Branch:
    return bj.Branch(kind=kind, mode=mode, claims=list(claims or [
        bj.Claim(provider="deepseek", cmp=">", goals_cmp="=", text="홈이 크다"),
        bj.Claim(provider="solar", cmp="<", goals_cmp="=", text="원정이 크다")]))


# ══════════════════════════════════════════════════════════════════
# 🔴 1단 — 코드가 가진 수로 먼저 가린다(검색 전에)
# ══════════════════════════════════════════════════════════════════



def _mid_box(h: float, a: float, n: int = 3) -> dict:
    """🔴 중앙 MF 능력치 대역 — **표가 고른 지표**로만 만든다(#1 사본 금지)."""
    from app.core import ability as _ab
    traits = list(dict(_ab.branch_table()["중원 수싸움"]).get("traits") or [])
    def _one(v: float) -> dict:
        return {"items": [{"key": k, "value": v} for k in traits]}
    return {**{f"H{i}": _one(h) for i in range(1, n + 1)},
            **{f"A{i}": _one(a) for i in range(1, n + 1)}}


def _mid_facts(n: int = 3) -> "_F":
    """🔴 양 팀 중앙 MF `n` 명씩 — **포메이션은 같게**(머릿수로는 못 가린다)."""
    return _F(xi={"team:000001": _XI("4-3-3", [
                      _P("MF", "중앙", f"H{i}", i) for i in range(1, n + 1)]),
                  "team:000002": _XI("4-3-3", [
                      _P("MF", "중앙", f"A{i}", 10 + i)
                      for i in range(1, n + 1)])})


def test_bj1_중원은_능력치로_가린다() -> None:
    """🔴🔴 **머릿수가 아니라 능력치다** — 사용자 지시 2026-10-17.

    > 선발 명단·후보명단이 들어오면 **그 선수들의 능력치로 변수를 결정**하게
    > 한다 … 전술에 관련해서는 … **변수에 그렇게 들어가야 한다**

    ⚠️ 실측 2026-10-17(가시와 vs 나고야): 1단이 `중원 수싸움` 을 머릿수로
       갈랐다(`3-4-2-1`=4 ↔ `4-3-3`=3 → 홈). 선수가 누구든 수만 같으면 같은
       답이다. 🔴 **포메이션이 같아도 능력치가 다르면 답이 달라야 한다** —
       그것을 여기서 센다.
    """
    #  🔴 포메이션을 **똑같이** 둔다 — 머릿수로는 절대 못 가린다
    facts = _F(xi={"team:000001": _XI("4-3-3", [
                       _P("MF", "중앙", "H1", 1), _P("MF", "중앙", "H2", 2),
                       _P("MF", "중앙", "H3", 3)]),
                   "team:000002": _XI("4-3-3", [
                       _P("MF", "중앙", "A1", 4), _P("MF", "중앙", "A2", 5),
                       _P("MF", "중앙", "A3", 6)])})
    def _box(h: float, a: float) -> dict:
        from app.core import ability as _ab
        traits = list(dict(_ab.branch_table()["중원 수싸움"]).get("traits") or [])
        def _one(v: float) -> dict:
            return {"items": [{"key": k, "value": v} for k in traits]}
        return {**{f"H{i}": _one(h) for i in (1, 2, 3)},
                **{f"A{i}": _one(a) for i in (1, 2, 3)}}
    #  ① 홈 중원이 낫다 → `>`
    bj.set_squad(_box(0.80, 0.30))
    op, why = bj.by_numbers(_branch("중원 수싸움"), _R(), facts)
    assert op == ">", (op, why)
    assert "0.80" in why and "0.30" in why, why
    assert "능력치" in why, why
    #  ② **같은 포메이션인데 능력치를 뒤집으면 답도 뒤집힌다**(머릿수였다면 못 한다)
    bj.set_squad(_box(0.30, 0.80))
    op2, why2 = bj.by_numbers(_branch("중원 수싸움"), _R(), facts)
    assert op2 == "<", (op2, why2)
    #  ③ 능력치를 **한 명도 못 받았으면** 빈 부등호다(2단으로 간다 · #3)
    bj.set_squad({})
    op3, why3 = bj.by_numbers(_branch("중원 수싸움"), _R(), facts)
    assert op3 == "" and "못 받았다" in why3, (op3, why3)


def test_bj2_차이가_작으면_안_가린다() -> None:
    """🔴 문턱 아래면 **안 가린다** — `=` 를 채택하지 않는다.

    ⚠️ 2026-10-17 부터 전술 갈래는 **능력치**로 가린다 — 문턱도 백분위 차다
       (`config/ability.yaml` 의 `branch_gap`).
    """
    from app.core import ability as _ab
    gap = _ab.branch_gap()
    #  🔴 차이를 문턱 **바로 아래**로 둔다 — 지어낸 수가 아니라 표에서 끌어온다
    bj.set_squad(_mid_box(0.50 + gap / 4.0, 0.50 - gap / 4.0))
    op, why = bj.by_numbers(_branch("중원 수싸움"), _R(), _mid_facts())
    assert op == "" and "안 가린다" in why, (op, why)
    #  ⚠️ 그리고 **문턱을 넘기면** 가린다(검사가 늘 빈손이 아니다)
    bj.set_squad(_mid_box(0.50 + gap, 0.50 - gap))
    op2, _why2 = bj.by_numbers(_branch("중원 수싸움"), _R(), _mid_facts())
    assert op2 == ">", op2


def test_bj3_측면은_lineup_에서_센다() -> None:
    """🔴🔴 실측 2026-10-17 — 자리·측면은 **`XI.lineup`** 에 있다.

    ⚠️ `XI.players` 는 **이름 글자 목록**(`list[str]`)이다. 그 칸을 Player 로
       읽으면 자리가 **늘 빈 글자**가 된다(⑤-b2 프롬프트가 그 병이었다).
    """
    # 🔴 **운영이 만드는 글자**로만 쓴다(`왼`·`중앙`·`오른`)
    home = _XI("4-4-2", [_P("LM", "왼"), _P("RM", "오른"), _P("LB", "왼"),
                         _P("RB", "오른"), _P("CB", "중앙"), _P("GK", "중앙")])
    away = _XI("4-4-2", [_P("CB", "중앙"), _P("CM", "중앙"), _P("GK", "중앙")])
    op, why = bj.by_numbers(_branch("측면 집중"), _R(),
                            _F(xi={"team:000001": home, "team:000002": away}))
    assert op == ">", (op, why)
    assert "홈 **4명**" in why and "원정 **0명**" in why, why
    # 🔴 글자 표는 **`fotmob` 하나**다 — 여기서 새로 적으면 또 어긋난다
    from app.collect import fotmob as fm
    assert fm.WINGS == ("왼", "오른") and "중앙" in fm.FLANKS
    assert "_fm.WINGS" in inspect.getsource(bj._flank_n), "🔴 표를 안 쓴다"
    # 🔴 자리 글자가 없으면 **못 셌다**고 적는다(0 으로 때우지 않는다 · #3)
    op0, why0 = bj.by_numbers(_branch("측면 집중"), _R(),
                              _F(xi={"team:000001": _XI("4-4-2"),
                                     "team:000002": away}))
    assert op0 == "" and "못 셌다" in why0, why0
    # 🔴🔴 **좌표가 안 와서 아무도 측면 글자가 없으면** — 그것도 **못 쟀다**다.
    #    ⚠️ 이 칸이 `0 ↔ 0` 으로 적히던 것이 실사고였다(거짓 수).
    blind = _XI("4-4-2", [_P("CB"), _P("CM"), _P("GK")])
    op1, why1 = bj.by_numbers(_branch("측면 집중"), _R(),
                              _F(xi={"team:000001": blind,
                                     "team:000002": away}))
    assert op1 == "" and "아무 선수에게도 없다" in why1, why1
    assert "0명" not in why1, f"🔴 못 잰 것을 0 으로 적는다 — {why1}"


def test_bj4_휴식일로_가린다() -> None:
    """🔴 휴식일이 **짧은 쪽이 불리**하다 — 그 쪽이 `cmp` 의 작은 쪽이다."""
    facts = _F(recent={"team:000001": {"rest_days": 2},
                       "team:000002": {"rest_days": 7}})
    op, why = bj.by_numbers(_branch("일정·피로도"), _R(), facts)
    assert op == "<", (op, why)
    assert "홈 **2일**" in why and "원정 **7일**" in why, why
    # 🔴 못 쟀으면 **이름으로** 남긴다
    op0, why0 = bj.by_numbers(_branch("일정·피로도"), _R(), _F())
    assert op0 == "" and "못 쟀다" in why0, why0


def test_bj5_수비는_실점_평균으로_가리고_무엇을_쟀는지_적는다() -> None:
    """🔴🔴 **거짓 수 금지** — 실점 평균은 **라인 높이가 아니다**.

    ⚠️ 이 저장소가 어제까지 세 번 다친 자리가 *"다른 것을 잰 수를 그 갈래의
       수라고 적는 것"* 이다. 🔴 그래서 **무엇을 쟀는지** 사유에 그대로 쓴다.
    """
    facts = _F(recent={"team:000001": {"recent_conceded_avg": 0.6},
                       "team:000002": {"recent_conceded_avg": 2.4}})
    op, why = bj.by_numbers(_branch("수비 라인"), _R(), facts)
    assert op == ">", (op, why)          # 홈이 덜 먹혔다 → 홈이 크다
    assert "실점 평균" in why and "라인 높이가 아니라 수비 상태" in why, why
    # 🔴 실점이 없으면 **ΔD** 로 간다(전략 판정이 이미 센 수)
    plan = _Plan({"L7": {"side": "home", "kind": "delta_def", "value": 5.0},
                  "A7": {"side": "away", "kind": "delta_def", "value": -40.0}})
    op2, why2 = bj.by_numbers(_branch("수비 라인"), _R(), _F(), plan)
    assert op2 == ">" and "ΔD" in why2, (op2, why2)
    # 🔴 둘 다 없으면 **안 가린다**
    op3, why3 = bj.by_numbers(_branch("수비 라인"), _R(), _F(), _Plan())
    assert op3 == "" and "⬜" in why3, (op3, why3)


def test_bj6_수가_없는_갈래는_2단으로_간다() -> None:
    #  🔴 **표에 있는 갈래는 빼고 본다** — `빌드업`·`압박 높이` 는 이제 능력치가
    #     가린다(2026-10-17). 그 둘은 재료가 없으면 *"능력치를 못 받았다"* 로
    #     떨어지고, 그 사유를 끝까지 들고 간다(아래에서 따로 센다).
    from app.core import ability as _ab
    said_tbl = set(_ab.branch_table())
    bj.set_squad({})
    for kind in ("세트피스", "역습 성향", "교체 운용", "기사 사실"):
        assert kind not in said_tbl, f"🔴 `{kind}` 가 표에 생겼다 — 시험을 옮겨라"
        op, why = bj.by_numbers(_branch(kind), _R(), _F())
        assert op == "" and "2단" in why, (kind, op, why)
    #  🔴 표에 있는데 **재료가 없으면** 왜 못 가렸는지가 남아야 한다(#3)
    for kind in ("빌드업", "압박 높이"):
        op, why = bj.by_numbers(_branch(kind), _R(), _F())
        assert op == "", (kind, op, why)
        assert "능력치" in why, (kind, why)


def test_bj7_1단은_투표가_아니라_측정이다() -> None:
    """🔴 수가 가리킨 쪽을 쓴다 — **어느 모델도 그 말을 안 했어도** 쓴다."""
    one = _branch("중원 수싸움", claims=[
        bj.Claim(provider="deepseek", cmp="<", goals_cmp="=", text="원정"),
        bj.Claim(provider="solar", cmp="<", goals_cmp="=", text="원정")])
    #  🔴 **두 모델 다 `<` 라고 했는데** 능력치는 홈이 낫다 → 수가 이긴다
    bj.set_squad(_mid_box(0.85, 0.25))
    said = bj.stage1([one], _R(), _mid_facts())
    assert one.picked == ">" and one.by == "수", (one.picked, one.by)
    assert one.picked_pv == "" and "어느 모델도" in one.why, one.why
    assert "수로 가렸다" in said, said
    # 🔴 그 수를 사유에 적는다(승격 근거다)
    ok, why = bj.may_promote(one)
    assert ok and "능력치" in why and "0.85" in why, why


def test_bj7b_1단은_총골_방향을_올리지_않는다() -> None:
    """🔴🔴 **코드는 총골을 잰 적이 없다**(계약 리뷰어 2026-10-17 · 절제로 잡음).

    1단이 잰 것은 **중앙 수·측면 수·휴식일·실점 평균**이다. 부등호가 맞은
    모델의 `goals_cmp` 를 그대로 가져오면 **모델만 말한 총골 방향**이
    *"잰 수"* 를 근거로 확률 자리에 든다 — 변수 글에는 `중앙 수 홈 5 ↔ 원정 4`
    만 남아 그 사실이 **읽히지 않는다**.
    🔴 그래서 1단 채택은 **승패 방향만** 올린다. 넓힐지는 사용자 결정이다
       (`docs/fable/questions/2026-10-17_stage1_goals.md`).
    ⚠️ 2단(문서로 `옳다` 를 받은 경우)은 다르다 — 그 주장 **전체**가 판정을
       받았으므로 `goals_cmp` 도 함께 올린다.
    """
    one = _branch("중원 수싸움", claims=[
        bj.Claim(provider="deepseek", cmp=">", goals_cmp="<", text="홈 중원"),
        bj.Claim(provider="solar", cmp="<", goals_cmp="<", text="원정 중원")])
    #  🔴 능력치가 홈을 가리킨다 → `deepseek`(`>`) 과 같은 쪽이다
    bj.set_squad(_mid_box(0.85, 0.25))
    bj.stage1([one], _R(), _mid_facts())
    assert one.picked == ">" and one.picked_pv == "deepseek"
    # 🔴 **총골은 안 올린다** — 모델이 `<`(적겠다) 라고 했어도 `=` 다
    assert one.picked_goals == "=", one.picked_goals
    assert "총골 방향은 안 올린다" in one.why, one.why
    # 🔴 변수까지 그렇게 간다(`goals="none"`)
    got = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="중원 수싸움", cmp=">", goals_cmp="<",
        text=f"{sl.CONFLICT} — deepseek `>` x ↔ solar `<` y")]), _R())
    assert got[0].goals == "down"          # ⑤-b2 가 낸 원래 값
    out, _said = bj.apply([one], got)
    assert (out[0].favors, out[0].goals) == ("home", "none"), \
        (out[0].favors, out[0].goals)

    # 🔴 **2단 채택은 총골도 올린다**(주장 전체가 문서 판정을 받았다)
    two = _branch("기사 사실", claims=[
        bj.Claim(provider="deepseek", cmp="<", goals_cmp="<", text="저득점")])
    two.by, two.picked, two.picked_goals = "교차", "<", "<"
    two.picked_pv, two.judge_pv = "deepseek", "solar"
    two.quote, two.url, two.grounded = "a" * 30, "https://x.example/a", True
    two.why = f"{bj.JUDGED} · 2단 교차"
    got2 = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="기사 사실", cmp="<", goals_cmp="<",
        text=f"{sl.ALONE} [deepseek] 저득점")]), _R())
    out2, _s2 = bj.apply([two], got2)
    assert (out2[0].favors, out2[0].goals) == ("away", "down"), \
        (out2[0].favors, out2[0].goals)


# ══════════════════════════════════════════════════════════════════
# 🔴 2단 — 교차 검증(② 자기 주장은 자기가 판정하지 않는다)
# ══════════════════════════════════════════════════════════════════


def test_bj8_자기_주장은_자기가_판정하지_않는다() -> None:
    assert bj.judge_pv_of("deepseek") == "solar"
    assert bj.judge_pv_of("solar") == "deepseek"
    # 🔴 상대가 없으면 **판정하지 않는다**(빈 글자) — 자기 검증 금지
    assert bj.judge_pv_of("solar", providers=("solar",)) == ""
    src = inspect.getsource(bj.cross)
    assert "judge_pv_of(one.provider)" in src, "🔴 교차를 강제하지 않는다"


def test_bj9_인용이_본문에_없으면_버린다() -> None:
    """🔴🔴 **접지** — 모델 기억으로 판정하면 안 된다(절대규칙 5).

    `s1_resolve._by_llm` 에 쓴 그 규율 그대로 — 본문에 없는 글자는 버린다.
    """
    docs = [("https://x.example/a",
             "Sporting kept a deep block all evening and conceded twice.")]
    ok, url = bj._ground("kept a deep block all evening", docs)
    assert ok and url == "https://x.example/a"
    # 🔴 본문에 없는 글자 → 거짓
    assert bj._ground("pressed high up the pitch always", docs)[0] is False
    # ⚠️ 너무 짧은 인용은 근거가 아니다(아무 글에나 들어 있다)
    assert bj._ground("deep", docs)[0] is False


def test_bj9b_판정_칸_이름이_절대규칙_5_와_안_부딪힌다() -> None:
    """🔴🔴 절대규칙 5 의 **글자** — *"`verdict` 필드에 LLM 출력이 닿으면
    계약 실패"*. 이 칸은 뜻으로는 등급이 아니지만 **이름이 같았다**(계약 리뷰어
    2026-10-17). 🔴 규칙 문장을 좁히는 것은 사용자 몫이라 **이름을 비켰다**.
    """
    assert set(bj.JudgeOut.model_fields) == {"ruling", "quote", "url"}, \
        bj.JudgeOut.model_fields
    assert "verdict" not in bj.JudgeOut.model_fields
    assert "verdict" not in {f for f in bj.Claim.__dataclass_fields__}
    # 🔴 LLM 이 낼 수 있는 글자는 **표의 셋**뿐이다(열거로 잠근다)
    assert bj.RULINGS == ("옳다", "그르다", "모르겠다")
    src = inspect.getsource(bj._rule_one)
    assert 'enums={"ruling": list(RULINGS)}' in src, "🔴 열거로 안 잠근다"
    # 🔴 질의 쪽 출력 칸도 **글자뿐**이다(사실·수 칸이 없다)
    assert set(bj.JQueries.model_fields) == {"queries", "langs", "sites"}, \
        bj.JQueries.model_fields


def test_bj10_판정이_본문을_읽는다는_것이_프롬프트에_있다() -> None:
    src = inspect.getsource(bj._rule_one)
    assert "네 기억으로 판정하지" in src, "🔴 모델 기억을 안 막는다"
    assert "글자 그대로" in src and "대조" in src, src[-500:]
    # 🔴 질의를 쓰는 쪽도 **사실을 말하지 않는다**
    src_q = inspect.getsource(bj._queries)
    assert "네 기억으로 답하지 마라" in src_q, src_q[:800]
    # 🔴 질의 검열은 **기존 두 자리**다(새 규칙을 짓지 않는다 · 사본 금지)
    assert "querywriter.keep" in src_q and "query_ok" in src_q


def test_bj11_던지는_통로는_기존_사슬이다() -> None:
    """🔴 새 엔진·새 fetch 경로를 만들지 않는다."""
    src = inspect.getsource(bj._docs)
    assert "chain.query" in src and "_ft.body_of" in src, src[:600]
    assert "aiohttp" not in src and "requests" not in src
    # 🔴🔴 **엔진을 지정한다** — 표는 `rules.news_engines()` 하나다(사본 금지)
    #    ⚠️ 지정 없이 쏘면 질의를 무시하는 엔진이 섞여 **포털·티켓**에 예산을
    #       태운다(이 저장소 실측 2026-10-02).
    assert "rules.news_engines()" in src, "🔴 엔진을 안 지정한다"
    assert "engines=eng" in src, src[-900:]
    # 🔴 **현지어 먼저** 던진다 — 일본어 질의를 영어 창으로 던지지 않는다
    assert "lang=lang" in src, "🔴 언어를 안 쓴다"


def test_bj11b_전술_용어로_질의하지_않는다() -> None:
    """🔴🔴 실측 2026-10-17 — 갈래 이름을 질의에 넣으면 **포털**이 걸린다.

    ⚠️ 받은 본문이 `jleague.jp` 첫 화면(5,174자) · DAZN 중계 안내 · **8월 25일
       묵은 기사**였고 판정은 당연히 `모르겠다` 였다. 🔴 질의는 주장 안의
       **확인 가능한 알맹이**(선수 이름·결장·선발 명단·순위)를 겨냥해야 한다.
    """
    src = inspect.getsource(bj._queries)
    assert "전술 용어를 질의에 쓰지 마라" in src, "🔴 그 규칙이 없다"
    for w in ("결장", "선발 명단", "최근 경기", "일정"):
        assert w in src, w
    # 🔴🔴 **낱말을 섞지 않는다** — ⚠️ 실측 2026-10-17: 보기를 한국어로만 적어
    #    모델이 `柏レイソル 柏田 선발` 처럼 섞어 던졌다(그 매체에서 안 걸린다).
    assert "질의 전체를 한 언어로" in src, "🔴 섞는 것을 안 막는다"
    for w in ("予想スタメン", "injury", "alineación probable"):
        assert w in src, w
    # 🔴 언어 코드는 **그 표가 원본**이다(여기서 새로 적지 않는다)
    from app.core.stages import s4b_gapsearch as gs
    assert bj._LANGS == tuple(gs.LANGS), "🔴 언어 표를 따로 지었다(사본)"
    assert "enums={\"langs\"" in src, "🔴 언어 코드를 안 잠근다"


def test_bj11c_엉뚱한_글은_버린다() -> None:
    """🔴🔴 **"글이 그 말을 안 했다" 와 "엉뚱한 글을 읽었다" 는 다르다**.

    ⚠️ 길이 문턱만으로는 포털 첫 화면(5,174자)이 **통과한다** — 그 글로 나온
       `모르겠다` 는 판정이 아니라 **잡음**이다(실측 2026-10-17).
    🔴 팀 표기 선필터를 둔다. ⚠️ 표기가 없으면 **거르지 않는다**.
    """
    assert bj._about("Kashiwa Reysol held Nagoya", ["Kashiwa", "Nagoya"])
    assert not bj._about("오늘의 주요 경기 일정과 중계 안내", ["Kashiwa"])
    # 🔴 표기를 못 만들었으면 **다 버리지 않는다**(없는 검문 금지)
    assert bj._about("아무 글", [])
    assert bj._about("아무 글", ["ab"])        # 두 글자 표기는 안 센다
    src = inspect.getsource(bj._docs)
    assert "n_off" in src and "팀 표기 없어 버린 본문" in src, \
        "🔴 버린 수를 안 남긴다(#3)"


def test_bj11c2_선필터가_실제로_버린다(monkeypatch) -> None:  # noqa: ANN001
    """🔴🔴 **글자 검사로는 못 센다**(절제로 잡았다 · 2026-10-17).

    ⚠️ `test_bj11c` 는 `_about` 를 **직접** 부르고 `_docs` 의 소스 글자만 봤다 —
       🔴 그래서 `_docs` 에서 **그 호출을 꺼도 초록**이었다(D46 과 같은 결:
       글자가 있는 것과 그것을 **부르는** 것은 다르다).
    🔴 그래서 `_docs` 를 **실제로 돌려** 버리는지 센다(사슬·본문만 대역이다).
    """
    import asyncio

    class _H:
        def __init__(self, url: str) -> None:
            self.url, self.snippet = url, ""

    class _Chain:
        async def query(self, text, *, lang="ko", engines=None):  # noqa: ANN001
            return [_H("https://x.example/a"), _H("https://x.example/b")]

    body = {"https://x.example/a": "Kashiwa Reysol beat Nagoya " + "x" * 500,
            "https://x.example/b": "오늘의 중계 안내입니다 " + "y" * 500}

    async def fake_body(net, url, **kw):  # noqa: ANN001
        return body[url], None, []

    from app.core.search import fetch as _ft
    monkeypatch.setattr(_ft, "body_of", fake_body)
    # 🔴 날짜 힌트가 없는 주소다 → `too_old` 는 **받는다**(모르는 것을 안 버린다)
    got, said = asyncio.run(bj._docs(["Kashiwa Nagoya"], net=None,
                                     chain=_Chain(), state=None,
                                     langs=["ja"], aliases=["Kashiwa"]))
    assert [u for u, _b in got] == ["https://x.example/a"], got
    assert "팀 표기 없어 버린 본문 1건" in said, said
    # 🔴 표기를 못 만들었으면 **거르지 않는다**(없는 검문으로 다 버리지 않는다)
    got2, _s2 = asyncio.run(bj._docs(["Kashiwa Nagoya"], net=None,
                                     chain=_Chain(), state=None,
                                     langs=["ja"], aliases=[]))
    assert len(got2) == 2, got2


# ══════════════════════════════════════════════════════════════════
# 🔴 3단 — ① 근거 없이 승격 금지 · ④ 인용·주소를 글에 남긴다
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# 🔴 손댈 자리 셋(사용자 지시 2026-10-17) — 2단의 상류를 고친다
# ══════════════════════════════════════════════════════════════════


def test_bj11d_현지어_매체는_robots_확인_뒤에만_쓴다() -> None:
    """🔴🔴 손댈 자리 ① — 지정 없이 쏘면 그 나라 매체 대신 **포털·학술 PDF**가
    걸린다(실측: `Atlas Duk no convocado` 6건이 researchgate·학회 PDF·
    huggingface·네이버 도움말).

    🔴 통로는 **이미 있다** — `querywriter.hosts`(꼴) → `check_hosts`(robots
       를 받아 실재 확인) → `site_queries`(`site:` 로 기존 사슬에 넣는다).
    ⚠️ 지어낸 주소를 쓰지 않는다(#4) — 확인 전에는 **안 쓴다**.
    """
    from app.core import querywriter as qw
    assert "sites" in bj.JQueries.model_fields, "🔴 매체를 안 받는다"
    src_q = inspect.getsource(bj._queries)
    assert "querywriter.hosts(" in src_q, "🔴 꼴 검사를 안 쓴다(제 파서를 지었나)"
    src_c = inspect.getsource(bj.cross)
    assert "_qw.check_hosts(" in src_c, "🔴 robots 확인 없이 쓴다(#4)"
    # 🔴 확인이 **실패하면 안 쓴다**(없는 매체로 좁히면 0건이 된다)
    assert "site: 안 쓴다" in src_c, src_c[-1500:]
    src_d = inspect.getsource(bj._docs)
    assert "_qw.site_queries(" in src_d, "🔴 `site:` 를 사슬에 안 넣는다"
    # 🔴 상한은 `querywriter` 가 든다(사본 금지)
    assert bj._SITE_CAP == qw.MAX_SITES


def test_bj11e_묵은_문서는_열지_않는다() -> None:
    """🔴🔴 손댈 자리 ② — 판정 대상은 **오늘의 팀 사정**이다.

    ⚠️ 실측 2026-10-17: 2단이 `footballchannel.jp/2026/08/25/…`(두 달 전
       기사)를 읽고 판정을 시도했다. 🔴 판정하는 함수는 `datehint.too_old`
       **하나**이고, 그 규칙은 *"날짜 힌트가 없으면 **받는다**"* 다.
    """
    from app import datehint as dh
    src = inspect.getsource(bj._docs)
    assert "_dh.too_old(" in src, "🔴 날짜를 안 본다"
    assert "n_old" in src and "묵은 문서" in src, "🔴 버린 수를 안 남긴다(#3)"
    # 🔴 그 규칙 자체를 확인한다 — 창 밖이면 버리고, **모르면 받는다**
    import datetime as _dt
    now = _dt.datetime(2026, 10, 17, tzinfo=_dt.timezone.utc)
    old_url = "https://www.footballchannel.jp/2026/08/25/post992952/"
    assert dh.too_old(old_url, now=now)[0] is True
    assert dh.too_old("https://x.example/news/abc", now=now)[0] is False


def test_bj11e2_묵은_문서를_실제로_안_연다(monkeypatch) -> None:  # noqa: ANN001
    """🔴🔴 **글자 검사로는 못 센다**(절제로 잡았다) — `n_old += 1` 을 `+= 0`
    으로 바꿔도 `test_bj11e` 는 **초록**이었다.

    🔴 그래서 `_docs` 를 돌려 **묵은 주소를 열지 않는지** 센다. ⚠️ 이 글은
       실사고에서 실제로 읽힌 그 기사다(`/2026/08/25/`).
    """
    import asyncio

    class _H:
        def __init__(self, url: str) -> None:
            self.url, self.snippet = url, ""

    OLD = "https://www.footballchannel.jp/2026/08/25/post992952/"
    NEW = "https://www.footballchannel.jp/2026/10/17/post999999/"

    class _Chain:
        async def query(self, text, *, lang="ko", engines=None):  # noqa: ANN001
            return [_H(OLD), _H(NEW)]

    opened: list[str] = []

    async def fake_body(net, url, **kw):  # noqa: ANN001
        opened.append(url)
        return "Kashiwa Reysol " + "x" * 500, None, []

    from app import window as _w
    from app.core.search import fetch as _ft
    import datetime as _dt
    monkeypatch.setattr(_ft, "body_of", fake_body)
    monkeypatch.setattr(_w, "now_utc",
                        lambda: _dt.datetime(2026, 10, 17,
                                             tzinfo=_dt.timezone.utc))
    got, said = asyncio.run(bj._docs(["Kashiwa"], net=None, chain=_Chain(),
                                     state=None, langs=["ja"],
                                     aliases=["Kashiwa"]))
    # 🔴 **묵은 주소는 열지도 않았다**(fetch 가 안 불렸다)
    assert OLD not in opened, opened
    assert [u for u, _b in got] == [NEW], got
    assert "묵은 문서" in said and "1건" in said, said


def test_bj11f_문서가_말할_수_있는_주장만_2단에_보낸다() -> None:
    """🔴🔴 손댈 자리 ③ — 기사는 *결장·선발·순위·일정*을 글자로 적고
    *"어느 쪽 수비 라인이 더 높나"* 는 **안 적는다**.

    ⚠️ 실측 2026-10-17: 전술 비교 갈래를 2단에 보내 다섯 번 전부 `모르겠다` 를
       받았다 — 검색 + 본문 + LLM 을 쓰고 얻은 것이 없다.
    ⚠️ 보내지 않는 것은 **버리는 것이 아니다** — 맥락 전용 + 사유다.
    """
    # 🔴 전술 비교는 **안 보낸다**
    ok, why = bj.doc_checkable(_branch("수비 라인"))
    assert ok is False and "전술 비교" in why, why
    # 🔴 그런데 **주장 글이 사실을 가리키면** 보낸다(선수 결장 등)
    ok2, why2 = bj.doc_checkable(_branch("수비 라인", claims=[
        bj.Claim(provider="deepseek", cmp=">", goals_cmp="=",
                 text="카이키가 결장해 뒷공간이 헐겁다")]))
    assert ok2 and "결장" in why2, why2
    # 🔴 그 갈래 자체가 문서 꼴이면 보낸다
    assert bj.doc_checkable(_branch("기사 사실"))[0]
    assert bj.doc_checkable(_branch("일정·피로도"))[0]
    # 🔴 `cross` 가 **검색 전에** 그것을 본다(예산)
    src = inspect.getsource(bj.cross)
    i, j = src.index("doc_checkable("), src.index("_queries(")
    assert i < j, "🔴 질의를 쓴 뒤에 걸러낸다(예산을 이미 썼다)"


def test_bj11g_버린_본문을_사유별로_센다() -> None:
    """🔴🔴 #3 — *"자료가 안 왔다"* 와 *"왔는데 못 뽑았다"* 는 다른 사실이다.

    ⚠️ 계약 리뷰어 2026-10-17: 독스트링은 *"버린 수를 사유에 적는다"* 라고 적고
       **코드는 `continue` 로 조용히 지나갔다**(팀 표기 없음만 셌다).
    """
    src = inspect.getsource(bj._docs)
    for w in ("n_dead", "n_thin", "n_off", "n_old"):
        assert w in src, w
    for w in ("못 받은 문서", "껍데기·짧은 본문", "팀 표기 없어 버린 본문",
              "묵은 문서"):
        assert w in src, w
    # 🔴 사다리 사유를 **버리지 않는다**(`body_of` 가 칸마다 적는다)
    assert "rungs" in src and '"why"' in src, "🔴 왜 껍데기인지 안 남긴다"


def test_bj11h_공급자_표는_b2_가_원본이다() -> None:
    """🔴 #1 — 손으로 적으면 ⑤-b2 를 바꿀 때 `judge_pv_of` 가 **묻지도 않은
    모델**을 판정자로 고른다(계약 리뷰어 2026-10-17)."""
    import inspect as _i
    want = _i.signature(sl.ask).parameters["providers"].default
    assert bj.PROVIDERS == tuple(want), (bj.PROVIDERS, want)
    assert "signature(_sl.ask)" in inspect.getsource(bj._providers)


def test_bj11i_단이_터져도_카드가_나온다() -> None:
    """🔴 §5 — 카드는 **항상** 나온다. 독스트링이 *"예외를 안 던진다"* 라고
    약속했는데 **2단만** 감싸고 있었다(계약 리뷰어 2026-10-17)."""
    src = inspect.getsource(bj.run)
    assert src.count("except Exception") >= 3, src
    for w in ("1단 🔴 터졌다", "🔴 터졌다 — "):
        assert w in src, w


def test_bj11j_보류_글에도_1단이_잰_수가_남는다() -> None:
    """🔴🔴 실측 2026-10-17(Necaxa) — `측면 집중` 을 **4명 ↔ 4명**으로 재고
    *"차이가 2명 미만"* 이라 못 가렸는데, 2단 문지기가 보류로 돌리면서
    `branch.why` 를 덮어 **그 수가 변수 글에서 사라졌다**.

    사람이 보면 *"측면을 아예 못 쟀다"* 로 읽힌다 — 어제 §4 의 그 병이다.
    """
    import asyncio
    one = _branch("측면 집중")
    one.num_why = "측면(왼·오른) 선발 홈 **4명** ↔ 원정 **4명** — 차이가 2명 미만이다"
    said = asyncio.run(bj.cross(one, _R(), state=None, net=None,
                                chain=object()))
    # 🔴 문지기가 돌려보냈는데(전술 비교) **잰 수는 글에 남았다**
    assert "전술 비교" in said and "4명" in said, said
    assert "1단이 잰 것" in one.why, one.why
    # 🔴 잰 것이 없으면 **안 붙인다**(빈 꼬리를 달지 않는다)
    two = _branch("빌드업")
    asyncio.run(bj.cross(two, _R(), state=None, net=None, chain=object()))
    assert "1단이 잰 것" not in two.why, two.why


def test_bj12_근거_없이_승격하면_막는다() -> None:
    """🔴🔴 ① **측정·근거 없는 승격 금지**(인계 §2 3단)."""
    # (가) 부등호가 없다
    one = _branch("빌드업")
    assert bj.may_promote(one)[0] is False
    # (나) 1단 채택인데 **잰 수가 없다**
    one = _branch("빌드업")
    one.by, one.picked = "수", ">"
    ok, why = bj.may_promote(one)
    assert ok is False and "잰 수가 없다" in why, why
    # (다) 2단 채택인데 **접지된 인용이 없다**
    one = _branch("빌드업")
    one.by, one.picked, one.judge_pv = "교차", ">", "solar"
    one.quote, one.url, one.grounded = "무언가", "https://x", False
    ok2, why2 = bj.may_promote(one)
    assert ok2 is False and "접지된 인용" in why2, why2
    # (라) 접지됐지만 **자기 검증**이다 → 막는다(②)
    one.grounded, one.picked_pv, one.judge_pv = True, "solar", "solar"
    ok3, why3 = bj.may_promote(one)
    assert ok3 is False and "자기 검증" in why3, why3
    # (마) 접지 + 교차 → 올린다
    one.picked_pv = "deepseek"
    ok4, why4 = bj.may_promote(one)
    assert ok4 and "인용" in why4, why4


def test_bj13_채택하면_변수가_확률에_닿고_근거가_글에_남는다() -> None:
    """🔴🔴 ④ **남겼다 ≠ 읽을 수 있다** — 인용·주소가 변수 글에 남아야 한다."""
    one = _branch("수비 라인")
    one.by, one.picked, one.picked_goals = "교차", "<", "<"
    one.picked_pv, one.judge_pv = "solar", "deepseek"
    one.quote, one.url, one.grounded = "Veres conceded twice again", \
        "https://x.example/a", True
    one.why = f"{bj.JUDGED} · **2단 교차** — deepseek 가 문서로 봤다"
    got = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="수비 라인", cmp=">", goals_cmp="=",
        text=f"{sl.CONFLICT} — deepseek `>` x ↔ solar `<` y")]), _R())
    assert got and got[0].usable_as_basis is False, got
    out, said = bj.apply([one], got)
    v = out[0]
    # 🔴 부등호 표가 방향을 옮긴다(사본 금지 — `dir_of_cmp` 하나다)
    assert (v.favors, v.goals) == sl.dir_of_cmp("<", "<") == ("away", "down")
    assert v.usable_as_basis is True, v
    assert one.url in v.claim and "Veres conceded twice again" in v.claim, \
        v.claim
    assert v.quote == one.quote
    assert bj.JUDGED in said, said


def test_bj14_보류는_맥락_전용으로_남고_사유가_읽힌다() -> None:
    one = _branch("빌드업")
    one.why = f"{bj.HELD} · 🔴 **서로 옳다가 엇갈렸다**"
    got = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="빌드업", cmp=">", goals_cmp="=",
        text=f"{sl.CONFLICT} — deepseek `>` x ↔ solar `<` y")]), _R())
    out, said = bj.apply([one], got)
    assert out[0].usable_as_basis is False, out[0]
    assert "엇갈렸다" in out[0].claim, out[0].claim
    assert bj.HELD in said, said


def test_bj15_갈래_상한이_있다() -> None:
    """🔴🔴 ⑤ 비용 — 충돌 갈래마다 검색 + 본문 + LLM 이 더 든다.

    카드 상한(`slate.CARD_CAP_MIN`) 안에서 돌게 **갈래 수 상한**을 둔다.
    """
    from app.core import slate
    assert 1 <= bj.MAX_JUDGE <= 3, bj.MAX_JUDGE
    assert slate.CARD_CAP_MIN >= 15
    src = inspect.getsource(bj.run)
    assert "done >= int(cap)" in src, "🔴 상한을 안 센다"
    assert "상한" in src and "건너뜀" in src, "🔴 건너뛴 갈래를 안 남긴다"
    # 🔴 카드 상한(시계)도 본다
    assert "clock" in src and "over" in src, src[-900:]
    # 🔴 **충돌이 먼저**다(같은 재료로 반대 결론이므로)
    rows = [bj.Branch(kind="a", mode="단독"), bj.Branch(kind="b", mode="충돌")]
    assert [b.kind for b in bj._order(rows)] == ["b", "a"]


# ══════════════════════════════════════════════════════════════════
# 🔴 배선 — 안 이은 코드는 없는 코드보다 나쁘다(#2)
# ══════════════════════════════════════════════════════════════════


def test_bj16_갈래가_쪼개진_꼴로_담긴다() -> None:
    """🔴 두 모델 주장이 **글자 한 줄로 뭉치면** 기계가 가릴 수 없다."""
    from unittest.mock import patch

    from app.core import llm as _llm
    from app.core.state import RunState

    def fake(**kw):
        cmp_ = "<" if kw["provider"] == "deepseek" else ">"
        return sl.StrategyRead(rows=[
            sl.StrategyRow(kind="수비 라인", cmp=cmp_, goals_cmp="=",
                           text=f"{kw['provider']} 의 말"),
            sl.StrategyRow(kind="세트피스", cmp=">", goals_cmp="=",
                           text="혼자 본 것")
            if kw["provider"] == "deepseek" else
            sl.StrategyRow(kind="중원 수싸움", cmp=">", goals_cmp="=",
                           text="중원")])

    facts = _F(xi={"team:000001": _XI("4-3-3"), "team:000002": _XI("4-3-3")})
    box: list = []
    with patch.object(_llm, "ask", side_effect=fake):
        out, why = sl.ask(_R(), facts, _Plan({"L1": {"kind": "formation",
                                                     "text": "x"}}),
                          state=RunState(), branches=box)
    kinds = {b.kind: b for b in box}
    assert "수비 라인" in kinds and kinds["수비 라인"].mode == "충돌", kinds
    one = kinds["수비 라인"]
    # 🔴 **주장이 쪼개져 있다** — 누가 무엇을 말했는지 기계가 안다
    assert {c.provider for c in one.claims} == {"deepseek", "solar"}
    assert {c.cmp for c in one.claims} == {"<", ">"}
    # ⚠️ 담는 것이 **글을 고치기 전**이어야 한다 — 뒤에 담으면 주장 글이
    #    충돌 꼬리표로 바뀐다
    assert all(sl.CONFLICT not in c.text for c in one.claims), one.claims
    assert any("deepseek 의 말" == c.text for c in one.claims), one.claims
    # 🔴 **단독**도 담는다(버리지 않는다 — 확인할 거리다)
    alone = [b for b in box if b.mode == "단독"]
    assert alone and all(len(b.claims) == 1 for b in alone), alone
    assert all(sl.ALONE not in c.text for b in alone for c in b.claims)
    assert out and why


def test_bj16b_판정_사유가_어느_자리에서도_안_잘린다() -> None:
    """🔴🔴 ④ **"남겼다" 와 "읽을 수 있다" 는 다르다**(인계 §4 · 실사고 10-17).

    ⚠️ 실사고 2026-10-17(Necaxa vs Atlas): 판정은 **섰는데**(중앙 수 홈 5 ↔
       원정 4 → deepseek 채택) 근거가 변수 글 **끝**에 붙어 러너 170자 ·
       카드 90자 · 묶음 120/150자 컷에 **전부 먹혔다** — 어느 자리에서도
       *왜 채택했나*를 읽을 수 없었다.
    🔴 그래서 꼬리표(`crosscheck.JUDGE_MARK`)를 달고, 읽는 자리는 **머리만**
       자르고 꼬리를 **따로 줄로** 적는다.
    """
    from app.core import crosscheck as cc
    from app.core.routing import VarRow, VariableSet
    from app.core.stages import s6_verdict as vd

    assert bj.MARK == cc.JUDGE_MARK, "🔴 꼬리표 글자를 따로 지었다(사본)"
    # 🔴 `apply` 가 그 꼬리표를 **달아서** 글을 남긴다
    one = _branch("중원 수싸움")
    one.by, one.picked, one.picked_pv = "수", ">", "deepseek"
    one.num_why = "중앙 수 홈 **5** ↔ 원정 **4** → `>`"
    one.why = f"{bj.JUDGED} · **1단 측정** — {one.num_why}"
    got = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="중원 수싸움", cmp=">", goals_cmp="=",
        text=f"{sl.CONFLICT} — " + "길고 긴 양쪽 문장 " * 12)]), _R())
    out, _said = bj.apply([one], got)
    said_claim = str(out[0].claim)
    assert bj.MARK in said_claim and "중앙 수 홈 **5**" in said_claim
    head, tails = cc.tails_of(said_claim)
    # 🔴 **머리가 어느 컷보다 길다** — 그래서 컷만 있으면 꼬리가 통째로 사라진다
    #    (러너 170 · 묶음 150/120 · 카드 90 — 2026-10-17 실사고가 그 꼴이었다)
    assert len(head) > 170, (len(head), head)
    assert tails and "중앙 수 홈 **5**" in tails[-1], tails

    # ── ① ⑯ 묶음(확률에 닿는 칸) — 꼬리가 산다
    row = VarRow(id="SL1", type="lineup_intent", places=["axis2"],
                 claim=said_claim)

    class _Prob:
        home = draw = away = 0.333
        lam = over = scores = {}

    box = vd.chain_of(None, _Prob(), None, VariableSet(rows=[row]))
    said_box = "\n".join(box)
    assert "중앙 수 홈 **5**" in said_box, said_box[-400:]

    # ── ② ⑯ 묶음(맥락 전용 칸) — 보류 사유도 산다
    one2 = _branch("빌드업")
    one2.why = f"{bj.HELD} · 🔴 **서로 옳다가 엇갈렸다**(deepseek ↔ solar)"
    got2 = sl.vars_of(sl.StrategyRead(rows=[sl.StrategyRow(
        kind="빌드업", cmp=">", goals_cmp="=",
        text=f"{sl.CONFLICT} — " + "또 아주 긴 양쪽 문장 " * 12)]), _R())
    out2, _s2 = bj.apply([one2], got2)
    row2 = VarRow(id="SL2", type="lineup_intent", places=["hypo"],
                  claim=str(out2[0].claim))
    box2 = vd.chain_of(None, _Prob(), None, VariableSet(rows=[row2]))
    assert "엇갈렸다" in "\n".join(box2), box2

    # ── ③ 카드 변수 블록 · ④ 러너 — 꼬리를 따로 줄로 적는다
    src = inspect.getsource(__import__("app.core.render",
                                       fromlist=["x"]).varset_block
                            if hasattr(__import__("app.core.render",
                                                  fromlist=["x"]),
                                       "varset_block") else bj.apply)
    said_render = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "_cc2.tails_of(one.claim)" in said_render, "🔴 카드가 꼬리를 자른다"
    said_run = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    assert said_run.count("tails_of") >= 2, "🔴 러너 두 자리 중 하나가 자른다"
    assert src


def test_bj17_운영_파이프라인에_배선됐다() -> None:
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert "branchjudge" in said, "🔴 운영이 안 부른다"
    assert "branches=said_branch" in said, "🔴 갈래를 안 담는다"
    assert "_bj.run(said_branch, var_sl" in said, "🔴 판정을 안 돌린다"
    # 🔴 **배치를 다시 세우기 전**이어야 승격된 변수가 확률 자리에 들어간다
    i = said.index("_bj.run(said_branch")
    j = said.index("varset = _routing.place(variables)", i)
    assert i < j, "🔴 배치 뒤에서 판정하면 승격이 확률에 안 닿는다"


def test_bj18_러너에_배선됐다() -> None:
    said = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    assert "⑤-b3 갈래 판정" in said, "🔴 장부에 칸이 없다"
    assert "branches=said_branch" in said and "_bj.run(" in said


def test_bj18b_러너가_읽는_칸이_실제로_있다() -> None:
    """🔴🔴 **글자 검사로는 못 센다**(실사고 2026-10-17).

    ⚠️ `Claim.verdict` 를 `ruling` 으로 바꿨는데 러너는 `c.verdict` 를 그대로
       읽고 있었다 — 스위트는 **초록**이었고(글자만 봤다) 실제 실행이
       `AttributeError` 로 **죽었다**(카드가 안 나왔다).
    🔴 그래서 러너가 읽는 `c.*`·`one.*` 칸을 **실제 칸 목록과 대조**한다.
    """
    import re
    said = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    i = said.index("⑤-b3 갈래 판정(충돌·단독)")
    j = said.index("--until=vars", i)
    block = said[i:j]
    ok_claim = set(bj.Claim.__dataclass_fields__)
    ok_branch = set(bj.Branch.__dataclass_fields__) | {"said", "target"}
    bad = [f"c.{a}" for a in set(re.findall(r"\bc\.(\w+)", block))
           if a not in ok_claim]
    bad += [f"one.{a}" for a in set(re.findall(r"\bone\.(\w+)", block))
            if a not in ok_branch]
    assert not bad, f"🔴 러너가 **없는 칸**을 읽는다: {bad}"


def test_bj19_용도가_설정에_있다() -> None:
    """🔴 표에 없는 용도는 터진다 — 수를 같이 적게 만든다(§9)."""
    from app.core import llm
    got = dict(llm.purpose_cfg("judge"))
    assert int(got.get("max_tokens") or 0) >= 2000, got
    # 🔴 같은 본문이면 같은 판정이어야 재현이 뜻을 갖는다
    assert float(got.get("temperature", 1)) == 0, got


def test_bj20_방향_표는_하나다() -> None:
    """🔴 부등호 → 방향을 두 자리에 적으면 한쪽이 늦게 바뀐다(#1)."""
    assert sl.dir_of_cmp(">", "<") == ("home", "down")
    assert sl.dir_of_cmp("=", "=") == ("both", "none")
    src = inspect.getsource(sl.vars_of)
    assert "dir_of_cmp(op, gop)" in src, "🔴 `vars_of` 가 표를 안 쓴다"
    src_a = inspect.getsource(bj.apply)
    assert "_sl.dir_of_cmp(" in src_a, "🔴 판정이 제 표를 지었다"
