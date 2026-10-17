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


class _P:
    def __init__(self, pos: str = "", flank: str = "") -> None:
        self.name, self.pos, self.flank = "x", pos, flank


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


def test_bj1_중원_수로_가린다() -> None:
    """🔴 두 포메이션의 **가운데 수** — `4-1-4-1`(5) vs `4-2-2-2`(4)."""
    from app.core import strategy as st
    assert st.mid_line("4-1-4-1") == 5 and st.mid_line("4-2-2-2") == 4
    # ⚠️ 칸이 둘뿐이면 가운데가 **없다**(0 이 아니다 · #3)
    assert st.mid_line("4-4") is None and st.mid_line("") is None
    facts = _F(xi={"team:000001": _XI("4-1-4-1"),
                   "team:000002": _XI("4-4-2")})
    op, why = bj.by_numbers(_branch("중원 수싸움"), _R(), facts)
    assert op == ">", (op, why)
    assert "중앙 수 홈 **5**" in why and "원정 **4**" in why, why


def test_bj2_차이가_작으면_안_가린다() -> None:
    """🔴 문턱 아래면 **안 가린다** — `=` 를 채택하지 않는다."""
    facts = _F(xi={"team:000001": _XI("4-4-2"), "team:000002": _XI("4-4-2")})
    op, why = bj.by_numbers(_branch("중원 수싸움"), _R(), facts)
    assert op == "" and "안 가린다" in why, (op, why)


def test_bj3_측면은_lineup_에서_센다() -> None:
    """🔴🔴 실측 2026-10-17 — 자리·측면은 **`XI.lineup`** 에 있다.

    ⚠️ `XI.players` 는 **이름 글자 목록**(`list[str]`)이다. 그 칸을 Player 로
       읽으면 자리가 **늘 빈 글자**가 된다(⑤-b2 프롬프트가 그 병이었다).
    """
    home = _XI("4-4-2", [_P("LM", "L"), _P("RM", "R"), _P("LB", "L"),
                         _P("RB", "R"), _P("CB"), _P("GK")])
    away = _XI("4-4-2", [_P("CB"), _P("CM"), _P("GK")])
    op, why = bj.by_numbers(_branch("측면 집중"), _R(),
                            _F(xi={"team:000001": home, "team:000002": away}))
    assert op == ">", (op, why)
    assert "홈 **4명**" in why and "원정 **0명**" in why, why
    # 🔴 자리 글자가 없으면 **못 셌다**고 적는다(0 으로 때우지 않는다 · #3)
    op0, why0 = bj.by_numbers(_branch("측면 집중"), _R(),
                              _F(xi={"team:000001": _XI("4-4-2"),
                                     "team:000002": away}))
    assert op0 == "" and "못 셌다" in why0, why0


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
    for kind in ("빌드업", "세트피스", "역습 성향", "교체 운용", "기사 사실",
                 "압박 높이"):
        op, why = bj.by_numbers(_branch(kind), _R(), _F())
        assert op == "" and "2단" in why, (kind, op, why)


def test_bj7_1단은_투표가_아니라_측정이다() -> None:
    """🔴 수가 가리킨 쪽을 쓴다 — **어느 모델도 그 말을 안 했어도** 쓴다."""
    one = _branch("중원 수싸움", claims=[
        bj.Claim(provider="deepseek", cmp="<", goals_cmp="=", text="원정"),
        bj.Claim(provider="solar", cmp="<", goals_cmp="=", text="원정")])
    facts = _F(xi={"team:000001": _XI("4-1-4-1"),
                   "team:000002": _XI("4-4-2")})
    said = bj.stage1([one], _R(), facts)
    assert one.picked == ">" and one.by == "수", (one.picked, one.by)
    assert one.picked_pv == "" and "어느 모델도" in one.why, one.why
    assert "수로 가렸다" in said, said
    # 🔴 그 수를 사유에 적는다(승격 근거다)
    ok, why = bj.may_promote(one)
    assert ok and "중앙 수" in why, why


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


def test_bj10_판정이_본문을_읽는다는_것이_프롬프트에_있다() -> None:
    src = inspect.getsource(bj._verdict)
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


# ══════════════════════════════════════════════════════════════════
# 🔴 3단 — ① 근거 없이 승격 금지 · ④ 인용·주소를 글에 남긴다
# ══════════════════════════════════════════════════════════════════


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
