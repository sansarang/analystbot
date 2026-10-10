"""🔴🔴 **v6 파이프라인 — 단계를 순서로 잇는다**(§5 · §8 3단계).

```
Question → s1 → s2 → s3 → s4 → s5 → s6 → s7 → Card
```

🔴 **단계는 예외를 위로 던지지 않는다** — 빈 출력 + `state` 의 사유로 다음 단계가
   돈다. 그래서 **카드는 항상 나온다**(§5). ⚠️ 그것이 2026-10-06 의 결함 ④
   (*"카드가 통째로 안 나왔다"*)를 구조로 막는 자리다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.schema import (AdjProb, Ambiguous, BaseProb, Board, Card, Doc,
                             Facts, Funnel, HypoSet, Judgement, MarketEval,
                             MarketProb, MatchRef, ProbTriple, Question,
                             Variable)
from app.core.state import RunState


#: 🔴 그 경기의 **마지막 실행**을 들고 있는 자리(재분석이 그것을 불러온다 · §4-1)
#
#  ⚠️ 모듈 전역이지만 **실행 상태가 아니다** — 재분석이 *"지난번 무엇을 봤나"* 를
#     알아야 하고, 그것은 프로세스가 사는 동안의 기억이다(봇이 한 프로세스다).
#  🔴 24시간이 지나면 **버린다**(§4-5: 그때는 전체를 새로 돈다).
_LAST: dict[str, dict] = {}
#: 🔴 그 기억을 몇 시간까지 쓰나 — §4-5 가 **24시간**이라 적었다
LAST_TTL_HOURS = 24


async def analyze(raw: str, *, pool: Any, net: Any, chain: Any,
                  state: RunState | None = None, board: Board | None = None,
                  board_text: str = "", board_image: str = "",
                  now: datetime | None = None) -> Card | Ambiguous:
    """🔴 질문 하나 → 카드 하나. ⚠️ 경기를 **못 고르면** `Ambiguous`(묻는다).

    🔴 `board_text` 를 주면 **코드가 파싱한다**(축구 §4 · `app/core/board.py`) —
       LLM 이 보드를 읽지 않는다.
    🔴 `board_image` 를 주면 **로컬 OCR** 로 글을 뽑아 같은 파서로 보낸다(네 층 §2-6).
       ⚠️ 외부 OCR API 를 부르지 않는다 — `app/core/ocr.py` 가 실행 파일을 직접 쓴다.
    """
    import asyncio

    from app.core.stages import (s1_resolve, s2_facts, s2b_base, s2c_market,
                                 s3_docs, s4_extract, s5_verify, s6_hypo,
                                 s7_judge)
    st = state if state is not None else RunState()
    q = _question(raw, now=now)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **보드를 s1 보다 먼저 읽는다** — 사용자 지시 2026-10-10(재작성) §1-1 ①
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 보드가 있으면 보드의 날짜·시각·두 팀·리그 표기를 **먼저 읽는다**
    #  > (이게 가장 정확한 단서다).
    #
    #  ⚠️ 종전에는 OCR 이 **s1 뒤**였다 — 그러면 캡처가 가진 가장 정확한 단서를
    #     경기 찾기가 **못 쓴다**. 🔴 캡처 → 글자 → s1 순서로 바꿨다.
    got_board, extra, bad, ocr_text = board, [], [], ""
    if board_image.strip() and not board_text.strip():
        from app.core import ocr as _ocr
        got_board, extra, bad, ocr_text = _ocr.board_of(board_image.strip())
        st.note(f"보드 캡처 — 로컬 OCR {len(ocr_text)}자 · "
                f"{len(getattr(got_board, 'lines', []) or [])}줄 · 못 읽음 {len(bad)}")
        # 🔴 OCR 글자가 **경기 찾기의 단서**다(§1-1 ①)
        board_text = ocr_text or board_text
    elif board_text.strip():
        from app.core import board as _board
        got_board, extra, bad = _board.parse(board_text)
        st.note(f"보드 {len(got_board.lines)}줄 · 추가 {len(extra)} · "
                f"못 읽음 {len(bad)}")
    ref = await s1_resolve.run(q, pool=pool, state=st, net=net,
                               board_text=board_text)
    if isinstance(ref, Ambiguous):
        return ref
    st.match_key = ref.id
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **네 층**(네 층 지시서 §1) — ①② 는 s2b, ④ 는 s2c(s2 와 병렬)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 한 층이 실패해도 다른 층을 막지 않는다(§1 마지막 줄) — 그래서 `gather` 로
    #     나란히 돌리고 **사유를 들고 빈 층**이 지나간다.
    facts, (feed_mk, user_mk) = await asyncio.gather(
        s2_facts.run(ref, state=st, net=net),
        s2c_market.run(ref, pool=pool, net=net, state=st, board=got_board))
    base_p, adj_p = await s2b_base.run(ref, facts, state=st, net=net)
    # 🔴🔴 §2 경우의 수 — **코드만**(LLM 없음). 순위표가 없으면 빈 표다
    look = s2b_base.outlook(ref, facts, state=st)
    cache: dict[str, Doc] = {}
    docs = await s3_docs.run(ref, facts, state=st, chain=chain, net=net,
                             cache=cache)
    cands = await s4_extract.run(ref, docs, state=st, chain=chain, net=net,
                                 cache=cache)
    # 🔴 s4 가 좁히기 2차로 문서를 더 받았을 수 있다 — **캐시가 전부를 든다**
    docs = list(cache.values()) or docs
    variables = s5_verify.run(ref, facts, docs, cands, state=st)
    # 🔴 ②(2차) — **검증된 결장 변수**까지 넣어 다시 센다(§4-2 · 네트워크 0)
    adj_p = s2b_base.again(ref, facts, base_p, variables, state=st)
    hypo = s6_hypo.run(ref, facts, variables, state=st)
    if ocr_text and got_board is not None:
        from app.core import odds as _odds
        user_mk = _odds.from_board(got_board, source="user_board(ocr)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **평가 줄의 출처 순서**(사용자 지시 2026-10-07 ①)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 사용자 보드 **>** 피드의 메인 라인(총점·핸디 `point` 그대로) **>** 없음.
    board_src = "user_board" if (got_board is not None and got_board.lines) else ""
    if not board_src and feed_mk.probs:
        from app.core import odds as _odds
        from app.core.schema import Board as _Board
        got_board = _Board(lines=_odds.lines_from(feed_mk))
        board_src = "feed"
        st.note(f"보드 없음 → **피드 메인 라인 {len(got_board.lines)}줄**로 평가한다"
                f"(기준선은 피드가 적은 그대로 · 메인 {_odds.main_points(feed_mk)})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **우리 열을 먼저 세고, 시나리오 무게를 그 열에 묶는다**(2026-10-07 재가중 ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전 순서는 s7(생존) → `_layers`(우리 열)였다. 그래서 **생존·양상·논평이
    #     우리 열과 다른 수**에서 나왔다(실측: 홈 73% 인데 논평이 원정 승).
    #  🔴 재가중은 **한 곳**이다(`reweight.of`) — 아래 모두가 그 결과를 쓴다.
    layers = _layers(ref, facts, variables, hypo, base_p, adj_p, feed_mk,
                     user_mk, state=st, outlook=look)
    layers["ocr_text"] = ocr_text
    from app.core import reweight as _reweight
    hypo = _reweight.of(hypo, layers.get("ours"), ref=ref, state=st)
    said = s7_judge.run(ref, facts, variables, hypo, state=st, board=got_board,
                        board_source=board_src, now=now)
    said = _direction(_lower(said, layers, state=st), layers, ref)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **먼저 숫자를 고치고, 그 숫자에서 논평을 만든다**(2026-10-07 ②③)
    # ══════════════════════════════════════════════════════════════════
    from app.core import shape as _shape
    from app.core.stages import s9_audit
    got_shape = _shape.of(hypo)
    if got_shape:
        st.note(f"s8 양상 — **{got_shape['shape']}** · {got_shape['why']}")
    # 🔴🔴 **검열까지 끝낸 논평**(2026-10-07 §4) — 작성자 DeepSeek · 검열자 Solar
    got_note = s9_audit.run(ref, facts, variables, hypo, said, got_shape,
                            state=st, board_source=board_src,
                            ours=layers.get("ours"))
    layers.update(_comment_layers(got_note, got_shape))
    card = card_of(ref, facts, variables, hypo, said, state=st,
                   board_extra=extra, board_bad=bad, layers=layers)
    # 🔴🔴 **1겹 이유 문단**(사용자 지시 2026-10-09(3차) §3·§4) — 카드가 다 선 뒤다
    #    ⚠️ 작성자 입력이 **카드의 사실 목록**이라 카드보다 **뒤**에 와야 한다.
    card = with_reason(card, state=st)
    # 🔴 **마지막 실행을 기억한다** — 재분석이 s3·s4 를 다시 돌지 않게(§4-1)
    _LAST[ref.id] = {"at": (now or datetime.now(timezone.utc)), "ref": ref,
                     "docs": docs, "cands": cands, "card": card,
                     "board_text": board_text}
    return card


async def reanalyze(raw: str, *, pool: Any, net: Any, chain: Any,
                    state: RunState | None = None,
                    now: datetime | None = None) -> Card | Ambiguous:
    """🔴🔴 **재분석**(축구 완성 지시서 §4) — s2 만 다시 돌고 s3·s4 는 **안 돈다**.

    > 1. 그 경기의 마지막 실행(RunState·Doc 캐시)을 불러온다. 기사 검색(s3)·추출(s4)은
    >    **다시 하지 않는다** — 비용·시간을 아끼고 변수가 회차마다 흔들리지 않게.
    > 2. s2 만 다시 돈다: XI(확정 여부), 결장 명단, 같은 조 먼저 끝난 경기 결과.
    > 3. 바뀐 사실로 IR01~IR03·IR05 변수를 다시 만들고, s6·s7 을 다시 돈다.
    > 4. 카드 맨 위에 `재분석 — 바뀐 것:` 한 블록.
    > 5. 마지막 실행이 24시간 넘었거나 없으면 **전체를 새로** 돈다.
    """
    from app.core.stages import (s1_resolve, s2_facts, s2b_base, s2c_market,
                                 s5_verify, s6_hypo, s7_judge)
    st = state if state is not None else RunState()
    q = _question(raw, now=now)
    ref = await s1_resolve.run(q, pool=pool, state=st, net=net)
    if isinstance(ref, Ambiguous):
        return ref
    st.match_key = ref.id
    last = _LAST.get(ref.id)
    when = now or datetime.now(timezone.utc)
    if last is None:
        st.note("재분석 — 🔴 마지막 실행이 **없다** → 전체를 새로 돈다(§4-5)")
        return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                             now=now)
    old = last["at"]
    if (when - old).total_seconds() > LAST_TTL_HOURS * 3600:
        st.note(f"재분석 — 마지막 실행이 {LAST_TTL_HOURS}시간을 넘었다"
                f"({old:%m-%d %H:%M}Z) → 전체를 새로 돈다(§4-5)")
        return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                             now=now)
    before: Card = last["card"]
    # ── ② s2 만 다시 돈다(기사·추출은 그대로 쓴다)
    facts = await s2_facts.run(ref, state=st, net=net)
    docs, cands = list(last["docs"]), list(last["cands"])
    st.set("docs", len(docs))
    st.set("candidates", len(cands))
    variables = s5_verify.run(ref, facts, docs, cands, state=st)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **변수가 그대로면 DeepSeek 를 다시 부르지 않는다**(사용자 지시 ④)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 재분석: 변수 목록이 **바뀌지 않았으면** DeepSeek 를 다시 부르지 않고 **이전
    #  > 시나리오를 그대로** 쓴다. 변수가 바뀐 경우에만 s6 재실행.
    #  > *"사실 그대로 → 등급 그대로"* 를 E2E 불변식으로.
    #
    #  ⚠️ 실측 2026-10-06: 사실이 하나도 안 바뀐 재분석에서 가설·시나리오가 새로
    #     나와 **등급이 흔들렸다**(`무패 원정 소액하단 → 없음`). 그것은 분석이 바뀐
    #     것이 아니라 **모델이 흔들린 것**이다 — 사용자가 보는 수가 그래서 변하면
    #     되돌아볼 수가 없다.
    same = _same_vars(before.variables, variables)
    if same and before.hypo is not None:
        hypo = before.hypo
        st.note(f"재분석 — 변수 {len(variables)}개가 **그대로다** → DeepSeek 를 "
                f"부르지 않고 이전 시나리오 {len(hypo.scenarios)}개를 그대로 쓴다")
        st.set("scenarios", len(hypo.scenarios))
    else:
        hypo = s6_hypo.run(ref, facts, variables, state=st)
    got_board, extra, bad = None, list(before.board_extra), list(before.board_bad)
    if last.get("board_text"):
        from app.core import board as _board
        got_board, extra, bad = _board.parse(str(last["board_text"]))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **재분석의 네 층**(네 층 지시서 §4 재분석 · §6 배당 움직임)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > XI 상태가 바뀌면 **② 만** 다시 계산(s3·s4 재실행 없음).
    #  > 피드 배당이 첫 실행보다 **5%p 이상** 움직였으면 *"시장 이동"* 을 적는다.
    #  🔴 피드 요청은 **1회**다(§2-2) — `reanalyze=True` 가 그 예산을 든다.
    base_p, adj_p = await s2b_base.run(ref, facts, state=st, net=net)
    adj_p = s2b_base.again(ref, facts, base_p, variables, state=st)
    look = s2b_base.outlook(ref, facts, state=st)
    feed_mk, user_mk = await s2c_market.run(ref, pool=pool, net=net, state=st,
                                            board=got_board, reanalyze=True)
    board_src = "user_board" if (got_board is not None and got_board.lines) else ""
    if not board_src and feed_mk.probs:
        from app.core import odds as _odds
        from app.core.schema import Board as _Board
        got_board = _Board(lines=_odds.lines_from(feed_mk))
        board_src = "feed"
    # 🔴 재분석도 **같은 순서**다 — 우리 열 → 재가중 → 생존(재가중 ①)
    layers = _layers(ref, facts, variables, hypo, base_p, adj_p, feed_mk,
                     user_mk, state=st, outlook=look)
    from app.core import reweight as _reweight
    hypo = _reweight.of(hypo, layers.get("ours"), ref=ref, state=st)
    said = s7_judge.run(ref, facts, variables, hypo, state=st, board=got_board,
                        board_source=board_src, now=now)
    said = _direction(_lower(said, layers, state=st), layers, ref)
    # 🔴🔴 논평 — **양상·근거 변수가 바뀐 경우에만** 다시 부른다(비용 · 지시 ③)
    from app.core import shape as _shape
    from app.core.stages import s8_comment, s9_audit
    got_shape = _shape.of(hypo)
    if s8_comment.same_input(before.shape, got_shape, before.variables,
                             variables) and before.commentary is not None:
        st.note("s8 논평 — 양상·근거 변수가 **그대로다** → 다시 부르지 않는다"
                "(검열도 다시 돌지 않는다 — 같은 글이다)")
        layers["shape"] = got_shape
        layers["commentary"] = before.commentary
        layers["comment_notes"] = list(before.comment_notes)
        layers["comment_audit"] = before.comment_audit
        layers["comment_violations"] = list(before.comment_violations)
    else:
        got_note = s9_audit.run(ref, facts, variables, hypo, said, got_shape,
                                state=st, board_source=board_src,
                                ours=layers.get("ours"))
        layers.update(_comment_layers(got_note, got_shape))
    changed = _diff(before, facts, variables, said)
    changed += _market_moved(before, layers, state=st)
    card = card_of(ref, facts, variables, hypo, said, state=st,
                   board_extra=extra, board_bad=bad, layers=layers,
                   changed=changed)
    _LAST[ref.id] = {**last, "at": when, "card": card}
    return card


def _diff(before: Card, facts: Facts, variables: list[Variable],
          said: Judgement) -> list[str]:
    """🔴 **바뀐 것**(§4-4) — XI 상태·변수·등급·걸린 방아쇠.

    ⚠️ *"바뀐 게 없다"* 도 적는다 — 빈 블록은 *"안 봤다"* 와 구분이 안 된다(#3).
    """
    out: list[str] = []
    for key, now_xi in facts.xi.items():
        was = before.facts.xi.get(key)
        old_state = was.state if was is not None else "없음"
        if old_state != now_xi.state:
            out.append(f"XI {key} — {old_state} → **{now_xi.state}**")
    old_ids = {v.id: v for v in before.variables}
    new_ids = {v.id: v for v in variables}
    for vid in sorted(set(new_ids) - set(old_ids)):
        out.append(f"변수 **생김** `{vid}` — {new_ids[vid].claim[:60]}")
    for vid in sorted(set(old_ids) - set(new_ids)):
        out.append(f"변수 **사라짐** `{vid}` — {old_ids[vid].claim[:60]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **열쇠에 기준선을 넣는다** — 실측 2026-10-06(콜롬비아–페루 재분석)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `handicap/Peru` 한 열쇠에 **두 줄**(`+0.5` 없음 · `+1.5` 소액)이 들어가
    #     사전이 뒤 줄로 덮였고, 그래서 *"소액 → 없음"* 이라는 **거짓 변화**를 적었다.
    #     🔴 보드 두 줄은 다른 마켓이다 — 기준선이 열쇠의 일부다.
    def _k(e: MarketEval) -> str:
        point = "" if e.line.point is None else f" {e.line.point}"
        return f"{e.line.market}/{e.line.side}{point}"

    was_grade = {_k(e): e.grade for e in before.evals}
    for e in said.evals:
        old_g = was_grade.get(_k(e))
        if old_g is not None and old_g != e.grade:
            out.append(f"등급 `{_k(e)}` — {old_g} → **{e.grade}**")
    if not out:
        out.append("바뀐 것 **없다**(XI 상태·변수·등급 모두 같다)")
    return out


def card_of(ref: MatchRef, facts: Facts, variables: list[Variable],
            hypo: HypoSet, said: Judgement, *, state: RunState,
            board_extra: list[str] | None = None,
            board_bad: list[str] | None = None,
            changed: list[str] | None = None,
            layers: dict | None = None) -> Card:
    """🔴 카드 하나로 모은다 — 렌더러가 보는 것은 **이 타입 하나**다(§3).

    🔴 `layers` 는 네 층(①②③④)과 §6 비교 결과다 — 없으면 **빈 층**이고 카드의 그
       열은 `—` 다(네 층 지시서 §1 마지막 줄).
    """
    box = dict(layers or {})
    return Card(
        board_extra=[str(x) for x in (board_extra or [])],
        board_bad=[str(x) for x in (board_bad or [])],
        changed=[str(x) for x in (changed or [])],
        base_prob=box.get("base") or BaseProb(why="① 을 안 돌렸다"),
        adj_prob=box.get("adj") or AdjProb(why="② 를 안 돌렸다"),
        market=box.get("market") or MarketProb(why="④ 를 안 돌렸다"),
        user_market=box.get("user_market") or MarketProb(),
        our_prob=box.get("ours"),
        compare=str(box.get("compare") or ""),
        compare_lines=[str(x) for x in (box.get("compare_lines") or [])],
        tilt=[str(x) for x in (box.get("tilt") or [])],
        market_why=[str(x) for x in (box.get("market_why") or [])],
        ocr_text=str(box.get("ocr_text") or ""),
        board_source=str(said.board_source or "none"),
        moves=[dict(x) for x in (box.get("moves") or [])],
        shape=dict(box.get("shape") or {}),
        commentary=box.get("commentary"),
        comment_notes=[str(x) for x in (box.get("comment_notes") or [])],
        # 🔴🔴 **검열 결과**(2026-10-07 §4-3) — 1겹 카드에는 안 나간다(`/디버그` 만)
        comment_audit=str(box.get("comment_audit") or "안 돌았다"),
        comment_violations=[str(x) for x in
                            (box.get("comment_violations") or [])],
        outlook=dict(box.get("outlook") or {}),
        match=ref, facts=facts, variables=variables,
        drops=[*state.drops, *hypo.drops], hypo=hypo, evals=said.evals,
        direction=said.direction, conclusion=said.conclusion,
        triggers=said.triggers,
        funnel=Funnel(counts=state.counted(),
                      drops=[*state.drops, *hypo.drops]),
        cost=state.wallet.snapshot(), started=said.started)


def _question(raw: str, *, now: datetime | None = None) -> Question:
    """🔴 `"A vs B"` 를 가른다. ⚠️ 못 가르면 **통째로** 한 이름으로 둔다(s1 이 본다)."""
    said = str(raw or "").strip()
    low = said.lower()
    team, opp = said, ""
    # 🔴 구분자 목록은 **옛 핸들러와 같다**(`app/bot/main.py`) — 4단계에서 입구를
    #    갈아끼웠으니 받는 꼴이 좁아지면 그것은 **기능 퇴화**다.
    for sep in (" vs ", " vs. ", " - ", " 대 ", " : "):
        if sep in low:
            i = low.index(sep)
            team, opp = said[:i].strip(), said[i + len(sep):].strip()
            break
    else:
        # ⚠️ `중국 팔레스타인` 처럼 **두 낱말**이면 둘째를 상대로 본다(옛 규칙).
        words = said.split()
        if len(words) == 2:
            team, opp = words[0], words[1]
    return Question(raw=said, team=team, opponent=opp,
                    asked_at=(now or datetime.now(timezone.utc)))

def _same_vars(before: list[Variable], now: list[Variable]) -> bool:
    """🔴 변수 목록이 **그대로인가** — 번호·유형·주체·방향·대상·근거 여부로 센다.

    ⚠️ `claim` 글자는 보지 않는다 — 같은 사실을 다른 문장으로 적는 것은 **같은 변수**다
       (그 흔들림이 재분석마다 등급을 바꾸는 것이 ④가 막으려는 것이다).
    🔴 무게(`weight`)와 `hardness` 는 **본다** — 그것이 바뀌면 생존 수가 바뀐다.
    """
    def key(v: Variable) -> tuple:
        return (v.id, v.type, v.subject, v.favors, v.goals, v.target,
                v.hardness, round(float(v.weight), 4), v.usable_as_basis)

    return sorted(key(v) for v in before) == sorted(key(v) for v in now)

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **네 층 비교와 등급 내림**(네 층 지시서 §5·§6·§7)
# ══════════════════════════════════════════════════════════════════


def with_reason(card, *, state: RunState):
    """🔴🔴 **1겹 이유 문단을 카드에 붙인다** — 작성 → 검열 → (재작성 1회) → 템플릿.

    사용자 지시 2026-10-09(3차) §4 마지막 줄:

    > 위반 시 기존처럼 **재작성 1회** → 실패하면 **코드 템플릿 문단**.

    🔴 **아무 수도 안 바꾼다** — 카드의 글 칸 셋만 채운다(`reason`·`reason_audit`·
       `reason_violations`). ⚠️ `Card` 는 얼어 있으므로 `model_copy` 로 갈아낀다.
    """
    from app.core.stages import s8b_reason, s9_audit
    said = s8b_reason.run(card, state=state)
    audit, bad = "안 돌았다", []
    if said is not None:
        bad = s9_audit.reason_check(said, card=card)
        if not bad:
            audit = "통과"
        else:
            state.note(f"s8b 검열 위반 {len(bad)}건 → **재작성 1회** — "
                       f"{'; '.join(bad[:3])}")
            again = s8b_reason.run(card, state=state, bad=bad)
            bad2 = (s9_audit.reason_check(again, card=card)
                    if again is not None else ["(i) 재작성이 안 왔다"])
            if again is not None and not bad2:
                said, audit, bad = again, "재작성 후 통과", []
            else:
                # 🔴 두 번 어긋났다 — **코드 템플릿 문단**이다(지어내지 않는다)
                said = s8b_reason.template(card)
                audit, bad = "템플릿", list(bad) + list(bad2)
                state.note(f"s8b 검열 두 번 어긋났다 → **코드 템플릿 문단** — "
                           f"{'; '.join(bad2[:3])}")
    else:
        said = s8b_reason.template(card)
        audit = "템플릿"
        state.note("s8b 이유 문단을 못 받았다 → **코드 템플릿 문단**")
    return card.model_copy(update={
        "reason": said, "reason_audit": audit,
        "reason_violations": [str(x) for x in bad]})


def _comment_layers(got, shape: dict) -> dict:
    """🔴 논평·검열 결과를 카드 칸으로. ⚠️ **한 곳**이다(두 입구가 같은 것을 쓴다).

    🔴 `shape_used` 가 있으면 **그것이 카드의 양상**이다(§4-1 (d) 가 낮춘 값) —
       논평과 카드가 서로 다른 양상을 말하면 그 자체가 모순이다.
    """
    return {"shape": (got.shape_used or shape), "commentary": got.said,
            "comment_notes": list(got.notes), "comment_audit": got.audit,
            "comment_violations": list(got.violations)}


def _layers(ref: MatchRef, facts: Facts, variables: list[Variable],
            hypo: HypoSet, base_p: BaseProb, adj_p: AdjProb,
            feed_mk: MarketProb, user_mk: MarketProb, *,
            state: RunState, outlook: dict | None = None) -> dict:
    """🔴 ③ 우리 확률 + §6 세 열 비교를 만든다. ⚠️ 못 만든 열은 **사유만** 남는다."""
    from app.core import compare
    from app.core.stages import s2c_market
    # 🔴🔴 ③ 우리 확률은 **①② 에서 출발한다**(사용자 지시 2026-10-06(6차) ①).
    #    ⚠️ ① 이 없으면 종전처럼 시나리오 비율이고, 카드가 그 사실을 적는다.
    start = adj_p.probs if adj_p.probs is not None else base_p.probs
    ours, why = compare.our_prob(hypo, start=start, variables=variables,
                                 adjusted=bool(adj_p.moved), ref=ref,
                                 outlook=outlook)
    # 🔴 §6 은 *"기준(**②반영**)·우리·시장"* 을 나란히 놓으라고 했다 — 그래서 비교도
    #    ② 를 반영한 수로 한다(카드 표와 **같은 수**여야 설명이 맞는다).
    base_for_compare = (base_p.model_copy(update={"probs": start})
                        if start is not None else base_p)
    market, label = s2c_market.column(feed_mk, user_mk)
    verdict, lines = compare.verdict_of(base_for_compare, ours, market)
    tilt = compare.tilt_reasons(ours, base_for_compare, hypo, variables,
                                measured=adj_p.measured)
    reasons = compare.market_reasons(base_p, adj_p, market, variables, ref)
    # 🔴 §5 중복 금지 — ② 가 돌았으면 결장 계열 무게 0 · 전력/폼 절반
    _, notes = compare.weight_rules(variables, measured=adj_p.measured)
    for line in notes:
        state.note(f"§5 중복 금지 — {line}")
    state.note(f"§6 세 열 판정 — **{verdict}**"
               + (f"(우리 {why})" if ours is not None else f"({why})"))
    return {"base": base_p, "adj": adj_p, "market": market,
            "outlook": dict(outlook or {}),
            # 🔴 ③ 이 움직인 양 — `our_prob` 가 방금 적어 둔 그 목록이다
            "moves": list(compare.MOVES),
            "user_market": user_mk, "ours": ours, "compare": verdict,
            "compare_lines": [*lines, (f"시장 열 — {label}" if label else "")],
            "tilt": tilt, "market_why": reasons}


def _direction(said: Judgement, layers: dict, ref: MatchRef) -> Judgement:
    """🔴 §7 방향 판정 — **세 열의 홈승·원정승을 다 적는다**(블록 9).

    ⚠️ 종전 방향 줄은 우리 확률만 적었다 — 세 열이 있으면 그 셋을 나란히 적고, 둘
       이상이 한 팀을 0.15 이상 앞세울 때만 그 팀을 적는다(§7 마지막 줄).
    🔴 열이 **우리뿐이면 종전 줄을 그대로 둔다**(없는 열을 지어내지 않는다).
    """
    from app.core import compare
    base_p, market = layers.get("base"), layers.get("market")
    if base_p is None or market is None:
        return said
    if base_p.probs is None and not (market.probs or {}):
        return said
    return said.model_copy(update={
        "direction": compare.direction_line(base_p, layers.get("ours"),
                                            market, ref)})


def _lower(said: Judgement, layers: dict, *, state: RunState,
           found_new: bool = False) -> Judgement:
    """🔴🔴 §7 — 세 열 규칙은 **등급을 내리기만** 한다. 올리는 길이 없다.

    🔴 `grade_step` 이 내릴 칸 수를 주고(99 면 `없음`), 여기서 **사다리를 내려간다**.
    ⚠️ 시장 확률이 등급 **계산에** 들어가는 것이 아니다 — 계산은 이미 끝났고 그
       결과를 내리기만 한다(§7 금지 첫 줄).
    """
    from app.core import compare
    step, why = compare.grade_step(str(layers.get("compare") or ""),
                                   found_new=found_new)
    if step <= 0:
        if why:
            state.note(f"§7 등급 유지 — {why}")
        return said
    ladder: list[str] = ["낸다", "소액", "소액하단", "없음"]
    out: list[MarketEval] = []
    for ev in said.evals:
        grade = ev.grade
        if grade in ladder:
            i = min(len(ladder) - 1, ladder.index(grade) + step)
            grade = ladder[i]                              # type: ignore[assignment]
        out.append(ev.model_copy(update={"grade": grade,
                                         "why": f"{ev.why} · {why}".strip(" ·")}))
    state.note(f"§7 등급 **내림** {step}칸 — {why}")
    return said.model_copy(update={"evals": out,
                                   "conclusion": f"{said.conclusion} · {why}"})


def _market_moved(before: Card, layers: dict, *, state: RunState) -> list[str]:
    """🔴 §6 — 배당이 **5%p 이상** 움직였나. 움직였으면 *"시장 이동"* 줄들.

    > 배당이 크게 움직였다는 건 **시장이 새 정보를 받았다**는 신호다.
    ⚠️ 그래도 **우리 확률을 시장 쪽으로 옮기지 않는다**(§6 금지) — 새 사실이 변수로
       들어와서 바뀌는 것만 허용한다. 🔴 이 함수는 **적기만** 한다.
    """
    from app.core import compare
    now = layers.get("market")
    if now is None or not (now.probs or {}):
        return []
    said = compare.moved(before.market, now)
    for line in said:
        state.note(f"§6 {line} — 새 기사를 다시 찾아볼 신호다")
    return said
