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
                  pick_key: str = "",
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
                               board_text=board_text, pick_key=pick_key)
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **선수단 교체 판정**(사용자 지시 2026-10-10 지적 ③) — s3 **앞**이다
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 여기서 세야 s3 가 *"전역·이적·방출"* 을 **찾을 수 있다**(검색은 아래서
    #     시작한다). ⚠️ 재료는 `facts` 뿐이다(XI·평소 XI·명단) — 새 통신 0건.
    from app.core import turnover as _turn
    turn = {side: _turn.read(ref, facts, side=side)
            for side in ("home", "away")}
    for side, one in turn.items():
        st.note(f"s2 선수단 교체({side}) — "
                + ("🔴 **켜졌다** · " if one.get("on") else "")
                + str(one.get("why") or ""))
    # 🔴🔴 사용자 결정 (3) — **전역 주기 팀이면 깃발과 무관하게** 그 개념을 넣는다
    #    (`전역`·`신병 합류` 가 그 개념의 맨 앞 둘이다). ⚠️ 실측 2026-10-10: 김천
    #    카드의 새 사실이 **0건**이었다 — 깃발이 꺼진 사이 질의도 안 나갔다.
    cycle = any(_turn.cycle_team(str(getattr(ref, f"{s}_name", "") or ""))
                for s in ("home", "away"))
    more = ({"F": ("squad_turnover",)}
            if cycle or any(one.get("on") for one in turn.values()) else None)
    if cycle:
        st.note("s3 전역 주기 팀 — **고정 질의**를 넣는다(`전역`·`신병 합류`)")
    docs = await s3_docs.run(ref, facts, state=st, chain=chain, net=net,
                             extra_words=more,
                             cache=cache)
    cands = await s4_extract.run(ref, docs, state=st, chain=chain, net=net,
                                 cache=cache)
    # 🔴 s4 가 좁히기 2차로 문서를 더 받았을 수 있다 — **캐시가 전부를 든다**
    docs = list(cache.values()) or docs
    variables = s5_verify.run(ref, facts, docs, cands, state=st,
                              turnover=turn)
    # 🔴🔴 **② 전역 새 사실로 깃발을 덮는다**(사용자 결정 2026-10-10 (a)②) —
    #    변수가 생긴 **뒤**에만 볼 수 있다(새 사실이 변수로 온다).
    for side in ("home", "away"):
        turn[side] = _turn.with_news(ref, turn[side], variables, side=side)
        if dict(turn[side]).get("kind") == "cycle_news":
            st.note(f"s2 선수단 교체({side}) — ② **전역 새 사실로 켜졌다** · "
                    + str(turn[side].get("why") or ""))
    # 🔴 ②(2차) — **검증된 결장 변수**까지 넣어 다시 센다(§4-2 · 네트워크 0)
    adj_p = s2b_base.again(ref, facts, base_p, variables, state=st)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **S1V — 변수 배치**(상성 엔진 지시서 2026-10-10 여섯째 V-3·V-4)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 각 변수는 성격에 따라 세 자리 중 하나 이상에 배치된다 — ① 상성 축의 입력
    #  > ② 검증 출처 ③ 가설의 근거. **확률에 닿는 길은 ① 뿐이다.**
    #
    #  🔴 배치표는 `config/variable_routing.yaml` 이고 배치는 `routing.place`
    #     하나가 한다. ⚠️ 배치 실패·미배치는 **이름으로** 남는다(C5·C6).
    from app.core import routing as _routing
    varset = _routing.place(variables)
    st.note(f"S1V 변수 배치 — {varset.why()}")
    for said in varset.fails:
        st.note(f"S1V {said}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **단계 2 — 가설(+예측 신호)만**. 시나리오는 단계 4다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > ① 딥서치로 재료를 먼저 모으고 ② 가설을 "시뮬레이션이 보여야 할 신호"로
    #  > 세운 뒤 ③ 시뮬레이션을 돌리고 ④ 검증하고 ⑤ 통과한 가설만으로 평을 쓴다.
    #
    #  🔴 **여기까지 확률이 없다**(가설 입력은 변수·사실뿐) — 그것이 §계약
    #     *"단계 2 는 단계 3 결과를 입력으로 받지 않는다"* 다.
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
    # 🔴🔴 **확정 라인업 전략**(사용자 지시 2026-10-10(둘째) §1·§3) — 확정 XI 일
    #    때만 판정이 나온다. 🔴 **잠정 확률을 먼저 세고** 최종과 나란히 든다(§4).
    from app.core.stages import s2d_strategy as _s2d
    plan = _s2d.run(ref, facts, state=st, turnover=turn,
                    news=[v for v in variables
                          if str(getattr(v, "subtask", "") or "").startswith("F-")])
    # 🔴🔴 **상성 세 축**(사용자 지시 2026-10-10(셋째)) — 축1 폼 · 축3 골 내용
    #    ⚠️ 축2(T1~T8)는 스타일 프로필 자료가 없어 아직 안 돈다(사유가 들어온다)
    from app.core.stages import s2e_matchup as _s2e
    edge = await _s2e.run(ref, facts, state=st, net=net)
    # 🔴 **가설은 S2 뒤에 선다**(C3) — 그래서 여기서는 **빈 묶음**으로 열을 만든다.
    #    ⚠️ `_layers` 는 시나리오를 **읽지 않는다**(확률을 S3 가 낸다) — 빈 묶음이
    #       뜻을 바꾸지 않는다.
    from app.core.schema import HypoSet as _HS
    hypo = _HS()
    layers = _layers(ref, facts, variables, hypo, base_p, adj_p, feed_mk,
                     user_mk, state=st, outlook=look, strategy=plan)
    layers["strategy"] = plan
    layers["matchup"] = edge
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확률은 한 곳이다 — 최종 = 시뮬레이션**(사용자 지시 2026-10-10 ④)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 최종 확률 = **시뮬레이션(묶인 분포) 결과**. 카드의 "시뮬" 줄과 최종 숫자가
    #  > 다르면 **계약 실패**. 잠정→최종 변화는 축별 기여로 분해해 합이 맞게.
    #
    #  🔴 확률층(①→②→③)이 낸 `ours` 는 이제 **시뮬의 입력**이다 — 그 홈/원정 비를
    #     맞추는 λ 기울기를 풀고, 거기에 축1 폼·축2·축3 을 얹어 **다시 센 승무패**가
    #     최종이다. ⚠️ 그래서 아래 모두(재가명·등급·양상·논평·오버)가 **같은 수**를
    #     쓴다. 🔴 실사고 2026-10-10: 시뮬 52% · 최종 38% 로 두 답이 나갔다.
    edge["turnover"] = turn
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **S2 상성 판정 → S3 확률**(상성 엔진 지시서 S2·S3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > P1 확률의 출처는 **상성 하나**다. 상성(오늘 XI 기준 네 축)이 기대 득점을
    #  > 정하고, 시뮬레이션이 그것을 승무패·오버로 바꾼다.
    #  > C1 S3 입력에 Elo·동기·일정·감독 발언·맞대결·시장·LLM 문장이 **없다**.
    #
    #  🔴 입력은 `FactBundle`(=`facts`) + `VariableSet` 의 ① 배치 변수뿐이다.
    from app.core import matchup as _mu
    from app.core import probmodel as _pm
    mr = _mu.report(ref, facts, edge, varset, strategy=plan,
                    turnover=turn)
    st.note(f"S2 상성 — {mr.why} · {mr.verdict.get('why')}")
    prob = _pm.run(ref, facts, mr, varset, edge=edge, state=st)
    edge["report"] = mr
    if prob.ok():
        from app.core.schema import ProbTriple as _PT
        edge["sim"] = prob.as_sim()
        edge["share"] = dict(prob.share)
        edge["share_refs"] = dict(prob.share_refs)
        edge["prob"] = prob
        # 🔴🔴 **S3 가 낸 수가 카드의 확률이다**(C2) — 뒤 단계는 안 바꾼다
        layers["ours"] = _PT(home=prob.home, draw=prob.draw, away=prob.away)
        # 🔴🔴 **§6 판정을 다시 센다** — ⚠️ 실사고 2026-10-10: `_layers` 가 S3
        #    **앞에서** 돌아 `ours=None` 으로 판정을 적었고, 여기서 수만 덮어
        #    카드가 *"우리 없음 — 우리 확률을 못 만들었다"* 를 **35% 옆에** 적었다.
        #    🔴 수를 덮으면 그 수로 **판정도 다시** 센다(한 함수다 · 사본 금지).
        said6 = compare_block(
            layers.get("base").model_copy(
                update={"probs": (adj_p.probs if adj_p.probs is not None
                                  else base_p.probs)}),
            layers["ours"], layers.get("market"), hypo, variables,
            measured=adj_p.measured,
            label=str(layers.get("market_label") or ""))
        layers["compare"] = said6["compare"]
        layers["tilt"] = said6["tilt"]
        # 🔴 시장 열 이름표는 첫 계산이 이미 붙였다 — 그 줄만 살려 이어 붙인다
        layers["compare_lines"] = [*said6["_lines"],
                                   *[x for x in (layers.get("compare_lines")
                                                 or []) if "시장 열 —" in str(x)]]
        st.note(f"§6 세 열 판정 **다시** — {said6['compare']}(S3 가 낸 우리 열로)")
        # 🔴 3-4 — 기여는 **리그 평균 대비**다. 그래서 `잠정` 열은 **리그 평균**
        #    확률이다(옛 `잠정`=전략 전 확률이 아니다 · §2: 옛 경로를 지웠다).
        base_sim = _pm.league_base(ref, facts, varset)
        if base_sim is not None:
            layers["prob_before"] = _PT(home=base_sim["home"],
                                        draw=base_sim["draw"],
                                        away=base_sim["away"])
    else:
        edge["sim"] = {"why": prob.gap}
        edge["share"] = {}
        st.note(f"S3 — 🔴 확률을 못 셌다 · {prob.gap}")
    layers["ocr_text"] = ocr_text
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **단계 4 — 검증(가설 ↔ 시뮬) → 시나리오**(순서 재편 §4)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 순서가 핵이다: 가설은 **시뮬을 보기 전에** 섰고(단계 2), 여기서 그
    #     가설의 **예측 신호**를 시뮬 산출과 대조한다. 그리고 **시나리오를 시뮬
    #     분포에서** 만든다(§4-4) — 그래야 시나리오·확률·스코어가 한 분포다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **S4 가설** — 입력은 **MatchupReport + VariableSet** 이다(4-1·C3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 S2 **뒤**이고 S3 숫자를 **보지 않는다**(C3) — `claims()` 는 확률을
    #     인자로도 본문으로도 안 받는다(계약이 센다).
    hypo = s6_hypo.claims(ref, facts, variables, state=st, mr=mr,
                          varset=varset)
    from app.core.stages import s6c_check as _s6c
    got_check = _s6c.run(ref, facts, hypo, dict(edge.get("sim") or {}),
                         variables=variables, turnover=turn, mr=mr,
                         varset=varset, layers=layers, state=st)
    if _s6c.rerun_needed(got_check):
        # 🔴 §4-3 — **최대 1회**. 지금은 조건이 성립하지 않아 안 돈다(사유는 표에)
        st.note("단계 4-3 — 재실행 1회")
    hypo = s6_hypo.scenarios(ref, facts, variables, hypo,
                             dict(edge.get("sim") or {}), state=st,
                             supported=list(got_check.get("supported") or []))
    layers["check"] = got_check
    layers["varset"] = varset
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
    # 🔴🔴 **전술 전문가 예측**(사용자 지시 2026-10-10(셋째) §6) — **확률을 다 센
    #    뒤**다. ⚠️ *"이야기(LLM 문장)는 확률을 움직이지 못한다"*(§4) — 그래서
    #    카드가 완성된 다음에 글만 더한다.
    card = with_tactic(card, state=st)
    # 🔴🔴 **최종 평**(사용자 지시 2026-10-10(넷째)) — *"카드의 **마지막 단계**"*.
    #    ⚠️ 사실 묶음이 전술 예측·확률·상성을 **다** 들어야 하므로 가장 뒤다.
    card = with_say(card, state=st)
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
        hypo = s6_hypo.claims(ref, facts, variables, state=st)
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확정 라인업 전략**(사용자 지시 2026-10-10(둘째) §1·§3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 라인업 상태가 **확정**(또는 두 매체 이상 보도)일 때만. 예상 XI 로는 전략을
    #  > 추론하지 않는다. … 라인업 전 확률은 **잠정**, 확정 라인업 반영 확률이 **최종**.
    #
    #  🔴 **잠정 확률을 먼저 센다**(전략 없이) — 그래야 카드가 `잠정 → 최종` 을
    #     나란히 적을 수 있다. ⚠️ 두 번 세는 것이 아니라 **같은 함수를 두 입력으로**
    #     부른다(규칙이 하나다).
    from app.core.stages import s2d_strategy as _s2d
    plan = _s2d.run(ref, facts, state=st,
                    news=[v for v in variables
                          if str(getattr(v, "subtask", "") or "").startswith("F-")])
    before_layers = _layers(ref, facts, variables, hypo, base_p, adj_p, feed_mk,
                            user_mk, state=st, outlook=look)
    # 🔴 재분석도 **같은 순서**다 — 우리 열 → 재가중 → 생존(재가중 ①)
    layers = _layers(ref, facts, variables, hypo, base_p, adj_p, feed_mk,
                     user_mk, state=st, outlook=look, strategy=plan)
    layers["strategy"] = plan
    # 🔴 §4 — **잠정 → 최종**. ⚠️ 전략이 없으면 둘이 같다(그 사실도 적는다)
    layers["prob_before"] = before_layers.get("ours")
    # 🔴🔴 **재분석에도 시나리오가 있어야 한다**(순서 재편 뒤처리) — `claims()` 는
    #    시나리오를 안 만들므로 여기서 **보강을 돌린다**. ⚠️ 재분석 경로는 상성·
    #    시뮬을 다시 돌지 않으므로 **분포에서 못 만든다** — 그 사실을 적는다(#3).
    if not hypo.scenarios:
        st.note("재분석 — 🔴 시뮬 분포가 없다(상성을 다시 안 돈다) → 시나리오는 "
                "**필수형 보강만**이다(§4-4 의 분포 시나리오가 아니다)")
        hypo = s6_hypo.scenarios(ref, facts, variables, hypo, {}, state=st)
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
        # 🔴 §2·§4 — 전략 판정과 **잠정 확률**(최종은 `our_prob`)
        strategy=box.get("strategy"),
        prob_before=box.get("prob_before"),
        matchup=dict(box.get("matchup") or {}),
        # 🔴🔴 **가설 검증표**(순서 재편 §4-5) — 최종 평이 `supported` 만 쓴다
        check=dict(box.get("check") or {}),
        # 🔴🔴 **변수 배치**(상성 엔진 V-4) — 긴 카드 `🔢 변수` 가 전부 보인다
        varset=box.get("varset"),
        match=ref, facts=facts, variables=variables,
        drops=[*state.drops, *hypo.drops], hypo=hypo, evals=said.evals,
        direction=said.direction, conclusion=said.conclusion,
        triggers=said.triggers,
        funnel=Funnel(counts=state.counted(),
                      drops=[*state.drops, *hypo.drops]),
        cost=state.wallet.snapshot(), started=said.started)


#: 🔴 두 팀을 가르는 **구분자** — 한 곳이다
SEPS: tuple[str, ...] = (" vs ", " vs. ", " - ", " 대 ", " : ")


def split_asked(raw: str) -> tuple[str, str]:
    """🔴🔴 `"A vs B"` 를 **가르는 한 곳** — `(팀, 상대)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 한 곳인가 — 실사고 2026-10-11 (시애틀 사운더스)
    ══════════════════════════════════════════════════════════════════

    같은 규칙이 `app/bot/main.py`(입구)와 여기 **두 곳에 사본**으로 있었고,
    사용자가 `시애틀 사운더스` 로 물었을 때 **한쪽만 고쳤더니 버그가 그대로**였다
    (`--deep` 은 이쪽을 지난다). 🔴 CLAUDE.md #1 — 사본 금지. 규칙은 여기다.

    🔴 두 낱말이어도 **이름표가 통째로 아는 이름**이면 한 팀이다
    (`시애틀 사운더스`·`맨체스터 시티`). ⚠️ `중국 팔레스타인`·`올랜도 크루` 처럼
    통째로는 모르면 종전처럼 **둘째를 상대로** 본다.
    """
    said = str(raw or "").strip()
    low = said.lower()
    for sep in SEPS:
        if sep in low:
            i = low.index(sep)
            return said[:i].strip(), said[i + len(sep):].strip()
    words = said.split()
    if len(words) == 2:
        try:
            from app.core import discover as _disc
            whole = _disc.one_team(said)
        except Exception:                                   # noqa: BLE001
            whole = False
        if not whole:
            return words[0], words[1]
    return said, ""


def _question(raw: str, *, now: datetime | None = None) -> Question:
    """🔴 `"A vs B"` 를 가른다. ⚠️ 못 가르면 **통째로** 한 이름으로 둔다(s1 이 본다).

    🔴 규칙은 `split_asked` 하나다(사본 금지).
    """
    said = str(raw or "").strip()
    team, opp = split_asked(said)
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


def compare_block(base_for_compare, ours, market, hypo,
                  variables: list, *, measured: bool = False,
                  label: str = "") -> dict:
    """🔴🔴 **§6 세 열 판정 — 한 곳**. 카드 칸(`compare`·`compare_lines`·`tilt`).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 함수로 뺐나 — 실사고 2026-10-10 (제노아 vs 피오렌티나)
    ══════════════════════════════════════════════════════════════════

    카드 7b 가 **서로 반대인 두 말**을 한 칸 안에서 했다:

        | Genoa 승 | 26% | **35%** | 50% |   ← 우리 열에 수가 **있다**
        판정: **우리 없음** — 우리 확률을 못 만들었다(시나리오 없음)

    🔴 까닭: `_layers` 는 **S3 앞에서** 한 번 돌아(그때 `ours` 가 `None` 이다)
       판정을 적고, S3 가 그 뒤에 `layers["ours"]` 만 덮었다. 판정·기울기는
       **다시 세지 않았다** → 낡은 말이 새 수 옆에 남았다.
    🔴 그래서 S3 뒤에 **이 함수를 다시 부른다**. 규칙은 한 곳이다(사본 금지).
    """
    from app.core import compare
    verdict, lines = compare.verdict_of(base_for_compare, ours, market)
    tilt = compare.tilt_reasons(ours, base_for_compare, hypo, variables,
                                measured=measured)
    return {"compare": verdict, "tilt": tilt, "_lines": lines,
            "compare_lines": [*lines, (f"시장 열 — {label}" if label else "")]}


def _layers(ref: MatchRef, facts: Facts, variables: list[Variable],
            hypo: HypoSet, base_p: BaseProb, adj_p: AdjProb,
            feed_mk: MarketProb, user_mk: MarketProb, *,
            state: RunState, outlook: dict | None = None,
            strategy: object = None, ours=None) -> dict:
    """🔴 ③ 우리 확률 + §6 세 열 비교를 만든다. ⚠️ 못 만든 열은 **사유만** 남는다."""
    from app.core import compare
    from app.core.stages import s2c_market
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **③ 로그 오즈 경로를 끊었다** — 상성 엔진 지시서 §2·C7
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 변수가 로그 오즈를 직접 미는 ③ 이동 경로(k=0.15·mover 목록·이동 상한)를
    #  > **확률 경로에서 뺀다** → 변수는 V-3 배치표대로 ①②③에.
    #  > C7 변수가 확률에 닿는 길은 **① 상성 축뿐**이다.
    #
    #  🔴 그래서 ③ 이동 함수를 **부르지 않는다**(그 함수는 지웠다). 우리 열은 **S3**
    #     (`probmodel.run`)이 낸 수이고, 파이프라인이 `ours` 로 넣어 준다.
    #  ⚠️ `start`(①②)는 **기준 열**로만 쓴다 — 출발점이 아니다(§2 첫 줄: Elo 를
    #     출발점에서 빼고 V1 검증으로 보낸다).
    start = adj_p.probs if adj_p.probs is not None else base_p.probs
    why = "S3(상성)이 낸 수"
    # 🔴 §6 은 *"기준(**②반영**)·우리·시장"* 을 나란히 놓으라고 했다 — 그래서 비교도
    #    ② 를 반영한 수로 한다(카드 표와 **같은 수**여야 설명이 맞는다).
    base_for_compare = (base_p.model_copy(update={"probs": start})
                        if start is not None else base_p)
    market, label = s2c_market.column(feed_mk, user_mk)
    said3 = compare_block(base_for_compare, ours, market, hypo, variables,
                          measured=adj_p.measured, label=label)
    verdict, lines, tilt = said3["compare"], said3["_lines"], said3["tilt"]
    reasons = compare.market_reasons(base_p, adj_p, market, variables, ref)
    # 🔴 §5 중복 금지 — ② 가 돌았으면 결장 계열 무게 0 · 전력/폼 절반
    _, notes = compare.weight_rules(variables, measured=adj_p.measured)
    for line in notes:
        state.note(f"§5 중복 금지 — {line}")
    state.note(f"§6 세 열 판정 — **{verdict}**"
               + (f"(우리 {why})" if ours is not None else f"({why})"))
    return {"base": base_p, "adj": adj_p, "market": market,
            "outlook": dict(outlook or {}),
            # 🔴🔴 **③ 이동 목록은 비었다**(C7) — 변수는 로그 오즈를 안 민다.
            #    ⚠️ 칸은 남겨 둔다(카드·계약이 그 이름을 안다) — 늘 빈 목록이고
            #       그 사실이 *"변수가 확률을 직접 안 움직인다"* 의 증거다.
            "moves": [],
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **S5-3 등급 조정**(상성 엔진 지시서 2026-10-10 여섯째) — 여기 더한다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > (c) 중 hard·강 반대 1개 이상 → **한 단계 내림** · (c) 반대 2개 이상 →
    #  > **등급 없음** · V7 주 가설 지지 0개 → 한 단계 내림 ·
    #  > (a)(b)·V6 은 등급 영향 **없음**.
    #
    #  🔴 내리는 길은 **이 함수 하나**다(사본 금지) — 세 열 규칙과 같은 사다리다.
    #  ⚠️ **확률은 안 바뀐다**(S5 머리줄) — 등급만 움직인다.
    box = dict(dict(layers.get("check") or {}).get("grade") or {})
    if box.get("none"):
        step, why = 99, " · ".join([why, *box.get("why", [])]).strip(" ·")
    elif int(box.get("steps") or 0) > 0:
        step += int(box["steps"])
        why = " · ".join([why, *box.get("why", [])]).strip(" ·")
    if step <= 0:
        if why:
            state.note(f"§7 등급 유지 — {why}")
        return said
    ladder: list[str] = ["낸다", "소액", "소액하단", "없음"]
    if step >= 99:
        step = len(ladder)                 # 🔴 `없음` 까지 내린다
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


def with_say(card: Card, *, state: RunState) -> Card:
    """🔴🔴 **최종 평을 카드에 더한다**(2026-10-10 넷째). ⚠️ 확률은 **안 건드린다**.

    🔴 확정 XI 가 아니어도 **돈다** — 이 평은 *"카드의 마지막 단계"* 이고 사실
       묶음에는 골 내용·폼·확률처럼 XI 와 무관한 칸이 많다. ⚠️ 라인업 칸이 비면
       묶음이 그것을 `없음` 으로 적고, 프롬프트가 *"그 칸은 말하지 마라"* 로 준다.
    """
    from app.core.stages import s9_say
    return card.model_copy(update={"say": s9_say.run(card, state=state)})


def with_tactic(card: Card, *, state: RunState) -> Card:
    """🔴🔴 §6 — **전술 예측을 카드에 더한다**. ⚠️ 확률은 **건드리지 않는다**.

    🔴 확정 XI 가 아니면 돌리지 않는다 — 입력에 *"오늘 XI 변화"* 가 있어야 한다
       (§6 입력 목록). ⚠️ 그 사실을 산출에 적는다.
    """
    from app.core import layer1
    from app.core.schema import TacticOut
    from app.core.stages import s2f_tactic
    if not layer1.xi_confirmed(card):
        said = "🔴 확정 XI 전 — 전술 예측을 돌리지 않는다(§6 입력에 XI 변화가 든다)"
        state.note(f"s2f {said}")
        return card.model_copy(update={
            "tactic": TacticOut(audit="확정 XI 전", violations=[said])})
    return card.model_copy(update={"tactic": s2f_tactic.run(card, state=state)})
