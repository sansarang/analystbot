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
              search: Any = None) -> Facts:
    """🔴 그 경기의 구조 사실. ⚠️ 실패해도 **빈 `Facts`** 를 돌려준다(§5)."""
    box: dict[str, Any] = {}
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
    # 🔴 XI 는 **결장 명단을 보고** 만든다(예상 명단에 결장자가 있으면 뺀다 · §2)
    for key, val in raw_xi.items():
        xi[key] = adapt.xi_of(key, val, source_url=str(val.get("source_url") or ""),
                              missing=missing.get(key))
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
            if p.pos:
                pos[p.name] = p.pos
    # 🔴🔴 **과거 경기에서도 포지션을 모은다**(사용자 지시 2026-10-06(6차) ③)
    #
    #  ⚠️ 실측 2026-10-06: 오늘 XI 가 없는 경기에서는 포지션 표가 **통째로 비어** ②
    #     기여표가 센터백과 공격수를 짝지었다. 🔴 같은 선수의 포지션은 직전 경기
    #     페이지에 **이미 있다**(`players_of` 가 `usualPlayingPositionId` 를 읽는다).
    for rows in past.values():
        for box_xi in rows:
            for p in box_xi.lineup:
                if p.pos:
                    pos.setdefault(p.name, p.pos)
    for rows in missing.values():
        for m in rows:
            if m.pos and m.name not in pos:
                pos[m.name] = m.pos
    # 🔴 **형식은 표가 정한다**(대회명·라운드) — 모르면 `unknown`(지어내지 않는다)
    fmt, why = _format_of(ref)
    state.note(f"s2 형식 — {why}")
    gaps = _gaps(xi=xi, missing=missing, coach=coach, box=box, pos=pos)
    if gaps:
        state.note("s2 못 받은 칸 — " + " · ".join(gaps))
    return adapt.facts_of(box, xi=xi, match_format=fmt,
                          sources=sorted(set(sources)), missing=missing,
                          coach=coach, player_pos=pos, gaps=gaps, squad=squad,
                          player_value=values, past_xi=past)


def _gaps(*, xi: dict, missing: dict, coach: dict, box: dict,
          pos: dict) -> list[str]:
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
    if not missing:
        out.append("결장 명단 미확보")
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
    if not callable(fn):
        return []
    try:
        raw = fn(ref.id)
    except Exception:                                       # noqa: BLE001
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
            state.note(f"s2 §3 경기당 총골 — "
                       + " · ".join(f"{n} {totals[n]['total_per_game']}"
                                    for n in want if n in totals)
                       + f" → 이 경기 기준 {std['match_total_baseline']}")
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
            rows = fm.team_recent(getattr(tp, "text", "") or "", tid, n=5,
                                  before=ref.kickoff_utc)
            if not rows:
                continue
            box.setdefault("recent", {})[key] = _recent_of(
                rows, kickoff=ref.kickoff_utc)
            state.note(f"s2 §2 폼 보완 — `{name}` 최근 {len(rows)}경기 "
                       f"← 팀 페이지(대회 섞임: "
                       f"{sorted({r['tournament'] for r in rows})})")
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
