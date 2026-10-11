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


async def run(ref: MatchRef, facts: Facts, *, state: RunState, net: Any,
              varset: Any = None, turnover: dict | None = None,
              strategy: Any = None) -> dict:
    """🔴🔴 세 축을 모은다. ⚠️ 못 모은 축은 **사유를 담아** 돌려준다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **F2 — 변수·깃발·전략이 재료로 들어온다**(지시서 2026-10-11)
    ══════════════════════════════════════════════════════════════════

    > ⑧ 입력 시그니처: `(ref, facts, varset_axis, turnover, strategy)`.
    >   · 결장·징계 변수 → 그 선수가 쥔 무기 **꺼짐**, 복귀 변수 → **켜짐**
    >   · 교체 운용 선수(선발 비율 30% 미만) → **후반 무기**
    >   · turnover r → 폼·골 내용·스타일 집계에서 **과거 경기 가중**
    >   · 전략(수비 위주·3백 전환 등) → **스타일 6축 조정**
    > 규칙 T1~T13 발동은 **이 조정된 재료**로 판정한다.

    🔴 그래서 **전략 판정(⑦)이 이 단계보다 먼저** 돈다(파이프라인이 그 순서다).
    """
    from app.core import form as _form
    from app.core import goals as _goals
    out: dict = {}
    rows = {}
    for side in ("home", "away"):
        name = str(getattr(ref, f"{side}_name", "") or "")
        got = await _history(net, name, state=state)
        if got is None:
            out[f"{side}_why"] = f"🔴 `{name}` 의 과거 경기를 못 받았다"
            continue
        rows[side] = got
    if len(rows) != 2:
        out["axis2_why"] = "🔴 두 팀 과거 경기를 다 못 받아 축2 를 안 센다"
        out["why"] = "🔴 두 팀 과거 경기를 다 못 받아 **상성을 안 센다**"
        state.note(f"s2e 상성 — {out['why']}")
        return out
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ① **한 경기 목록** — 폼 블록·축1·두 창이 전부 이것을 본다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-11(LAFC–밴쿠버): 카드의 폼 블록은 **fotmob 폼 블록**
    #     (5경기)을, 축1 은 **경기 페이지 목록**(10경기)을 읽었다 — 그래서
    #     *"최근5 실점 10, 최근10 실점 9"* 라는 **불가능한 수**가 나란히 찍혔다.
    games = {side: games_of(rows[side]) for side in ("home", "away")}
    # 🔴🔴 ④ — **평소 XI·오늘 빠짐을 id 로** 센다(사용자 지시 2026-10-11 ④).
    #    ⚠️ 실사고 2026-10-11(가와사키): 캡처가 한글(`이즈미`)이고 결장 명단이
    #       로마자(`Ryuji Izumi`)라 글자로는 **다른 사람**이었다 — 그래서 선발이
    #       무기 꺼짐으로도 들어갔다.
    from app.core import playerid as _pid
    pid_box = {side: _pid.build(rows=_pid_rows(facts, getattr(ref, side, ""),
                                               games[side]),
                                ko=_ko_players())
               for side in ("home", "away")}
    usual = {side: {_pid.resolve(pid_box[side], said=x)[0] or f"name:{x}"
                    for x in usual_xi(rows[side])}
             for side in ("home", "away")}
    # 🔴 ① 계약 — 창이 어긋나면 **축1 미계산 + 운영자 알림**
    window_bad = {side: _form.windows_bad(games[side])
                  for side in ("home", "away")}
    out["games"] = games
    out["window_bad"] = window_bad
    out["usual_xi"] = {s: sorted(v) for s, v in usual.items()}
    for side, said in window_bad.items():
        if said:
            state.note(f"🔴🔴 **운영자 알림** — {side} 경기 목록의 두 창이 "
                       f"어긋났다: {said} → 축1 을 안 센다")
            logger.error("[s2e] 창 불일치 %s — %s", side, said)
    # ── 축3 골 프로필
    prof = {side: _goals.profile_of(str(getattr(ref, f"{side}_name", "")),
                                    rows[side])
            for side in ("home", "away")}
    rest = {side: _rest_days(facts, getattr(ref, side)) for side in
            ("home", "away")}
    fired = _goals.fire(prof["home"], prof["away"], rest=rest)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **축2 — 스타일 프로필 6축 + T1~T6**(사용자 지시 §2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 재료는 **같은 경기 페이지의 통계**다(새 통신이 없다) — 실측 2026-10-10
    #     에 그 표가 28칸이었다(`expected_goals_set_play`·`aerials_won` 포함).
    #  🔴 **꺼진 무기**(§2 둘째 줄)는 `strategy.read` 의 핵심 선수 상태로 센다 —
    #     확정 XI 가 아니면 빈 목록이다(그 사실이 사유에 남는다).
    from app.core import strategy as _strat
    from app.core import style as _style
    styles = {side: _style.profile_of(
        str(getattr(ref, f"{side}_name", "")), rows[side])
        for side in ("home", "away")}
    reads = {side: _strat.read(ref, facts, side=side)
             for side in ("home", "away")}
    # 🔴 F2 — **전략으로 6축을 조정한 뒤** 규칙을 발동한다(재료가 먼저 굳으면
    #    전략은 뒤늦은 장식이 된다)
    said_plan = {side: _plan_of(strategy, side) for side in ("home", "away")}
    styles = {side: _style.adjust(styles[side], said_plan[side])
              for side in ("home", "away")}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ③ **평소 XI 의 결장만 무기를 끈다** — 사용자 지시 2026-10-11 ③
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-11: `strategy._key_state` 는 리그 페이지의 **팀당 상위
    #     2명**만 든다 — 그래서 뮐러(6/8 선발 · 오늘 결장)가 **어디에도 안 세어져**
    #     밴쿠버의 꺼진 무기가 0 이었다. 🔴 그래서 **오늘 빠진 선수**를
    #     `facts.missing`(결장 목록)에서 직접 받아 넘긴다.
    #  🔴 끄는 대상은 **평소 XI ∩ 오늘 빠짐**이다 — 로테이션으로 빠진 선수(결장
    #     사실이 없는)는 **세지 않는다**(모르는 것을 결장으로 바꾸지 않는다 · #4).
    out_today = {side: {_pid.resolve(pid_box[side], said=x)[0] or f"name:{x}"
                        for x in _out_today(facts, getattr(ref, side, ""))}
                 for side in ("home", "away")}
    offs = {side: _style.off_weapons(reads[side], styles[side],
                                     usual=usual[side],
                                     out_today=out_today[side])
            for side in ("home", "away")}
    # 🔴 #3 — **왜 0 인가**를 적는다(평소 XI 없음 · 빠짐 없음 · 비중 모자람)
    off_why = {}
    for side in ("home", "away"):
        hit = sorted(usual[side] & out_today[side])
        att = dict(getattr(reads[side], "att_table", None) or {})
        off_why[side] = _off_why(
            usual=usual[side], out_today=out_today[side],
            share=_style._att_share(reads[side], hit) if hit else 0.0,
            table=len(att))
    out["off_why"] = off_why
    state.note("s2e ③ 꺼진 무기 — "
               + " · ".join(f"{s} {off_why[s]}" for s in ("home", "away")))
    # 🔴 F2 — **변수(결장·복귀)도 무기를 끄고 켠다**(XI 만 보던 자리다)
    for side in ("home", "away"):
        gone, back = _style.off_from_vars(varset, side)
        # 🔴 ③ — **변수 경로도 같은 문을 지난다**(실측 2026-10-11: `IR02-home`
        #    이 에보비세(3/10 선발)로 공격 축 셋을 통째로 껐다)
        gone = _gate_off(gone, usual=usual[side], out_today=out_today[side])
        offs[side] = sorted({*offs[side], *gone} - set(back))
    late = {side: _style.late_weapons(reads[side]) for side in ("home", "away")}
    fired2 = _style.fire(styles["home"], styles["away"], off=offs)
    # 🔴 F2/R3 — **r 가중**(선수단 교체)을 재료에 적어 둔다 — 축1·축3 이 그 수로
    #    과거 경기를 깎고, 보고가 그 사실을 적는다(조용히 깎지 않는다 · #3)
    from app.core import matchup as _mu
    out["r"] = _mu.r_of(varset, ref, turnover=turnover)
    out["turnover"] = dict(turnover or {})
    out["strategy_move"] = {s: said_plan[s] for s in ("home", "away")}
    state.note(f"s2e F2 — 전략 {said_plan} · r {out['r']} · "
               f"꺼진 무기 { {s: len(v) for s, v in offs.items()} }")
    out.update({"style": styles, "fired2": fired2, "off": offs, "late": late,
                "axis2_why": (
                    " · ".join(f"{s} {one.why}" for s, one in styles.items())
                    + f" · 발동 {len(fired2)}건"
                    + (f" · 꺼진 무기 {offs}" if any(offs.values()) else "")
                    # 🔴 #3 — 0 이어도 **까닭**을 적는다
                    + " · 꺼짐 판정 " + " / ".join(
                        f"{s} {off_why[s]}" for s in ("home", "away"))
                    + (f" · 후반 무기 {late}" if any(late.values()) else ""))})
    # ── 축1 보정 폼(운 요소 할인은 축3 의 T12 가 준다)
    elo = _elo_of(ref, rows)
    cut = {side: _luck_cut(fired, side) for side in ("home", "away")}
    form = {side: _form.form_of(
        str(getattr(ref, f"{side}_name", "")),
        _as_form(rows[side], str(getattr(ref, f"{side}_name", ""))),
        elo=elo, luck_goals=cut[side], games=games[side])
        for side in ("home", "away")}
    pool = [f.index() for f in form.values() if f.index() is not None]
    for side, one in form.items():
        one.pct_att = _form.percentile(one.index(), pool)
    # 🔴🔴 §5 — 긴 카드가 적는 **골 목록 표**(분·유형·상태·xG). 같은 함수들로
    #    세므로 표와 비중이 어긋나지 않는다(`goals.table_of`).
    out["table"] = {side: _goals.table_of(rows[side])
                    for side in ("home", "away")}
    out.update({"form": form, "profile": prof, "fired": fired, "rest": rest,
                # 🔴 ① — 축1 이 이 칸을 보고 **안 센다**(틀린 수가 λ 로 가는 길을 끊는다)
                "window_bad": window_bad,
                "why": (f"축1 폼 {', '.join(f'{s} {f.index()}' for s, f in form.items())}"
                        f" · 축3 발동 {len(fired)}건")})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §4 — **분 단위 시뮬레이션**(해석 계산 · 같은 입력이면 같은 수)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 λ 는 **이 경기 총골 기준**에서 나눈다(새 기준선을 만들지 않는다) —
    #     그 기준은 `facts.standings["match_total_baseline"]` 하나다.
    #  ⚠️ 기준이 없으면 시뮬레이션을 **안 돈다**(λ 를 지어내지 않는다 · #4).
    # 🔴🔴 ④ — **시뮬레이션은 여기서 돌지 않는다**(사용자 지시 2026-10-10).
    #    확률층(①→②→③)이 `ours` 를 낸 **뒤**에 `final_sim` 이 한 번 돌고, 그
    #    결과가 **최종 확률**이다. ⚠️ 여기서 폼만으로 한 번 돌리면 그 수가
    #    카드에 남아 최종과 **두 답**이 된다(실사고 2026-10-10: 52% 대 38%).
    out["sim"] = {"why": "🔴 아직 안 돌았다 — 확률층 뒤에 `final_sim` 이 돈다"}
    state.note(f"s2e 상성 — {out['why']}")
    logger.info("[s2e] 상성 — %s · 발동 %s", out["why"],
                [f.rule for f in fired])
    return out


async def _history(net: Any, name: str, *, state: RunState
                   ) -> list[dict] | None:
    """🔴 그 팀 **최근 끝난 경기 + 골 목록**. 못 받으면 `None`.

    🔴 주소는 **팀 일정 HTML → 경기 페이지 HTML** 이다(robots 허용 경로).
    ⚠️ `/api/*` 는 막혀 있다 — 쓰지 않는다(금지 조항).
    """
    from app.collect import fotmob as fm
    from app.core import discover as _d
    from app.core.stages.s2_facts import _day_page
    try:
        idx = await fm.team_index(net)
        hits = _d._slug_hit(idx, name)
        if not hits:
            return None
        tid, slug = hits[0]
        page = await _day_page(net, fm.team_fixtures_url(tid, slug),
                               state=state, team=f"{name} 일정")
        if page is None:
            return None
        fx = [r for r in _d.team_fixtures(getattr(page, "text", "") or "", tid)
              if r.get("finished")][-BACK:]
        out: list[dict] = []
        for m in fx:
            url = str(m.get("page") or "")
            if url.startswith("/"):
                url = fm.BASE + url
            one = await _day_page(net, url, state=state,
                                  team=f"{name} 골 타임라인")
            if one is None:
                continue
            j = fm.payload(getattr(one, "text", "") or "") or {}
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
                        "stats": fm.stats_of(j)})
        return out or None
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2e 과거 경기 — 🔴 터졌다({name}): {exc!r}")
        return None


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
        for g in (box.get("goals") or []):
            scored_home = bool(g.get("home")) != bool(g.get("own_goal"))
            if scored_home == mine_home:
                gf += 1
            else:
                ga += 1
        at_home, at_away = ((gf, ga) if mine_home else (ga, gf))
        out.append({
            "date": str(box.get("utc") or "")[:10],
            "league": str(box.get("league") or ""),
            "side": ("home" if mine_home else "away"),
            "opp": str(box.get("away_name") if mine_home
                       else box.get("home_name")),
            "score": f"{at_home}-{at_away}",
            "gf": gf, "ga": ga,
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
              out_today: set[str]) -> list[str]:
    """🔴🔴 ③ **꺼진 무기의 문** — 평소 XI 중 오늘 빠진 선수가 있어야 끈다.

    > "평소 XI(최근 폼 계산 기간)에 있었는데 오늘 빠진 선수"만 무기를 끈다.
    >   — 사용자 지시 2026-10-11 ③

    ⚠️ `usual` 이 **비면 막지 않는다** — 선발 자료를 못 받았다는 뜻이고, 없는
       자료로 **있는 사실(결장)을 지우면** 조용한 0 이 된다(#3).
    """
    if not axes or not usual:
        return list(axes)
    return list(axes) if (usual & out_today) else []


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


def usual_starts(rows: list[dict]) -> tuple[dict[str, int], int]:
    """🔴 ③ — `{선수: 선발 경기 수}` 와 **선발 명단이 있는 경기 수**.

    ⚠️ 선발 명단을 못 받은 경기는 **분모에서 뺀다** — 없는 자료를 0 으로 세면
       모두의 비율이 내려간다(#3 · 실측: 밴쿠버 10경기 중 2경기가 빈 명단이었다).
    """
    got: dict[str, int] = {}
    n = 0
    for one in games_of(rows):
        names = {str(x) for x in (one.get("starters") or []) if x}
        if not names:
            continue
        n += 1
        for nm in names:
            got[nm] = got.get(nm, 0) + 1
    return got, n


def usual_xi(rows: list[dict]) -> set[str]:
    """🔴🔴 ③ — **평소 XI**: 폼 창에서 **주로 선발로 뛴 선수**.

    > "평소 XI(최근 폼 계산 기간)에 있었는데 오늘 빠진 선수"만 무기를 끈다.
    > 그 기간 내내 빠져 있던 장기 결장(에보비세)은 폼에 이미 들어 있으니 끄지
    > 않는다(이중 계산). — 사용자 지시 2026-10-11 ③

    🔴 "주로"는 `USUAL_SHARE`(절반) 이다 — 그 수와 까닭을 위에 적어 뒀다.
    """
    got, n = usual_starts(rows)
    if not n:
        return set()
    return {nm for nm, k in got.items() if k / n >= USUAL_SHARE}


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
