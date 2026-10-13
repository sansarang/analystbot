"""🔴🔴 **v6 s2 — 구조 사실.** `MatchRef → Facts`(§5).

지시서 §5 s2: *"기존 어댑터 호출 → `adapt.py` 에서 `Facts` 로. 어댑터마다 다른
모양(`players` dict/list 등)은 **여기서만** 흡수. `match_format` 은 대회명·라운드
정보로 정하고 모르면 `unknown`."*

⚠️ 없으면 `None`·빈 것이다 — **지어내지 않는다**(§3).
"""
from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core import adapt
from app.core.schema import XI, DropReason, Facts, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 경기당 **추가 fetch 상한**(사용자 승인 2026-10-06(5차) ②) — 팀마다 이만큼
#
#  > 경기 페이지에서 직전 경기 링크를 **최대 5개까지** 따라가 평소 XI 를 만든다.
#  > 경기당 추가 fetch 상한 **5**, 캐시 **하루**.
FOLLOW_CAP = 5
#: 🔴 하루 캐시 자리 — ⚠️ 저장소가 아니라 `var/` 다(커밋하지 않는다)
FOLLOW_DIR = pathlib.Path(__file__).resolve().parents[3] / "var" / "follow"


@dataclass
class _Page:
    """🔴 하루 캐시에서 꺼낸 쪽 — 어댑터가 보는 칸만 흉내 낸다(`url`·`text`·`ok`)."""

    url: str
    text: str
    ok: bool = True
    status: int = 200


async def run(ref: MatchRef, *, state: RunState, net: Any = None,
              search: Any = None,
              xi_capture: dict | None = None) -> Facts:
    """🔴 그 경기의 구조 사실. ⚠️ 실패해도 **빈 `Facts`** 를 돌려준다(§5).

    🔴🔴 `xi_capture` 는 **사람이 준 라인업**이다(`{"home": 글, "away": 글}`).
       ⚠️ 실사고 2026-10-11: 소비자(`_fill_capture`)와 파서는 있는데 **채우는 곳이
       없었다** — 통로가 통째로 안 이어져 있었다(#2 배선). 사용자가 캡처를 보내도
       봇이 쓸 수 없었다.
    """
    box: dict[str, Any] = {}
    if xi_capture:
        box["xi_capture"] = dict(xi_capture)
    xi: dict[str, XI] = {}
    missing: dict[str, list] = {}
    coach: dict[str, Any] = {}
    sources: list[str] = []
    raw_xi: dict[str, dict] = {}
    #: 🔴 선수 **가치**를 담은 사실들(오늘 XI · 직전 경기) — ② 가 쓴다
    raw_value: list[dict] = []
    #: 🔴 팀별 **과거 경기 선발 여럿**(최신부터) — ② 가 평소 XI 를 여기서 만든다
    past: dict[str, list[XI]] = {}
    #: 🔴 §1 — 깊이 소스가 받은 **경기 페이지 본문들**(조 순위표 주소의 재료)
    raw_pages: list[str] = []
    try:
        got = await _depth(ref, net=net, search=search, state=state,
                           pages=raw_pages)
    except Exception as exc:                                # noqa: BLE001
        state.drop("s2", DropReason.NO_DOC, f"깊이 소스가 터졌다: {exc!r}")
        got = []
    for fact in got:
        qid = str(getattr(fact, "question_id", "") or "")
        val = getattr(fact, "value", None)
        if not isinstance(val, dict):
            continue
        tail = qid.rpartition(":")[2]
        url = str(getattr(fact, "source", "") or "")
        if url:
            sources.append(url)
        if tail == "standings":
            box.setdefault("standings", {}).update(val)
        elif tail == "form":
            team = str(getattr(fact, "team", "") or "")
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **폼도 열쇠로 넣는다** — 실측 2026-10-06
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 종전엔 **이름**(`"South Korea"`)으로 넣었다. 그래서 해석 규칙이
            #     `facts.recent.get(ref.home)`(열쇠)로 찾다가 **한 번도 못 찾았다** —
            #     S01(폼)·IR04(이상치)·IR12(연속)가 통째로 0건이었다.
            #  🔴 `Facts` 의 팀 칸은 **전부 `TeamKey`** 다(§3) — 이름은 렌더할 때만.
            key = _key_of(ref, team) if team else ""
            if key:
                box.setdefault("recent", {})[key] = dict(val)
            elif team:
                state.note(f"s2 폼 — `{team}` 을 열쇠로 못 바꿨다(그 칸을 버린다)")
        elif tail == "h2h":
            box.setdefault("h2h", {}).update(val)
        elif tail == "baseline" and val.get("team"):
            # 🔴 **직전 경기 선발**(⑦) — IR02·IR06 이 이것을 본다
            key = _key_of(ref, str(val.get("team")))
            if key:
                mine = adapt.xi_of(key, {**val, "lineup_state": "none"},
                                   source_url=url)
                # 🔴 **여러 경기를 쌓는다**(② 평소 XI · 승인 ②). ⚠️ `last_xi` 는
                #    **첫 번째**(가장 최근)만 쓴다 — IR02 가 그것을 본다.
                past.setdefault(key, []).append(mine)
                box.setdefault("last_xi", {}).setdefault(key, mine)
                # 🔴 **직전 경기 페이지도 가치 출처다**(② · 네 층 §4-3) — 오늘 XI 가
                #    없어도 평소 XI 의 가치는 거기서 온다
                raw_value.append(dict(val))
                # 🔴 **일정**(IR11) — 직전 경기 날짜·상대를 적는다(가장 최근 것)
                said_v = dict(val.get("venue") or {})
                box.setdefault("schedule", {}).setdefault(key, {
                    "last_match": val.get("from_date"),
                    "last_opponent": val.get("from_match"),
                    # 🔴 IR11(7차 §6) — 직전 경기 좌표와 **이 경기 좌표**
                    "last_venue": said_v.get("name") or None,
                    "last_lat": said_v.get("lat"), "last_lon": said_v.get("lon"),
                    "source_url": url})
        elif tail in ("lineup", "xi") and val.get("team"):
            key = _key_of(ref, str(val.get("team")))
            if key:
                # 🔴 **결장 명단·감독을 같은 사실에서 받는다**(축구 §2)
                raw_xi[key] = {**val, "source_url": url}
                mine = adapt.missing_of(val.get("missing"), source_url=url)
                if mine:
                    missing[key] = mine
                got_coach = adapt.coach_of(val.get("coach"))
                if got_coach is not None:
                    coach[key] = got_coach
    # 🔴 XI 는 **결장 명단을 보고** 만든다 — 🔴🔴 뺄지는 `absence.removable` 이
    #    정한다(B 단독은 **안 뺀다** · 지시 2026-10-13 밤 다섯째 2번).
    #    ⚠️ 이 자리에서는 대회 열쇠(`league:…`)가 **아직 안 만들어졌다**(아래
    #       `_kind_of` 가 만든다) — 그래서 `ref` 의 리그 글자를 넘긴다. 등급 표가
    #       그 리그를 모르면 **공통 표**로 떨어진다(`sources.table`).
    said_league = str(getattr(ref, "league", "") or "")
    for key, val in raw_xi.items():
        xi[key] = adapt.xi_of(key, val, source_url=str(val.get("source_url") or ""),
                              missing=missing.get(key), league=said_league)
        if xi[key].conflicts:
            state.note(f"s2 예상 명단 충돌 — {', '.join(xi[key].conflicts)}")
    # 🔴 **소집 명단**(선발+교체 전원) — ①-b 예외와 ② 가 이 표를 쓴다
    squad: dict[str, list[str]] = {}
    for key, val in raw_xi.items():
        got = adapt.names_of(val.get("squad"))
        if got:
            squad[key] = got
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **같은 조 순위표·잔여 경기**(사용자 지시 2026-10-06(7차) §1)
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **이 경기 구장 좌표**(IR11 재료) — 경기 페이지에서 한 번만 읽는다
    here = _venue(raw_pages)
    if here:
        for row in (box.get("schedule") or {}).values():
            row.setdefault("lat", here.get("lat"))
            row.setdefault("lon", here.get("lon"))
            row.setdefault("venue", here.get("name"))
        state.note(f"s2 §6 이 경기 구장 — {here.get('name')} "
                   f"({here.get('lat')},{here.get('lon')})")
    said = await _group(ref, state=state, net=net, pages=raw_pages)
    if said:
        # 🔴 `Facts.standings` 안의 **`group` 칸**이다 — 기존 칸(홈 이점·쪼갠 표)을
        #    덮지 않는다(⚠️ `box["group"]` 에 두면 `facts_of` 가 안 싣는다 · 실측)
        box.setdefault("standings", {})["group"] = said
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **폼 보완**(사용자 지시 2026-10-09(5차) ②) — 세 가지를 더 받는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `facts.recent` 가 비면 경기 페이지가 아니라 **팀 페이지**에서 최근 5경기
    #  > 스코어를 받는다. 동시에 **리그 표**에서 경기당 총골을 구조 사실로 둔다.
    #  > 팀 **핵심 선수**(시즌 득점·도움 상위 2명)도 받는다.
    #
    #  🔴 실사고 2026-10-09(가시마–감바): 경기 페이지가 폼을 안 줘 `recent` 가
    #     **0건**이었다 — 득점 흐름 변수가 하나도 없었고 이유 문단이 템플릿이 됐다.
    #  ⚠️ **폼이 이미 있으면 팀 페이지를 안 받는다**(통신 예산 · §19-b).
    await _auto_register(ref, box, state=state, net=net, pages=raw_pages)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **사람이 준 라인업이 있으면 그것이 이긴다**(사용자 지시 2026-10-10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 데스크탑 라인업 캡쳐 확인해라.. **네이버 스포츠에는 이미 떴다**..
    #
    #  🔴 실측 2026-10-10(김천–안양 T-50분): 네이버에는 확정 라인업이 떴는데
    #     fotmob 은 아직이었다(사다리 다섯 칸 전부 `없음`). 사람이 준 글이
    #     **유일한 통로**였다. ⚠️ 이름이 아니라 **등번호로** 잇는다(한글↔로마자).
    await _fill_capture(ref, box, xi, state=state, net=net, pages=raw_pages)
    await _fill_form(ref, box, state=state, net=net, pages=raw_pages)
    # 🔴🔴 **선수별 시즌 기록**(최종 평 §1-1) — 선수단 페이지 · 팀당 한 번
    await _fill_squad(ref, box, state=state, net=net)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **라인업 사다리**(사용자 지시 2026-10-10 A-1) — 경기 페이지가 못 줄 때
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 순서는 `config/lineup_sources.yaml` 의 `ladder` 가 든다. ⚠️ 여기서 그
    #     순서를 다시 적지 않는다(사본 금지) — 사다리를 **읽어서** 돈다.
    #  🔴 지금 이 자리가 채우는 것은 **공식 출처의 사실**이다(일정·구단 SNS·
    #     타임라인). 선발 11명을 주는 칸은 실측으로 **아직 없다**(표에 적었다).
    await _fill_official(ref, box, state=state, net=net)
    # 🔴🔴 **선수 → 시장가치 표**(② 라인업 전력 · 네 층 지시서 §4-3)
    #
    #  🔴 경기 페이지가 이미 들고 온다 — 새 출처를 붙이지 않는다(실측 2026-10-06:
    #     `marketValue` 가 선발·교체 칸에 있다 · `config/rating_sources.yaml`).
    values: dict[str, float] = {}
    for val in (*raw_xi.values(), *raw_value):
        values.update(adapt.values_of(val))
    if values:
        state.note(f"s2 선수 가치 {len(values)}명 ← 경기 페이지(②가 쓴다)")
    # 🔴 **선수 → 포지션 표**(경기 단위 · §2) — §1-1 결장 유형과 IR01·IR02 가 쓴다
    pos: dict[str, str] = {}
    for key, box_xi in xi.items():
        for p in box_xi.lineup:
            # 🔴🔴 **세부 자리가 먼저다**(`spot` — 좌표에서 온 `LB`·`CB`·`RB`).
            #    ⚠️ 실사고 2026-10-10: 묶음 글자(`DF`)만 실어 `slot_of` 가 풀백까지
            #       **중앙 수비로** 셌다 — 카드가 "CB 네 명"을 냈다(사용자가 잡았다).
            said = str(getattr(p, "spot", "") or "") or str(p.pos or "")
            if said:
                pos[p.name] = said
    # 🔴🔴 **과거 경기에서도 포지션을 모은다**(사용자 지시 2026-10-06(6차) ③)
    #
    #  ⚠️ 실측 2026-10-06: 오늘 XI 가 없는 경기에서는 포지션 표가 **통째로 비어** ②
    #     기여표가 센터백과 공격수를 짝지었다. 🔴 같은 선수의 포지션은 직전 경기
    #     페이지에 **이미 있다**(`players_of` 가 `usualPlayingPositionId` 를 읽는다).
    for rows in past.values():
        for box_xi in rows:
            for p in box_xi.lineup:
                said = str(getattr(p, "spot", "") or "") or str(p.pos or "")
                if said:
                    pos.setdefault(p.name, said)
    for rows in missing.values():
        for m in rows:
            if m.pos and m.name not in pos:
                pos[m.name] = m.pos
    # 🔴 **형식은 표가 정한다**(대회명·라운드) — 모르면 `unknown`(지어내지 않는다)
    fmt, why = _format_of(ref)
    state.note(f"s2 형식 — {why}")
    # 🔴🔴 **포지션 분류 검사**(사용자 지시 2026-10-10 ②) — 어긋나면 사유를 남긴다
    from app.core import strategy as _st
    for key, box_xi in xi.items():
        said = _st.pos_fault([p.name for p in box_xi.lineup], pos)
        if said:
            state.note(f"s2 포지션 분류 — {key} {said}")
            box.setdefault("pos_fault", {})[key] = said
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **결장 사다리**(사용자 지시 2026-10-11 ①) — fotmob 칸이 비면 내려간다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-11(광주–울산): 결장이 fotmob 의 `unavailable` 칸 **하나**에
    #     매달려 있었고 그 칸이 비자 *"결장 명단 미확보"* → 기사 0 → 전략 버림 →
    #     전술 템플릿까지 **한 줄로 이어졌다**.
    from app.core import absence as _ab
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **칸 3 연맹 징계 — 받아 온다**(지시 2026-10-13 밤 넷째 3번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 표(`config/league_discipline.yaml`)에 **받아서 확인한 주소**가 있는
    #     리그만 받는다. ⚠️ **L2** — 공시는 **현재 값**이므로 **재생에서는
    #     안 받는다**(그 사실을 사유가 적는다).
    said_kind = _kind_of(ref, box)
    said_disc = await _discipline_rows(net, ref, league=said_kind,
                                       state=state)
    for key, rows in dict(said_disc.get("add") or {}).items():
        missing.setdefault(key, []).extend(rows)
    said_lad = _ab.ladder(
        adapt.facts_of(box, xi=xi, missing=missing, squad=squad,
                       past_xi=past, coach=coach),
        keys=[str(getattr(ref, "home", "")), str(getattr(ref, "away", ""))],
        league=said_kind,
        discipline={k: v for k, v in said_disc.items() if k != "add"}
        if said_disc.get("asked") else None)
    for key, rows in dict(said_lad.get("add") or {}).items():
        missing.setdefault(key, []).extend(rows)
    state.note("s2 결장 사다리 — " + _ab.said_of(said_lad))
    logger.info("[s2] 결장 사다리 — %s", _ab.said_of(said_lad))
    gaps = _gaps(xi=xi, missing=missing, coach=coach, box=box, pos=pos,
                 rungs=list(said_lad.get("rungs") or []))
    if gaps:
        state.note("s2 못 받은 칸 — " + " · ".join(gaps))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **[2a] 상태별 득점률 표를 싣는다**(수정 지시서 2026-10-12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 위치: ③ 구조 사실 수집. 팀별 상태 배율을 facts에 싣는다
    #  > (없으면 **리그값·🔴**).
    #
    #  🔴 수를 여기서 만들지 않는다 — `tools/fit_state_rates.py` 가 만든
    #     `data/state_rates/<리그>.yaml` 을 **읽기만** 한다(#1 사본 금지).
    #  ⚠️ 대회 유형 열쇠(`league:PD`)를 만드는 함수는 **완성된 facts** 를 본다 —
    #     그래서 묶음을 **먼저 만들고** 그 위에 얹는다(실측 2026-10-12: `ref` 에
    #     `competition_key` 칸이 없어 표가 통째로 안 실렸다).
    got_facts = adapt.facts_of(box, xi=xi, match_format=fmt,
                          sources=sorted(set(sources)), missing=missing,
                          coach=coach, player_pos=pos, gaps=gaps, squad=squad,
                          player_value=values, past_xi=past,
                          absence_rungs=list(said_lad.get("rungs") or []),
                          player_stats=dict(box.get("player_stats") or {}),
                          # 🔴 ③ — 팀별 공격 기여 표(비중의 분모)
                          player_stats_team=dict(
                              box.get("player_stats_team") or {}))
    from app.core import staterates as _sr
    from app.core.stages.s5_verify import comp_kind as _ck
    said_lg = ""
    try:
        said_lg = str(_ck(ref, got_facts) or "")
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2 [2a] 대회 유형 열쇠를 못 만들었다({exc!r:.40})")
    # 🔴 L3 — **as_of 이전 판**만 본다(운영은 오늘 이전, 재현은 그 경기 이전)
    state_tab, state_why = _sr.pair(
        league=said_lg, home=str(getattr(ref, "home", "") or ""),
        away=str(getattr(ref, "away", "") or ""),
        as_of=getattr(ref, "kickoff_utc", None))
    state.note(f"s2 [2a] 상태 배율(`{said_lg}`) — "
               + (_sr.said_of(state_tab, state_why) if state_tab
                  else f"⬜ 없다({state_why.get('home') or ''})"))
    logger.info("[s2] [2a] 상태 배율 — %s · %s", said_lg,
                _sr.said_of(state_tab, state_why) if state_tab else "⬜ 없다")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§7 경기 직전 상태**(지시서 2026-10-12(둘째)) — ③ 가 싣는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 왜 — 실사고 둘에서 봇은 *"3주 휴식 후 홈"*·*"직전 컵 일정"* 을 **몰랐다**.
    #     그 둘은 과거 성적표에 적혀 있지 않다.
    #  🔴 목록은 **폼·축1 과 같은 것**이다(`_history` + `games_of`) — 사본 금지.
    #  ⚠️ 확률에는 아직 **안 들어간다**(§9 전진 선택이 채택해야 들어간다 · S1).
    said_ctx = await _context_of(net, ref, state=state)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **두 팀 총골 기준을 표본으로 수축한다**(수정 지시 2026-10-13 4번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: 상하이–대전 λ 가 2.818/2.170(총골 **4.99**)이었다 — 대회 실측
    #     2.8213 의 1.77배다. 까닭은 λ 바닥이 **ACL 리그 단계 2경기**로 센 두 팀
    #     총골 **5.5** 였다는 것이다(대회 기준은 한 번도 안 쓰였다).
    #  🔴 운영 확률은 **얼린 M1**(K0)이 내고 그것도 같은 칸을 읽으므로 **칸을
    #     고친다** — 수축한 수를 싣고 원값·표본·사유를 옆 칸에 남긴다(#3).
    said_std = dict(getattr(got_facts, "standings", None) or {})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대회 홈/원정 성적**(사용자 지시 2026-10-13 ①) — 대륙 대회의 S03 을
    #    **대회 일정 표**로 채운다(표시 전용 · λ 는 득점 실측만 쓴다).
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측: ACL 카드의 S03 이 *"홈 **승률** 수치 없음"* 이었다 — 대회 유형의
    #     승률 표가 없어서다. 🔴 그 수는 **대회 일정 한 장**에 있다(직전 2시즌
    #     스코어 · 중립 단계 제외) — `tools/fit_comp_record.py` 가 판으로 적어 둔다.
    from app.core import competition as _cp3
    if _cp3.kind_require(said_lg)[0] == "club_continental":
        from app.core import comprecord as _cr
        said_ha, why_ha = _cr.comp_of(said_lg)
        if said_ha and not said_std.get("home_advantage"):
            said_std["home_advantage"] = dict(said_ha)
            state.note(f"s2 ① 대회 홈 우위(표시) — `{said_lg}` "
                       f"{said_ha.get('win_pct_delta'):+}%p · {why_ha}")
        said_rec = _cr.said_of(said_lg,
                               home=str(getattr(ref, "home_name", "") or ""),
                               away=str(getattr(ref, "away_name", "") or ""))
        said_std["comp_record"] = said_rec
        state.note(f"s2 ① 대회 홈/원정 성적 — {said_rec[:120]}")
    if said_std.get("match_total_baseline") is not None:
        from app import rules as _r3
        from app.core import goalbase as _gb
        said_comp = dict(_r3.goal_baseline(said_lg) or {}).get(
            "goals_per_match")
        got_base, why_base = _gb.shrink(
            said_std.get("match_total_baseline"),
            played=said_std.get("match_total_played"),
            comp_total=(float(said_comp) if said_comp is not None else None))
        if got_base is not None:
            said_std["match_total_raw"] = said_std["match_total_baseline"]
            said_std["match_total_baseline"] = round(float(got_base), 3)
            said_std["match_total_why"] = why_base
            state.note(f"s2 §3 총골 기준(`{said_lg}`) — {why_base}")
            logger.info("[s2] §3 총골 기준 — %s", why_base)
    return got_facts.model_copy(update={
        "state_rates": state_tab, "state_rates_why": state_why,
        "standings": said_std, "context": said_ctx})


async def _context_of(net, ref, *, state) -> dict:
    """🔴 §7 — 두 팀의 `ContextRow`. ⚠️ 못 받으면 **빈 묶음**이고 사유를 적는다."""
    from app.core import context as _ctx
    from app.core.stages.s2e_matchup import _history as _hist
    from app.core.stages.s2e_matchup import games_of as _games_of
    out: dict = {}
    for side in ("home", "away"):
        name = str(getattr(ref, f"{side}_name", "") or "")
        try:
            rows = await _hist(net, name, state=state,
                               as_of=ref.kickoff_utc, ref=ref)
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s2 [§7] `{name}` 경기 목록을 못 받았다({exc!r:.40})")
            continue
        said = _games_of(rows or [])
        if not said:
            state.note(f"s2 [§7] `{name}` — ⬜ 경기 목록이 비었다(휴식·부하 없음)")
            continue
        got = _ctx.row_of(name, said, as_of=ref.kickoff_utc)
        out[side] = got
        state.note(f"[③] 일정 `{name}` — {got.why}")
    return out


async def _discipline_rows(net, ref, *, league: str, state) -> dict:
    """🔴🔴 칸 3 — 연맹 징계 공시를 **받아** 그 경기의 결장을 만든다.

    돌려주는 표: `{asked, n, why, add: {팀 열쇠: [Missing …]}}`.
    🔴 **L2** — 공시는 **현재 값**이다 → **재생(카세트)에서는 안 받는다**.
    🔴 표에 **받아서 확인한 주소**가 없는 리그는 그냥 넘긴다(옛 사유가 남는다).
    """
    from app import cassette as _cas
    from app import rules as _rules
    from app.core.schema import Missing
    box = _rules.discipline_of(str(league or ""))
    said_jpn = ""
    if not box:
        # 🔴🔴 **일본 클럽 경기면 공시를 붙인다**(실측 2026-10-13).
        #  ⚠️ 운영에서 리그 열쇠가 `league:fotmob224`(순위표 없는 일본 대회 ·
        #     58팀)로 떨어졌고, 그래서 J1 표의 주소가 **안 붙었다**. 🔴 그 대회가
        #     J1 인지 컵인지 **fotmob 이 이름을 안 준다**(`leagueName`·`title` 둘
        #     다 ⬜) → **단정하지 않는다**(#4). 대신 **공시 자체가 리그를 가리지
        #     않는다**는 실측을 쓴다(한 표에 J1·J2·U-21 이 함께 실린다).
        from app.core import autoleague as _al
        said_cc = str(dict(_al.load(str(league or "")) or {}).get("ccode")
                      or "")
        if said_cc == "JPN":
            box = dict(_rules.discipline_of("league:J1") or {})
            said_jpn = (f" · ⚠️ 리그 열쇠가 `{league}`(일본 · ccode JPN)라 **J1 "
                        f"공시를 빌려 붙였다**(공시는 리그를 가리지 않는다)")
    if not box or "data.j-league.or.jp" not in str(box.get("url") or ""):
        return {"asked": False, "n": 0, "why": "", "add": {}}
    if _cas.mode() == _cas.REPLAY:
        return {"asked": True, "n": 0, "add": {},
                "why": ("⏸ **재생에서는 안 받는다** — 공시는 **현재 값**이다"
                        "(L2) · 주소는 표에 있다")}
    from app.collect import jl_official as _jo
    rows, why = await _jo.fetch_suspensions(net)
    if not rows:
        return {"asked": True, "n": 0, "add": {}, "why": f"🔴 {why}"}
    at = getattr(ref, "kickoff_utc", None)
    if at is None:
        return {"asked": True, "n": 0, "add": {},
                "why": "🔴 킥오프가 없어 **대상 경기를 못 맞춘다**"}
    from datetime import timedelta
    day = (at + timedelta(hours=9)).strftime("%-m/%-d")
    add: dict[str, list] = {}
    n = 0
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        name = str(getattr(ref, f"{side}_name", "") or "")
        from app.core import discover as _d
        said, why2 = _jo.for_match(rows, team_names=list(_d.aliases_of(name)),
                                   day=day)
        del why2
        for one in said:
            # 🔴 스키마가 이 통로를 **이미 알고 있었다** — `source="discipline"`
            #    (`reason="suspension"`). ⚠️ 없는 칸(`hard`·`note`)을 지어내지
            #    않는다 — 사유는 `why` 에 적는다.
            add.setdefault(key, []).append(Missing(
                name=str(one["player"]), reason="suspension",
                source="discipline", source_url=_jo.SUSPEND,
                why=(f"J리그 출장정지 공시 · {one['kind']} · "
                     f"{str(one['match'])[:40]}")))
            n += 1
    return {"asked": True, "n": n, "add": add,
            "why": ((f"출장정지 공시 **{n}명**(공시 {len(rows)}줄 · 대상 "
                     f"{day} · 주소 {_jo.SUSPEND})" if n
                     else f"⬜ 공시 {len(rows)}줄에 **이 경기({day}) 선수가 "
                          f"없다**") + said_jpn)}


def _load_of(seq: list, kickoff) -> int | None:
    """🔴 **14일 내 경기 수** — 세는 곳은 `context.row_of` 하나다(사본 금지).

    ⚠️ 날짜가 없으면 `None` 이다(0 으로 메우면 *"푹 쉬었다"* 는 거짓이 된다 · #3).
    """
    if kickoff is None or not seq:
        return None
    from app.core import context as _ctx
    rows = [{"utc": f"{x.get('date')}T00:00:00Z", "comp": "league",
             "gf": 0, "ga": 0}
            for x in seq if x.get("date")]
    if not rows:
        return None
    try:
        got = _ctx.row_of("", rows, as_of=kickoff)
    except Exception:                                       # noqa: BLE001
        return None
    return int(got.load_14d)


def _kind_of(ref, box: dict) -> str:
    """🔴 그 경기의 **대회 유형 열쇠** — 사다리의 징계 표가 이 글자를 본다.

    🔴 그 글자를 만드는 함수는 하나다(`probmodel._kind`) — 사본 금지.
    """
    from app.core import probmodel as _pm
    from app.core.schema import Facts
    try:
        # 🔴🔴 **번호를 함께 넘긴다**(실측 2026-10-13) — `comp_kind` 는
        #    *"번호가 있으면 번호가 글자를 이긴다"* 인데, 여기서 만든 **임시
        #    Facts 에 `league_id` 가 없어** 그 규칙이 돌지 못했다. 그래서 J리그
        #    컵 경기가 손 표(`league:JLC`)가 아니라 **자동 등록
        #    `league:fotmob224`** 로 떨어졌고, 그 리그의 원천 표·징계 공시가
        #    **안 붙었다**(결장 사다리 칸 3 이 "통로 없음"이라고 적었다).
        return str(_pm._kind(ref, Facts(
            standings=dict(box.get("standings") or {}),
            league_id=str(box.get("league_id") or ""))) or "")
    except Exception:                                       # noqa: BLE001
        return ""


def _gaps(*, xi: dict, missing: dict, coach: dict, box: dict,
          pos: dict, rungs: list | None = None) -> list[str]:
    """🔴🔴 **못 받은 칸을 이름으로**(축구 §2 마지막 줄 · #3 조용한 0 금지).

    > 어느 칸이든 못 받으면 `None` 과 사유. 블록 1 *"자료 한계"* 에 **칸별로** 적는다.
    """
    out: list[str] = []
    if not xi:
        out.append("XI 없음(경기 페이지에 라인업이 아직 없다)")
    elif all(v.state == "none" or not v.lineup for v in xi.values()):
        # 🔴 XI 칸은 **있는데 비어 있다**(결장·감독만 실려 왔다) — ⚠️ 이것을
        #    *"예상만"* 이라고 적으면 **없는 라인업이 있는 것처럼** 읽힌다. 실측
        #    2026-10-06: 그 오해가 IR02 에 빈 XI 를 견주게 해 거짓 변수를 냈다(②).
        out.append("오늘 XI 없음(상태 none — IR02·IR03 이 안 돈다)")
    elif all(v.state != "confirmed" for v in xi.values()):
        out.append("확정 XI 아직 없음(예상만)")
    # 🔴🔴 ① — *"결장 명단 미확보"는 **네 칸 모두 0일 때만**"* (사다리가 판정한다)
    if not missing:
        from app.core import absence as _ab
        said = {"rungs": list(rungs or [])}
        if not rungs or _ab.unknown(said):
            out.append("결장 명단 미확보 — " + (_ab.said_of(said)
                                               if rungs else "사다리를 안 돌렸다"))
    if not coach:
        out.append("감독 미확보")
    if not box.get("standings"):
        out.append("순위표 없음")
    if not box.get("recent"):
        out.append("폼 없음")
    if not box.get("h2h"):
        out.append("맞대결 없음")
    if not pos:
        out.append("선수 포지션 표 비었음(결장 유형은 다수결로 간다)")
    if not box.get("last_xi"):
        out.append("직전 경기 XI 없음(IR02·IR06 이 못 돈다)")
    if not box.get("schedule"):
        out.append("일정 없음(IR11 이 못 돈다)")
    # 🔴🔴 **포지션 분류 오류**(사용자 지시 2026-10-10 ②) — 칸별 수가 어긋났다
    for key, said in dict(box.get("pos_fault") or {}).items():
        out.append(f"{key} {said}")
    return out


def _key_of(ref: MatchRef, name: str) -> str:
    """🔴 이름 → 그 경기의 **두 열쇠 중 하나**. ⚠️ 못 가리면 빈 글자."""
    from app import teamref
    got, _why = teamref.key_of(name)
    if got in (ref.home, ref.away):
        return str(got)
    low = name.strip().lower()
    if low and low == ref.home_name.strip().lower():
        return ref.home
    if low and low == ref.away_name.strip().lower():
        return ref.away
    return ""


def _format_of(ref: MatchRef) -> tuple[str, str]:
    """🔴 경기 형식 — `scenarios.match_format` 표가 든다(사본 금지)."""
    from app import scenarios
    got, why = scenarios.match_format(round_note="",
                                      competition=ref.competition)
    return str(got), str(why)


async def _depth(ref: MatchRef, *, net: Any, search: Any,
                 state: RunState, pages: list[str] | None = None) -> list:
    """🔴🔴 **공식 깊이 소스** — 어느 어댑터가 아나는 `ingest.context_of` 가 정한다.

    ⚠️ 주소를 여기 적지 않는다(§2 · 사본 금지) — 종목마다 다른 경로를 손으로 적으면
       리그가 늘 때 한 발 늦는다. 🔴 `ingest.context_of(리그, ext_id)` 하나가 그
       라우팅의 원본이다.
    ⚠️ **어댑터가 깊이를 안 주는 리그가 있다**(KBO 는 `sources_context` 가 빈
       목록이다 — 그 API 가 예고 선발·라인업을 안 준다). 그때는 빈 목록이 **정직한
       상태**다(있는 척하는 함수를 두지 않는다 · CLAUDE.md #2).
    """
    from app.collect import ingest
    if net is None:
        return []
    fn = ingest.context_of(ref.competition, ref.id)
    raw: Any = []
    if callable(fn):
        try:
            raw = fn(ref.id)
        except Exception:                                   # noqa: BLE001
            raw = []
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **다른 출처로 확정한 축구 경기도 fotmob 깊이를 받는다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-10(제노아 vs 피오렌티나): S0 가 **fdorg 슬레이트**로
    #     확정해 `ext_id = fdorg:558588` 이었고, fotmob 깊이는 `fotmob:` 접두만
    #     받으므로 이 자리가 **빈 목록**을 냈다 → XI·폼·맞대결·순위표가 전부 0,
    #     **축0 ⬜**(백필이 예측력을 잰 유일한 축)이었다.
    #  🔴 자료가 없는 것이 아니라 **열쇠가 없었다**(#2 배선). 번호를 푸는 통로는
    #     `discover.fotmob_id` 다 — 주소·사다리를 여기 적지 않는다(사본 금지).
    #  ⚠️ **조용히 하지 않는다**(#3) — 이었는지 못 이었는지 보고에 남는다.
    if not raw and str(getattr(ref, "sport", "") or "") == "soccer":
        from app.core import discover as _disc
        try:
            mid, why = await _disc.fotmob_id(
                net, home=ref.home_name, away=ref.away_name,
                day=(ref.kickoff_utc.date() if ref.kickoff_utc else None))
        except Exception as exc:                            # noqa: BLE001
            mid, why = "", f"🔴 fotmob 번호 풀이가 죽었다 — {exc!r}"
        state.note(f"s2 깊이 — 어댑터(`{ref.id}`)가 깊이를 안 준다 → {why}")
        if mid:
            from app.collect import fotmob as _fm
            raw = _fm.sources_context(f"fotmob:{mid}")
    if not raw:
        return []
    # 🔴 **부품이 무엇을 돌려줄지 타입으로 모른다** — `Iterable` 인지 확인하고 센다.
    #    ⚠️ 모르는 것을 `list()` 에 넣으면 strict 가 맞게 막는다(그 자리가 ① 결함의
    #       뿌리다 — "받는 쪽이 꼴을 믿었다").
    srcs: list[Any] = list(raw) if isinstance(raw, (list, tuple)) else []
    out: list = []
    for src in srcs:
        url = str(getattr(src, "url", "") or "")
        parse = getattr(src, "parse", None)
        if not (url and callable(parse)):
            continue
        got = await net.get(url)
        if not getattr(got, "ok", False):
            continue
        # 🔴 §1 — **경기 페이지 본문을 모아 둔다**(조 순위표 주소를 거기서 만든다)
        if pages is not None:
            said_text = str(getattr(got, "text", "") or "")
            if said_text:
                pages.append(said_text)
        follow = getattr(src, "follow", None)
        parse_follow = getattr(src, "parse_follow", None)
        for name in (ref.home_name, ref.away_name):
            # 🔴 `cells` 를 보는 곳은 `adapt` 하나다(⑤ 정적 검사)
            q = adapt.lineup_question(ref, name)
            try:
                said = parse(got, q)
            except Exception:                               # noqa: BLE001
                continue
            if isinstance(said, (list, tuple)):
                out += list(said)
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **직전 경기를 한 번 따라간다**(사용자 지시 2026-10-06(3차) ⑦)
            # ══════════════════════════════════════════════════════════
            #
            #  > 경기 페이지의 직전 경기 링크를 **한 번 따라가** `last_xi`·`schedule`
            #  > 칸을 채운다(IR02·IR06·IR11용).
            #
            #  ⚠️ 파서는 동기 함수라 망에 못 간다 — 그래서 **여기서** 열고 그쪽 파서
            #     (`parse_follow`)에 넘긴다(옛 세포가 하던 일이다 · §6 부품 재사용).
            #  🔴 **한 팀에 하나, 한 번만** 연다 — 열기 예산은 비싸다(§4-6).
            out += await _follow_once(src, got, q, name, net=net, state=state,
                                      follow=follow,
                                      parse_follow=parse_follow)
    return out


async def _follow_once(src: Any, got: Any, q: Any, team: str, *, net: Any,
                       state: RunState, follow: Any,
                       parse_follow: Any) -> list:
    """🔴🔴 그 팀의 **직전 경기 최대 5개**를 따라가 평소 XI·일정 재료를 받는다(⑦).

    ══════════════════════════════════════════════════════════════════
    🔴 **다섯으로 늘렸다** — 사용자 승인 2026-10-06(5차) ②
    ══════════════════════════════════════════════════════════════════

    > 경기 페이지에서 직전 경기 링크를 **최대 5개까지** 따라가 평소 XI 를 만든다.
    > **경기당 추가 fetch 상한 5**, 캐시 **하루**.

    ⚠️ 종전에는 하나만 따라갔다 — 그래서 §4-1(평소 XI 최소 3경기)이 ② 를 늘
       건너뛰게 했다(카드에 *"표본 1경기"* 가 찍혔다).
    🔴 **캐시가 하루**다(`_day_cache`) — 재분석이 같은 다섯 쪽을 다시 받지 않는다.
    ⚠️ 못 열거나 파서가 없으면 **빈 목록 + 사유**다 — 조용히 0 을 내지 않는다(#3).
    """
    if not (callable(follow) and callable(parse_follow)):
        state.note(f"s2 ⑦ `{team}` 직전 경기 — 어댑터가 따라가기를 안 준다")
        return []
    try:
        # 🔴 그 부품이 무엇을 돌려줄지 **타입으로 모른다** — 목록인지 보고 센다
        raw = follow(got, q)
        urls = ([str(u) for u in raw if str(u).strip()]
                if isinstance(raw, (list, tuple)) else [])
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2 ⑦ `{team}` 링크 뽑기 실패 — {exc!r}")
        return []
    if not urls:
        state.note(f"s2 ⑦ `{team}` 직전 경기 링크가 페이지에 없다")
        return []
    out: list = []
    spent = 0
    for url in urls[:FOLLOW_CAP]:
        if spent >= FOLLOW_CAP:
            state.note(f"s2 ⑦ `{team}` fetch 상한 {FOLLOW_CAP} 에 닿았다")
            break
        page = await _day_page(net, str(url), state=state, team=team)
        spent += 1
        if page is None:
            continue
        try:
            said = parse_follow(page, q)
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s2 ⑦ `{team}` 직전 경기 파싱 실패 — {exc!r}")
            continue
        rows = list(said) if isinstance(said, (list, tuple)) else []
        out += rows
        state.note(f"s2 ⑦ `{team}` 직전 경기({str(url)[-40:]}) → 사실 {len(rows)}건")
    state.note(f"s2 ⑦ `{team}` 직전 경기 {spent}쪽 따라갔다(상한 {FOLLOW_CAP}) → "
               f"사실 {len(out)}건")
    return out


async def _day_page(net: Any, url: str, *, state: RunState, team: str):
    """🔴 **하루 캐시**로 한 쪽 받는다(승인 ②). ⚠️ 못 받으면 `None` + 사유.

    🔴 캐시는 `var/follow/{날짜}/{해시}.html` 다 — 재분석·두 번째 회차가 같은 다섯
       쪽을 다시 받지 않는다. ⚠️ **날짜가 바뀌면 새로 받는다**(그 쪽의 사실이 바뀐다).
    """
    import hashlib

    day = datetime.now(timezone.utc).date().isoformat()
    box = FOLLOW_DIR / day
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    mine = box / f"{key}.html"
    if mine.is_file():
        state.note(f"s2 ⑦ `{team}` 하루 캐시 적중 — {url[-40:]}")
        return _Page(url=url, text=mine.read_text(encoding="utf-8"), ok=True)
    try:
        page = await net.get(url)
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2 ⑦ `{team}` 직전 경기 열기 실패 — {exc!r}")
        return None
    if not getattr(page, "ok", False):
        state.note(f"s2 ⑦ `{team}` 직전 경기 열기 실패 — 상태 "
                   f"{getattr(page, 'status', '?')}")
        return None
    try:
        box.mkdir(parents=True, exist_ok=True)
        mine.write_text(str(getattr(page, "text", "") or ""), encoding="utf-8")
    except OSError as exc:
        state.note(f"s2 ⑦ 하루 캐시를 못 적었다 — {exc}")
    return page


async def _fill_official(ref: MatchRef, box: dict, *, state: RunState,
                         net: Any) -> None:
    """🔴🔴 A-1 ③ — **리그 공식 출처**에서 받을 수 있는 것을 받는다.

    🔴 사다리에 `kleague_official` 이 있는 리그만 돈다(표가 정한다). ⚠️ 선발을
       주는 칸은 실측으로 **아직 없다** — 그래서 여기서 받는 것은 **일정·구단
       공식 SNS·타임라인**이고, 그 사실이 `box["official"]` 에 남는다.
    ⚠️ 실패해도 **분석을 막지 않는다**(곁딸린 사실이다).
    """
    from app.core import competition as _comp
    from app.core import lineups as _ln
    key, _why = _comp.key_of(competition=str(ref.competition or ""))
    ids = [str(x.get("id")) for x in _ln.ladder(key)]
    if "kleague_official" not in ids:
        return
    from app.collect import kleague as _kl
    when = ref.kickoff_utc
    if when is None:
        return
    got = await _kl.official_schedule(net, year=when.year, month=when.month)
    if not got.get("games"):
        state.note(f"s2 A-1 K리그 공식 — 일정을 못 받았다({got.get('why')})")
        return
    row = _kl.official_find(got["games"], home=ref.home_name,
                            away=ref.away_name)
    if not row:
        state.note("s2 A-1 K리그 공식 — 일정에서 이 경기를 못 찾았다"
                   f"(일정 {len(got['games'])}줄)")
        return
    said = {"game_id": row.get("gameId"), "meet_seq": row.get("meetSeq"),
            "round": row.get("roundId"), "status": row.get("gameStatus"),
            "field": row.get("fieldNameFull") or row.get("fieldName")}
    # 🔴 **구단 공식 SNS**(사용자가 SNS 수집을 허용했다) — 주소를 공식 API 가 준다
    sns: dict[str, dict] = {}
    for c in got.get("clubs") or []:
        nm = str(c.get("teamName") or "")
        if nm and (nm in ref.home_name or nm in ref.away_name
                   or str(c.get("teamNameShort") or "") in
                   (row.get("homeTeamName"), row.get("awayTeamName"))):
            sns[nm] = {k: c.get(k) for k in
                       ("clubInstagram", "clubTwitter", "clubFacebook",
                        "homepage") if c.get(k)}
    if sns:
        said["club_sns"] = sns
    pl = await _kl.official_players(net, year=when.year,
                                   meet_seq=int(row.get("meetSeq") or 1),
                                   game_id=int(row.get("gameId") or 0))
    said["players_why"] = pl.get("why")
    if pl.get("home") or pl.get("away"):
        said["players"] = {"home": pl["home"], "away": pl["away"]}
    tl = await _kl.official_timeline(net, year=when.year,
                                     meet_seq=int(row.get("meetSeq") or 1),
                                     game_id=int(row.get("gameId") or 0))
    if tl:
        said["timeline_rows"] = (len(tl.get("firstHalf") or [])
                                 + len(tl.get("secondHalf") or []))
        said["scorers"] = {"home": tl.get("homeScorer") or [],
                           "away": tl.get("awayScorer") or []}
    box["official"] = said
    state.note(f"s2 A-1 K리그 공식 — gameId {said['game_id']} · 선발 "
               f"{'받았다' if said.get('players') else '못 받았다'}"
               f"({said['players_why']}) · 구단 SNS {len(sns)}곳")


async def _fill_capture(ref: MatchRef, box: dict, xi: dict, *,
                        state: RunState, net: Any, pages: list[str]) -> None:
    """🔴🔴 **사람이 준 라인업 글 → 확정 XI**. 글이 없으면 아무것도 안 한다.

    글은 `box["xi_capture"]` 에 있다(입구가 넣는다 — `{"home": 글, "away": 글}`).
    🔴 **등번호로 잇는다** — 번호표는 경기 페이지(없으면 직전 경기)가 준다.
    ⚠️ 상태는 `confirmed` 이고 출처는 **`user_capture`** 로 남긴다 — 카드가 그
       사실을 적는다(fotmob 이 줬다고 말하지 않는다).
    """
    said = dict(box.get("xi_capture") or {})
    if not said:
        return
    from app.collect import fotmob as fm
    from app.core import xicapture as _cap
    nums: dict = {}
    for text in pages:
        got = fm.squad_numbers(fm.payload(text) or {})
        for side, table in got.items():
            nums.setdefault(side, {}).update(table)
    for side in ("home", "away"):
        text = str(said.get(side) or "")
        if not text.strip():
            continue
        rows = _cap.parse(text)
        if len(rows) < 11:
            state.note(f"s2 캡처 XI({side}) — 🔴 줄이 {len(rows)}개다(11 미만) "
                       f"— 쓰지 않는다")
            continue
        key = str(getattr(ref, side))
        one, why = _cap.to_xi(rows, nums.get(side) or {}, team=key,
                              formation=_cap.formation_of(text))
        xi[key] = one
        state.note(f"s2 캡처 XI({side}) — {why}")
        logger.info("[s2] 사람이 준 라인업(%s) — %s", side, why)


async def _auto_register(ref: MatchRef, box: dict, *, state: RunState,
                         net: Any, pages: list[str]) -> None:
    """🔴🔴 **리그 자동 등록은 분석마다 걸린다** — 사용자 결정 2026-10-10 §2.

    > 경기를 찾으면 그 경기의 리그 id로 자동 등록을 건다(**이미 있으면 갱신만**).

    ⚠️ 실사고 2026-10-10 ①: `findgame` 에만 걸어 뒀더니 **표에 이미 있는 경기**는
       등록이 안 걸렸다 — 엘살바도르 경기 재실행에서 카드가 대회를 **라리가**로
       판정했고 경고조차 없었다(이름이 나라를 넘어 겹친다).
    ⚠️ 실사고 2026-10-10 ②: 이 일을 `_fill_form`(폼 보완) **안에** 뒀더니
       **컵대회에서 안 걸렸다** — 그 함수는 리그 표 주소가 없으면 일찍 돌아가고,
       호주컵은 순위표가 없다. 🔴 그래서 **자기 함수**다. 한 함수가 두 일을 하면
       한쪽의 퇴로가 다른 쪽을 삼킨다.
    🔴 리그 id·나라 코드는 **`general`** 에서 읽는다 — 순위표 칸(`content.table`)은
       컵대회에서 `False` 다(실측). `general` 은 둘 다 준다(`9471`·`AUS`).
    🔴 하루 한 번만 받는다(`discover.register` 안의 신선도 검사).
    """
    from app.collect import fotmob as fm
    from app.core import discover
    j = next((fm.payload(x) for x in pages if fm.payload(x)), None) or {}
    lid = fm.league_id_of(j)
    if not lid:
        state.note("s2 자동 등록 — 🔴 경기 페이지가 리그 id 를 안 준다")
        return
    # 🔴🔴 **번호를 사실에 담는다** — 대회 판정이 글자로만 가지 않게(실사고 두 번)
    box["league_id"] = str(lid)
    _box, why = await discover.register(
        net, league_id=lid, league_name=str(ref.competition or ""),
        ccode=fm.ccode_of(j))
    state.note(f"s2 자동 등록 — {why}")
    logger.info("[s2] 자동 등록 — %s", why)


async def _fill_form(ref: MatchRef, box: dict, *, state: RunState, net: Any,
                     pages: list[str]) -> None:
    """🔴🔴 §2 — **폼·총골·핵심 선수**를 보완한다. ⚠️ `box` 를 제자리에서 채운다.

    🔴 셋 다 **리그 표에서 시작한다** — 팀 번호가 거기 있다(우리가 짓지 않는다).
    ⚠️ 하나라도 못 받으면 그 사실을 `gaps` 가 이름으로 남긴다(#3) — 그리고 블록 3
       의 셋이 비면 카드 머리에 *"자료 부족 카드"* 가 붙는다(§2 마지막 줄).
    """
    from app.collect import fotmob as fm
    # ① 리그 표 페이지 — 팀 번호·경기당 총골이 거기 있다
    url = None
    for text in pages:
        j = fm.payload(text)
        if j:
            url = fm.league_table_url(j)
            if url:
                break
    if not url:
        state.note("s2 §2 폼 보완 — 리그 표 주소를 못 만들었다(어댑터가 안 준다)")
        return
    page = await _day_page(net, url, state=state, team="폼 보완")
    tj = fm.payload(getattr(page, "text", "") or "") if page is not None else None
    if not tj:
        state.note("s2 §2 폼 보완 — 리그 표 페이지를 못 받았다")
        return
    ids = fm.team_ids(tj)
    totals = fm.team_totals(tj)
    want = {ref.home_name: ref.home, ref.away_name: ref.away}
    got_tot = {key: totals[name] for name, key in want.items() if name in totals}
    if got_tot:
        std = box.setdefault("standings", {})
        std["team_totals"] = got_tot
        # 🔴🔴 **이 경기의 총골 기준**(§3 총골 기준 층) — 두 팀 평균이다
        vals = [float(v["total_per_game"]) for v in got_tot.values()]
        if len(vals) == 2:
            std["match_total_baseline"] = round(sum(vals) / 2, 3)
            # 🔴🔴 **표본(경기 수)도 싣는다**(수정 지시 2026-10-13 4번) —
            #    ⚠️ 실사고: 상하이–대전 카드가 **ACL 리그 단계 2경기**로 센 두 팀
            #       총골 **5.5** 를 λ 바닥으로 썼다(대회 실측 2.82의 1.95배).
            #       그 칸이 **표본을 안 들고 있어** 받는 쪽이 수축을 못 했다.
            #    🔴 두 팀 중 **적게 치른 쪽**의 경기 수다(둘 다 많아야 믿는다).
            std["match_total_played"] = int(min(
                int(v.get("played") or 0) for v in got_tot.values()))
            state.note(f"s2 §3 경기당 총골 — "
                       + " · ".join(f"{n} {totals[n]['total_per_game']}"
                                    f"({totals[n]['played']}경기)"
                                    for n in want if n in totals)
                       + f" → 이 경기 기준 {std['match_total_baseline']}"
                       f"(표본 {std['match_total_played']}경기)")
    else:
        state.note("s2 §2 경기당 총골 — 리그 표에 두 팀이 없다")
    # ② 폼 — **비었을 때만** 팀 페이지를 받는다
    if not box.get("recent"):
        for name, key in want.items():
            tid = ids.get(name)
            if tid is None:
                state.note(f"s2 §2 폼 보완 — `{name}` 팀 번호를 못 찾았다")
                continue
            tp = await _day_page(net, fm.team_fixtures_url(tid, "x"),
                                 state=state, team=f"{name} 팀 페이지")
            if tp is None:
                continue
            # 🔴🔴 `as_of` 는 **필수 인자**다(사용자 지시 2026-10-12 ⓐ) —
            #    ⚠️ 실사고 2026-10-13(이스트 벵골–알쇼르타): 이 자리가 그것을
            #       안 넘겨 `TypeError` 로 **카드가 통째로 터졌다**. 이 길은
            #       `recent` 가 비었을 때만 도는 **퇴로**라서 J1·K1 카드에서는
            #       한 번도 안 지났다(리그 표가 폼을 줬다).
            rows = fm.team_recent(getattr(tp, "text", "") or "", tid, n=5,
                                  as_of=ref.kickoff_utc,
                                  before=ref.kickoff_utc)
            if not rows:
                continue
            box.setdefault("recent", {})[key] = _recent_of(
                rows, kickoff=ref.kickoff_utc)
            state.note(f"s2 §2 폼 보완 — `{name}` 최근 {len(rows)}경기 "
                       f"← 팀 페이지(대회 섞임: "
                       f"{sorted({r['tournament'] for r in rows})})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ① **폼도 상성과 같은 목록에서 센다** — 사용자 지시 2026-10-11 ①
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 목록을 만드는 함수는 **상성의 그것**이다(`s2e_matchup._history` +
    #     `games_of`) — 사본을 만들지 않는다(#1). ⚠️ 그 통로는 **하루 캐시**를
    #     쓰므로(`_day_page`) 상성이 뒤에 같은 쪽을 다시 받지 않는다.
    #  ⚠️ 목록을 못 받으면 **옛 칸을 그대로 둔다**(있는 수를 지우지 않는다 · #3).
    from app.core.stages.s2e_matchup import _history as _hist
    from app.core.stages.s2e_matchup import games_of as _games_of
    for name, key in want.items():
        # 🔴🔴 **L1 누설 금지** — 이 통로도 **킥오프 이전**만 본다.
        #    ⚠️ 실사고 2026-10-12(광주–울산 as-of 재현): `as_of` 를 **안 넘겨**
        #       `TypeError` 로 터졌다 — 게이트를 필수 인자로 만든 뒤 이 자리를
        #       안 고쳤다. 🔴 터져서 보인 것이 다행이다(조용히 새지 않았다).
        rows = await _hist(net, name, state=state, as_of=ref.kickoff_utc,
                           ref=ref)
        made = _games_of(rows or [])
        if not made:
            state.note(f"s2 ① 폼 한 원천 — `{name}` 경기 목록을 못 받았다"
                       f"(옛 폼 칸을 그대로 둔다)")
            continue
        old_box = dict((box.get("recent") or {}).get(key) or {})
        box.setdefault("recent", {})[key] = {
            **old_box, **_recent_from_games(made, kickoff=ref.kickoff_utc)}
        state.note(f"s2 ① 폼 한 원천 — `{name}` {len(made)}경기 목록에서 "
                   f"두 창을 잘랐다(상성과 같은 목록)")
    # ③ 핵심 선수 — 리그 통계 페이지 + 전체 목록
    lid = str((((fm._page(fm.payload(pages[0]) or {}).get("content") or {})
                .get("table") or {}).get("parentLeagueId")) or "") if pages else ""
    if not lid:
        return
    sp = await _day_page(net, fm.league_stats_url(lid, "x"), state=state,
                         team="리그 득점 순위")
    if sp is None:
        return
    all_url = fm.key_players_url(getattr(sp, "text", "") or "")
    ap = await _day_page(net, all_url, state=state,
                         team="득점+도움 전체") if all_url else None
    for name, key in want.items():
        tid = ids.get(name)
        if tid is None:
            continue
        got = (fm.key_players_all(getattr(ap, "text", "") or "", team_id=tid, n=2)
               if ap is not None else [])
        if not got:
            got = fm.key_players(getattr(sp, "text", "") or "", team_id=tid, n=2)
        if got:
            box.setdefault("standings", {}).setdefault("key_players", {})[key] = got
            state.note(f"s2 §2 핵심 선수 — `{name}` "
                       + " · ".join(f"{x['name']} {x['value']}" for x in got))


async def _fill_squad(ref: MatchRef, box: dict, *, state: RunState, net: Any,
                      ) -> None:
    """🔴🔴 **선수단 페이지 → 선수별 시즌 기록**(최종 평 §1-1 *"비교 수치"*).

    🔴 왜 필요한가: `standings["key_players"]` 는 팀마다 **상위 2명**뿐이다. 그래서
       교체로 들어온 선수의 수를 **한 명도 못 댔다**(실측 2026-10-10). 선수단
       페이지는 **전원**의 시즌 득점·도움·레이팅·나이·키·부상을 준다.
    🔴 통신은 **팀당 한 번**이고 하루 캐시다(`_day_page`). ⚠️ `/api/*` 가 아니다.
    ⚠️ 못 받으면 **빈 표**이고 사유를 남긴다(#3) — 사실 묶음이 `없음` 으로 적는다.
    """
    from app.collect import fotmob as fm
    from app.core import discover as _d
    try:
        idx = await fm.team_index(net)
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2 선수단 기록 — 🔴 팀 색인을 못 받았다({exc!r})")
        return
    out: dict[str, dict] = {}
    # 🔴 ③ — **팀별로도** 담는다(공격 기여 비중의 분모가 한 팀이어야 한다)
    mine: dict[str, dict] = {}
    for name, key in ((str(ref.home_name or ""), str(ref.home or "")),
                      (str(ref.away_name or ""), str(ref.away or ""))):
        # 🔴🔴 **등급을 가린다**(여자팀·2군) — 규율은 `discover.pick_team` 하나다
        got_pick = await _d.pick_team(net, name, ref=ref, state=state,
                                      page_of=_day_page)
        if not got_pick:
            state.note(f"s2 선수단 기록 — `{name}` 을 팀 색인에서 못 찾았다")
            continue
        tid, slug = got_pick
        page = await _day_page(net, fm.squad_url(tid, slug), state=state,
                               team=f"{name} 선수단")
        got = (fm.squad_stats(getattr(page, "text", "") or "")
               if page is not None else {})
        if not got:
            state.note(f"s2 선수단 기록 — `{name}` 선수단 페이지가 비었다")
            continue
        out.update(got)
        if key:
            mine[key] = dict(got)
        state.note(f"s2 선수단 기록 — `{name}` {len(got)}명 · 득점+도움 합 "
                   + str(sum(int(v.get("goals") or 0)
                             + int(v.get("assists") or 0)
                             for v in got.values())))
    if out:
        box["player_stats"] = out
    if mine:
        box["player_stats_team"] = mine


def _recent_from_games(games: list[dict], *, kickoff=None) -> dict:
    """🔴🔴 ① — **상성이 쓰는 그 경기 목록**으로 `facts.recent` 를 만든다.

    > 한 원천(같은 경기 목록)에서 두 창을 자른다. — 사용자 지시 2026-10-11 ①

    ⚠️ 실측 2026-10-11(재현 1회차): 카드 블록 3 은 밴쿠버 **최근5 실 8**(1.60)을
       적었는데 같은 카드의 `S01-away` 는 **실점 평균 2.0** 이었다 — 폼이
       *또 다른 파서*(fotmob 폼 블록·`team_recent`)에서 왔기 때문이다. 🔴 그래서
       S01 이 읽는 이 칸도 **그 목록**에서 센다.

    🔴 평균은 **최근 5경기**다(카드 블록 3·S01 글자가 말하는 그 창) — 목록 전체
       (10경기)는 `games` 로 함께 둔다. 창을 세는 함수는 `form.window_sums` 하나다.
    """
    from app.collect import fotmob as _fm
    from app.core import form as _form
    rows = [dict(g) for g in (games or [])]
    five = _form.window_sums(rows, 5)
    # 🔴🔴 **칸 이름과 순서를 `fotmob.parse_form` 과 맞춘다**(사본 금지의 반대쪽
    #    함정): ⚠️ 실측 2026-10-11 — 내가 `conceded` 로만 적었더니 `s5_verify.
    #    _form_goal_dirs` 가 읽는 `goals_against` 가 없어 **실점 방향이 조용히
    #    사라졌다**(#3 — 못 잰 칸은 이름으로 남아야 하는데 칸 자체가 없어졌다).
    # 🔴 순서는 **최신이 앞**이다(`team_recent`·`parse_form` 이 그 순서다 —
    #    연속 계산이 그것을 쓴다). ⚠️ `games` 는 반대로 **오래된 것이 앞**이고
    #    창은 꼬리에서 자른다.
    seq = [{"date": g.get("date"), "side": g.get("side"),
            "opponent": g.get("opp"),
            "tournament": g.get("league") or "",
            "goals_for": int(g.get("gf") or 0),
            "goals_against": int(g.get("ga") or 0),
            "result": ("W" if float(g.get("gf") or 0) > float(g.get("ga") or 0)
                       else "L" if float(g.get("gf") or 0)
                       < float(g.get("ga") or 0) else "D"),
            "score": f"{int(g.get('gf') or 0)}-{int(g.get('ga') or 0)}",
            # 🔴 옛 칸 이름도 남긴다(`_recent_of` 를 읽던 자리)
            "scored": float(g.get("gf") or 0.0),
            "conceded": float(g.get("ga") or 0.0)}
           for g in rows[-5:][::-1]]
    got = [float(g.get("gf") or 0.0) for g in rows[-5:]]
    trimmed, _why = _fm.trimmed_avg(got) if got else (None, "")
    rest = None
    if kickoff is not None and seq:
        from datetime import date as _date
        try:
            last = max(_date.fromisoformat(str(x["date"])) for x in seq
                       if x.get("date"))
            rest = (kickoff.date() - last).days
        except (ValueError, TypeError, AttributeError):
            rest = None
    n = int(five["n"])
    return {
        # 🔴 승패 글자는 **득실로 센다**(다른 파서의 글자를 베끼지 않는다)
        "last5": [x["result"] for x in seq],
        # 🔴🔴 **연패**(사용자 지시 2026-10-11) — *"연패한 팀일수록 승리에 더
        #    간절하다"* 를 가설에 넣으려면 그 수가 있어야 한다.
        #  🔴 **최신부터 연속**인 것만 센다(가운데 무승부·승리에서 끊긴다).
        #  ⚠️ `seq` 는 최신이 앞이다 — 그 순서를 쓴다.
        "streak_losing": next(
            (i for i, x in enumerate(seq) if x["result"] != "L"), len(seq)),
        "matches": n,
        "sequence": seq,
        "rest_days": rest,
        # 🔴🔴 **§5-2 — 14일 내 경기 수**(통합 지시서 2026-10-13 밤 셋째).
        #  🔴 세는 곳은 `context.row_of` **하나**다(사본 금지) — 카드가 그 수를
        #     적고 **확률은 안 바뀐다**(§5-2: *"확률 불변"*).
        "load_14d": _load_of(seq, kickoff),
        "recent_scored_avg": (round(five["gf"] / n, 3) if n else None),
        "recent_trimmed_avg": trimmed,
        "recent_conceded_avg": (round(five["ga"] / n, 3) if n else None),
        # 🔴 ① 목록 자체 — 카드 블록 3 과 축1 이 **같은 줄**을 본다
        "games": rows,
        "windows": {str(w): _form.window_sums(rows, w) for w in _form.WINDOWS},
        "source": "fotmob 팀 일정 + 경기 페이지(상성과 같은 목록)"}


def _recent_of(rows: list[dict], *, kickoff=None) -> dict:
    """🔴 팀 페이지 줄들 → `facts.recent` 꼴. ⚠️ 칸 이름을 경기 페이지와 맞춘다.

    🔴 그래야 `s5_verify` 의 폼 변수(S01)가 **분기 없이** 읽는다(#1 사본 금지).
    ⚠️ 대회가 섞여 있다(리그·컵·ACL) — 그 글자를 `sequence` 에 남겨 카드가 적는다.
    """
    # 🔴 `trimmed_avg` 는 **`fotmob` 이 든다**(`league` 가 아니다 — 추측해 쓰면
    #    터진다 · 실사고 2026-10-09: `AttributeError: module 'app.league' has no
    #    attribute 'trimmed_avg'` 로 카드가 통째로 죽었다).
    from app.collect import fotmob as _fm
    seq = [{"date": r["date"], "side": r["side"], "score": r["score"],
            "opponent": (r["away"] if r["side"] == "home" else r["home"]),
            "tournament": r["tournament"],
            "scored": (r["home_score"] if r["side"] == "home"
                       else r["away_score"]),
            "conceded": (r["away_score"] if r["side"] == "home"
                         else r["home_score"])}
           for r in rows]
    got = [float(x["scored"]) for x in seq]
    con = [float(x["conceded"]) for x in seq]
    trimmed, _why = _fm.trimmed_avg(got) if got else (None, "")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **휴식일을 센다**(실측 2026-10-09 강원) — 직전 경기와 킥오프의 차
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `휴식 못 쟀다` 로 비었다. 🔴 그런데 강원은 직전 경기가 **09-27**
    #     이고 이 경기가 10-09 다 — **12일 공백**(A매치 휴식기)이 이 경기의 사실이다.
    #     그 수를 비워 두면 IR11(일정 과부하)도 반대쪽(장기 휴식)도 못 센다.
    #  🔴 날짜만 있으므로 **일 단위**다(시각을 지어내지 않는다).
    rest = None
    if kickoff is not None and seq:
        from datetime import date as _date
        try:
            last = max(_date.fromisoformat(str(x["date"])) for x in seq
                       if x.get("date"))
            rest = (kickoff.date() - last).days
        except (ValueError, TypeError, AttributeError):
            rest = None
    return {"last5": [r["result"] for r in rows],
            "sequence": seq,
            "rest_days": rest,
            "load_14d": _load_of(seq, kickoff),
            "recent_scored_avg": round(sum(got) / len(got), 3) if got else None,
            "recent_trimmed_avg": trimmed,
            "recent_conceded_avg": round(sum(con) / len(con), 3) if con else None,
            "source": "fotmob 팀 페이지(대회 섞임)"}


async def _group(ref: MatchRef, *, state: RunState, net: Any,
                 pages: list[str]) -> dict:
    """🔴🔴 §1 — **같은 조 순위표 + 조 전체 일정**. ⚠️ 못 받으면 빈 표(지어내지 않는다).

    > 등록·미등록 대회 **모두**: 경기 페이지의 같은 조 순위표를 `Facts.standings` 로.
    > 잔여 경기 · **같은 라운드 다른 경기의 킥오프 시각**도 받는다.

    🔴 순위표는 **리그 표 페이지**에 있다(경기 페이지의 `content.table` 은 id 만 든다).
       `fotmob.league_table_url()` 이 그 주소를 만들고, **하루 캐시**로 한 번만 받는다.
    ⚠️ fotmob 이 아닌 어댑터에는 이 길이 없다 — 그때는 빈 표이고 카드가 `unknown` 이다.
    """
    from app.collect import fotmob as fm
    for text in pages:
        j = fm.payload(text)
        if not j:
            continue
        url = fm.league_table_url(j)
        if not url:
            continue
        page = await _day_page(net, url, state=state, team="조 순위표")
        if page is None:
            return {}
        tj = fm.payload(getattr(page, "text", "") or "")
        if not tj:
            return {}
        names = [ref.home_name, ref.away_name]
        table = fm.group_table(tj, names)
        if not table:
            state.note(f"s2 §1 조 순위표 — 두 팀({names})이 든 표를 못 찾았다")
            return {}
        rows = [str(r.get("name") or "") for r in table.get("rows") or []]
        fixtures = fm.group_fixtures(tj, rows)
        left = [f for f in fixtures if not f.get("finished")]
        table["fixtures"] = fixtures
        table["remaining"] = len(left)
        table["source_url"] = url
        state.note(f"s2 §1 조 순위표 `{table.get('group')}` {len(rows)}팀 · 일정 "
                   f"{len(fixtures)}경기(남은 {len(left)}) ← {url}")
        return table
    state.note("s2 §1 조 순위표 — 경기 페이지에서 표 주소를 못 만들었다(어댑터가 안 준다)")
    return {}


def _venue(pages: list[str]) -> dict:
    """🔴 경기 페이지들에서 **구장 좌표**를 한 번 읽는다(IR11 · 7차 §6)."""
    from app.collect import fotmob as fm
    for text in pages:
        j = fm.payload(text)
        if not j:
            continue
        got = fm.venue_of(j)
        if got:
            return got
    return {}
