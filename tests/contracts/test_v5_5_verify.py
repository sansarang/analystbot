"""🔴🔴 **v5 §5 검증층** — 에이전트 출력을 변수로 승격하는 관문. [#10 #13]

§5 원문:

> 에이전트가 돌려준 `variables[]` 는 아래 **여섯 검사를 전부 통과해야** 변수가
> 된다. 하나라도 걸리면 그 항목은 폐기되고 **사유가 깔때기에 남는다.** 폐기는
> 조용히 하지 않는다 — 카드 하단 `dropped:` 줄에 **개수와 사유**를 적는다.

§5-1 인용 검증 — `quote` 가 fetch 로 받아 둔 **그 URL 본문에 문자 그대로** 있어야
한다(공백·따옴표 정규화 후 부분 문자열). 없으면 `quote_not_found`.
§5-2 신원 필터 — 본문에 두 팀 중 하나의 이름·별칭 + 명단 선수 2명 이상 또는
대회명·상대명. 남녀·연령 표식 불일치면 `identity_mismatch`. 경기와 무관한 발언은
`off_match`.
§5-3 날짜 — `published_at` 이 킥오프 7일 전 ~ 킥오프 사이.
§5-7 중복·충돌 — MinHash 유사도 0.8 이상을 한 묶음. 충돌이면 `conflict` 로 두
변수 모두 보존하되 hardness 0.
§5-8 재사용 — `reverified:false` 로 표시하고 hardness 한 단계 내린다(M31).

══════════════════════════════════════════════════════════════════
🔴 왜 — **에이전트는 지어낼 수 있다**
══════════════════════════════════════════════════════════════════

실측 2026-10-04(§17-b L2): 모델이 위키 역사 문서에서 **Alex McLeish**(옛 스코틀랜드
감독)를 끌어와 *"로테이션 땜질"* 이라고 적었다. 🔴 §12-c-6 인용 대조가 거부했다 —
§5-1 이 그것을 **모든 변수**에 건다.

🔴 **§10-4 M36** — 원정 기록을 홈 변수로(10-04) — side_mismatch 폐기
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).

⚠️ **시험 이름의 번호가 조항 번호다**(§9-3) — `test_v5_7_…` 은 §9-3 의
   파서가 **§7** 로 읽는다. 🔴 §5-7 을 뜻하려면 `test_v5_5_7_…` 이어야
   한다(실측 2026-10-04: 그래서 §5-4·§5-5·§5-7·§5-8 이 **안 덮인 것으로**
   세어졌다). 이름이 곧 계약이다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)


def _var(**kw):
    from app.agentschema import AgentVar
    base = dict(id="R1", type="absence_def", team="team:000151",
                direction_hint="opp_goals_up", claim="주전 수비가 결장한다",
                quote="Elmas is out with an ankle injury",
                url="https://ok.example/a", published_at=KICK - timedelta(days=1),
                lang="en", conflict=False, reverified=True)
    base.update(kw)
    return AgentVar(**base)


BODY = ("North Macedonia host Scotland on Friday. "
        "Elmas is out with an ankle injury, the coach confirmed. "
        "Trajkovski and Alioski are expected to start.")


def _ctx(**kw):
    from app.verifylayer import Context
    base = dict(home="team:000151", away="team:000266",
                home_names=("North Macedonia", "Северна Македонија"),
                away_names=("Scotland",), competition="UEFA Nations League",
                roster=("Elmas", "Trajkovski", "Alioski"),
                kickoff=KICK, bodies={"https://ok.example/a": BODY})
    base.update(kw)
    return Context(**base)


# ══════════════════════════════════════════════════════════════════
# §5-1 인용 검증
# ══════════════════════════════════════════════════════════════════


def test_v5_5_1_본문에_있는_인용은_통과한다():
    from app.verifylayer import verify_one
    ok, reason, why = verify_one(_var(), _ctx())
    assert ok is True, (reason, why)


def test_v5_5_1_지어낸_인용은_폐기한다():
    """🔴🔴 §5-1 — *"에이전트가 지어낸 변수는 여기서 **전부 죽는다**."*"""
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, why = verify_one(
        _var(quote="Alex McLeish said he would rotate"), _ctx())
    assert ok is False and reason is Reason.QUOTE_NOT_FOUND, (reason, why)


def test_v5_5_1_공백_따옴표를_정규화한다():
    """🔴 §5-1 — *"공백·따옴표 정규화 후 **부분 문자열**."*"""
    from app.verifylayer import verify_one
    ok, _, why = verify_one(
        _var(quote='  “Elmas   is  out with an ankle injury”  '), _ctx())
    assert ok is True, why


def test_v5_5_1_받아_둔_본문이_없으면_폐기한다():
    """🔴 **대조할 본문이 없으면 통과시키지 않는다**(fail-closed).

    ══════════════════════════════════════════════════════════════════
    🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    `if not body:` 분기를 지워도 **초록이었다** — 본문이 빈 문자열이면 그 다음
    `quote not in body` 가 어차피 잡는다(같은 사유를 낸다).
    🔴 그래서 **사유 글이 다름**을 본다: *"본문을 받아 두지 않았다"*(수집 문제)와
       *"인용이 본문에 없다"*(지어냈다)는 **고칠 곳이 다르다** — §8-6 이 막는
       거짓 사유가 바로 그 섞임이다.
    """
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, why = verify_one(_var(), _ctx(bodies={}))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이제 enum 으로 갈렸다** — 지시서(오픈월드) §1-1 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 계약은 *"글이 다름"* 으로 둘을 갈랐다 — 그것이 할 수 있는 최선이었다.
    #  🔴 실측 2026-10-04 이 그 한계를 보였다: 포르투갈 후보 **12건 전부**가
    #     `quote_not_found` 로 묶여, 깔때기만 보면 *"에이전트가 지어냈다"* 로
    #     읽혔다. **실제로는 본문을 못 받은 것**(배선 끊김)이었다.
    #  → 지시서가 사유를 **`BODY_MISSING`** 으로 갈랐다. 고칠 곳도 갈린다:
    #       body_missing     → **수집**
    #       quote_not_found  → **에이전트**
    assert ok is False and reason is Reason.BODY_MISSING, (reason, why)
    assert reason.fix_where == "수집", reason.fix_where
    # 🔴 **어느 쪽인지** 글이 말해야 한다
    assert "받아 두지 않았다" in why, (
        f"🔴 *'본문을 못 받았다'* 와 *'인용이 없다'* 가 섞였다 — 고칠 곳이 "
        f"다르다(수집 vs 에이전트): {why}")
    # ⚠️ 그리고 **지어낸 인용**은 다른 글을 낸다
    _, _, why2 = verify_one(_var(quote="지어낸 말"), _ctx())
    assert "본문에 없다" in why2, why2
    assert why != why2


def test_v5_5_1_인용이_비면_폐기한다():
    """🔴 §2 — *"응답에 인용이 없는 변수는 §5-1 이 버린다."*"""
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, _ = verify_one(_var(quote=""), _ctx())
    assert ok is False and reason is Reason.QUOTE_NOT_FOUND


# ══════════════════════════════════════════════════════════════════
# §5-2 신원 필터
# ══════════════════════════════════════════════════════════════════


def test_v5_5_2_명단_선수_둘이면_통과한다():
    """🔴 §5-2 — *"명단 선수 **2명 이상**이 등장하거나 대회명·상대명."*"""
    from app.verifylayer import verify_one
    ok, _, why = verify_one(_var(), _ctx(competition="", away_names=()))
    assert ok is True, why          # 본문에 Elmas·Trajkovski·Alioski 셋


def test_v5_5_2_남녀_표식이_다르면_폐기한다():
    """🔴 §5-2 — 남녀·연령 표식 불일치면 `identity_mismatch`."""
    from app.reasons import Reason
    from app.verifylayer import verify_one
    body = ("North Macedonia Women host Scotland Women. "
            "Elmas is out with an ankle injury. Trajkovski starts.")
    ok, reason, why = verify_one(
        _var(), _ctx(bodies={"https://ok.example/a": body}))
    assert ok is False and reason is Reason.IDENTITY_MISMATCH, why


@pytest.mark.parametrize("mark", ["Women", "U21", "U-23", "여자", "女子",
                                  "femenil"])
def test_v5_5_2_표식_목록을_선언에서_읽는다(mark):
    from app.verifylayer import AGE_SEX_MARKS
    assert any(mark.lower() in m.lower() or m.lower() in mark.lower()
               for m in AGE_SEX_MARKS), (mark, AGE_SEX_MARKS)


def test_v5_5_2_우리_팀이_없으면_폐기한다_M14():
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, _ = verify_one(
        _var(), _ctx(bodies={"https://ok.example/a":
                             "Elmas is out with an ankle injury. Trajkovski."},
                     home_names=("Nowhere United",), away_names=(),
                     competition="", roster=()))
    assert ok is False and reason is Reason.IDENTITY_MISMATCH


def test_v5_5_2_다른_대회_이야기면_off_match_M36():
    """🔴 §5-2 — *"경기와 무관한 발언(다른 대회·다른 상대 언급만)은 `off_match`."*

    ⚠️ 실측 2026-10-04: `Song was noncommittal about his **WBC** participation`
       이 감독 발언 변수로 올라왔다 — 이 경기와 무관하다.
    """
    from app.reasons import Reason
    from app.verifylayer import verify_one
    body = ("Elmas is out with an ankle injury ahead of the World Baseball "
            "Classic. North Macedonia will miss him at the WBC.")
    ok, reason, why = verify_one(
        _var(), _ctx(bodies={"https://ok.example/a": body},
                     away_names=(), roster=()))
    assert ok is False and reason is Reason.OFF_MATCH, why


# ══════════════════════════════════════════════════════════════════
# §5-3 날짜
# ══════════════════════════════════════════════════════════════════


def test_v5_5_3_칠일_전까지만_받는다():
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, _, _ = verify_one(_var(published_at=KICK - timedelta(days=6)), _ctx())
    assert ok is True
    ok2, r2, _ = verify_one(_var(published_at=KICK - timedelta(days=8)), _ctx())
    assert ok2 is False and r2 is Reason.DATE_MISSING or r2 is Reason.POST_MATCH \
        or r2 is Reason.DATE_MISSING


def test_v5_5_3_킥오프_뒤는_post_match():
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, _ = verify_one(
        _var(published_at=KICK + timedelta(hours=1)), _ctx())
    assert ok is False and reason is Reason.POST_MATCH


def test_v5_5_3_날짜가_없으면_date_missing_M13():
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, _ = verify_one(_var(published_at=None), _ctx())
    assert ok is False and reason is Reason.DATE_MISSING


def test_v5_5_3_naive_날짜는_받지_않는다():
    """🔴 §8-7 — 내부는 전부 UTC·tz 포함."""
    from app.verifylayer import verify_one
    ok, _, why = verify_one(
        _var(published_at=datetime(2026, 10, 3, 12)), _ctx())
    assert ok is False, why


# ══════════════════════════════════════════════════════════════════
# §5-7 중복·충돌 · §5-8 재사용
# ══════════════════════════════════════════════════════════════════


def test_v5_5_7_같은_주장은_한_묶음으로_센다():
    """🔴 §5-7 — *"MinHash 유사도 **0.8 이상**을 한 묶음으로 세어 독립 출처 수."*"""
    from app.verifylayer import independent_sources
    rows = [("https://a.example/1", "Elmas is out with an ankle injury"),
            ("https://b.example/2", "Elmas is out with an ankle injury!"),
            ("https://c.example/3", "Trajkovski will start in attack")]
    n, groups = independent_sources(rows)
    assert n == 2, (n, groups)


def test_v5_5_7_충돌이면_둘_다_보존하고_무게_0():
    """🔴 §5-7 — *"두 매체가 다른 상태를 말하면 `conflict:true` 로 **두 변수
    모두 보존**하되 hardness 0."*"""
    from app.verifylayer import hardness_for
    assert hardness_for("official", conflict=True) == 0
    assert hardness_for("official", conflict=False) == 2


def test_v5_5_8_재검증_안_한_변수는_한_단계_내린다_M31():
    """🔴 §5-8 · M31 — *"`reverified:false` 로 표시하고 hardness 한 단계 내린다."*"""
    from app.verifylayer import hardness_for
    assert hardness_for("official", reverified=False) == 1
    assert hardness_for("local", reverified=False) == 0


def test_v5_5_5_tip_등급은_변수가_못_된다():
    """🔴 §4-3·§5-5 — *"`tip` 등급은 0 이고 **변수가 되지 못한다**."*"""
    from app.reasons import Reason
    from app.verifylayer import verify_one
    ok, reason, why = verify_one(
        _var(url="https://forebet.com/x"),
        _ctx(bodies={"https://forebet.com/x": BODY}))
    assert ok is False and reason is Reason.TIP_SOURCE, why


# ══════════════════════════════════════════════════════════════════
# §5 — 폐기는 **조용히 하지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_v5_5_4_폐기를_사유_개수로_적는다():
    """🔴 §5 — *"카드 하단 `dropped:` 줄에 **개수와 사유**를 적는다."*"""
    from app.funnel import Funnel
    from app.verifylayer import verify_all
    fun = Funnel()
    got = verify_all(
        [_var(id="R1"), _var(id="R2", quote="지어낸 말"),
         _var(id="R3", published_at=None)], _ctx(), funnel=fun)
    assert [v.id for v in got] == ["R1"], [v.id for v in got]
    line = fun.drop_line()
    assert "quote_not_found 1" in line and "date_missing 1" in line, line
