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

from app.core import infoquality as _iq
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


def _xi_of(path: str, *, state: RunState) -> dict | None:
    """🔴🔴 **사람이 준 라인업 캡처 → `{"home": 글, "away": 글}`**.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 — 사용자 지시 2026-10-11 (스포팅 KC vs 포틀랜드)
    ══════════════════════════════════════════════════════════════════

    > 확정 XI 뜨면 다시 돌려라. 만일에 확인하지 못하면 내 데스크탑 바탕화면에
    > 있다..캡쳐..

    🔴 fotmob 이 **킥오프 40분 전에도 `predicted`** 였고(실측), 사용자 캡처에는
       확정 XI 가 있었다 — 세 자리가 달랐다. ⚠️ 그런데 `s2_facts._fill_capture`
       (소비자)와 `xicapture.parse`(파서)는 있는데 **채우는 곳이 없었다**(#2).
    🔴 OCR 은 **로컬**(`app/core/ocr.py` · tesseract)이고 외부 API 를 안 부른다.
    🔴 가름은 **차례**다 — 캡처 한 장에 두 팀이 위아래로 있으면 앞 11명이 홈,
       다음 11명이 원정이다. ⚠️ 22줄이 안 되면 **쓰지 않는다**(지어내지 않는다).
    """
    said = str(path or "").strip()
    if not said:
        return None
    from app.core import ocr as _ocr
    from app.core import xicapture as _cap
    text, why = _ocr.read(said)
    rows = _cap.parse(text)
    forms = _cap.forms_of(text)
    state.note(f"XI 캡처 — {why} · 글자 {len(text)} · 번호 줄 {len(rows)} · "
               f"포메이션 {forms or '못 읽음'}")
    if len(rows) < 22:
        state.note(f"XI 캡처 — 🔴 번호 줄이 {len(rows)}개다(22 미만) — **쓰지 않는다**")
        return None

    def _block(got: list[dict], form: str) -> str:
        head = f"{form}\n" if form else ""
        return head + "\n".join(f"{r['number']} {r['name']}" for r in got)

    return {"home": _block(rows[:11], forms[0] if forms else ""),
            "away": _block(rows[11:22], forms[1] if len(forms) > 1 else "")}


async def analyze(raw: str, *, pool: Any, net: Any, chain: Any,
                  state: RunState | None = None, board: Board | None = None,
                  board_text: str = "", board_image: str = "",
                  pick_key: str = "", xi_image: str = "",
                  reuse: dict | None = None, before: Card | None = None,
                  now: datetime | None = None,
                  break_facts: list | None = None,
                  break_rerun: str = "") -> Card | Ambiguous:
    """🔴 질문 하나 → 카드 하나. ⚠️ 경기를 **못 고르면** `Ambiguous`(묻는다).

    🔴 `board_text` 를 주면 **코드가 파싱한다**(축구 §4 · `app/core/board.py`) —
       LLM 이 보드를 읽지 않는다.
    🔴 `board_image` 를 주면 **로컬 OCR** 로 글을 뽑아 같은 파서로 보낸다(네 층 §2-6).
       ⚠️ 외부 OCR API 를 부르지 않는다 — `app/core/ocr.py` 가 실행 파일을 직접 쓴다.
    """
    import asyncio

    from app.core.stages import (s1_resolve, s2_facts, s2b_base, s2c_market,
                                 s3_docs, s4_extract, s5_verify,
                                 s7_judge)
    st = state if state is not None else RunState()
    # 🔴🔴 **P0 상한**(수정 지시 2026-10-13 밤) — 카드 한 장 15분. 넘는 단계는
    #    ⬜ + 사유로 넘긴다(멈추지 않는다). ⚠️ 재생·시험은 안 건다(`clock` 이
    #    이미 있으면 그대로 쓴다).
    if st.clock is None:
        from app.core import deadline as _dline
        from app.core import slate as _slate
        st.clock = _dline.Deadline(_slate.CARD_CAP_MIN)
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
    xi_said = _xi_of(xi_image, state=st)
    if board_text.strip():
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
        s2_facts.run(ref, state=st, net=net, xi_capture=xi_said),
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **재분석은 ③ 문서·⑤ 추출만 다시 쓴다**(지시서 2026-10-11 F1)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 재사용은 ③의 기사 문서·⑤의 기사 추출 결과만(검색·LLM 추출 비용 절약).
    #  > 구조 사실·라인업·새 사실 72시간은 **다시 받는다**.
    #
    #  🔴 그래서 위 `s2_facts`(구조·라인업)는 **늘 다시 돈다** — 재사용 목록에 없다.
    said_reuse = dict(reuse or {})
    if said_reuse.get("docs") is not None:
        docs = list(said_reuse.get("docs") or [])
        cands = list(said_reuse.get("cands") or [])
        st.note(f"재분석 — ③ 문서 {len(docs)}건 · ⑤ 추출 {len(cands)}건을 "
                f"**그대로 쓴다**(검색·LLM 추출을 다시 하지 않는다 · F1)")
        st.set("docs", len(docs))
        st.set("candidates", len(cands))
    else:
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
    #  ⚠️ **재가중(⑳)은 지웠다**(§1 처분) — 확률·생존은 격자 하나에서 온다.
    # 🔴🔴 **확정 라인업 전략**(사용자 지시 2026-10-10(둘째) §1·§3) — 확정 XI 일
    #    때만 판정이 나온다. 🔴 **잠정 확률을 먼저 세고** 최종과 나란히 든다(§4).
    from app.core.stages import s2d_strategy as _s2d
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **[1a·1b] 경기 우선순위 지수** — 수정 지시서 2026-10-12
    # ══════════════════════════════════════════════════════════════════
    #
    #  > [1b] 위치: ⑦ 전략 판정, 판정 함수 **앞**.
    #
    #  🔴 재료: 오늘 XI(`facts.xi`) · 선수 가치(`facts.player_value`) ·
    #     선발 빈도(⑧ 이 만든 `usual_starts` — **창 10경기**).
    #  ⚠️ **시즌 출전 시간 자료가 없다**(실측 2026-10-12) — 그래서 "최강 XI" 는
    #     선발 빈도로 고르고 카드가 그 사실을 적는다(#4).
    #  🔴 P1 — 이 수를 **축0 에 곱하지 않는다**. 축0 근거 줄과 K5 입력으로만.
    plan = _s2d.run(ref, facts, state=st, turnover=turn,
                    news=[v for v in variables
                          if str(getattr(v, "subtask", "") or "").startswith("F-")])
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **라인업 신원 검문**(사용자 지시 2026-10-11 ③) — 상성 **앞**이다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > (a) 11명 전원 id 확정 (b) GK 정확히 1명 (c) 선발 id 가 결장·명단 제외·
    #  > 없는 선수·꺼진 무기 목록에 **하나도 없다**. 어기면 상성·확률을 내지 않고
    #  > "라인업 신원 미확정 — 누구" 카드. **숫자를 낸 채 🔴만 다는 것 금지.**
    #
    #  ⚠️ 실사고 2026-10-11(가와사키 캡처): 브로더센·와키자카·나가이·이즈미가
    #     **선발이면서** 결장·교체·무기 꺼짐에 동시에 들어갔고, 카드는 그 상태로
    #     확률 51% 를 **냈다**. 🔴 서로 모순인 입력으로 만든 수는 내지 않는다.
    from app.core import lineupgate as _gate
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **XI 가 **아예 없으면** 검문을 건너뛴다**(P0 · 수정 지시 2026-10-13 밤)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 사전 실행: T−24h **기본 카드(XI 없이)** → T−3h 갱신 → 확정 XI 뜨면 ⑲.
    #
    #  ⚠️ 실측 2026-10-13(페르시브–비엣텔 · T−23h): 경기 페이지에 라인업이
    #     **아직 없어서** 검문이 *"누구인지도 못 짚었다"* 로 걸렸고 **확률이
    #     통째로 안 나왔다**. 그러면 T−24h 기본 카드가 **불가능**하다.
    #  🔴 검문이 막으려는 것은 *"서로 모순인 XI 입력으로 만든 수"* 다 — XI 가
    #     **없는 것은 모순이 아니다**. 그때는 팀 수준 입력으로 바닥을 만들고,
    #     등급 상한은 이미 `xi_state_cap`(라인업 상태)이 내린다.
    said_xi_rows = sum(
        len(list(getattr((facts.xi or {}).get(str(getattr(ref, s, ""))),
                         "lineup", None) or []))
        for s in ("home", "away"))
    said_gate = (_gate.Gate(ok=True, names=[], why="")
                 if said_xi_rows == 0
                 else _gate_of(ref, facts, turn, state=st))
    if said_xi_rows == 0:
        st.note("③ 라인업 신원 검문 **건너뜀** — 어느 쪽도 XI 가 없다(T−24h 기본 "
                "카드) · 모순이 아니라 **없는 것**이다 → 팀 수준 입력으로 간다")
    if not said_gate.ok:
        st.note(f"🔴🔴 **라인업 신원 미확정** — {said_gate.why}")
        return _gate_card(ref, facts, variables, said_gate, state=st,
                          docs=docs, before=before)
    # 🔴🔴 **상성 세 축**(사용자 지시 2026-10-10(셋째)) — 축1 폼 · 축3 골 내용
    #    ⚠️ 축2(T1~T8)는 스타일 프로필 자료가 없어 아직 안 돈다(사유가 들어온다)
    from app.core.stages import s2e_matchup as _s2e
    # 🔴 F2 — 재료가 **변수·깃발·전략**을 받는다(전략은 바로 위에서 섰다)
    edge = await _s2e.run(ref, facts, state=st, net=net,
                          varset=varset, turnover=turn, strategy=plan)

    # 🔴 **가설은 S2 뒤에 선다**(C3) — 그래서 여기서는 **빈 묶음**으로 열을 만든다.
    #    ⚠️ `_layers` 는 시나리오를 **읽지 않는다**(확률을 S3 가 낸다) — 빈 묶음이
    #       뜻을 바꾸지 않는다.
    layers = _layers(ref, facts, variables, base_p, adj_p, feed_mk,
                     user_mk, state=st, outlook=look, strategy=plan)
    layers["strategy"] = plan
    layers["matchup"] = edge
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§11 앙상블 그림자 판**(통합 지시서 2026-10-13 밤) — 기록용
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 **E0 유지**(채택 없음)이므로 운영 확률은 **M1 단독**이다. 이 판은
    #     카드가 **E2 그림자 줄**을 적는 데만 쓴다(EN8: 등급·생존 금지).
    #  ⚠️ 판 고르기는 `versions`(엄격히 이전 · L3) 하나다 — 같은 날 판은 안 쓴다.
    try:
        from app.core import ensemble as _ens
        from app.core import probmodel as _pmd0
        said_kind = str(_pmd0._kind(ref, facts) or "")
        said_plate, said_why = _ens.plate_of(
            league=said_kind, as_of=getattr(ref, "kickoff_utc", None))
        edge["ens_w"] = dict(said_plate.get("w") or {})
        edge["ens_why"] = said_why
        st.note(f"§11 앙상블 그림자 판 — {said_why}")
    except Exception as exc:                                # noqa: BLE001
        edge["ens_w"] = {}
        edge["ens_why"] = f"🔴 판을 못 읽었다: {exc!r:.60}"
    # 🔴 **(가) 표시 전용** — 라인업 수를 ② 칸에 **표시로만** 싣는다(확률 경로 밖).
    #    ⚠️ `adj_prob.probs` 는 건드리지 않는다 — 계약이 그 자리를 센다.
    if layers.get("adj") is not None:
        layers["adj"] = layers["adj"].model_copy(update={
            "lineup_view": dict(edge.get("lineup_view") or {}),
            "lineup_view_why": str(edge.get("lineup_view_why") or "")})
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑩ 가설 — 상성 판정 직후·확률 앞**(지시서 2026-10-11 F6/R8)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 가설 세우기를 ⑨ 상성 판정 **직후**·⑪ 확률 **앞**으로 옮긴다.
    #  > 입력: MatchupReport + VariableSet — **시뮬 출력 없음**.
    #
    #  🔴 C3 는 그대로다(`claims()` 는 확률을 인자로도 본문으로도 안 받는다) —
    #     이번에 바뀐 것은 **순서**다. 가설이 상성 결론에서 **뻗어 나가야** 하고,
    #     확률 뒤에 서면 *"수를 보고 말을 맞춘 것"* 과 구분이 안 된다.
    # ══════════════════════════════════════════════════════════════════
    # ⚠️ **⑭ 가설 · ⑮ 무너뜨릴 조건은 지웠다**(지시서 2026-10-12(셋째) §1 처분)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > ⑭ 가설(LLM) — 삭제(**누설 위험**(4-3) · 검증 불가)
    #  > ⑮ 무너뜨릴 조건 K1~K6 — §9 이변 신호(코드)로 흡수 후 삭제
    #
    #  🔴 그 자리를 지금 지키는 것: **§9 공변량**(코드가 만든 수)과 **§10 경고**.
    # 🔴🔴 **⑯ 에 Elo 바닥을 넘긴다**(사용자 결정 2026-10-12 (a) · C1 개정)
    #  ⚠️ `base_p.probs` 가 `None` 이면(Elo 없음) ⑯ 은 **옛 구조**로 돈다 — 지어내지
    #     않는다. 그 사실은 `prob.why` 에 적힌다.
    prob = _pm.run(ref, facts, mr, varset, edge=edge, state=st,
                   floor=base_p.probs)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **그림자 — 옛 M1**(수정·검증 지시 2026-10-14e §4)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 통과 조합을 설정 플래그 `M1v2` 로 운영 전환 · 기존 M1 은 **그림자로 30경기
    #  > 유지** · score_cards 가 두 판 같이 채점.
    #
    #  🔴 통신 0건이다 — `matchup.report` 와 `probmodel.run` 은 **이미 받은 재료**로
    #     도는 계산이다. ⚠️ 실패하면 ⬜ 와 사유를 남긴다(조용히 0 을 넣지 않는다).
    from app.core import m1v2 as _c
    said_old: dict | None = None
    if _c.any_on():
        try:
            with _c.off():
                mr_old = _mu.report(ref, facts, edge, varset, strategy=plan,
                                    turnover=turn)
                prob_old = _pm.run(ref, facts, mr_old, varset, edge=edge,
                                   state=None, floor=base_p.probs)
            said_old = {"home": prob_old.home, "draw": prob_old.draw,
                        "away": prob_old.away,
                        "why": f"옛 M1(후보 꺼짐) · {mr_old.verdict.get('why')}"}
            st.note(f"S3 그림자 옛 M1 — 홈 {prob_old.home:.1%} · 무 "
                    f"{prob_old.draw:.1%} · 원정 {prob_old.away:.1%}")
        except Exception as exc:                            # noqa: BLE001
            said_old = {"why": f"🔴 옛 M1 그림자를 못 셌다 — {exc!r:.120}"}
    if said_old:
        # 🔴 카드가 보는 것은 `card.matchup`(= `edge`)다 — 그 사전에 싣는다
        edge["shadow_old"] = dict(said_old)
    edge["report"] = mr
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **xG 판을 한 번 더 센다**(사용자 결정 2026-10-12 — 3번 b)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 4번: 같은 경기 득실판 vs xG판 확률 비교 … (b) **두 판을 카드에 나란히**
    #  > 적어 둔다 — 백필 브라이어 비교가 될 때까지 **기본값은 득실판**이다.
    #
    #  🔴 같은 재료·같은 함수로 센다 — 다른 것은 **축1 지수(100% xG · 운 할인 끔)**
    #     와 **계수 블록**(`xg:`)뿐이다. ⚠️ 등급·보드·최종 평은 **안 건드린다**.
    #  ⚠️ `with` 안에서 도는 둘은 **동기 함수**다(계약이 센다) — 그 사이에 다른
    #     경기 계산이 끼어들 수 없다.
    if edge.get("form_xg"):
        edge_xg = {**edge, "form": edge["form_xg"]}
        with _mu.xg_coeffs():
            mr_xg = _mu.report(ref, facts, edge_xg, varset, strategy=plan,
                               turnover=turn)
            prob_xg = _pm.run(ref, facts, mr_xg, varset, edge=edge_xg,
                              state=st, floor=base_p.probs)
        # 🔴 **수는 평범한 사전으로 싣는다** — ⚠️ 카드가 저장을 지나면
        #    데이터클래스가 안 살아 있다(실측 2026-10-11: `prob` 칸이 비었다).
        edge["xg_pass"] = {
            "sim": (prob_xg.as_sim() if prob_xg.ok() else {}),
            "gaps": {k: v for k, v in (mr_xg.gaps() or {}).items()},
            "verdict": str((mr_xg.verdict or {}).get("edge") or ""),
            "strength": str((mr_xg.verdict or {}).get("strength") or ""),
            "form": {s: (one.index() if one else None)
                     for s, one in dict(edge["form_xg"]).items()},
            "why": ("" if prob_xg.ok() else str(prob_xg.gap))}
        st.note("S3 **xG 판**(나란히) — "
                + (f"홈 {prob_xg.home:.0%} · 무 {prob_xg.draw:.0%} · 원정 "
                   f"{prob_xg.away:.0%}" if prob_xg.ok()
                   else f"🔴 못 셌다 — {prob_xg.gap}"))
    else:
        edge["xg_pass"] = {"sim": {}, "gaps": {}, "total": None,
                           "verdict": "", "form": {},
                           "why": str(edge.get("xg_why") or
                                      "🔴 xG 판 없음 — 재료가 없다")}
    if prob.ok():
        from app.core.schema import ProbTriple as _PT
        edge["sim"] = prob.as_sim()
        edge["share"] = dict(prob.share)
        edge["share_refs"] = dict(prob.share_refs)
        # 🔴🔴 **수는 평범한 사전으로도 싣는다**(사용자 결정 2026-10-12 5번: *"뼈대
        #    확률과 최종 확률을 둘 다 기록"*). ⚠️ 카드가 저장을 지나면 데이터클래스가
        #    안 살아 있다(실측 2026-10-11) — 그래서 `floor`·`shadow` 를 사전으로 둔다.
        edge["floor"] = dict(prob.floor or {})
        # 🔴 §5 무승부 보정의 **보정 전 수와 판**(카드가 그 줄을 적는다)
        edge["draw_fix"] = dict(prob.draw_fix or {})
        edge["shadow"] = dict(prob.shadow or {})
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
            layers["ours"], layers.get("market"), variables,
            measured=adj_p.measured,
            label=str(layers.get("market_label") or ""))
        layers["compare"] = said6["compare"]
        layers["tilt"] = said6["tilt"]
        # 🔴 시장 열 이름표는 첫 계산이 이미 붙였다 — 그 줄만 살려 이어 붙인다
        layers["compare_lines"] = [*said6["_lines"],
                                   *[x for x in (layers.get("compare_lines")
                                                 or []) if "시장 열 —" in str(x)]]
        st.note(f"§6 세 열 판정 **다시** — {said6['compare']}(S3 가 낸 우리 열로)")
        # 🔴🔴 ④ **근거 검열도 다시 센다** — ⚠️ 실사고 2026-10-11(엘체–셀타):
        #    `_layers` 가 S3 **앞에서** 돌아 `ours=None` 이었고, `compare.py` 의
        #    대체(*"시장이 미는 쪽의 반대가 우리 결론"*)가 우리 27%/45% 를
        #    **Elche 쪽**이라고 적었다. 🔴 수를 덮으면 그 수로 **근거 줄도 다시**.
        from app.core import compare as _cmp
        layers["market_why"] = _cmp.market_reasons(
            base_p, adj_p, layers.get("market"), variables, ref,
            ours=layers["ours"])
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **4번 — 예상 XI 판 / 확정 XI 판을 둘 다 싣는다**(2026-10-13 밤 넷째)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 지금 카드의 확률이 **확정 XI 판**이면, **지난 실행**(예상 XI 때)의
    #     확률을 `prob_expected` 로 싣는다 — 그래야 `score_cards` 가 두 판을
    #     **짝지어** 채점할 수 있다(지시 4번).
    #  ⚠️ **확률은 안 바뀐다** — 저장·채점용이다(계약이 등급·생존을 잠근다).
    #  🔴 XI 상태를 읽는 문은 `layer1.xi_state` 하나다(사본 금지).
    said_prev = dict(_LAST.get(ref.id) or {})
    got_prev = said_prev.get("card")
    if got_prev is not None:
        from app.core import layer1 as _l1
        was = _l1.xi_state(got_prev)
        if was == "예상" and getattr(got_prev, "our_prob", None) is not None:
            layers["prob_expected"] = got_prev.our_prob
            layers["prob_expected_why"] = (
                f"지난 실행(**예상 XI 판** · "
                f"{said_prev.get('at').strftime('%H:%M') if said_prev.get('at') else '시각 모름'})")
        else:
            layers["prob_expected_why"] = (
                f"⬜ 지난 실행의 XI 상태가 `{was}` 다 — 예상 XI 판이 아니다")
    else:
        layers["prob_expected_why"] = "⬜ 지난 실행이 없다(첫 분석이다)"
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
    #  🔴🔴 **그 호출은 위로 올라갔다**(F6/R8 — 상성 직후·확률 앞). 여기서는
    #     세운 가설을 **검증**에 넘긴다.
    # ══════════════════════════════════════════════════════════════════
    # ⚠️ **⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·재가중도 지웠다**(§1 처분)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > ⑱ 반증 딥서치 — 목적 변경 → **"오늘 사실 확인 질의"**(§2)로 재배치
    #  > ⑳ 시나리오 — 삭제(생존은 이미 격자에서)
    #  > ㉒ 반증 판정 — §11 판정 행동으로 흡수 후 삭제
    #
    #  🔴 되돌림(⑲)은 **남는다** — 확정 XI·새 결장이 오면 ⑧⑪⑬⑯ 을 다시 돈다
    #     (그 길은 `reanalyze` 다). ⚠️ 반증이 그것을 트리거하던 길은 없어졌다.
    layers["break_rerun"] = break_rerun
    layers["varset"] = varset
    # 🔴 F5 — **생존은 시뮬 분포에서** 센다(시나리오는 표시용이다)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **P5 시장 괴리**(예측 지시 2026-10-13 23:10 KST) — **표시 + 상한**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 차이 ≥10%p 줄은 🔴 시장 괴리 + 그 경기에서 **⬜ 인 입력 목록** ·
    #  > ⬜ 걸린 괴리 줄은 **결론 상한 "접는다"**.
    #
    #  🔴 시장 확률은 **등급 계산에 안 들어간다**(네 층 §7) — 들어가는 것은
    #     *"접는다 상한"* 하나이고 그것은 **우리가 모르는 정보**를 경계하는 장치다.
    said_div, said_fold = _divergence_of(ref, facts, prob, got_board, layers)
    if said_div:
        st.note(f"P5 시장 괴리 — {said_div[:160]}")
    # 🔴 카드 줄도 **이 글자**를 쓴다(렌더러가 다시 세지 않는다)
    if said_div:
        layers["divergence"] = said_div
    said = s7_judge.run(ref, facts, variables, state=st, board=got_board,
                        board_source=board_src, now=now,
                        fold_why=said_fold,
                        # 🔴🔴 **보드 없음 결론 규칙 (가)의 재료**(사용자 결정
                        #    2026-10-13) — 우리 확률의 **최고값**이다. ⚠️ 판정
                        #    쪽에서 격자를 다시 세지 않는다(계약 M1-3).
                        top=(max(prob.home, prob.draw, prob.away)
                             if (prob is not None and prob.ok()) else None),
                        dist=dict(dict(edge.get("sim") or {}).get("scores")
                                  or {}))
    # 🔴🔴 **[3d] 반증 판정을 기존 등급 위에 얹는다**(지시서 2026-10-12)
    #    ⚠️ 확률은 안 바뀐다(C2) · 시장은 들어가지 않는다(C12).
    # ⚠️ **㉒ 반증 판정은 지웠다**(§1 처분) — 그 일(등급을 내리는 것)은 §11 판정
    #    행동(이변 경고·InfoQ)이 바로 아래에서 한다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§13·§14 정보 품질 InfoQ** — 지시서 2026-10-12(둘째) · 등급만 바꾼다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > InfoQ ≤ 2 → 등급 한 단계↓ · "조건부" 이상 불가 · 빠진 칸을 방아쇠로.
    #
    #  🔴 확률·λ·생존에 **닿지 않는다**(계약 C13-1) — 이 자리는 등급 **뒤**다.
    said_iq = _infoq_of(ref, facts, layers, edge)
    layers["infoq"] = said_iq
    said = _iq.apply(said, said_iq)
    st.note(f"[㉑] {said_iq.why}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§10·§14 이변 경고** — 확률 불변 · **등급만** 바꾼다(계약 U3·U4·U5)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 🔴 이변 경고: 강팀 승·강팀 핸디 → **등급 없음(접는다)**. 약팀 보호 줄만
    #  > 판정 대상. 🟡: 강팀 줄 **한 단계↓**.
    #
    #  🔴 판(계수·분위·검증 통과)이 없으면 **경고를 켜지 않는다** — 손값 금지(§0).
    said_up = _upset_of(ref, facts, layers, edge, infoq=said_iq)
    layers["upset"] = said_up
    if said_up is not None and said_up.grade:
        said = _upset_apply(said, said_up, ref=ref, layers=layers)
        st.note(f"[⑳] {said_up.why}")
    said = _direction(said, layers, ref)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **먼저 숫자를 고치고, 그 숫자에서 논평을 만든다**(2026-10-07 ②③)
    # ══════════════════════════════════════════════════════════════════
    from app.core import shape as _shape
    # 🔴 §1 처분 — 양상은 **격자**에서 센다(시나리오 무게가 아니다)
    got_shape = _shape.of(dict(dict(edge.get("sim") or {}).get("scores")
                               or {}))
    if got_shape:
        st.note(f"s8 양상 — **{got_shape['shape']}** · {got_shape['why']}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **F7 — 글은 한 편이다**(지시서 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 논평(s9_audit 작성)·이유 문단(s8b)·전술 예측(s2f)·최종 평(s9_say)
    #  > → **최종 평 한 번**(작성 1회 + 검열 1회).
    #
    #  ⚠️ 넷이 따로 돌던 때는 **서로 다른 말**을 했고 경기당 LLM 글 호출이 넷이었다.
    #  🔴 양상(`shape`)은 **코드 산출**이라 그대로 둔다 — 글이 아니다.
    layers["shape"] = got_shape
    # 🔴 F1 — 직전 카드가 있으면 **바뀐 것**을 함께 싣는다(머리줄이 그것을 적는다)
    changed = (_diff(before, facts, variables, said)
               + _market_moved(before, layers, state=st)
               + _moved(before, layers, mr) if before is not None else [])
    card = card_of(ref, facts, variables, said, state=st,
                   board_extra=extra, board_bad=bad, layers=layers,
                   changed=(changed or None))
    # 🔴🔴 **F7 — 글 한 편**(작성 1 + 검열 1). 카드가 다 선 **뒤**다 — 작성자
    #    입력이 **카드의 사실 목록**이기 때문이다. ⚠️ 이야기가 확률을 못 움직인다.
    card = with_say(card, state=st)
    # 🔴 **마지막 실행을 기억한다** — 재분석이 s3·s4 를 다시 돌지 않게(§4-1)
    _LAST[ref.id] = {"at": (now or datetime.now(timezone.utc)), "ref": ref,
                     "docs": docs, "cands": cands, "card": card,
                     "board_text": board_text}
    return card


async def reanalyze(raw: str, *, pool: Any, net: Any, chain: Any,
                    xi_image: str = "",
                    state: RunState | None = None,
                    now: datetime | None = None) -> Card | Ambiguous:
    """🔴🔴 **재분석** — 지시서 2026-10-11 **F1**: 확정 XI 가 오면 **상성부터 다시**.

    > reanalyze: 확정(또는 2매체 보도) XI가 들어오면 ④ 깃발부터 ⑯까지 **전부 다시**
    > 돈다. 재사용은 ③의 기사 문서·⑤의 기사 추출 결과만(검색·LLM 추출 비용 절약).
    > 구조 사실·라인업·새 사실 72시간은 다시 받는다.
    > "상성·시뮬 그대로, 시나리오 필수형 보강만" 경로 **삭제**.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이렇게 바뀌었나 — 실측 2026-10-11
    ══════════════════════════════════════════════════════════════════

    이 함수는 **파이프라인의 두 번째 사본**이었다. `analyze` 의 ⑧ 상성 재료·⑨ 상성
    판정·⑪ 확률·⑫ 검증을 **아예 안 불렀고**, 그래서 재분석 카드에는 **우리 확률이
    없었다**(시나리오도 "필수형 보강만"). 사본은 원본이 자랄 때 따라가지 못한다
    (CLAUDE.md #1). 🔴 그래서 **사본을 지우고** `analyze` 에 재사용 인자를 넘긴다.
    """
    from app.core.stages import s1_resolve
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
                             now=now, xi_image=xi_image)
    old = last["at"]
    if (when - old).total_seconds() > LAST_TTL_HOURS * 3600:
        st.note(f"재분석 — 마지막 실행이 {LAST_TTL_HOURS}시간을 넘었다"
                f"({old:%m-%d %H:%M}Z) → 전체를 새로 돈다(§4-5)")
        return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                             now=now, xi_image=xi_image)
    st.note("재분석 — ④ 깃발부터 ⑯까지 **전부 다시** 돈다(F1) · 재사용은 "
            "③ 문서·⑤ 추출뿐이다")
    return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                         now=now, xi_image=xi_image,
                         board_text=str(last.get("board_text") or ""),
                         reuse={"docs": last.get("docs") or [],
                                "cands": last.get("cands") or []},
                         before=last.get("card"))


def _id_rows(facts, key: str) -> list[dict]:
    """🔴 ① — 그 팀의 **신원표 재료 줄들**(출처를 함께 적는다).

    출처 셋(지시서의 그것): **fotmob 명부**(오늘 XI·직전 XI 의 번호·포지션) ·
    **최근 경기 라인업**(`past_xi`) · **소집 명단**(`squad`) · **결장 명단**.
    ⚠️ 번호가 없는 출처(소집 명단·결장)는 이름만 넣는다 — 지어내지 않는다.
    """
    out: list[dict] = []

    def _xi(one, src: str) -> None:
        for p in (getattr(one, "lineup", None) or []):
            out.append({"name": getattr(p, "name", ""),
                        "number": getattr(p, "number", None),
                        "pos": getattr(p, "pos", ""), "source": src})
        for nm in (getattr(one, "players", None) or []):
            out.append({"name": str(nm), "source": src})
        for nm in (getattr(one, "bench", None) or []):
            out.append({"name": str(nm), "source": f"{src}/벤치"})

    one = (facts.xi or {}).get(key)
    if one is not None:
        _xi(one, "오늘 XI")
    last = (facts.last_xi or {}).get(key)
    if last is not None:
        _xi(last, "직전 XI")
    for past in list((facts.past_xi or {}).get(key) or []):
        _xi(past, "최근 경기")
    out += [{"name": str(nm), "source": "소집 명단"}
            for nm in ((facts.squad or {}).get(key) or [])]
    out += [{"name": getattr(m, "name", ""), "pos": getattr(m, "pos", ""),
             "source": "결장 명단"}
            for m in ((facts.missing or {}).get(key) or [])]
    return [r for r in out if str(r.get("name") or "").strip()]


def _schedule_line(facts) -> str:
    """🔴 §7 — 카드 머리의 **일정 한 줄**. ⚠️ 없으면 그 사실을 적는다(#3)."""
    box = dict(getattr(facts, "context", None) or {})
    if not box:
        return "일정 — ⬜ **못 쟀다**(경기 목록을 못 받았다)"
    def _one(side: str) -> str:
        got = box.get(side)
        if got is None:
            return "⬜ 없음"
        return (f"휴식 {got.rest_days}일" +
                ("(휴식기 후 첫 리그)"
                 if (got.break_days is not None
                     and got.break_days >= 14
                     and got.league_n_since_break == 0) else "") +
                f" · 14일 내 {got.load_14d}" +
                (" · **4일 내 컵**" if got.cup_4d else ""))
    return (f"일정: 홈 {_one('home')} / 원정 {_one('away')}"
            f" — ⚠️ **확률에는 아직 안 들어간다**(§9 전진 선택 전)")


def _upset_of(ref: MatchRef, facts, layers: dict, edge: dict, *, infoq):
    """🔴🔴 §10 — 경고 점수. **판이 없으면 `None`**(경고를 켜지 않는다).

    🔴 신호는 **확률로 못 간 것만**이다(S2) — λ 식이 채택한 항은 `adopted` 로 뺀다.
    ⚠️ 지금 λ 식에 채택된 항은 **없다**(§9 전진 선택 전) — 그래서 `adopted` 는
       빈 묶음이고, 그 사실이 사유에 남는다.
    """
    from app.core import upset as _up
    from app.core import versions as _v
    box = _v.path_of("upset_model", "all")
    try:
        model, why = _v.pick(box, as_of=getattr(ref, "kickoff_utc", None))
    except ValueError:
        return None
    if not model or not dict(model.get("coef") or {}):
        return None
    ours = layers.get("ours")
    if ours is None:
        return None
    probs = [float(ours.home), float(ours.draw), float(ours.away)]
    fav = 0 if probs[0] >= probs[2] else 2
    said = {"weak_fav": 1.0 if probs[fav] < _up.WEAK_FAV else 0.0,
            "thin_info": 1.0 if getattr(infoq, "score", 5) <= 2 else 0.0}
    got = _up.score_of(said, model=dict(model), adopted=set())
    got.why = f"{got.why} · 판 {why}"
    return got


def _upset_apply(said, got, *, ref: MatchRef, layers: dict):
    """🔴🔴 §14 — 🔴 는 **강팀 줄을 접고**, 🟡 는 강팀 줄을 한 단계 내린다.

    🔴 확률·생존은 **그대로**다(U3) — 바뀌는 것은 `grade` 와 결론 문구뿐이다.
    """
    from app.core import upset as _up
    from app.core.stages.s7_judge import BREAK_LADDER
    ours = layers.get("ours")
    probs = [float(ours.home), float(ours.draw), float(ours.away)]
    fav_side = "home" if probs[0] >= probs[2] else "away"
    fav_name = str(getattr(ref, f"{fav_side}_name", "") or "")
    step = _up.step_of(got.grade)
    out = []
    for ev in said.evals:
        # 🔴 줄 이름 꼴은 **카드 표와 같은 것**이다(`render._b7`: `시장 쪽 점`) —
        #    다른 글자를 만들면 `folds` 가 강팀 줄을 못 알아본다.
        point = ("" if getattr(ev.line, "point", None) is None
                 else f" {ev.line.point}")
        said_line = (f"{getattr(ev.line, 'market', '')} "
                     f"{getattr(ev.line, 'side', '') or ''}{point}").strip()
        if _up.folds(said_line, grade=got.grade, fav_name=fav_name,
                     fav_side=fav_side, home=ref.home_name,
                     away=ref.away_name):
            out.append(ev.model_copy(update={
                "grade": "보류",
                "why": f"{ev.why} · 🔴 **이변 경고 — 강팀 줄을 접는다**"}))
            continue
        grade = ev.grade
        if step and grade in BREAK_LADDER:
            i = min(len(BREAK_LADDER) - 1, BREAK_LADDER.index(grade) + step)
            grade = BREAK_LADDER[i]
        out.append(ev.model_copy(update={
            "grade": grade,
            "why": (f"{ev.why} · {got.grade} 이변 경고"
                    if step else ev.why)}))
    note = (f"{got.grade} **이변 경고** — "
            + ("강팀 접는다 · 약팀 보호 줄만"
               if got.grade == _up.RED else "강팀 줄 한 단계↓"))
    return said.model_copy(update={
        "evals": out, "notes": list(said.notes) + [f"[⑳] {note} · {got.why}"]})


def _infoq_of(ref: MatchRef, facts, layers: dict, edge: dict):
    """🔴🔴 §13 — 다섯 칸을 **이 실행이 이미 아는 것**에서 센다(새로 받지 않는다).

    🔴 `None` 은 **계산 불가**(⬜)다 — 재현·백필은 기사 칸을 만들 수 없다.
    ⚠️ 점수를 만드는 규칙은 `app/core/infoquality.BOXES` 하나다(사본 금지).
    """
    xi = dict(getattr(facts, "xi", None) or {})
    both_xi = all(getattr(xi.get(str(getattr(ref, side, "") or "")), "lineup",
                          None) for side in ("home", "away"))
    ladder = dict(getattr(facts, "absence_ladder", None) or {})
    said_ladder = (bool(ladder) and
                   any(int(v or 0) > 0 for v in ladder.values())) if ladder \
        else None
    fresh = layers.get("fresh_count")
    bench = dict(getattr(facts, "bench", None) or {})
    said_bench = bool(bench) and all(bench.get(str(getattr(ref, side, "")
                                                  or "")) is not None
                                     for side in ("home", "away"))
    ctx = dict(getattr(facts, "context", None) or {})
    said_ctx = (bool(ctx) and all(ctx.get(side) for side in ("home", "away"))
                if ctx else None)
    return _iq.score_of({
        "xi_ids": bool(both_xi),
        "ladder": said_ladder,
        "fresh": (None if fresh is None else bool(int(fresh or 0) > 0)),
        "context": said_ctx,
        "bench_ids": said_bench,
    })



def _gate_of(ref: MatchRef, facts, turn: dict, *, state: RunState):
    """🔴🔴 ③ — **검문을 돌린다**. 신원표를 만들고 id 로만 견준다.

    🔴 `꺼진 무기` 는 이 자리에서 **아직 없다**(축2 가 상성 안에서 만든다) — 그
       목록은 **결장·명단 제외에서 파생**되므로 그 둘이 깨끗하면 함께 깨끗하다.
       ⚠️ 그 사실을 여기 적어 둔다(없는 검사를 했다고 말하지 않는다 · #3).
    """
    from app import rules as _rules
    from app.core import lineupgate as _gate
    from app.core import playerid as _pid
    ko = dict(_rules.names_ko().get("players") or {})
    ids: dict = {}
    pos: dict = {}
    boxes: dict = {}
    said_rows: list[str] = []
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        box = _pid.build(rows=_id_rows(facts, key), ko=ko)
        one = (facts.xi or {}).get(key)
        rows = list(getattr(one, "lineup", None) or [])
        got_ids: list[str] = []
        got_pos: list[str] = []
        for p in rows:
            ident, why = _pid.resolve(
                box, said=str(getattr(p, "name", "") or ""),
                number=getattr(p, "number", None))
            got_ids.append(ident)
            if str(getattr(p, "pos", "") or "").upper() == "GK":
                got_pos.append("GK")
            said_rows.append(f"{side} `{getattr(p, 'name', '')}`"
                             f"({getattr(p, 'number', None)}) → "
                             f"`{ident or '🔴 못 풀었다'}` · {why}")
        # 🔴 번호가 없어 GK 를 못 읽었으면 **신원표의 포지션**으로 한 번 더 본다
        if not got_pos:
            got_pos = ["GK" for ident in got_ids
                       if ident and str(box[ident].pos or "").upper() == "GK"]
        ids[side] = got_ids
        pos[side] = got_pos
        # 🔴 "누구"는 **사람이 읽는 이름**으로 적는다(`playerid.said_of`)
        state.note(f"신원표({side}) — "
                   + " · ".join(_pid.said_of(box, x) for x in got_ids if x))
        # ── (c) 의 목록들 — **id 로** 담는다
        miss = [_pid.resolve(box, said=getattr(m, "name", ""))[0]
                for m in ((facts.missing or {}).get(key) or [])]
        offs = [_pid.resolve(box, said=str(nm))[0]
                for nm in (dict(turn.get(side) or {}).get("off_squad") or [])]
        boxes[side] = {"결장 명단": [x for x in miss if x],
                       "없는 선수(명단 제외)": [x for x in offs if x]}
    state.note("신원 풀이 — " + " / ".join(said_rows[:24]))
    return _gate.check(ids=ids, pos=pos,
                       clash=_gate.clash_of(xi_ids=ids, boxes=boxes))


def _gate_card(ref: MatchRef, facts, variables: list, gate, *,
               state: RunState, docs: list, before: Card | None):
    """🔴🔴 ③ — **"라인업 신원 미확정" 카드**. 상성·확률 칸을 **비운 채** 낸다.

    > 숫자를 낸 채 🔴만 다는 것 금지.
    """
    from app.core.schema import Card as _C
    state.note(gate.card())
    # 🔴🔴 **`notes` 칸은 `Card` 에 없다**(`Frozen` · extra 금지) —
    #    ⚠️ 실사고 2026-10-13(이스트 벵골–알쇼르타): 이 자리가 `notes=` 를 넘겨
    #       **카드가 통째로 터졌다**(`ValidationError: extra_forbidden`). 이 길은
    #       신원 검문이 걸릴 때만 도는 **퇴로**라서 여태 한 번도 안 지났다.
    #    🔴 사유는 **결론 줄**에 적는다(그 자리가 *"왜 확률이 없나"* 를 말한다) ·
    #       같은 글은 `state.note` 로도 남는다(위 줄).
    return _C(match=ref, facts=facts, variables=list(variables or []),
              funnel=state.counted_box() if hasattr(state, "counted_box")
              else _C(match=ref, facts=facts).funnel,
              conclusion=gate.card(), stance="🔴 확률 미산출(신원 검문)")


def _moved(before: Card, layers: dict, mr: object) -> list[str]:
    """🔴🔴 **F1 — 바뀐 것: 상성 축(전→후)·확률(전→후)·등급(전→후)**.

    ⚠️ 직전 카드가 그 수를 들고 있을 때만 적는다(없으면 그 사실을 적지 않는다 — 빈
       줄을 지어내지 않는다 · #3).
    """
    out: list[str] = []
    was = dict(getattr(before, "matchup", None) or {})
    old_mr = was.get("report")
    if old_mr is not None and mr is not None:
        from app.core import matchup as _mu
        a, b = _mu.fingerprint(old_mr), _mu.fingerprint(mr)
        if a != b:
            out.append(
                f"상성 축 — {getattr(old_mr, 'why', '')[:60]} → "
                f"{getattr(mr, 'why', '')[:60]}(지문 {a} → **{b}**)")
    old_p, now_p = getattr(before, "our_prob", None), layers.get("ours")
    if old_p is not None and now_p is not None:
        said = [(k, getattr(old_p, k, None), getattr(now_p, k, None))
                for k in ("home", "draw", "away")]
        if any(x != y for _k, x, y in said if x is not None and y is not None):
            out.append("확률 — " + " · ".join(
                f"{k} {float(x):.0%}→**{float(y):.0%}**"
                for k, x, y in said if x is not None and y is not None))
    return out


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
            said: Judgement, *, state: RunState,
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
        divergence=str(box.get("divergence") or ""),
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
        # 🔴 **P0** — 쓴 시간·건너뛴 단계(카드 머리가 적는다)
        time_note=(state.clock.said_of()
                   if getattr(state, "clock", None) is not None else ""),
        prob_expected=box.get("prob_expected"),
        prob_expected_why=str(box.get("prob_expected_why") or ""),
        matchup=dict(box.get("matchup") or {}),
        # 🔴🔴 **가설 검증표**(순서 재편 §4-5) — 최종 평이 `supported` 만 쓴다
        check=dict(box.get("check") or {}),
        # 🔴🔴 **변수 배치**(상성 엔진 V-4) — 긴 카드 `🔢 변수` 가 전부 보인다
        varset=box.get("varset"),
        match=ref, facts=facts, variables=variables,
        drops=list(state.drops), evals=said.evals,
        direction=said.direction, conclusion=said.conclusion,
        # 🔴 [3d] 반증 — 판정과 조건 전문을 카드가 든다(⑯)
        # ⚠️ 이 자리에서 재료 묶음의 이름은 `box["matchup"]` 이다(`edge` 가 아니다 —
        #    그것은 파이프라인 본체의 지역 이름이다 · 계약이 잡았다 2026-10-12).
        stance=said.stance,
        # 🔴 §10 — 이변 경고 한 줄(등급만 바꿨다 · 확률은 그대로다)
        upset=str(getattr(box.get("upset"), "why", "") or ""),
        # 🔴 §7 — 일정 한 줄(표시 전용 · 확률은 §9 가 채택할 때 들어간다)
        schedule=_schedule_line(facts),
        # 🔴 §13 — 머리 줄이 적는다(확률에는 안 닿는다 · C13-1)
        infoq=str(getattr(box.get("infoq"), "why", "") or ""),
        infoq_score=(int(getattr(box.get("infoq"), "score", 0))
                     if box.get("infoq") is not None else None),
        break_rerun=str(box.get("break_rerun") or ""),
        breaks=list(dict(box.get("matchup") or {}).get("breaks") or []),
        triggers=said.triggers,
        funnel=Funnel(counts=state.counted(),
                      drops=list(state.drops)),
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



def _comment_layers(got, shape: dict) -> dict:
    """🔴 논평·검열 결과를 카드 칸으로. ⚠️ **한 곳**이다(두 입구가 같은 것을 쓴다).

    🔴 `shape_used` 가 있으면 **그것이 카드의 양상**이다(§4-1 (d) 가 낮춘 값) —
       논평과 카드가 서로 다른 양상을 말하면 그 자체가 모순이다.
    """
    return {"shape": (got.shape_used or shape), "commentary": got.said,
            "comment_notes": list(got.notes), "comment_audit": got.audit,
            "comment_violations": list(got.violations)}


def compare_block(base_for_compare, ours, market,
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
    tilt = compare.tilt_reasons(ours, base_for_compare, variables,
                                measured=measured)
    return {"compare": verdict, "tilt": tilt, "_lines": lines,
            "compare_lines": [*lines, (f"시장 열 — {label}" if label else "")]}


def _layers(ref: MatchRef, facts: Facts, variables: list[Variable],
            base_p: BaseProb, adj_p: AdjProb,
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
    said3 = compare_block(base_for_compare, ours, market, variables,
                          measured=adj_p.measured, label=label)
    verdict, lines, tilt = said3["compare"], said3["_lines"], said3["tilt"]
    # 🔴 ④ — **우리 결론의 방향**을 넘긴다(근거 검열의 기준이다)
    reasons = compare.market_reasons(base_p, adj_p, market, variables, ref,
                                     ours=ours)
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


def _divergence_of(ref, facts, prob, board, layers) -> tuple[str, str]:
    """🔴🔴 **P5** — 보드가 있으면 괴리 줄과 **상한 사유**를 만든다.

    🔴 ⬜ 입력 목록은 **카드가 이미 아는 사유**에서 읽는다(사본 금지):
       기준(Elo)·리그 오프셋·대회 이력·축1~3·XI 판.
    """
    from app.core import divergence as _dv
    if prob is None or not prob.ok() or board is None:
        return "", ""
    prices: list[float] = []
    for market, side in (("win", "home"), ("draw", ""), ("win", "away")):
        got = [float(x.price) for x in (board.lines or [])
               if str(x.market) == market and str(x.side or "") == side
               and x.price]
        prices.append(got[0] if got else 0.0)
    if min(prices) <= 0:
        return "", ""
    # 🔴 ⬜ 인 입력들 — 그 경기에서 **못 센 칸**만 이름으로 모은다
    box = dict(getattr(facts, "standings", None) or {})
    gaps: list[str] = []
    said_base = dict(layers or {}).get("base")
    if said_base is None or getattr(said_base, "probs", None) is None:
        gaps.append("Elo 기준")
    if "⬜" in str(box.get("league_gap") or "") or not box.get("league_gap"):
        gaps.append("리그 오프셋")
    said_hist = str(box.get("comp_history") or "")
    if "⬜" in said_hist or "🟡" in said_hist or not said_hist:
        gaps.append("대회 이력")
    said_edge = dict(getattr(prob, "share", None) or {})
    if any(abs(float(said_edge.get(k) or 0.0)) < 1e-9
           for k in ("axis1", "axis2", "axis3")):
        gaps.append("축1~3 일부")
    if not (facts.xi or {}):
        gaps.append("XI 판")
    return _dv.said_of([prob.home, prob.draw, prob.away], prices, gaps=gaps)


def _direction(said: Judgement, layers: dict, ref: MatchRef) -> Judgement:
    """🔴 §7 방향 판정 — **세 열의 홈승·원정승을 다 적는다**(블록 9).

    ⚠️ 종전 방향 줄은 우리 확률만 적었다 — 세 열이 있으면 그 셋을 나란히 적고, 둘
       이상이 한 팀을 0.15 이상 앞세울 때만 그 팀을 적는다(§7 마지막 줄).
    🔴🔴 **열이 우리뿐이어도 적는다**(예측 지시 2026-10-13 §0) — 그 열 하나로
       정하고 *"열이 하나다"* 를 글자에 남긴다(문장 꼴은 `survive.direction_line`
       하나다 · 사본 금지). ⚠️ 없는 열은 **지어내지 않는다**(빈 칸으로 넘긴다).
    """
    from app.core import compare
    base_p, market = layers.get("base"), layers.get("market")
    said_ours = layers.get("ours")
    # 🔴🔴 **우리 확률만 있어도 방향을 적는다**(예측 지시 2026-10-13 §0:
    #    *"결론은 봇 확률(%)만으로"*). ⚠️ 종전에는 기준·시장이 둘 다 없으면
    #    **그냥 돌려보냈고**, 그래서 ACL 카드의 방향 줄이 **빈 글자**였다
    #    (카드가 *"방향 줄이 비었다 — 이것은 결함이다"* 를 찍었다 · 실측).
    if said_ours is None and (base_p is None or base_p.probs is None):
        return said
    if base_p is None:
        from app.core.schema import BaseProb as _BP
        base_p = _BP(probs=None, why="⬜ 기준(Elo) 없다")
    if market is None:
        from app.core.schema import MarketProb as _MP
        market = _MP()
    return said.model_copy(update={
        "direction": compare.direction_line(base_p, said_ours, market, ref)})


def _grade_by_check(said: Judgement, layers: dict, *,
                    state: RunState) -> Judgement:
    """🔴🔴 **F4** — 등급을 내리는 길은 **⑫ 검증 하나**다(지시서 2026-10-11).

    > `s7_judge` 의 `_lower`(세 열 규칙) **삭제**. 등급 조정은 ⑫ 검증 규칙
    > (5-3: 상성 사각 hard 반대·가설 지지 0)만. 시장은 **카드 표시만**(C12).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 세 열 규칙을 걷었나
    ══════════════════════════════════════════════════════════════════

    종전에는 `compare.grade_step`(기준·우리·시장 세 열)이 **먼저** 칸 수를 주고
    거기에 검증 조정을 더했다. 그런데 그 표의 절반이 **시장**(`시장이 다르다`·
    `시장만 튄다`)이었다 — 시장이 등급에 닿는 길이 남아 있던 것이다(C12 위반 소지).
    🔴 그래서 **검증 하나만** 남긴다. 🔴 `우리만 반대`(= 기준과 앞세우는 쪽이
    다르다)는 시장 규칙이 아니라 **기준(V1) 규칙**이라 검증 쪽으로 옮겨 둔다.

    ⚠️ **확률은 안 바뀐다**(S5 머리줄) — 등급만 움직인다.
    """
    step, why = 0, ""
    box = dict(dict(layers.get("check") or {}).get("grade") or {})
    if box.get("none"):
        step, why = 99, " · ".join(box.get("why", [])).strip(" ·")
    elif int(box.get("steps") or 0) > 0:
        step = int(box["steps"])
        why = " · ".join(box.get("why", [])).strip(" ·")
    if step <= 0:
        if why:
            state.note(f"⑫ 검증 — 등급 유지 — {why}")
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
    state.note(f"⑫ 검증 — 등급 **내림** {step}칸 — {why}")
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
    """🔴🔴 **㉔ 결론 문단 — 코드 템플릿 하나**(지시서 2026-10-12(셋째) §1 처분).

    > ㉔ 최종 평·논평(LLM) → **코드 템플릿으로 교체**(FactBundle → 정해진 문장).
    > LLM 호출 삭제.

    🔴 글을 짓는 곳은 `layer1.template_lines` **하나다**(사본 금지) — 숫자에서
       문장을 만든다. ⚠️ 종전에는 LLM 이 한 편을 쓰고 그 문단을 쪼개 담았고,
       3문장이 안 될 때만 템플릿으로 떨어졌다. 🔴 이제 **늘 템플릿**이다.
    🔴 왜 지웠나 — 광주 재현에서 LLM 문장이 **근거에 없는 4-3** 을 적었다(그 수가
       실제 결과와 같았다). 검증할 수 없는 서술은 확률도 등급도 못 움직이면서
       **누설 위험**만 남긴다(지시서 §0).
    """
    from app.core import layer1 as _l1
    from app.core.schema import ReasonLine, ReasonPara
    rows, refs = _l1.template_lines(card)
    said = ReasonPara(sentences=[ReasonLine(text=t, fact_refs=r)
                                 for t, r in zip(rows, refs, strict=False)])
    state.note(f"㉔ 결론 문단 — **코드 템플릿** {len(rows)}문장(LLM 없음)")
    return card.model_copy(update={"reason": said, "reason_audit": "템플릿"})
