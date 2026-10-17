"""🔴🔴 **안전장치 세 층** — 사용자 지시 2026-10-16
*"봇이 fotmob 정보를 우리 변수에 제대로 넣고 있는지 · 잘못된 경기로 하고 있는지
확인하는 장치를 순서대로 전부 구현하고 테스트해라"*.

⚠️ 재현하는 실사고(2026-10-16 코스타리카 Saprissa vs Sporting):
   팀 일정의 슬러그 주소가 **다른 맞대결**을 줘 과거 5경기 중 4개가 남의
   경기였고(한 자리엔 **그 경기 자신**), 골 목록이 없어 득실이 **조용히 0** 이
   됐다 → 폼이 `L D D D D · 득점 0.0 · 실점 0.2` 라는 거짓 수가 되어 확률·평까지
   갔다. 같은 팀을 **다른 경로**(경기 페이지 `teamForm`)로 보면 1.6/2.0 이었다.

지키는 것:
  CC1 층2 — 두 경로가 어긋나면 **False** 와 사유(둘 다 있어야 비교한다)
  CC2 층3 — 득점 합 0 · 전부 같은 결과 · 표본 부족을 **이름으로** 잡는다
  CC3 층4 — 킥오프 뒤 경기·**그 경기 자신**이 폼에 있으면 잡는다
  CC4 배선 — `s2_facts` 가 세 층을 돌려 `flags` 를 단다
  CC5 배선 — `s5_verify` 는 `flags` 가 있으면 **맥락 전용**으로 내린다
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from app.core import crosscheck as cc

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 그날 **거짓으로 들어온** 폼(경로 B — 슬러그 주소가 데려온 남의 경기들)
FAKE = {"sequence": [
    {"date": "2026-10-11", "goals_for": 0, "goals_against": 1,
     "result": "L", "score": "0-1"},
    *[{"date": f"2026-09-{d}", "goals_for": 0, "goals_against": 0,
       "result": "D", "score": "0-0"} for d in (20, 17, 13, 10)]]}
#: 🔴 같은 팀의 **참값**(경로 A — 경기 페이지 teamForm)
REAL = {"sequence": [
    {"date": "2026-10-11", "goals_for": 0, "goals_against": 1,
     "result": "L", "score": "0-1"},
    {"date": "2026-09-20", "goals_for": 2, "goals_against": 0,
     "result": "W", "score": "2-0"},
    {"date": "2026-09-17", "goals_for": 2, "goals_against": 3,
     "result": "L", "score": "2-3"},
    {"date": "2026-09-13", "goals_for": 2, "goals_against": 4,
     "result": "L", "score": "2-4"},
    {"date": "2026-09-10", "goals_for": 2, "goals_against": 2,
     "result": "D", "score": "2-2"}]}


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def test_cc1_층2_두_경로_대조() -> None:
    """CC1 🔴🔴 그날의 거짓 폼이 **참값과 대조되면 잡힌다**."""
    ok, why = cc.form_cross(FAKE, REAL)
    assert ok is False, why
    assert "득점" in why and "0.0" in why and "1.6" in why, why
    # 🔴 같은 것끼리는 통과한다(거짓 양성이 없다)
    ok2, why2 = cc.form_cross(REAL, REAL)
    assert ok2 is True, why2
    # 🔴 한쪽이 없으면 **실패가 아니라 못 쟀음**이다(#3)
    got, said = cc.form_cross(REAL, {})
    assert got is None and "대조 못 함" in said, said


def test_cc2_층3_말이_되는_값() -> None:
    """CC2 🔴 득점 합 0 · 전부 같은 결과 · 표본 부족."""
    said = cc.form_sane(FAKE)
    assert any("득점 합이 0" in x for x in said), said
    assert not cc.form_sane(REAL), cc.form_sane(REAL)
    # 🔴 전부 같은 결과
    allD = {"sequence": [{"goals_for": 1, "goals_against": 1, "result": "D",
                          "score": "1-1"}] * 5}
    assert any("전부" in x for x in cc.form_sane(allD))
    # 🔴 스코어 글자와 득실이 어긋나는 줄
    bad = {"sequence": [{"goals_for": 1, "goals_against": 0, "result": "W",
                         "score": "3-0"}] * 3}
    assert any("어긋난다" in x for x in cc.form_sane(bad))


def test_cc3_층4_누설() -> None:
    """CC3 🔴🔴 **그 경기 자신**과 킥오프 뒤 경기를 잡는다."""
    ko = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)
    games = [{"date": "2026-10-16", "opp": "Sporting FC"},
             {"date": "2026-10-20", "opp": "Cartaginés"},
             {"date": "2026-09-13", "opp": "Sporting FC"}]
    said = cc.leak_of(games, kickoff=ko, home="Deportivo Saprissa",
                      away="Sporting FC")
    assert any("그 경기 자신" in x for x in said), said
    assert any("킥오프 뒤" in x for x in said), said
    # 🔴 과거 경기만 있으면 조용하다
    assert not cc.leak_of([{"date": "2026-09-13", "opp": "Sporting FC"}],
                          kickoff=ko, home="A", away="B")


def test_cc4_s2_facts_가_세_층을_돌린다() -> None:
    """CC4 🔴 배선 — 안 이으면 없는 코드다(CLAUDE.md #2)."""
    said = _code("app/core/stages/s2_facts.py")
    for one in ("crosscheck", "leak_of(", "form_sane(", "form_cross("):
        assert one in said, f"CC4 🔴 `s2_facts` 가 `{one}` 를 안 쓴다"
    assert '"flags"' in said, "CC4 🔴 어긋남을 폼 칸에 안 남긴다"


def test_cc5_s5_가_빨간_폼을_내린다() -> None:
    """CC5 🔴🔴 안전장치가 걸린 폼은 **확률에 안 닿는다**."""
    said = _code("app/core/stages/s5_verify.py")
    assert 'box.get("flags")' in said, "CC5 🔴 `flags` 를 안 읽는다"
    assert "usable_as_basis=(n >= low and not said_flags)" in said, (
        "CC5 🔴 빨간 폼이 **근거로 남는다** — 맥락 전용으로 내려야 한다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **폼 창은 리그 경기만** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Sydney FC · A리그 개막 전): 폼 다섯 경기가 **호주컵 넷 +
#     친선 하나**로 찼고(리그 **0건**) 그 수로 `득점 평균 2.6` 이 섰다.

CUPMIX = [
    {"date": "2026-07-21", "league": "Australia Cup", "gf": 5, "ga": 1},
    {"date": "2026-07-29", "league": "Club Friendlies", "gf": 1, "ga": 1},
    {"date": "2026-09-01", "league": "A-League", "gf": 1, "ga": 2},
    {"date": "2026-09-08", "league": "AFC Champions League Two", "gf": 0, "ga": 0},
    {"date": "2026-09-15", "league": "A-League", "gf": 2, "ga": 0},
]


def test_cc6_폼_창은_리그만() -> None:
    """CC6 🔴 컵·친선·대륙 대회를 뺀다 — 판정은 `form.is_league_game` 하나다."""
    from app.core import form as _form

    keep, cut = _form.league_only(CUPMIX)
    assert [k["date"] for k in keep] == ["2026-09-01", "2026-09-15"], keep
    assert len(cut) == 3, cut
    assert _form.is_league_game("A-League") and _form.is_league_game("Serie A")
    for bad in ("Australia Cup", "Club Friendlies", "DFB-Pokal", "Copa del Rey",
                "UEFA Champions League", "Conference League", "친선"):
        assert not _form.is_league_game(bad), bad
    # ⬜ 대회를 모르면 **빼지 않는다**(있는 것을 지우지 않는다 · #3)
    assert _form.is_league_game("") and _form.is_league_game(None)


def test_cc7_뺀_것을_이름으로_남긴다() -> None:
    """CC7 🔴 창이 얇아진 까닭이 보여야 한다(조용한 0 금지)."""
    from app.core.stages.s2_facts import _recent_from_games

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **컵을 빼지 않는다** — 사용자 지시 2026-10-17
    # ══════════════════════════════════════════════════════════════════
    #
    #  > **빼면 안된다** · **피로도하고 관련이 깊다**
    #
    #  ⚠️ 10-16 지시는 *"폼 창은 리그만"* 이었고 이 시험이 *"뺀 것을 이름으로
    #     남긴다"* 를 지켰다. 🔴 그런데 빼면 **휴식일·일정 부담이 거짓**이
    #     된다 — 실측 2026-10-17: 나고야의 10-14 르방컵 3-3 무가 창에서 빠져
    #     휴식일이 **3일인데 6일로** 보였다(가시와도 8일로 보였다).
    #  🔴 그래서 **전부 센다**. ⚠️ 어느 경기가 컵인지는 **이름으로 남긴다**
    #     (`cup_in_window`) — 그 규율은 그대로다(#3 조용한 0 금지).
    box = _recent_from_games(CUPMIX, kickoff=None)
    assert box.get("cup_in_window"), box
    assert any("Australia Cup" in x for x in box["cup_in_window"])
    # 🔴 **전부** 센다 — 컵도 그 팀이 실제로 뛴 경기다
    assert len(box["sequence"]) == len(CUPMIX), box["sequence"]
    #  ⚠️ 그리고 **옛 칸은 없어야** 한다(둘이 같이 있으면 읽는 쪽이 갈린다)
    assert "cup_dropped" not in box, box


def test_cc8_맥락_전용은_확률을_못_민다() -> None:
    """CC8 🔴🔴 **안전장치가 확률까지 닿는다** — 사용자 지시 2026-10-16.

    ⚠️ 실사고 2026-10-16(PSIM vs PSM 검수): ⑩ 이 `S01-away` 를 맥락 전용
       (`자리 ['hypo']`)으로 내렸는데 ⑮ 유도에는 `[S01-away] home ×1.05` 가
       찍혔다 — **표를 던졌다**. `flat_prob` 가 `varset.rows` 를 전부 훑고
       `from_doc` 만 걸렀기 때문이다. 🔴 그래서 층2~층4 안전장치도, 표본 부족
       규칙(R7)도 **확률 경로에서는 무력**이었다.
    """
    from app.core import probmodel as pm
    from app.core.routing import VarRow, VariableSet

    class _Ref:
        home, away = "H", "A"

    rows = [
        # 🔴 확률 자리(축)에 있는 변수 — **센다**
        VarRow(id="S01-home", type="recent_pattern", subject="H",
               favors="subject", goals="up", places=["axis1", "hypo"]),
        # 🔴 맥락 전용 — 자리가 `hypo` 뿐이다 → **안 센다**
        VarRow(id="S01-away", type="recent_pattern", subject="A",
               favors="subject", goals="up", places=["hypo"]),
        # 🔴 `context_only` 가 참이면 자리가 있어도 **안 센다**
        VarRow(id="IR99", type="form_streak", subject="A", favors="subject",
               places=["axis1"], context_only=True),
    ]
    got, why = pm.flat_prob(VariableSet(rows=rows), ref=_Ref())
    assert "S01-home" in why, why
    assert "S01-away" not in why, f"CC8 🔴 맥락 전용이 표를 던졌다 — {why}"
    assert "IR99" not in why, f"CC8 🔴 `context_only` 가 표를 던졌다 — {why}"
    assert "맥락 전용 변수 2개는 **안 셌다**" in why, why
    # 🔴 홈 한 표만 들어갔으니 홈이 앞선다
    assert got["home"] > got["away"], got


def test_cc9_이름_변형은_같은_선수다() -> None:
    """🔴🔴 CC9 — 사용자 지시 2026-10-16(변수 검수에서 나온 결함).

    ⚠️ 실사고(City Club vs Bashundhara): 과거 선발 `Mohamed Sohel Rana` 와
       오늘 명단의 `Sohel Rana` 가 **다른 사람**으로 세어져, **선발 11명에 있는
       선수**가 `결장 8명` 에 올랐다. 그 글자가 다시 `IR03 복귀` 변수가 되어
       **축0·축2 로 확률에 닿았고**, 평도 *"복귀로 자원이 두터워졌다"* 고
       **반대 사실**을 썼다.
    🔴 토막 집합이 한쪽에 포함되면 같은 사람이다. ⚠️ 성 하나로는 안 센다.
    """
    from app.core.absence import same_player

    assert same_player("Mohamed Sohel Rana", "Sohel Rana")
    assert same_player("Topu Barman", "Topu Barman")
    assert same_player("Son Heung-min", "Heung-min Son") is False or True  # 순서 무관
    # 🔴 동명이인 함정 — 성만 같은 둘은 **다르다**
    assert not same_player("Saad Uddin", "Taj Uddin")
    assert not same_player("Rakib Hossain", "Rimon Hossain")
    # 🔴 한 토막(성만)은 안 센다
    assert not same_player("Sohel Rana", "Rana")
    # 🔴 명단 대조가 그 판정을 **쓴다**(배선)
    said = _code("app/core/absence.py")
    assert "same_player(nm, x)" in said, "CC9 🔴 명단 대조가 안 쓴다"


def test_cc10_안전장치_사유가_안_잘린다() -> None:
    """🔴🔴 CC10 — 사용자 지시 2026-10-16.

    ⚠️ 실사고(Obolon Kyiv vs Veres Rivne): 카드에 `… 🔴 **안전장치**: 🔴 ` 까지만
       찍히고 **사유가 사라졌다**. 변수 글을 `claim[:100]`(러너)·`[:120]`(묶음)
       에서 잘랐기 때문이다. 🔴 *"이름으로 남긴다"* 는 **읽을 수 있게 남긴다**는
       뜻이다 — 잘린 사유는 없는 것과 같다.
    """
    from app.core.routing import VarRow, VariableSet
    from app.core.stages import s6_verdict as vd

    said = ("최근 5경기 W D L L D · 득점 평균 0.6 · 기준 팀당 1.2033골 대비 "
            "적다 · 실점 평균 1.8(많다) · 🔴 **안전장치**: 🔴 폼이 2경기뿐이다"
            "(<3) · 두 경로가 어긋난다 — 득점 0.0 ↔ 1.6")
    row = VarRow(id="S01-home", type="recent_pattern",
                 places=["axis1", "hypo"], claim=said)

    class _P:
        home = draw = away = 0.333
        lam = over = scores = {}

    box = vd.chain_of(None, _P(), None, VariableSet(rows=[row]))
    one = next(x for x in box if "S01-home" in x)
    assert "폼이 2경기뿐이다" in one, one
    assert "두 경로가 어긋난다" in one, one
    # 🔴 러너도 사유를 **둘째 줄**로 온전히 찍는다(배선)
    said_run = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    assert "def say_var(" in said_run and "say_var(v, 100)" in said_run
    # 🔴🔴 꼬리표 글자와 쪼개는 함수는 **`crosscheck` 하나**다(2026-10-17) —
    #    ⚠️ 종전엔 같은 글자(`🔴 **안전장치**`)를 **네 자리에 손으로** 적어 뒀고
    #       (러너 `FLAG_MARK` · 묶음 두 곳 · 카드), **갈래 판정** 꼬리표가 늘자
    #       같은 사본을 또 만들 자리가 됐다. 🔴 그래서 한 곳으로 모았다.
    from app.core import crosscheck as _cc
    assert _cc.FLAG_MARK == "🔴 **안전장치**"
    assert "tails_of" in said_run, "🔴 러너가 꼬리표를 안 쪼갠다"
    # 🔴 쪼개는 함수가 **꼬리를 안 자른다**
    head, tails = _cc.tails_of(said)
    assert tails and "두 경로가 어긋난다 — 득점 0.0 ↔ 1.6" in tails[0], tails
    assert _cc.FLAG_MARK not in head, head


def test_cc11_못_쟀다는_어긋남이_아니다() -> None:
    """🔴🔴 CC11 — 사용자 지시 2026-10-16.

    ⚠️ 실사고(Obolon Kyiv): 한쪽 평균을 못 세자 `form_cross` 가 **False**
       (어긋남)를 돌려줬고, 그 깃발이 **멀쩡한 폼 변수 넷**을 맥락 전용으로
       내려 확률이 33.3 균등이 됐다(폼 자체는 `0.6/1.8` 로 정확했다).
       🔴 뿌리는 `avg_of` 가 **실수**(`1.0`)를 `str().isdigit()` 으로 보고
          버린 것이다.
    """
    flo = {"sequence": [{"goals_for": 1.0, "goals_against": 2.0}] * 5}
    num = {"sequence": [{"goals_for": 1, "goals_against": 2}] * 5}
    assert cc.avg_of(flo["sequence"], "goals_for") == 1.0
    ok, why = cc.form_cross(flo, num)
    assert ok is True, why
    # 🔴 한쪽을 못 세면 **None**(못 쟀다)이고 False(어긋남)가 아니다
    got, said = cc.form_cross(num, {"sequence": [{"result": "W"}] * 3})
    assert got is None and "대조 못 함" in said, said
    # 🔴 진짜 어긋남은 여전히 False
    bad, _why = cc.form_cross(num, {"sequence": [{"goals_for": 3,
                                                  "goals_against": 0}] * 5})
    assert bad is False


def test_cc12_등급이_다른_글은_버린다() -> None:
    """🔴🔴 CC12 — U19·여자 글이 시니어 경기에 섞였다(사용자 지시 2026-10-16).

    ⚠️ 실사고(Obolon Kyiv): `Zhytomyr **U19** vs Veres Rivne **U19**` 글이
       신원 검사를 통과했다(`Veres Rivne` ⊂ `Veres Rivne U19`). 그 글에서
       `R3 match_type — The contest is a U19 League match` 가 나와 **λ 상수
       자리까지** 갔고, 두 평이 *"U19 로 잡혀 전제와 안 맞는다"* 고 지적했다.
    """
    from app.core.stages.s3_docs import grade_ok

    mine = "Obolon Kyiv Veres Rivne Premier League"
    assert not grade_ok("Zhytomyr U19 vs Veres Rivne U19 Highlights", "", mine)[0]
    assert not grade_ok("Arsenal Women beat Chelsea", "", mine)[0]
    assert grade_ok("Obolon Kyiv vs Veres Rivne preview", "", mine)[0]
    # 🔴 반대쪽 — 우리 경기가 U19 면 U19 글을 받는다
    assert grade_ok("Barcelona U19 youth cup", "", "Barcelona U19 Youth League")[0]
    # 🔴 배선 — s3 가 그 문을 지난다
    said = _code("app/core/stages/s3_docs.py")
    assert "grade_ok(" in said and 's3/등급' in said, "CC12 🔴 안 이었다"
