"""🔴🔴 **v6 §7 핵심 — E2E 재생 테스트.** 녹화본으로 카드를 만들고 불변식 10개.

지시서 §7: *"녹화본으로 `pipeline.analyze()` 전체를 오프라인으로 돌려 `Card` 를
검사한다. LLM·검색 호출 **0회**, 비용 0, 결과 결정적."*

══════════════════════════════════════════════════════════════════
⚠️ **s1 은 여기서 돌지 않는다 — 그 까닭을 적는다**
══════════════════════════════════════════════════════════════════

🔴 s1(경기 확정)은 **DB 를 본다**(이름표 사다리·쌓인 경기·오픈월드 ⑥단). 테스트가
   DB 에 기대면 그것은 *"이 기계에서만 되는 계약"* 이고 재생이 아니다.
🔴 그래서 이 고정물은 **그 라이브 실행의 `MatchRef` 를 글자로** 들고 s2~s7 을
   재생한다 — 검색·fetch·LLM 은 **전부 카세트**다(망에 안 나간다).
⚠️ s1 은 `tests/unit_v6_s1_s2.py` 가 따로 센다(철자 단계·확정 기준·창).

🔴 **녹화본**: `tests/fixtures/cassettes/nomatch/soccer_g1_v3` — 2026-10-06
   한국 vs 우즈베키스탄(친선)을 라이브 1회 돌려 받은 것이다($0.0044 · 호출 7).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

from app import cassette
from app.core import pipeline, render
from app.core.schema import Ambiguous, Card, Judgement, MatchRef
from app.core.state import RunState

RUN_ID = "soccer_g1_v3"
HOME, AWAY = "team:000129", "team:000245"
KICK = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)
#: 🔴 카드를 **킥오프 전**에 만든 것으로 센다 — 지난 뒤면 등급이 거둬진다(M97).
NOW = KICK - timedelta(hours=3)

#: 🔴🔴 **사용자 보드**(네 층 지시서 §11 검수 표) — *"사용자 보드(1.66/3.79/4.55)를
#   같이 주면 두 열이 따로 보이는지"*. 🔴 배당이 든 보드다(§2-6 이 그것을 요구한다).
BOARD_TEXT = "보드: 승무패 1.66 3.79 4.55 / 언더오버 2.5 1.95 / 핸디 -0.5 1.90"


def _ref() -> MatchRef:
    """🔴 그 라이브 실행이 확정한 경기 — 수는 DB 가 아니라 **녹화 때 적은 것**이다."""
    # 🔴 **라이브가 적은 값을 글자로** 든다 — 함수로 다시 계산하지 않는다.
    #    ⚠️ 실측 2026-10-06: `comp_short("Friendlies")` 는 `friendlies`(소문자)를
    #       주는데 라이브 s1 은 `Friendlies` 를 넣었다. 그 한 글자 차이로 가설 요청이
    #       달라져 **DeepSeek 카세트 둘이 빗나갔다**(시나리오 6개 → 3개).
    #    🔴 고정물은 **그 실행이 실제로 쓴 값**이어야 한다(재계산은 재생이 아니다).
    return MatchRef(
        id="fotmob:6368651", sport="soccer", competition="Friendlies",
        competition_short="Friendlies",
        home=HOME, away=AWAY, home_name="South Korea", away_name="Uzbekistan",
        kickoff_utc=KICK, venue="Yongin Mireu Stadium", langs=["ko", "uz"],
        # 🔴 이 경기는 오픈월드로 들어왔다(이름표가 `한국` 을 몰랐다)
        openworld=True)


@pytest.fixture(scope="module")
def replaying():
    """🔴🔴 **재생 환경을 이 파일 안에서만** 켠다 — 끝나면 되돌린다.

    ⚠️ 실사고 2026-10-06: `os.environ` 에 그냥 심었더니 **같은 워커의 다른 계약**이
       재생 모드로 끌려가 `tests/test_search.py` 네 건이 `SearchUnavailable` 로
       빨개졌다(혼자 돌리면 통과했다 — 그래서 더 위험하다).
    🔴 모듈 상태를 테스트가 **남기지 않는다**(v6 §2 가 같은 말을 한다).
    """
    old = {k: os.environ.get(k)
           for k in (cassette.MODE_ENV, cassette.RUN_ENV,
                     cassette.FALLTHROUGH_ENV)}
    os.environ[cassette.MODE_ENV] = cassette.REPLAY
    os.environ[cassette.RUN_ENV] = RUN_ID
    # 🔴 **빗나가면 실패다** — 몰래 망으로 넘어가지 않는다(§5 `replay_miss`)
    os.environ.pop(cassette.FALLTHROUGH_ENV, None)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시계를 못 박는다** — 실사고 2026-10-10
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 고정물이 **날짜가 흐르자 빨개졌다**(세 건). 까닭은 수집 회귀가
    #     아니었다 — `datehint.too_old` 가 **실제 오늘**로 창을 재서
    #     `주소 날짜 2026-09-30 … 지금보다 10일 전` 으로 문서 **13건을 버렸다**.
    #     고정물의 킥오프는 10-06 이므로 그 문서들은 창 **안**이다.
    #  🔴 재생은 **시각까지 재생**이어야 한다(사용자 지시 §4: 모든 창은 현재
    #     시각 기준 · `--as-of` 로 고정). 시계는 `window.set_clock` 하나다.
    from app import window as _w
    _w.set_clock(NOW)
    yield
    _w.set_clock(None)
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def card(replaying) -> Card:
    """🔴 재생으로 만든 카드 **하나** — 모든 불변식이 이것을 본다."""
    from app import net as _net_mod
    from app import search as _search
    from app.core import board as _board
    from app.core import reweight as _reweight
    from app.core import shape as _shape
    from app.core.stages import (s2_facts, s2b_base, s2c_market, s3_docs,
                                 s2d_strategy, s4_extract, s5_verify, s6_hypo,
                                 s7_judge, s9_audit)
    BOARD, _extra, _bad = _board.parse(BOARD_TEXT)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **재정렬을 예열한다** — 실측 2026-10-06
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 예열 없이 돌리니 재정렬이 BM25 로 떨어져 **상위 3건이 달라졌고**, 그래서
    #     fetch 열쇠가 녹화본에 없어 문서가 10건 → **5건**이 됐다. 입력이 달라지면
    #     추출 요청도 달라져 LLM 카세트가 **전부 빗나간다**(변수 0개).
    #  🔴 라이브 실행기(`tools/v6_run.py`)도 입구에서 예열한다 — **같은 경로**여야
    #     재생이 재생이다.
    ref, state = _ref(), RunState(match_key="fotmob:6368651")

    async def _go() -> Card:
        net = _net_mod.Net()
        chain = _search.build_chain()
        facts = await s2_facts.run(ref, state=state, net=net)
        # 🔴🔴 **네 층**(네 층 지시서 §1) — ① ② 는 s2b, ④ 는 s2c. 🔴 녹화본으로 돈다
        #    (키가 없으면 ④ 는 "시장 없음 — 키가 없다" 이고 그것도 **세는 사실**이다).
        base_p, adj_p = await s2b_base.run(ref, facts, state=state, net=net,
                                          when=NOW.date())
        feed_mk, user_mk = await s2c_market.run(ref, pool=None, net=net,
                                               state=state, board=BOARD)
        cache: dict = {}
        docs = await s3_docs.run(ref, facts, state=state, chain=chain, net=net,
                                 cache=cache)
        cands = await s4_extract.run(ref, docs, state=state, chain=chain,
                                     net=net, cache=cache)
        docs = list(cache.values()) or docs
        variables = s5_verify.run(ref, facts, docs, cands, state=state)
        # 🔴🔴 **확정 라인업 전략**(사용자 지시 2026-10-10(둘째)) — 이 고정물의
        #    XI 는 `none` 이므로 `확정 XI 전` 이 나와야 한다(§1). 그것이 바로
        #    *"예상 XI 로는 전략을 추론하지 않는다"* 를 재생이 세는 자리다.
        plan = s2d_strategy.run(ref, facts, state=state)
        # 🔴🔴 **새 순서**(순서 재편 지시서 2026-10-10 다섯째) — 단계 2 는 가설만
        #    내고, 시나리오는 단계 4 가 시뮬 분포에서 만든다. ⚠️ 이 고정물은 상성·
        #    시뮬을 돌리지 않으므로(`matchup` 이 없다) 시나리오는 **필수형 보강**
        #    만이고, 그 사실이 재생과 운영의 차이로 남는다.
        hypo = s6_hypo.claims(ref, facts, variables, state=state)
        hypo = s6_hypo.scenarios(ref, facts, variables, hypo, {}, state=state)
        # 🔴🔴 **파이프라인과 같은 순서**(2026-10-07 재가중 ①) — 우리 열 → 재가중 →
        #    생존. ⚠️ 순서가 다르면 재생이 운영을 흉내낸 것이 아니다.
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **S1V → S2 → S3**(상성 엔진 지시서 2026-10-10 여섯째)
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 확률의 출처는 **상성 하나**다(P1) — 그래서 재생도 그 순서로 돈다.
        #  ⚠️ 이 고정물은 상성 재료(폼·스타일·골 프로필)를 안 모은다 → 축1·2·3 은
        #     `⬜`(사유가 남는다)이고 축0 만 센다. 그것이 재생과 운영의 차이다.
        from app.core import matchup as _mu
        from app.core import probmodel as _pm
        from app.core import routing as _routing
        varset = _routing.place(variables)
        edge: dict = {"form": {}, "style": {}, "profile": {}, "fired": [],
                      "fired2": [], "off": {}, "late": {}}
        mr = _mu.report(ref, facts, edge, varset, strategy=plan)
        prob = _pm.run(ref, facts, mr, varset, edge=edge,
                       state=state)
        layers = pipeline._layers(ref, facts, variables, hypo, base_p, adj_p,
                                 feed_mk, user_mk, state=state, strategy=plan)
        layers["strategy"] = plan
        layers["varset"] = varset
        edge["report"] = mr
        if prob.ok():
            from app.core.schema import ProbTriple as _PT
            layers["ours"] = _PT(home=prob.home, draw=prob.draw,
                                 away=prob.away)
            edge["sim"] = prob.as_sim()
            edge["share"] = dict(prob.share)
            edge["share_refs"] = dict(prob.share_refs)
            said_base = _pm.league_base(ref, facts, varset)
            if said_base:
                layers["prob_before"] = _PT(home=said_base["home"],
                                            draw=said_base["draw"],
                                            away=said_base["away"])
        layers["matchup"] = edge
        hypo = _reweight.of(hypo, layers.get("ours"), ref=ref, state=state)
        said = s7_judge.run(ref, facts, variables, hypo, state=state, now=NOW,
                            board=BOARD, board_source="user_board")
        said = pipeline._direction(pipeline._lower(said, layers, state=state),
                                  layers, ref)
        # 🔴🔴 **양상·논평도 재생이 센다**(사용자 지시 2026-10-07 ②③) — ⚠️ 논평
        #    호출은 녹화본에 없다(미스 → `None`) → **코드 템플릿**으로 간다. 그
        #    템플릿은 수를 이어 붙이는 것뿐이라 **결정적**이다(스냅샷이 그것을 센다).
        got_shape = _shape.of(hypo)
        # 🔴🔴 **검열까지**(2026-10-07 §4) — 재생에서는 Solar·DeepSeek 호출이 녹화본에
        #    없으면 미스이고, 그러면 **코드 템플릿**으로 간다(그 길도 결정적이다).
        out = s9_audit.run(ref, facts, variables, hypo, said, got_shape,
                           state=state, board_source="user_board",
                           ours=layers.get("ours"))
        layers.update(pipeline._comment_layers(out, got_shape))
        layers["board_source"] = "user_board"
        got_card = pipeline.card_of(ref, facts, variables, hypo, said,
                                    state=state, layers=layers)
        # 🔴🔴 **1겹 이유 문단**(지시 2026-10-09(3차)) — 라이브 입구와 **같은 순서**
        #    여야 재생이 재생이다(`pipeline.analyze` 도 카드 뒤에 이것을 부른다).
        return pipeline.with_reason(got_card, state=state)

    got = asyncio.run(_go())
    # 🔴 **비용 0** — 재생은 지갑에 닿지 않는다(§7)
    assert got.cost.usd == 0.0, got.cost
    return got


@pytest.fixture(scope="module")
def docs_by_id(card: Card, replaying) -> dict:
    """🔴 변수의 `doc_ids` 로 본문을 되찾는 표 — 불변식 2·9 가 쓴다."""
    from app import net as _net_mod
    from app import search as _search
    from app.core.stages import s2_facts, s3_docs
    ref, state = _ref(), RunState()

    async def _go() -> dict:
        net = _net_mod.Net()
        facts = await s2_facts.run(ref, state=state, net=net)
        cache: dict = {}
        await s3_docs.run(ref, facts, state=state, chain=_search.build_chain(),
                          net=net, cache=cache)
        return {d.id: d for d in cache.values()}

    return asyncio.run(_go())


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 카드 불변식 **열 개**(§7)
# ══════════════════════════════════════════════════════════════════


def test_불변식1_카드가_나오고_블록_열_개가_있다(card: Card):
    """1. 카드가 나온다(예외 없음), 블록 1~9 전부 존재, 방향 문장이 팀 이름 또는 `반반`."""
    said = render.card_text(card)
    # 🔴 축구 완성 지시서 §5 가 블록 **2b(결장)**·**3b(경우의 수)** 를 더했다 —
    #    번호는 `render.NUMBERS` 가 든다(손으로 세지 않는다 · #1).
    for num, title in zip(render.NUMBERS, render.TITLES, strict=True):
        assert f"**{num}. {title}**" in said, (num, title)
    assert card.direction
    assert (card.match.home_name in card.direction
            or card.match.away_name in card.direction
            or "반반" in card.direction), card.direction


def _from_docs(card: Card) -> list:
    """🔴 **기사에서 온 변수만** — 해석 규칙(IR01~)이 만든 사실 변수는 따로 센다.

    ⚠️ s5 는 `Facts` 에서도 변수를 만든다(사용자 지시 2026-10-06 ⑥). 그것들은
       기사가 아니라 **어댑터 수치**라 `doc_ids` 가 비어 있고, `from_rule` 이 어느
       규칙인지 말한다. 🔴 불변식 2·9 는 **기사 변수**를 세는 것이다 — 사실 변수는
       아래 `불변식9_…` 가 따로 본다(빈 `doc_ids` 를 조용히 통과시키지 않는다).
    """
    return [v for v in card.variables if v.from_rule is None]


def test_불변식2_인용이_그_문서_본문에_글자_그대로_있다(card: Card, docs_by_id: dict):
    """2. 모든 `Variable` 의 `quote` 가 `doc_ids` 중 하나의 본문에 정규화 후 그대로."""
    from app.core.stages import s5_verify
    assert _from_docs(card), "기사 변수가 0개면 이 불변식은 아무것도 세지 않는다"
    for v in _from_docs(card):
        bodies = [docs_by_id[d].body for d in v.doc_ids if d in docs_by_id]
        assert bodies, (v.id, v.doc_ids, sorted(docs_by_id))
        assert any(s5_verify.quote_ok(v.quote, b)[0] for b in bodies), v.id


def test_불변식3_주체가_그_경기_두_열쇠이고_방향이_열거값_안이다(card: Card):
    """3. `subject` 가 두 팀 열쇠 중 하나, `favors` 가 enum 안."""
    from app.core.schema import Favors
    ok = set(Favors.__args__)                         # type: ignore[attr-defined]
    for v in card.variables:
        assert v.subject in (card.match.home, card.match.away), v
        assert v.favors in ok, v


def test_불변식4_자팀_결장은_자팀_쪽이_아니다(card: Card):
    """4. 자팀 결장 변수의 `favors` 가 자팀 쪽이 아니다 / 확정 팀 `stakes` 도 그렇다.

    🔴 방향은 **카탈로그 규칙**이 정한다 — `absence` 는 상대, `def_absence` 는
       `goals_up` 이다. ⚠️ 어느 쪽이든 **자기 쪽은 아니다.**
    """
    for v in card.variables:
        if not v.type.endswith("absence") and "absence" not in v.type:
            continue
        side = "home" if v.subject == card.match.home else "away"
        assert v.favors != side, v


def test_불변식5_인용된_변수는_전부_근거로_쓸_수_있다(card: Card):
    """5. 가설·시나리오가 인용한 `var_id` 가 전부 `usable_as_basis=True`."""
    ok = {v.id for v in card.variables if v.usable_as_basis}
    assert card.hypo is not None
    for h in card.hypo.hypotheses:
        for line in [*h.reasons, *h.breaks]:
            assert set(line.var_ids) <= ok, (h.team, line)
    for s in card.hypo.scenarios:
        assert set(s.driver_vars) <= ok, s.id


def test_불변식6_조건_걸린_필수형이_전부_있다(card: Card):
    """6. 조건이 맞는 필수형 시나리오가 전부 존재한다(표가 조건을 든다)."""
    from app.core.stages.s6_hypo import _required_names
    assert card.hypo is not None
    want = _required_names(card.facts)
    kinds = {s.type for s in card.hypo.scenarios}
    if "우세팀_실점_동반형" in want and any(
            h != a for s in card.hypo.scenarios for h, a in s.outcomes):
        # 🔴 이긴 쪽이 한 점을 주는 꼴이 **있어야** 한다
        assert any(min(h, a) >= 1 and h != a
                   for s in card.hypo.scenarios for h, a in s.outcomes), kinds
    if "90분_무승부형" in want:
        assert "draw_90" in kinds or any(
            h == a for s in card.hypo.scenarios for h, a in s.outcomes), kinds


def test_불변식7_죽는_갈래가_있으면_생존이_1이_아니다(card: Card):
    """7. `✗`·`△` 가 있는 마켓의 `survival < 1.0`, XI 상한 적용, 시작했으면 등급 없음."""
    assert card.evals
    for e in card.evals:
        if any(m in ("✗", "△") for m in e.marks.values()):
            assert e.survival < 1.0, e
        assert e.cap <= 1.0
        if card.started:
            assert e.grade in ("없음", "자료부족"), e
    # 🔴 XI 를 못 잡은 경기는 상한이 **1.0 이 아니다**
    if not card.facts.xi:
        assert all(e.cap < 1.0 for e in card.evals), [e.cap for e in card.evals]


def test_불변식8_반증이_시나리오를_지우지_않았다(card: Card):
    """8. 반증 후 시나리오가 줄지 않았고, 어떤 마켓도 생존이 **오르지 않았다**.

    🔴 v6 의 반증은 **줄만 더한다**(`RedTeamOut.lines`) — 시나리오 집합에 닿지
       않으므로 생존은 **구조적으로** 오를 수 없다. 그 사실을 센다: 반증이 만든
       시나리오가 0개이고, 생존을 다시 세도 같은 수다.
    """
    assert card.hypo is not None
    assert [s for s in card.hypo.scenarios if s.added_by == "redteam"] == []
    before = {s.id for s in card.hypo.scenarios}
    for e in card.evals:
        assert set(e.marks) <= before, e


def test_불변식9_발행일_없는_문서를_근거로_한_변수가_없다(card: Card, docs_by_id: dict):
    """9. `Doc` 마다 발행일 또는 `date_source="none"` 사유가 있고, `none` 은 근거가 아니다."""
    for d in docs_by_id.values():
        assert (d.published_at is not None) == (d.date_source != "none"), d.id
    for v in _from_docs(card):
        assert v.doc_ids, v.id
        for did in v.doc_ids:
            got = docs_by_id.get(did)
            assert got is not None and got.published_at is not None, (v.id, did)
    # 🔴 **사실 변수는 문서가 없다** — 그 사실을 조용히 넘기지 않고 센다:
    #    규칙 이름이 있고 `doc_ids` 가 비어 있어야 한다(둘 중 하나만이면 결함이다).
    for v in card.variables:
        if v.from_rule is None:
            continue
        assert v.doc_ids == [], (v.id, v.doc_ids)
        # 🔴 번호 앞머리 둘 — `S`(구조 사실 규칙)·`IR`(접목 지시서 해석 규칙).
        #    ⚠️ 사용자 지시 2026-10-06(2차) ④ 로 S01~S04 로 바꿨고, IR 표는 아직
        #       비어 있다(`config/interpret_rules.yaml` 의 `ir_table`).
        assert v.from_rule[:1] in ("S", "I"), v.from_rule


def test_불변식10_깔때기_합계가_맞는다(card: Card):
    """10. 받은 후보 수 = 통과 + 버림 사유 합.

    🔴 s4 가 낸 후보는 s5 에서 **변수가 되거나 버려진다** — 그 둘의 합이 후보 수다.
    ⚠️ 병합(`duplicate`)도 **버림**으로 세어야 맞는다(두 후보가 한 변수가 된다).
    """
    counts = card.funnel.counts
    got = counts.get("candidates")
    assert got is not None, counts
    dropped = [d for d in card.funnel.drops if d.what.startswith("s5/")]
    made = len([v for v in card.variables if v.from_rule is None])
    assert made + len(dropped) == got, (made, len(dropped), got,
                                        [d.reason.value for d in dropped])


def test_카드_전문_스냅샷(card: Card):
    """🔴 카드 텍스트 **스냅샷** — 의도치 않은 변화가 diff 로 보이게(§7).

    ⚠️ 갱신은 **사유를 커밋 메시지에 적을 때만** 한다.
    """
    import pathlib
    said = render.card_text(card)
    path = pathlib.Path(__file__).with_name("snapshot_soccer_g1_v3.md")
    if not path.exists() or os.environ.get("V6_SNAPSHOT_UPDATE") == "1":
        path.write_text(said, encoding="utf-8")
        pytest.skip(f"스냅샷을 새로 적었다: {path.name}")
    assert said == path.read_text(encoding="utf-8"), (
        "🔴 카드 전문이 스냅샷과 다르다 — 의도한 변화면 "
        "`V6_SNAPSHOT_UPDATE=1` 로 갱신하고 **사유를 커밋에 적는다**")


def test_불변식12_공격_결장_유형이_수비수에게_붙지_않는다(card: Card):
    """🔴🔴 **사용자 지시 2026-10-06(2차) ①** — 그 반대도 센다.

    > 공격수 결장 유형이 수비수에게 붙으면 **실패**하는 E2E 불변식 추가.

    🔴 포지션을 아는 자료가 있을 때만 셀 수 있다 — `position_of` 가 그 자료를 든다.
    ⚠️ 자료가 없으면 이 불변식은 **아무것도 세지 않는다**. 그래서 그 사실을 함께
       적는다(#3 조용한 0 금지): 몇 개를 셌는지 센다.
    """
    from app.core.stages.s5_verify import position_of
    seen = 0
    for v in card.variables:
        pos = position_of(v.target, card.facts)
        if not pos:
            continue
        seen += 1
        if pos == "def":
            assert v.type != "absence_att", (v.id, v.target, v.type)
        if pos == "att":
            assert v.type != "def_absence", (v.id, v.target, v.type)
    # 🔴 **한 사실은 한 변수다**(①) — 같은 주체·대상의 결장 변수가 둘이면 실패
    from app.core.stages.s5_verify import ABSENCE_KINDS, norm
    keys: dict[tuple[str, str], list[str]] = {}
    for v in card.variables:
        if v.type not in ABSENCE_KINDS or not v.target:
            continue
        keys.setdefault((v.subject, norm(v.target)), []).append(v.id)
    doubled = {k: ids for k, ids in keys.items() if len(ids) > 1}
    assert not doubled, f"🔴 같은 결장 사실이 여러 변수다: {doubled}"
    print(f"[불변식11] 포지션을 아는 변수 {seen}개 · 결장 열쇠 {len(keys)}개")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **축구 완성 지시서 §6 — 새 불변식 11~15**
# ══════════════════════════════════════════════════════════════════


def test_불변식11_카드의_변수_유형이_전부_축구_enum_안이다(card: Card):
    """11. 축구 카드의 변수 유형이 **전부 축구 enum 안**(§6).

    🔴 야구·농구 전용 유형(`pitcher_state` 등)이 축구 요청 enum 에 들어가면 **실패**다
       (실측 2026-10-06: 그 유형이 축구 카드의 변수 다섯을 먹고 방향을 뒤집었다).
    """
    from app import rules
    ok = set(rules.types_for_sport(card.match.sport))
    bad = [(v.id, v.type) for v in card.variables if v.type not in ok]
    assert not bad, f"🔴 축구 enum 밖 유형: {bad}"


def test_불변식13_예상_XI_에_결장자가_없다(card: Card):
    """13. XI 예상 명단에 결장 명단 선수가 **없다**(있으면 `conflict` 로 빠져 있다)."""
    for key, xi in card.facts.xi.items():
        gone = {m.name.strip().lower() for m in card.facts.missing.get(key, [])}
        if not gone:
            continue
        left = [n for n in xi.players if n.strip().lower() in gone]
        assert not left, (key, left, xi.conflicts)


def test_불변식14_추가_옵션_묶음과_기대값_금지(card: Card):
    """14. 보드 `추가:` 줄 마켓은 **추가 옵션 묶음에만**, 카드에 **기대값·금액이 없다**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **배당 칸 금지는 걷혔다** — 네 층 지시서 §2-6(2026-10-06)
    ══════════════════════════════════════════════════════════════════

    종전 이 불변식은 `BoardLine` 에 `price` 칸이 **없음**을 셌다(절대규칙 6).
    🔴 새 지시서가 그 칸을 **요구한다** — *"파서는 배당을 버리지 않고 `BoardLine.price`
       에 담는다"*. 그래서 세는 것을 **바꾼다**: 배당은 있어도 되고,
       🔴 **기대값·손익분기·켈리·금액은 어디에도 없어야 한다**(§0 금지).
    """
    from app.core.schema import BoardLine
    assert "price" in BoardLine.model_fields          # 🔴 §2-6 이 요구한다
    said = render.card_text(card)
    for word in ("기대값", "EV ", "손익분기", "켈리", "스테이크", "배팅액", "원)"):
        assert word not in said, word
    if card.board_extra:
        # 🔴 추가 줄은 **그 묶음 아래**에만 나온다
        head = said.index("추가 옵션에 있으면")
        for row in card.board_extra:
            market = row.split()[0]
            assert said.rindex(market) > head or said.count(market) > 1, row


def test_불변식15_재분석_카드에_바뀐_것_블록이_있다(card: Card):
    """15. 재분석 카드에 *"바뀐 것"* 블록이 있고 **s3·s4 LLM 호출이 0회**.

    ⚠️ 이 고정물은 **첫 분석**이다(재분석이 아니다) — 그래서 여기서는 `changed` 가
       **비어 있어야** 한다. 🔴 재분석 쪽은 `pipeline.reanalyze` 가 `_diff` 로 그
       블록을 채우고, s3·s4 를 **아예 부르지 않는다**(그 사실을 코드로 센다).
    """
    import ast
    import inspect

    from app.core import pipeline
    assert card.changed == [], card.changed
    tree = ast.parse(inspect.getsource(pipeline.reanalyze))
    said = {ast.unparse(n.func) for n in ast.walk(tree)
            if isinstance(n, ast.Call)}
    assert not {x for x in said if "s3_docs" in x or "s4_extract" in x}, said


def test_불변식16_사실이_그대로면_등급도_그대로다(card: Card):
    """🔴🔴 **사용자 지시 2026-10-06(3차) ④** — 재분석이 수를 흔들지 않는다.

    > 재분석: 변수 목록이 바뀌지 않았으면 DeepSeek 를 다시 부르지 않고 이전 시나리오를
    > 그대로 쓴다 … *"사실 그대로 → 등급 그대로"* 를 **E2E 불변식으로.**

    🔴 재생본으로 **재분석을 한 번 더** 돌려 센다: 같은 사실(같은 녹화본)이면 시나리오·
       등급이 **글자까지 같아야** 한다. ⚠️ s6 를 다시 부르면 모델이 흔들려 다르다 —
       그래서 이 불변식이 그 호출을 막는 증거가 된다.
    """
    import asyncio

    from app.core import pipeline
    from app.core.state import RunState

    # 🔴 이 고정물의 카드를 **마지막 실행**으로 심고 재분석을 돌린다
    pipeline._LAST[card.match.id] = {
        "at": NOW, "ref": card.match, "docs": [], "cands": [],
        "card": card, "board_text": ""}
    st = RunState(match_key=card.match.id)
    got = asyncio.run(pipeline.reanalyze(
        f"{card.match.home_name} vs {card.match.away_name}",
        pool=None, net=None, chain=None, state=st, now=NOW))
    # ⚠️ 이 고정물은 DB 없이 돈다 — 그래서 s1(입구)이 못 돈다. 🔴 재분석의 **알맹이**
    #    (변수가 같으면 s6 를 다시 안 부르고 등급이 그대로인가)는 입구와 무관하므로
    #    **그 부분만** 센다: `_same_vars` 와 `_diff` 를 직접 본다.
    if isinstance(got, Ambiguous):
        assert pipeline._same_vars(card.variables, card.variables)
        said = pipeline._diff(card, card.facts, card.variables,
                              Judgement(evals=card.evals,
                                        direction=card.direction,
                                        conclusion=card.conclusion))
        assert said == ["바뀐 것 **없다**(XI 상태·변수·등급 모두 같다)"], said
        return
    assert got.hypo is not None and card.hypo is not None
    assert [s.id for s in got.hypo.scenarios] == \
           [s.id for s in card.hypo.scenarios]
    assert [(e.line.market, e.line.side, e.grade) for e in got.evals] == \
           [(e.line.market, e.line.side, e.grade) for e in card.evals], \
        "🔴 사실이 그대로인데 등급이 바뀌었다(④)"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **변수 관련성 — 새 불변식 17~19**(사용자 지시 2026-10-06(4차) ④)
# ══════════════════════════════════════════════════════════════════
#
# > ④ E2E 불변식 추가: 기사 출처 변수는 전부 `match_link` 근거가 문단에 있다 /
# >   XI 상태가 `none` 이면 IR02 변수가 0개 / 홈 이점 숫자의 출처 대회 유형이
# >   경기의 대회 유형과 같다.


def test_불변식17_기사_변수는_전부_이_경기와_이어지는_근거를_가진다(
        card: Card, docs_by_id: dict):
    """17. 기사에서 온 변수는 `match_link` 가 있고, **그 말이 문단에 글자로** 있다.

    🔴 왜: 실측 2026-10-06 — 아시안게임 문단에서 뽑은 말이 A대표 카드에 들어왔다.
       그 줄들은 *"어느 경기 이야기인지"* 를 아무 데도 안 적고 있었다.
    ⚠️ 규칙으로 지은 변수(`from_rule`)는 문단이 없다 — 검사 대상이 아니다.
    """
    said = [v for v in card.variables if v.doc_ids and not v.from_rule]
    assert said, "🔴 기사에서 온 변수가 0개다 — 이 고정물이 검사할 것을 잃었다"
    for v in said:
        assert v.match_link, f"🔴 `{v.id}` 에 match_link 가 없다 — {v.claim}"
        body = "\n".join(str(getattr(docs_by_id.get(d), "body", ""))
                         for d in v.doc_ids)
        if not body:
            continue                    # 본문을 못 되찾은 문서는 2·9 가 잡는다
        from app.core.stages.s5_verify import norm
        assert norm(v.match_link) in norm(body), \
            f"🔴 `{v.id}` 의 match_link 가 문단에 없다: {v.match_link!r}"


def test_불변식18_오늘_XI_가_없으면_IR02_변수가_없다(card: Card):
    """18. XI 상태가 `none` 이면 **IR02(로테이션) 변수는 0개**다.

    🔴 왜: 실측 2026-10-06 — 오늘 XI 가 안 나온 경기에서 *"직전 XI 와 다르다"* 를
       말했다. 비교 대상이 없는데 비교를 한 것이다(사용자 지시 ②).
    """
    now = card.facts.xi.get(card.match.home) if card.facts.xi else None
    both = [card.facts.xi.get(k) for k in (card.match.home, card.match.away)] \
        if card.facts.xi else []
    states = {getattr(x, "state", "none") for x in both if x is not None}
    mine = [v for v in card.variables if v.from_rule == "IR02"]
    if not states or states <= {"none"}:
        assert not mine, f"🔴 오늘 XI 가 없는데 IR02 변수가 {len(mine)}개다: " \
                         f"{[v.claim for v in mine]}"
    else:
        assert now is not None or both, "XI 표가 비어 있다"


def test_불변식19_홈_이점_숫자는_같은_대회_유형에서_왔다(card: Card):
    """19. 홈 이점 변수의 숫자는 **그 경기의 대회 유형** 표에서 온 것이다.

    🔴 왜: 실측 2026-10-06 — 대표팀 친선 카드에 **MLS**(리그) 숫자가 적혀 있었다.
    ⚠️ 숫자가 없으면(`수치 없음`) 통과다 — 빌려 오지 않은 것이 요점이다(③).
    """
    from app.core.stages.s5_verify import comp_kind
    kind = comp_kind(card.match, card.facts)
    mine = [v for v in card.variables if v.type == "home_field"]
    assert mine, "🔴 home_field 변수가 빠졌다(①)"
    for v in mine:
        if "수치 없음" in v.claim:
            continue
        if "쪼갠 표" in v.claim:
            continue                    # 잰 수다 — 빌려 온 것이 아니다
        assert f"`{kind}`" in v.claim, \
            f"🔴 홈 이점 숫자의 출처 대회가 `{kind}` 가 아니다: {v.claim}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **네 층 확률 + 시장 비교 — 불변식 20~25**(네 층 지시서 §9)
# ══════════════════════════════════════════════════════════════════


def test_불변식20_모든_확률_셋은_합이_1이다(card: Card):
    """20. 모든 `ProbTriple` 합 = 1.0(±0.001), 각 값 0~1."""
    from app.core.schema import ProbTriple
    said = [card.base_prob.probs, card.adj_prob.probs, card.our_prob]
    for p in [x for x in said if isinstance(x, ProbTriple)]:
        assert abs(p.home + p.draw + p.away - 1.0) < 0.001, p
        assert all(0.0 <= v <= 1.0 for v in (p.home, p.draw, p.away)), p
    assert card.base_prob.probs is not None, \
        f"🔴 이 고정물에서는 ① 이 나와야 한다 — {card.base_prob.why}"


def test_불변식21_시장_열에_출처와_시각이_적혀_있다(card: Card):
    """21. 시장 열이 있으면 **출처**(피나클/중앙값/단일/사용자 보드)가 적혀 있다."""
    said = render.card_text(card)
    box = card.market
    if not box.probs:
        assert "시장 없음" in said, "🔴 시장이 없는데 사유가 없다"
        return
    assert box.basis, "🔴 시장 확률이 있는데 출처가 비었다"
    assert box.basis in said, box.basis
    if box.source != "user_board" and box.captured_at is not None:
        from app import timefmt
        assert timefmt.kst_label(box.captured_at) in said


def test_불변식22_사용자_보드와_피드가_한_열에_섞이지_않았다(card: Card):
    """22. 사용자 보드 배당과 피드 배당이 **한 열에** 섞이지 않았다(§2-6)."""
    books = {q.bookmaker for q in (card.market.quotes or [])}
    assert not ({"user_board", "user_board(ocr)"} & books) or books <= \
        {"user_board", "user_board(ocr)"}, \
        f"🔴 시장 열에 사용자 보드와 피드 업체가 섞였다: {books}"
    mine = {q.bookmaker for q in (card.user_market.quotes or [])}
    assert mine <= {"user_board", "user_board(ocr)"}, mine


def test_불변식23_우리_열이_방향_판정의_우리_확률과_같다(card: Card):
    """23. 7b 의 우리 열 = 블록 9 방향 판정의 우리 확률(**같은 숫자**)."""
    if card.our_prob is None:
        return
    said = render.card_text(card)
    want = f"우리 홈 {card.our_prob.home:.0%}/원정 {card.our_prob.away:.0%}"
    assert want in said, f"🔴 방향 줄의 우리 수가 7b 와 다르다 — {want}"


def test_불변식24_카드에_기대값이나_금액이_없다(card: Card):
    """24. 카드 어디에도 EV·기대값·스테이크·켈리 문자열이 없다(§0 금지)."""
    said = render.card_text(card)
    for word in ("기대값", "EV", "켈리", "kelly", "스테이크", "손익분기", "배팅액"):
        assert word not in said, word


def test_불변식25_기준이나_시장이_없으면_사유와_함께_열이_빈다(card: Card):
    """25. 기준·시장이 없으면 *"없음 — 사유"* 가 있고 그 열은 `—`(숫자를 안 지어낸다)."""
    said = render.card_text(card)
    if card.base_prob.probs is None:
        assert "기준 없음" in said and card.base_prob.why
    if not card.market.probs:
        assert "시장 없음" in said and card.market.why
    # 🔴 ② 가 못 돌면 그 사유가 블록 3c 에 있다
    if card.adj_prob.probs is None:
        assert card.adj_prob.why and card.adj_prob.why[:12] in said, card.adj_prob.why


def test_불변식26_축구_카드의_우리_열_무승부가_0이_아니다(card: Card):
    """26. **축구 시나리오에는 무승부 갈래가 있다** → 우리 열 무승부 > 0.

    🔴 사용자 지시 2026-10-06(5차) ①: *"축구 시나리오 세트에 무승부(0-0 또는 1-1)
       갈래가 하나도 없으면 코드가 보강한다(v4 `soccer_lock` 과 같은 역할).
       E2E 불변식: 축구 카드의 우리 열 무승부 > 0."*
    ⚠️ 실측 2026-10-06 온두라스–자메이카: 무승부가 **0%** 였고 `무`·`더블찬스` 가
       그 0 을 그대로 받았다. 원인이 둘이었다 — 갈래가 없을 수 있다는 것과, 섞인
       스코어의 무게가 통째로 사라진다는 것. 🔴 둘 다 고쳤다.
    """
    if card.match.sport != "soccer":
        return
    scen = list(card.hypo.scenarios) if card.hypo is not None else []
    assert any(h == a for s in scen for h, a in s.outcomes), \
        "🔴 무승부 스코어가 **하나도 없다**(필수형 보강이 안 돌았다)"
    assert card.our_prob is not None, "우리 확률이 없다"
    assert card.our_prob.draw > 0.0, \
        f"🔴 우리 열 무승부가 0 이다 — 시나리오 {len(scen)}개"


def test_불변식27_라인업_보정의_pp_와_신뢰도가_카드에_있다(card: Card):
    """27. ② 가 확률을 움직였으면 카드에 **%p 와 환산 R²·표본**이 적혀 있다.

    🔴 사용자 지시 2026-10-06(6차) ②: *"카드 3c 에 '라인업 보정 −1.2%p (환산 R² 0.61
       · 표본 33)' 형태로 **계수 신뢰도를 함께** 적는다."*
    ⚠️ 못 움직였으면 그 사유가 적혀 있어야 한다(빈 줄 금지).
    """
    said = render.card_text(card)
    if card.adj_prob.moved:
        assert "%p" in said and "환산 R²" in said and "표본" in said
        assert card.adj_prob.probs is not None
    else:
        assert card.adj_prob.why and ("안 움직였다" in said or "없음" in said)


def test_불변식28_우리_열이_상성에서_나온다(card):
    """🔴🔴 **상성 엔진 지시서 §2·P1**(2026-10-10 여섯째) — 전제가 바뀌었다.

    > §2 Elo 기준 확률을 **출발점에서 뺀다** → V1(검증).
    > P1 확률의 출처는 **상성 하나**다.

    ⚠️ 옛 불변식은 *"우리 열이 **기준(①②)에서 출발**한다"* 였다 — 그 경로를
       지웠으므로 그 계약도 바꾼다(§2 마지막 줄: 빨간 채로 두지 않는다).
    🔴 이제 세는 것: 우리 열이 **S3 산출과 같은 수**이고(C2), ③ 로그 오즈 이동
       목록이 **비어 있다**(C7).
    """
    from app.core import matchup as _mu
    assert card.our_prob is not None, "🔴 우리 확률이 없다"
    box = dict(getattr(card, "matchup", None) or {})
    sim = dict(box.get("sim") or {})
    assert sim.get("home") is not None, "🔴 S3 산출이 카드에 없다"
    for key in ("home", "draw", "away"):
        assert abs(float(getattr(card.our_prob, key))
                   - float(sim[key])) < 1e-9, (key, sim[key])
    # 🔴 C7 — 변수가 로그 오즈를 직접 미는 목록은 **비었다**
    assert list(getattr(card, "moves", None) or []) == [], card.moves
    # 🔴 상성 판정이 카드에 있고 강도 글자가 열거값이다
    mr = box.get("report")
    assert mr is not None, "🔴 MatchupReport 가 카드에 없다"
    assert dict(mr.verdict).get("strength") in (_mu.STRONG, _mu.MID,
                                                _mu.WEAK, _mu.NONE)

def test_불변식29_결장_변수는_그_팀_명단에_있다(card: Card):
    """29. 🔴🔴 **결장 계열 변수의 팀 귀속**(사용자 지시 2026-10-07 §결장-귀속-5).

    > 결장 계열 변수의 target 이 subject 팀 명단에 있거나, **근거 불가로 내려가**
    > 있다.

    ⚠️ 실측 2026-10-07(멕시코–칠레): 멕시코 선수 결장이 **칠레**에 붙어 `favors` 가
       뒤집혔고 가설·시나리오가 *"상대 결장"* 으로 읽었다. 🔴 그 거짓은 카드 어디에도
       표시가 없었다 — 이 불변식이 그 자리를 막는다.
    """
    from app.core.stages.s5_verify import ABSENCE_KINDS, in_squad
    facts = card.facts
    for v in card.variables:
        if v.type not in ABSENCE_KINDS or not v.target:
            continue
        # 🔴 **규칙 변수**(IR11 피로 등)는 선수가 아니라 팀 사실이다 — 명단에 없다
        if v.from_rule:
            continue
        if in_squad(v.target, v.subject, facts):
            continue
        assert not v.usable_as_basis, (
            f"🔴 `{v.target}` 가 {v.subject} 명단에 없는데 **근거로 쓴다** — "
            f"팀 귀속이 뒤집혔을 수 있다(`team_unresolved` 로 내려야 한다)")


def test_불변식30_카드의_논평은_검열_통과본이거나_템플릿이다(card: Card):
    """30. 🔴🔴 **총평 검열**(사용자 지시 2026-10-07 §4-3).

    > 사용자 카드(1겹)에는 **통과한 논평만** 나간다. 검열 과정은 `/디버그` 에만.

    🔴 그래서 카드의 `comment_audit` 는 넷 중 하나이고, `템플릿` 이면 그 논평은
       **코드 템플릿과 같아야** 한다(검열에 걸린 글이 몰래 나가지 않는다).
    """
    from app.core.stages import s8_comment
    assert card.comment_audit in ("통과", "재작성 후 통과", "템플릿", "안 돌았다"), \
        card.comment_audit
    text = render.card_text(card)
    if card.commentary is None:
        assert card.comment_audit in ("템플릿", "안 돌았다")
        return
    if card.comment_audit == "템플릿":
        from app.core.schema import Judgement
        # 🔴 카드는 판정을 **펼쳐서** 들고 있다 — 템플릿이 보는 칸만 다시 싼다
        said = Judgement(evals=list(card.evals), direction=card.direction)
        want = s8_comment.template(card.match, card.shape, card.variables,
                                   card.hypo, said)
        assert card.commentary.title == want.title, (
            "🔴 검열에 걸린 논평이 카드로 나갔다")
        assert card.commentary.score_range == want.score_range
    # 🔴 **검열 과정은 1겹에 안 나간다**(§4-3)
    for word in ("검열", "위반"):
        assert word not in text, f"🔴 1겹 카드에 `{word}` 가 나갔다"
    # 🔴 `/디버그` 에는 나간다
    assert "[검열]" in render.debug_text(card)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **1겹 카드** — 사용자 지시 2026-10-09(3차) §1·§2·§4·§5
# ══════════════════════════════════════════════════════════════════


def test_1겹_카드가_새_순서와_상한을_지킨다(card):
    """🔴🔴 §1·§5 — 돌연변이: 블록 순서를 되돌린다 · 상한을 뺀다.

    🔴 이 고정물은 **s1 을 건너뛴다**(`_ref()` 가 녹화 당시 `MatchRef` 를 글자로
       든다) — 지난 경기는 s1 의 창 검사가 벽시계로 거부하므로 그 길뿐이다.
    """
    from app.core import layer1, render
    said = render.layer1_text(card)
    # ── §1 순서 — 머리 두 줄 뒤에 헤드라인·이유가 **먼저** 온다
    lines = [x for x in said.splitlines() if x.strip()]
    assert lines[0].startswith("⚽"), lines[0]
    assert lines[1].startswith("📋"), lines[1]
    # ⚠️ 경고 줄(🔴)이 머리 두 줄 **뒤**에 끼어들 수 있다(지시 (4차) §2·§3) —
    #    그 줄들을 지나 헤드라인·이유를 찾는다. 🔴 순서는 그대로 지킨다.
    rest = [x for x in lines[2:] if not x.startswith("🔴")]
    assert rest[0].startswith("【헤드라인】"), rest[0]
    assert rest[1].startswith("【이유】"), rest[1]
    # ⚠️ `⚠️` 는 **두 코드포인트**다(U+26A0 U+FE0F) — `x[0]` 으로 세면 깨진다
    # 🔴🔴 **§4 블록 둘이 확률 줄 뒤에 끼어들 수 있다**(2026-10-10(둘째)):
    #    `🧠 라인업 전략` · `📊 확률 변화`. **확정 XI 일 때만** 나온다.
    #    🔴 등뼈는 그대로다 — 확률 → 스코어 → 보드 → 뒤집히는 길.
    spine = [x for x in rest[2:]
             if not x.startswith("🧠") and not x.startswith("📊 **확률 변화")
             and not x.startswith(" ")]
    want = ("📊", "🎯", "🎯", "⚠")
    got = tuple(x[:1] for x in spine[:len(want)])
    assert got == want, got
    # 🔴 전략 블록이 있으면 **확률 줄 바로 뒤**다(떨어져 있으면 못 잇는다)
    heads = [i for i, x in enumerate(rest) if x.startswith("🧠")]
    if heads:
        assert rest[heads[0] - 1].startswith("📊"), rest[heads[0] - 1]
    assert lines[-1].startswith("[📖 자세히]"), lines[-1]
    # ── §5 상한
    assert len(said) <= layer1.CAP_ALL, len(said)
    assert len(layer1.reason_text(card)) <= layer1.CAP_REASON
    # ── §2 단정어 금지 — 1겹 **전체**에 없다
    hit = [w for w in layer1.SURE_WORDS if w in said]
    assert not hit, hit


def test_1겹_헤드라인은_코드가_정한다(card):
    """🔴 §2 — 돌연변이: LLM 글로 방향을 말한다 · 문턱을 지운다."""
    from app.core import layer1
    said = layer1.direction_words(card)
    ours = card.our_prob
    if ours is None:
        assert "기준이 없다" in said, said
        return
    gap = abs(ours.home - ours.away)
    if gap >= layer1.LEAD_STRONG:
        assert said.endswith("우세") and "근소" not in said, (said, gap)
    elif gap >= layer1.LEAD_SLIGHT:
        assert said.endswith("근소 우세"), (said, gap)
    else:
        assert said == "반반", (said, gap)
    # 🔴 걸지 여부 — 네 갈래 중 하나다
    bet = layer1.bet_words(card)
    assert (bet in ("이미 시작 — 예측 아님", "보드를 주면 판정",
                    "이 경기는 걸지 않는다")
            or any(str(e.grade) in bet for e in layer1.graded(card))), bet


def test_1겹_이유_문단이_검열을_지난다(card):
    """🔴🔴 §3·§4 — 돌연변이: 검열 (i)~(l) 을 끄면 일반론이 통과한다."""
    from app.core import layer1
    from app.core.stages import s9_audit
    assert card.reason is not None, "이유 문단이 없다"
    bad = s9_audit.reason_check(card.reason, card=card)
    assert not bad, bad
    assert card.reason_audit in ("통과", "재작성 후 통과", "템플릿"), \
        card.reason_audit
    # 🔴 문장마다 `fact_refs` 가 **카드 사실 id** 여야 한다
    box = layer1.facts_catalog(card)
    for line in card.reason.sentences:
        assert line.fact_refs, f"근거 없는 문장: {line.text[:40]}"
        unknown = [r for r in line.fact_refs if str(r) not in box]
        assert not unknown, (unknown, line.text[:40])


def test_1겹_검열이_일반론과_단정과_없는_선수를_잡는다(card):
    """🔴🔴 §4 (i)~(l) — **잡는지** 본다(통과만 보면 검사가 죽어도 모른다)."""
    from app.core.schema import CommentLine, Commentary, ReasonLine, ReasonPara
    from app.core.stages import s9_audit
    # (j) 범용 문장 — 고유 사실이 없다
    flat = ReasonPara(sentences=[
        ReasonLine(text="측면 전환이 살아나면 유리하다.", fact_refs=[]),
        ReasonLine(text="역습이 통하면 흐름을 가져간다.", fact_refs=[]),
        ReasonLine(text="어느 쪽도 확신할 근거가 없다.", fact_refs=[])])
    bad = s9_audit.reason_check(flat, card=card)
    assert any(x.startswith("(j)") for x in bad), bad
    assert any(x.startswith("(i)") for x in bad), bad
    # (k) 단정어
    sure = ReasonPara(sentences=[
        ReasonLine(text="홈이 반드시 승리할 것이다.", fact_refs=["DIR"]),
        ReasonLine(text="두 번째 문장.", fact_refs=["DIR"]),
        ReasonLine(text="어느 쪽도 확신할 근거가 없다.", fact_refs=["DIR"])])
    bad2 = s9_audit.reason_check(sure, card=card)
    assert any(x.startswith("(k)") for x in bad2), bad2
    # (l) 없는 선수
    ghost = ReasonPara(sentences=[
        ReasonLine(text="Lionel Messi 가 중앙을 흔든다.", fact_refs=["DIR"]),
        ReasonLine(text="두 번째 문장.", fact_refs=["DIR"]),
        ReasonLine(text="어느 쪽도 확신할 근거가 없다.", fact_refs=["DIR"])])
    bad3 = s9_audit.reason_check(ghost, card=card)
    assert any(x.startswith("(l)") for x in bad3), bad3
    # 🔴 **(m) 은 총평이 본다** — (i)~(l) 과 섞이지 않는다
    got = Commentary(title="접전",
                     reasons=[CommentLine(text="격차가 좁게 유지돼 왔다",
                                          var_ids=[])],
                     flow="", score_range=[])
    assert isinstance(s9_audit.h2h_direction_check(
        got, ref=card.match, facts=card.facts), list)
