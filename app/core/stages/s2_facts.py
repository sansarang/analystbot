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
    try:
        got = await _depth(ref, net=net, search=search, state=state)
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
                box.setdefault("schedule", {}).setdefault(key, {
                    "last_match": val.get("from_date"),
                    "last_opponent": val.get("from_match"),
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
                 state: RunState) -> list:
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
