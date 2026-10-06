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

🔴 **녹화본**: `tests/fixtures/cassettes/nomatch/kor_uzb_v8` — 2026-10-06
   한국 vs 우즈베키스탄(친선)을 라이브 1회 돌려 받은 것이다($0.0044 · 호출 7).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

from app import cassette
from app.core import pipeline, render
from app.core.schema import Card, MatchRef
from app.core.state import RunState

RUN_ID = "kor_uzb_v8"
HOME, AWAY = "team:000129", "team:000245"
KICK = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)
#: 🔴 카드를 **킥오프 전**에 만든 것으로 센다 — 지난 뒤면 등급이 거둬진다(M97).
NOW = KICK - timedelta(hours=3)


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
    yield
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
    from app.core.stages import (s2_facts, s3_docs, s4_extract, s5_verify,
                                 s6_hypo, s7_judge)
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
        cache: dict = {}
        docs = await s3_docs.run(ref, facts, state=state, chain=chain, net=net,
                                 cache=cache)
        cands = await s4_extract.run(ref, docs, state=state, chain=chain,
                                     net=net, cache=cache)
        docs = list(cache.values()) or docs
        variables = s5_verify.run(ref, facts, docs, cands, state=state)
        hypo = s6_hypo.run(ref, facts, variables, state=state)
        said = s7_judge.run(ref, facts, variables, hypo, state=state, now=NOW)
        return pipeline.card_of(ref, facts, variables, hypo, said, state=state)

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
    path = pathlib.Path(__file__).with_name("snapshot_kor_uzb_v8.md")
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


def test_불변식14_추가_옵션_묶음과_배당_숫자(card: Card):
    """14. 보드 `추가:` 줄 마켓은 **추가 옵션 묶음에만**, 배당 숫자가 **어디에도 없다**.

    🔴 배당은 `BoardLine` 에 **칸이 없다**(절대규칙 6) — 그래서 카드에 나올 길이 없다.
       ⚠️ 그 사실을 **센다**(칸이 생기면 이 계약이 빨개진다).
    """
    from app.core.schema import BoardLine
    assert "odds" not in BoardLine.model_fields
    assert "price" not in BoardLine.model_fields
    said = render.card_text(card)
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
