"""🔴🔴 **s2e — 상성 세 축**. 사용자 지시 2026-10-10(셋째).

> 엔진의 질문은 하나다 — *"이 팀이 오늘 이 라인업으로 이 상대를 이길 수 있나"*.
> 답은 세 겹: **축1 보정 폼** · **축2 전술 상성** · **축3 골 내용 상성**.

🔴 이 단계가 하는 일: 세 축의 **수를 모으고 규칙을 발동**한다. 확률 이동은
   `compare.our_prob`(③)과 `goals`·`strategy` 의 이동량이 한다.
🔴 **골 타임라인은 경기 페이지마다 한 번** 받는다 — 두 팀 × 최근 10경기 = 최대
   20번이다. ⚠️ 그 수는 그대로 통신 수이므로 **하루 캐시**를 쓴다(`_day_page`).
🔴 축2(전술 상성 T1~T8)는 **스타일 프로필 6축**이 필요하다 — 그 자료(점유율·
   패스·압박 지표)를 받는 통로가 아직 없다(실측 2026-10-10). 그래서 지금은
   **축1·축3 만** 돌고 그 사실을 산출에 적는다(#3 조용히 비우지 않는다).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.schema import Facts, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §1·§3 — 두 팀 각각 몇 경기를 되짚나(지시서가 적은 10)
BACK = 10


def _plan_of(strategy: Any, side: str) -> str:
    """🔴 그 팀의 **전략 판정 글자**(없으면 빈 글자 — 지어내지 않는다)."""
    for one in (getattr(strategy, "lines", None) or []):
        if str(getattr(one, "side", "")) == side:
            return str(getattr(one, "strategy", "") or "")
    return ""
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성 단계(`run`)를 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라**
#
#  🔴 **까닭 — 결과가 버려지고 있었다.** `run` 이 축0~축3(Elo 잔차·폼·스타일·
#     시간대)을 모아 `probmodel` 의 λ 시뮬로 보냈는데, 같은 함수 마지막 세 줄이
#     승무패를 `flat_prob`(1/3 균등 + 변수)로 **덮고** `lam`·`over`·`scores` 를
#     **비웠다**. 즉 `eloratings.net` 통신과 몬테카를로를 돌리고 **버렸다**.
#     ⚠️ 울산 실행 로그가 그 낭비를 적었다: `[s2e] Elo 를 못 찾은 팀 1곳`.
#
#  🔴 **남긴 것 — 이 파일은 이제 "경기 이력·폼 재료"다**(상성이 아니다):
#       `_history`   그 팀의 지난 경기 목록(10경기) — `s2_facts` 가 쓴다
#       `games_of`   경기 한 줄 꼴 — 폼·결장·전략이 읽는 그 꼴이다
#       `usual_xi`   폼 창의 선발 합집합 — `style` 이 쓴다
#       `adv_players` 공격 기여 — `strategy` 가 쓴다
#     ⚠️ 그 넷은 **② 바닥 사실의 재료**이지 상성 계산이 아니다. 지우면
#        폼·결장·전략이 같이 죽는다(실측으로 확인하고 남겼다).





async def _history(net: Any, name: str, *, state: RunState, as_of,
                   ref: Any = None, tid_hint: str = "") -> list[dict] | None:
    """🔴 그 팀 **최근 끝난 경기 + 골 목록**. 못 받으면 `None`.

    🔴 주소는 **팀 일정 HTML → 경기 페이지 HTML** 이다(robots 허용 경로).
    ⚠️ `/api/*` 는 막혀 있다 — 쓰지 않는다(금지 조항).
    """
    from app.collect import fotmob as fm
    from app.core import discover as _d
    from app.core.stages.s2_facts import _day_page
    try:
        # 🔴🔴 **등급을 가린다** — 색인이 같은 슬러그를 두 번 준다(여자팀·2군).
        #    고르는 규율은 `discover.pick_team` 하나다(#1 사본 금지).
        # 🔴🔴 **번호가 오면 색인을 안 본다**(P1) — 색인(6,028팀)에 **V리그·태국
        #    리그 팀이 없다**(실측 2026-10-13: 꽁안 하노이 0건). 그 번호는 경기
        #    페이지가 준다(`fotmob.side_ids` → `facts.standings["team_ids"]`).
        got = ((str(tid_hint), "x") if tid_hint
               else await _d.pick_team(net, name, ref=ref, state=state))
        if tid_hint:
            state.note(f"s2e P1 `{name}` — 색인 대신 **경기 페이지의 팀 번호** "
                       f"`{tid_hint}` 로 과거 경기를 받는다")
        if not got:
            # 🔴 **어디서 멈췄나를 적는다**(P1 · 조용한 0 금지) — 등록 리그 밖
            #    팀이 여기서 떨어지면 축1~축3 이 통째로 빈다(실측: 꽁안 하노이).
            state.note(f"s2e ⬜ `{name}` — **팀 번호를 못 골랐다**(색인·별칭) "
                       f"→ 과거 경기 0건")
            return None
        tid, slug = got
        page = await _day_page(net, fm.team_fixtures_url(tid, slug),
                               state=state, team=f"{name} 일정")
        if page is None:
            state.note(f"s2e ⬜ `{name}`(번호 {tid}) — **팀 일정 페이지를 못 "
                       f"받았다** → 과거 경기 0건")
            return None
        # 🔴🔴 **누설 금지**(사용자 지시 2026-10-12 ⓐ · 계약 L1) — `as_of` **이전**
        #    경기만 본다. ⚠️ 실사고 2026-10-12: 여기가 *"끝난 경기"* 만 걸러서
        #    **분석 대상 경기 자신**(1-2 · xG 0.85/1.04)이 폼에 들어갔다.
        #  🔴 거르는 문은 `fotmob.before_as_of` 하나다(사본 금지).
        said_done = [r for r in _d.team_fixtures(
            getattr(page, "text", "") or "", tid) if r.get("finished")]
        fx = fm.before_as_of(said_done, as_of=as_of)[-BACK:]
        if not fx:
            state.note(f"s2e ⬜ `{name}`(번호 {tid}) — 일정에 **as-of 이전 끝난 "
                       f"경기가 0건**이다(받은 경기 {len(said_done)}건) → "
                       f"축1~축3 을 못 센다")
        if len(said_done) != len(fx):
            state.note(f"s2e 누설 막음 — `{name}` 끝난 경기 {len(said_done)}건 중 "
                       f"as-of 이전 {len(fx)}건만 본다")
        out: list[dict] = []
        for m in fx:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **번호로 받는다 — 슬러그 주소는 남의 경기를 준다**
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-16(코스타리카 Saprissa): 팀 일정의 `page` 는
            #     `/matches/<A>-vs-<B>/<슬러그>#<번호>` 꼴이고 **`#번호` 는
            #     브라우저 조각이라 서버가 무시한다**. 그래서 같은 두 팀이 여러
            #     번 만난 경우 서버가 **다른 맞대결**(보통 최신·다음 경기)을 준다.
            #     실측 — 과거 5경기 중 **4경기가 엉뚱한 페이지**였다:
            #       09-10 기대 6119118 → 받은 5833808(골 0건)
            #       09-13 기대 5833791 → 받은 **5833806 = 분석 대상 경기 자신**
            #       09-17 기대 6119122 → 받은 5833808 · 09-20 기대 5833796 → 5833823
            #     🔴 그 페이지엔 골 목록이 없으니 `goals_of` 가 0 이고 `games_of`
            #        의 `gf/ga` 가 **조용히 0** 이 됐다 → 폼이 *"득점 0.0 · 실점
            #        0.2"* 라는 거짓 수가 됐고, 평·확률이 그 수로 갔다.
            #  🔴 그래서 **`fotmob.match_url(번호)`** 로 받는다(번호는 유일하다).
            #  🔴 그리고 **받은 페이지가 그 경기인지 확인한다** — `general.matchId`
            #     가 기대 번호와 다르면 **그 줄을 버리고 사유를 남긴다**(#3).
            said_id = str(m.get("id") or "").strip()
            if not said_id:
                state.note(f"s2e ⬜ `{name}` 과거 경기에 **번호가 없다** — "
                           f"{str(m.get('utc') or '')[:10]} 줄을 버린다")
                continue
            one = await _day_page(net, fm.match_url(said_id), state=state,
                                  team=f"{name} 골 타임라인")
            if one is None:
                continue
            j = fm.payload(getattr(one, "text", "") or "") or {}
            got_id = str((((j.get("props") or {}).get("pageProps") or {})
                          .get("general") or {}).get("matchId") or "")
            if got_id and got_id != said_id:
                # 🔴 **남의 경기다** — 폼에 넣지 않는다(위 머리말의 그 사고)
                state.note(f"s2e 🔴 `{name}` {str(m.get('utc') or '')[:10]} — "
                           f"기대 번호 `{said_id}` 인데 페이지는 `{got_id}` 다 "
                           f"→ 그 경기를 **버린다**")
                continue
            # 🔴 **홈/원정을 여기서 가린다** — 신원 계약(3단계)이 아래 단계에서
            #    이름 비교를 금지한다. ⚠️ 그 가림을 이름으로 하되 **한 곳**이다.
            mine = _d.same_any(str(m["home"]), _d.aliases_of(name), loose=True)
            them = _d.same_any(str(m["away"]), _d.aliases_of(name), loose=True)
            # 🔴🔴 **평소 XI 의 재료**(사용자 지시 2026-10-11 ③) — 그 경기의
            #    **우리 쪽 선발 11명**이다. 이것이 있어야 *"폼 창에 있었는데 오늘
            #    빠진 선수"* 와 *"그 창 내내 빠져 있던 장기 결장"* 을 가른다.
            lu = ((fm._page(j).get("content") or {}).get("lineup") or {})
            which = "homeTeam" if (mine and not them) else "awayTeam"
            starters = [str(r.get("name") or "")
                        for r in fm.players_of(dict(lu.get(which) or {}))]
            out.append({"home_name": m["home"], "away_name": m["away"],
                        "mine_home": (mine if mine != them else None),
                        # 🔴 ① — **날짜·대회**를 들고 다닌다(두 창 표의 재료)
                        "utc": str(m.get("utc") or ""),
                        "league": str(m.get("league_name") or ""),
                        "starters": [x for x in starters if x],
                        "goals": fm.goals_of(j),
                        # 🔴 §2 — **6축 재료**(경기 통계 · 같은 페이지에서 온다)
                        "stats": fm.stats_of(j),
                        # 🔴🔴 **고급 지표 재료**(지시서 2026-10-12 ①) — 슈팅별
                        #    xG(분·상황)와 편을 가릴 팀 번호. ⚠️ 팀 xG 자체는
                        #    `stats` 에 이미 있다(`expected_goals`) — 두 번 받지 않는다.
                        "shots": fm.shots_of(j),
                        "side_ids": fm.side_ids(j),
                        # 🔴 선수 기여표(xG+xA) 재료 — 같은 페이지다(새 통신 0)
                        "player_adv": fm.player_adv(j)})
        return out or None
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2e 과거 경기 — 🔴 터졌다({name}): {exc!r}")
        return None


#: 🔴🔴 **분 구간**(§3-2 와 같은 경계다 — 사본 금지: 그 블록이 이 셋을 쓴다)
XG_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-30", 0, 30), ("31-60", 31, 60), ("61-90+", 61, 200))

#: 🔴 팀 통계에서 읽는 열쇠 — **fotmob 의 `key` 글자**다(실측 2026-10-12)
#  ⚠️ `tackles` 만 꼴이 다르다(`matchstats.headers.tackles`) — 받아서 확인했다.
ADV_KEYS: dict[str, str] = {
    "xg": "expected_goals",
    "xg_open": "expected_goals_open_play",
    "xg_set": "expected_goals_set_play",
    "box_touch": "touches_opp_box",
    "shots_in_box": "shots_inside_box",
    "interceptions": "interceptions",
    "tackles": "matchstats.headers.tackles",
    "passes_ok": "accurate_passes",
}


def _pair(stats: dict, key: str) -> tuple[float | None, float | None]:
    """🔴 `{key: (홈, 원정)}` 에서 수 둘. 없으면 `(None, None)`(0 이 아니다 · #3)."""
    got = (dict(stats or {})).get(key)
    if not got or len(tuple(got)) != 2:
        return (None, None)
    out = []
    for one in tuple(got):
        val = (dict(one).get("n") if isinstance(one, dict) else one)
        out.append(float(val) if isinstance(val, (int, float)) else None)
    return (out[0], out[1])


def _mine_theirs(stats: dict, key: str, *, mine_home: bool
                 ) -> tuple[float | None, float | None]:
    """🔴 그 열쇠를 **우리/상대**로 갈라 준다."""
    a, b = _pair(stats, key)
    return (a, b) if mine_home else (b, a)


def _adv_of(box: dict, *, mine_home: bool) -> dict:
    """🔴🔴 한 경기의 **고급 지표**(지시서 2026-10-12 ①②) — 우리 기준.

    🔴 재료는 둘뿐이다: `stats`(팀 통계 · `ADV_KEYS`)와 `shots`(슈팅별 xG).
       ⚠️ 못 읽은 칸은 **`None` 과 이름**이다(0 으로 메우지 않는다 · #3).
    🔴 `press` 대리 지표(사용자 결정 2026-10-12 ②): PPDA 가 어디에도 없다
       (fotmob 168항목·Understat 전면 금지) → **(태클+인터셉트) ÷ 상대 정확 패스**.
       그 분자·분모를 **따로** 싣는다 — 창을 합칠 때 비율을 다시 세야 한다
       (경기별 비율의 평균은 합의 비율과 다르다).
    """
    stats = dict(box.get("stats") or {})
    why: list[str] = []
    xgf, xga = _mine_theirs(stats, ADV_KEYS["xg"], mine_home=mine_home)
    if xgf is None or xga is None:
        why.append("팀 xG 없음")
    open_f, _ = _mine_theirs(stats, ADV_KEYS["xg_open"], mine_home=mine_home)
    set_f, _ = _mine_theirs(stats, ADV_KEYS["xg_set"], mine_home=mine_home)
    if open_f is None and set_f is None:
        why.append("상황별 xG 없음")
    tk_f, _ = _mine_theirs(stats, ADV_KEYS["tackles"], mine_home=mine_home)
    ic_f, _ = _mine_theirs(stats, ADV_KEYS["interceptions"],
                           mine_home=mine_home)
    _, pass_t = _mine_theirs(stats, ADV_KEYS["passes_ok"],
                             mine_home=mine_home)
    num = None if (tk_f is None and ic_f is None) else (
        float(tk_f or 0.0) + float(ic_f or 0.0))
    if num is None or not pass_t:
        why.append("press 대리 지표 재료 없음")
    box_f, _ = _mine_theirs(stats, ADV_KEYS["box_touch"],
                            mine_home=mine_home)
    if box_f is None:
        why.append("박스 터치 없음")
    _, in_box_t = _mine_theirs(stats, ADV_KEYS["shots_in_box"],
                               mine_home=mine_home)
    if in_box_t is None:
        why.append("허용 박스 슈팅 없음")
    # ── 슈팅별 xG → 분 구간·상황 묶음(우리 슈팅만)
    ids = tuple(box.get("side_ids") or ("", ""))
    mine_id = (ids[0] if mine_home else ids[1]) if len(ids) == 2 else ""
    mins = {name: 0.0 for name, _, _ in XG_BUCKETS}
    group: dict[str, float] = {}
    n_shot = 0
    for one in (box.get("shots") or []):
        said = dict(one)
        if mine_id and str(said.get("team_id") or "") != mine_id:
            continue
        val = said.get("xg")
        if val is None:
            continue
        n_shot += 1
        got = int(said.get("min") or 0)
        for name, lo, hi in XG_BUCKETS:
            if lo <= got <= hi:
                mins[name] = round(mins[name] + float(val), 3)
                break
        key = str(said.get("group") or "기타")
        group[key] = round(group.get(key, 0.0) + float(val), 3)
    if not n_shot:
        why.append("슈팅별 xG 없음")
    return {
        "xgf": (round(float(xgf), 3) if xgf is not None else None),
        "xga": (round(float(xga), 3) if xga is not None else None),
        # 🔴 `xg_n` 은 **팀 xG 를 읽은 경기냐**다(1 또는 0) — 골 수가 아니다
        "xg_n": (1 if (xgf is not None and xga is not None) else 0),
        "xg_open": (round(float(open_f), 3) if open_f is not None else None),
        "xg_set": (round(float(set_f), 3) if set_f is not None else None),
        "xg_min": dict(mins) if n_shot else {},
        "xg_group": dict(group),
        "press_num": (round(num, 2) if num is not None else None),
        "press_den": (round(float(pass_t), 2) if pass_t else None),
        "box_touch": (round(float(box_f), 2) if box_f is not None else None),
        "shots_in_box_against": (round(float(in_box_t), 2)
                                 if in_box_t is not None else None),
        "why": " · ".join(why),
    }
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성·시뮬과 함께 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**
#
#  🔴 아래 함수들은 **상성 축(축0~축3)이 쓰던 부품**이다 — 스타일 6축·무기 표·
#     백분위·창 검사·공격 기여·중심화. 상성 단계를 지우자 **부르는 곳이 0**
#     이 됐다(`tests/test_wiring.py` 가 고아로 잡았다 · #2).



def _score_pair(raw: object) -> tuple[int, int] | None:
    """🔴 `"3 - 3"` → `(3, 3)`. 못 읽으면 `None`(지어내지 않는다 · #4).

    ⚠️ fotmob 은 공백을 넣어 준다(`"3 - 3"`) — 실측 2026-10-17.
    """
    import re as _re
    m = _re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(raw or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def games_of(rows: list[dict]) -> list[dict]:
    """🔴🔴 ① — **한 원천의 경기 목록**. 두 창(5·10)을 이 목록에서 자른다.

    > 폼 블록(5경기)과 축1(10경기)의 경기 목록을 날짜·대회·스코어로 나란히 찍어라.
    > **한 원천(같은 경기 목록)에서 두 창을 자른다.** — 사용자 지시 2026-10-11 ①

    한 줄: `{date, league, side, opp, score, gf, ga, starters}`.
    🔴 득·실은 **골 목록에서 센다**(자책골은 상대 득점으로) — 스코어 글자를 다시
       파싱하지 않는다.
    ⚠️ `mine_home` 이 `None` 인 줄(우리 팀을 못 가린 경기)은 **버린다** — 득실을
       어느 쪽에 줄지 모르는 수를 폼에 넣지 않는다(#4).
    """
    out: list[dict] = []
    for row in (rows or []):
        box = dict(row)
        if box.get("mine_home") is None:
            continue
        mine_home = bool(box.get("mine_home"))
        gf = ga = 0
        # 🔴🔴 A — **xG 도 센다**(사용자 지시 2026-10-11) — 골 줄에 이미 있다.
        #    ⚠️ 실측: 축1 은 **골 수만** 썼다(`form.py` 의 xG 언급은 독스트링뿐).
        #    🔴 xG 가 없는 골은 **빼지 않고 센 수만** 더한다 — 그 사실을 칸으로
        #       남긴다(`xg_n` = xG 가 있던 골 수 · #3 조용한 0 금지).
        xgf = xga = 0.0
        xg_n = 0
        for g in (box.get("goals") or []):
            scored_home = bool(g.get("home")) != bool(g.get("own_goal"))
            mine = (scored_home == mine_home)
            if mine:
                gf += 1
            else:
                ga += 1
            val = g.get("xg")
            if val is None:
                continue
            xg_n += 1
            if mine:
                xgf += float(val)
            else:
                xga += float(val)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **스코어 글자와 대조한다** — 사용자 지적 2026-10-17
        # ══════════════════════════════════════════════════════════════
        #
        #  > "직전 경기 승/무/패"로 나와야 하는거 아니냐? · **무는 어떻게
        #  > 표시돼는지 fotmob 에** 확인해봐라
        #
        #  🔴 fotmob 은 **두 가지로** 준다 — `resultString: "D"` 와
        #     `score: "3 - 3"`(실측 2026-10-17 나고야 vs 파지아노 10-14).
        #  ⚠️ 그런데 위는 **골 목록을 세고 있었다**(`gf += 1`). 골 줄이 비거나
        #     하나를 못 읽으면 **`3-3` 이 `3-2`(승)** 가 된다 — 무승부가
        #     통째로 사라진다. 독스트링이 *"스코어 글자를 다시 파싱하지
        #     않는다"* 고 적었는데, 그 선택이 이 병을 만들었다.
        #  🔴 그래서 **스코어가 있으면 그것이 이긴다**(출처가 직접 말한 수다).
        #     ⚠️ 어긋나면 그 사실을 줄에 남긴다(#3) — 조용히 고르지 않는다.
        said_score = _score_pair(box.get("score"))
        said_gap = ""
        if said_score is not None:
            s_home, s_away = said_score
            g_home, g_away = ((gf, ga) if mine_home else (ga, gf))
            if (s_home, s_away) != (g_home, g_away):
                said_gap = (f"🔴 골 목록 {g_home}-{g_away} ↔ 스코어 "
                            f"{s_home}-{s_away} — **스코어를 쓴다**")
                gf, ga = ((s_home, s_away) if mine_home else (s_away, s_home))
        at_home, at_away = ((gf, ga) if mine_home else (ga, gf))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **고급 지표**(지시서 2026-10-12 ①②) — 이 줄의 재료는 전부
        #     `stats`(팀 통계)와 `shots`(슈팅별)에서 온다.
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고 2026-10-12: 축1 이 쓰던 `xgf/xga` 는 **득점한 골의 xG**였다
        #     (`goals[].xg`) — 그것은 *운 요소* 재료이고 **팀 xG 가 아니다**.
        #     🔴 그래서 위에서 센 수는 `luck_xg*` 로 이름을 바꿔 남기고, 폼이
        #        보는 `xgf/xga` 는 **팀 xG**(`expected_goals`)로 갈아 끼운다.
        adv = _adv_of(box, mine_home=mine_home)
        out.append({
            # 🔴 §7 ContextRow 가 **시각**을 본다(날짜만으로는 창을 못 자른다)
            "utc": str(box.get("utc") or ""),
            "date": str(box.get("utc") or "")[:10],
            "league": str(box.get("league") or ""),
            "side": ("home" if mine_home else "away"),
            "opp": str(box.get("away_name") if mine_home
                       else box.get("home_name")),
            "score": f"{at_home}-{at_away}",
            # 🔴 두 경로가 어긋났으면 **그 사실을 줄에 싣는다**(#3)
            "score_gap": said_gap,
            "gf": gf, "ga": ga,
            # 🔴 **운 요소 재료**(T12) — 득점한 골의 xG 합과 그 수(폼이 아니다)
            "luck_xgf": round(xgf, 3), "luck_xga": round(xga, 3),
            "luck_xg_n": xg_n,
            # 🔴🔴 **팀 xG**(폼·축1 이 보는 수) — 없으면 `None` 이고 `xg_n` 이 0 이다
            "xgf": adv["xgf"], "xga": adv["xga"], "xg_n": adv["xg_n"],
            # 🔴 무기 표(상황별 xG)·축3(분 구간 xG)·축2 대리 지표
            "xg_open": adv["xg_open"], "xg_set": adv["xg_set"],
            "xg_min": adv["xg_min"], "xg_group": adv["xg_group"],
            "press_num": adv["press_num"], "press_den": adv["press_den"],
            "box_touch": adv["box_touch"],
            "shots_in_box_against": adv["shots_in_box_against"],
            "adv_why": adv["why"],
            "starters": list(box.get("starters") or [])})
    return out


#: 🔴🔴 ③ **평소 XI 의 문턱** — 선발 명단이 있는 경기의 이 비율 이상 선발
#
#  ⚠️ 실측 2026-10-11: *"창에 한 번이라도 선발"* 로 세면 밴쿠버 **32명** · LAFC
#     22명이다(로테이션·컵 경기까지). 그 목록으로는 *"오늘 빠졌다"* 가 뜻을
#     잃는다. 🔴 실측 선발 횟수 — 뮐러 **6/8** · 바드왈 2/8 · 에보비세 **3/10**.
USUAL_SHARE = 0.5


def _off_why(*, usual: set[str], out_today: set[str], share: float,
             table: int) -> str:
    """🔴🔴 **꺼진 무기의 까닭** — #3 조용한 0 금지.

    ⚠️ 실사고 2026-10-11: 카드에 `꺼진 무기 away 0` 만 적혀 있어 *평소 XI 를 못
       만든 것인지 · 빠진 선수가 없는 것인지 · 비중이 모자란 것인지* 를 가릴 수
       없었다(그 셋은 서로 다른 고장이다).
    """
    if not usual:
        return ("🔴 평소 XI 를 못 만들었다(과거 선발 명단 0건) — 꺼진 무기를 "
                "안 센다")
    hit = sorted(usual & out_today)
    return (f"평소 XI {len(usual)}명 · 오늘 빠짐 "
            + (", ".join(hit) if hit else "없다")
            + (f" · 공격 기여 비중 {share:.1%}"
               f"(문턱 {_style_cuts()}) · 기여표 {table}명"
               if hit else ""))


def _style_cuts() -> str:
    """🔴 무기 꺼짐 문턱을 **원본에서** 읽어 적는다(사본 금지)."""
    from app.core import style as _st
    return f"{_st.OFF_SMALL:.0%}/{_st.OFF_BIG:.0%}"


def _gate_off(axes: list[str], *, usual: set[str],
              out_today: set[str], share: float | None = None) -> list[str]:
    """🔴🔴 ③ **꺼진 무기의 문** — 평소 XI 중 오늘 빠진 선수가 있어야 끈다.

    > "평소 XI(최근 폼 계산 기간)에 있었는데 오늘 빠진 선수"만 무기를 끈다.
    >   — 사용자 지시 2026-10-11 ③

    ⚠️ `usual` 이 **비면 막지 않는다** — 선발 자료를 못 받았다는 뜻이고, 없는
       자료로 **있는 사실(결장)을 지우면** 조용한 0 이 된다(#3).
    """
    if not axes or not usual:
        return list(axes)
    if not (usual & out_today):
        return []
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **비중도 같은 문을 지난다**(사용자 지시 2026-10-11 ⑤)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-11(엘체–셀타): `off_weapons`(XI 경로)는 비중으로 걸러
    #     0개였는데, **변수 경로**(`off_from_vars`)가 고정 세 축을 통째로 켜서
    #     카드가 *양 팀 똑같이 3개*(`box_entry`·`direct`·`forward`)를 적었다 —
    #     그 자리에 적힌 공격 기여 비중은 **0.0%**(문턱 15%)였다. 양 팀이 늘 같은
    #     값이면 축2 의 차는 언제나 0 이다.
    #  🔴 그래서 변수 경로도 **빠진 선수의 공격 기여 비중**을 본다 — 모자라면
    #     **공격 무기는 끄지 않고**(`matchup.SIX_DEF` 밖) 수비 쪽만 남긴다.
    #  ⚠️ `share` 를 **안 주면 막지 않는다** — 못 쟀다는 뜻이고, 없는 자료로
    #     있는 사실(결장)을 지우면 조용한 0 이다(#3).
    if share is None:
        return list(axes)
    from app.core import style as _st0
    if float(share) >= float(_st0.OFF_SMALL):
        return list(axes)
    from app.core.matchup import SIX_DEF
    return [x for x in axes if x in SIX_DEF]


def _lineup_view(ref, facts, *, pid_box: dict, usual: dict
                 ) -> tuple[dict, str]:
    """🔴🔴 **(가) 표시용 라인업 수** — `L9` 와 평소 대비 공격 기여 %. `(값, 사유)`.

    🔴 재료는 **선수 가치 v2 판**(`player_box` · `data/player_box/<리그>/<as_of>`)
       과 **평소 XI**(이미 id 로 센 것)와 **오늘 XI id** 다.
    ⚠️ 판이 없으면 **미산출 + 사유**다(지어내지 않는다 · #3). 🔴 이 수는 확률에
       가지 않는다 — `tests/contracts/test_v19_2_lineup_view.py` 가 그것을 센다.
    """
    from app.core import lineupfix as _lf
    from app.core import playerid as _pid
    from app.core import probmodel as _pmd
    from app.core.ratings import player_box as _pbx
    kind = str(_pmd._kind(ref, facts) or "")
    at = getattr(ref, "kickoff_utc", None)
    if not kind or at is None:
        return {}, (f"🔴 **라인업 표시 미산출** — 대회 열쇠/킥오프가 없다"
                    f"(열쇠 `{kind}`)")
    box, why_plate = _pbx.plate_of(league=kind, as_of=at)
    if not box:
        return {}, f"🔴 **라인업 표시 미산출** — {why_plate}"
    said: dict[str, dict] = {}
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        one = (getattr(facts, "xi", None) or {}).get(key)
        names = ([getattr(p, "name", "") for p in (getattr(one, "lineup", None)
                                                   or [])]
                 or list(getattr(one, "players", None) or []))
        today = {_pid.resolve(pid_box[side], said=nm)[0] or f"name:{nm}"
                 for nm in names if str(nm or "").strip()}
        said[side] = {"xi": sorted(today), "usual": sorted(usual[side]),
                      "bench": []}
    if not said["home"]["xi"] or not said["away"]["xi"]:
        return {}, ("🔴 **라인업 표시 미산출** — 오늘 XI 를 id 로 못 세웠다"
                    f"(홈 {len(said['home']['xi'])}명 · 원정 "
                    f"{len(said['away']['xi'])}명)")
    got, why = _lf.view_of(home=said["home"], away=said["away"], box=box)
    return got, (why + f" · {why_plate}" if got else why)


def _ko_players() -> dict:
    """🔴 `names_ko.yaml` 의 선수 한글 표기(원본은 그 파일 하나다)."""
    from app import rules as _rules
    return dict(_rules.names_ko().get("players") or {})


def _pid_rows(facts, key: str, games: list) -> list[dict]:
    """🔴 ④ — 신원표 재료(오늘 XI·최근 경기 선발·소집 명단·결장 명단)."""
    out: list[dict] = []
    one = (getattr(facts, "xi", None) or {}).get(key)
    for p in (getattr(one, "lineup", None) or []):
        out.append({"name": getattr(p, "name", ""),
                    "number": getattr(p, "number", None),
                    "pos": getattr(p, "pos", ""), "source": "오늘 XI"})
    for nm in (getattr(one, "players", None) or []):
        out.append({"name": str(nm), "source": "오늘 XI"})
    for nm in (getattr(one, "bench", None) or []):
        out.append({"name": str(nm), "source": "오늘 XI/벤치"})
    for game in list(games or []):
        out += [{"name": str(x), "source": "최근 경기"}
                for x in (dict(game).get("starters") or []) if x]
    out += [{"name": str(nm), "source": "소집 명단"}
            for nm in ((getattr(facts, "squad", None) or {}).get(key) or [])]
    out += [{"name": getattr(m, "name", ""), "source": "결장 명단"}
            for m in ((getattr(facts, "missing", None) or {}).get(key) or [])]
    return [r for r in out if str(r.get("name") or "").strip()]


def _out_today(facts, key: str) -> set[str]:
    """🔴 ③ — **오늘 빠진 선수 이름**(결장 목록). ⚠️ 벤치는 `key_state` 가 든다.

    🔴 원본은 `facts.missing[팀]` 이다(카드 블록 2b 가 적는 그 목록) — 사본을
       만들지 않는다. ⚠️ 이름이 없으면 건너뛴다(빈 글자를 선수로 세지 않는다).
    """
    # 🔴 칸 이름은 **`name`** 이다(`schema.Missing`) — ⚠️ 나는 `player` 로 적어
    #    조용히 빈 집합을 돌릴 뻔했다(계약이 그 칸을 센다).
    rows = list((getattr(facts, "missing", None) or {}).get(key) or [])
    return {str(getattr(one, "name", "") or "").strip()
            for one in rows if str(getattr(one, "name", "") or "").strip()}
# 🔴 상성·시뮬 삭제(2026-10-17)로 **부르는 곳이 0** 이 된 부품 — 같이 걷는다.



def _as_form(rows: list[dict], name: str) -> list[dict]:
    """🔴 §1 입력 꼴로 바꾼다 — `{gf, ga, opp}`(우리 기준).

    🔴 목록은 `games_of` 하나가 만든다(사본 금지) — 폼 블록·축1·두 창이 **같은
       목록**을 본다(사용자 지시 2026-10-11 ①).
    """
    return [{"gf": one["gf"], "ga": one["ga"], "opp": one["opp"]}
            for one in games_of(rows)]


def _luck_cut(fired: list, side: str) -> float | None:
    """🔴🔴 ② — 그 팀의 **운 요소 골 수**(k). 없으면 `None`.

    > T12 "운 요소 득점 k/n"이면 빼는 골은 **최대 k**. ×0.5 일괄 할인 삭제.
    >   — 사용자 지시 2026-10-11 ②

    🔴 **비율이 아니다** — T12 가 센 골 수(`luck_goals`)를 그대로 낸다.
    ⚠️ 그 수를 못 받으면 `None`(할인 없음)이다 — 비율로 되돌아가지 않는다.
    """
    for f in (fired or []):
        if f.rule == "T12" and f.side == side and not f.watch_only:
            got = dict(f.moves()).get("luck_goals")
            if got:
                return float(got)
    return None


def _elo_of(ref: MatchRef, rows: dict) -> dict:
    """🔴🔴 §1 — **팀 이름 → Elo**. 보정 폼의 핵이다.

    🔴 등급은 `app/collect/leagueelo.rating_of` 하나가 든다(사본 금지) — 그 함수가
       별칭표로 이름을 잇고 `via` 로 출처를 말한다.
    🔴 **상대 팀들도 넣는다** — 보정은 *"그 경기 상대가 누구였나"* 로 하므로 최근
       경기의 상대 이름이 전부 필요하다.
    ⚠️ 못 찾은 이름은 **빈칸으로 둔다**(0 으로 메우지 않는다) — `adjust_one` 이
       *"Elo 를 못 받아 보정 안 했다"* 를 사유로 남긴다.
    """
    from app.collect import leagueelo
    want = {str(ref.home_name), str(ref.away_name)}
    for side in ("home", "away"):
        for one in (rows.get(side) or []):
            box = dict(one)
            want |= {str(box.get("home_name") or ""),
                     str(box.get("away_name") or "")}
    out: dict = {}
    miss: list[str] = []
    for nm in sorted(x for x in want if x.strip()):
        got, _why = leagueelo.rating_of(nm)
        if got is not None:
            out[nm] = float(got)
        else:
            miss.append(nm)
    if miss:
        logger.info("[s2e] Elo 를 못 찾은 팀 %d곳 — %s", len(miss), miss[:6])
    return out


def _rest_days(facts: Facts, key: str) -> int | None:
    """🔴 T10 재료 — 그 팀의 **휴식일**. `s2_facts` 가 센 값을 읽는다."""
    box = dict((facts.recent or {}).get(str(key)) or {})
    got = box.get("rest_days")
    try:
        return int(got)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **확률은 한 곳이다** — 사용자 지시 2026-10-10(다섯 지적 ④)
# ══════════════════════════════════════════════════════════════════
#
#  > *"최종 확률 = **시뮬레이션(묶인 분포) 결과**. 카드의 '시뮬' 줄과 최종 숫자가
#  > 다르면 계약 실패. 잠정→최종 변화는 축별 기여(폼·전술·골 내용)로 분해해 합이
#  > 맞게."*
#
#  ⚠️ 실사고 2026-10-10(김천–안양): 시뮬이 **52%**, 최종이 **38%** 였다 — 한 카드가
#     두 답을 냈다. 🔴 원인: λ 를 **폼 차이로만** 갈라서 ①②③(Elo·라인업·변수·
#     전략)을 전혀 안 봤다. 그러니 두 경로가 서로 모르는 수를 냈다.
#  🔴 이제 이렇게 한 줄로 꿴다:
#     ① 확률층(①→②→③)이 `ours` 를 낸다 — 그 **홈/원정 비**를 맞추는 λ 기울기를
#        **풀어서** 찾는다(계수가 없다 · 적합할 것도 없다)
#     ② 그 위에 **축1 폼 기울기**와 **축2·축3 규칙의 λ 이동**을 얹는다
#     ③ **최종 확률 = 그 시뮬레이션의 승무패**다(카드의 모든 수가 여기서 나온다)
#  🔴 기여 분해는 **단계를 쌓아** 잰다(겹침 없이 합이 정확히 맞는다):
#     `잠정(p0) → +폼(p1) → +전략(p2) → +축2(p3) → +축3(p4=최종)`

#: 🔴 λ 기울기의 바닥·천장(한쪽이 0 이 되지 않게)
TILT_LO, TILT_HI = -0.9, 0.9
#: 🔴 비를 맞추는 이분법 횟수 — 30 번이면 1e-9 아래로 좁혀진다
SOLVE_STEPS = 30


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **옛 확률 경로를 지웠다** — 상성 엔진 지시서 §2(2026-10-10 여섯째)
# ══════════════════════════════════════════════════════════════════
#
#  여기 있던 `final_sim`·`solve_tilt`·`form_tilt`·`_within_cap` 을 **지웠다**:
#    · `final_sim` 은 **확률층(③ 로그 오즈)의 비를 맞추는** 기울기를 풀었다 —
#      그 확률층이 §2 로 사라졌으므로 맞출 비가 없다.
#    · `form_tilt`(임시 0.25)·`_within_cap`(±0.5 로그 오즈)도 그 경로의 부품이다.
#  🔴 지금은 **S2 → S3** 다: `matchup.report` 가 축 넷을 내고
#     `probmodel.run` 이 `λ = 리그 평균 × 홈 이점 × exp(β × 축 차)` 로 센다.
#  ⚠️ 그 함수들을 쓰던 계약은 **새 계약으로 바꿨다**(§2 마지막 줄: 빨간 채로 두지
#     않는다) — `tests/contracts/test_v7_2_matchup.py`.
