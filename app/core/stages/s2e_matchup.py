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


async def run(ref: MatchRef, facts: Facts, *, state: RunState, net: Any,
              ) -> dict:
    """🔴🔴 세 축을 모은다. ⚠️ 못 모은 축은 **사유를 담아** 돌려준다."""
    from app.core import form as _form
    from app.core import goals as _goals
    out: dict = {"axis2_why": ("🔴 축2(전술 상성 T1~T8)는 **스타일 프로필 6축** "
                               "자료가 없어 돌지 않는다 — 점유율·패스·압박 지표를 "
                               "받는 통로가 아직 없다(실측 2026-10-10)")}
    rows = {}
    for side in ("home", "away"):
        name = str(getattr(ref, f"{side}_name", "") or "")
        got = await _history(net, name, state=state)
        if got is None:
            out[f"{side}_why"] = f"🔴 `{name}` 의 과거 경기를 못 받았다"
            continue
        rows[side] = got
    if len(rows) != 2:
        out["why"] = "🔴 두 팀 과거 경기를 다 못 받아 **상성을 안 센다**"
        state.note(f"s2e 상성 — {out['why']}")
        return out
    # ── 축3 골 프로필
    prof = {side: _goals.profile_of(str(getattr(ref, f"{side}_name", "")),
                                    rows[side])
            for side in ("home", "away")}
    rest = {side: _rest_days(facts, getattr(ref, side)) for side in
            ("home", "away")}
    fired = _goals.fire(prof["home"], prof["away"], rest=rest)
    # ── 축1 보정 폼(운 요소 할인은 축3 의 T12 가 준다)
    elo = _elo_of(ref, rows)
    cut = {side: _luck_cut(fired, side) for side in ("home", "away")}
    form = {side: _form.form_of(
        str(getattr(ref, f"{side}_name", "")), _as_form(rows[side],
                                                        str(getattr(ref, f"{side}_name", ""))),
        elo=elo, luck_discount=cut[side]) for side in ("home", "away")}
    pool = [f.index() for f in form.values() if f.index() is not None]
    for side, one in form.items():
        one.pct_att = _form.percentile(one.index(), pool)
    out.update({"form": form, "profile": prof, "fired": fired, "rest": rest,
                "why": (f"축1 폼 {', '.join(f'{s} {f.index()}' for s, f in form.items())}"
                        f" · 축3 발동 {len(fired)}건")})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §4 — **분 단위 시뮬레이션**(해석 계산 · 같은 입력이면 같은 수)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 λ 는 **이 경기 총골 기준**에서 나눈다(새 기준선을 만들지 않는다) —
    #     그 기준은 `facts.standings["match_total_baseline"]` 하나다.
    #  ⚠️ 기준이 없으면 시뮬레이션을 **안 돈다**(λ 를 지어내지 않는다 · #4).
    out["sim"] = _simulate(ref, facts, out, state=state)
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
            out.append({"home_name": m["home"], "away_name": m["away"],
                        "mine_home": (mine if mine != them else None),
                        "goals": fm.goals_of(j)})
        return out or None
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s2e 과거 경기 — 🔴 터졌다({name}): {exc!r}")
        return None


def _as_form(rows: list[dict], name: str) -> list[dict]:
    """🔴 §1 입력 꼴로 바꾼다 — `{gf, ga, opp}`(우리 기준).

    🔴 홈/원정은 `_history` 가 이미 가려 뒀다(`mine_home`) — 여기서 이름을
       다시 비교하지 않는다(신원 계약 3단계).
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
        out.append({"gf": gf, "ga": ga,
                    "opp": (box.get("away_name") if mine_home
                            else box.get("home_name"))})
    return out


def _luck_cut(fired: list, side: str) -> float | None:
    """🔴 §1 마지막 줄 — 그 팀에 **T12 공격 할인**이 걸렸나(없으면 `None`)."""
    for f in (fired or []):
        if f.rule == "T12" and f.side == side and not f.watch_only:
            got = dict(f.moves()).get("form_attack_discount")
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


def _simulate(ref: MatchRef, facts: Facts, box: dict, *,
              state: RunState) -> dict:
    """🔴🔴 §4 — 세 축 → **스코어 분포·승무패·오버·선제골 팀 승률**.

    🔴 λ 를 두 팀으로 나누는 규칙은 **보정 폼 지수의 차이**다 — 축1 이 이미 상대
       전력을 보정했으므로 그 차이가 *"누가 더 넣나"* 를 말한다.
    ⚠️ 기준 총골이 없으면 `{}` 다(사유를 적는다 · 지어내지 않는다).
    """
    from app.core import goals as _g
    from app.core import sim as _sim
    base = dict(getattr(facts, "standings", None) or {}).get(
        "match_total_baseline")
    if base is None:
        said = "🔴 이 경기 총골 기준이 없다 — §4 시뮬레이션을 안 돈다"
        state.note(f"s2e {said}")
        return {"why": said}
    form = dict(box.get("form") or {})
    h = form.get("home").index() if form.get("home") else None
    a = form.get("away").index() if form.get("away") else None
    # 🔴 **기준 총골을 둘로 나눈다** — 폼 지수 차이로 기울인다
    #    ⚠️ 기울이는 계수(0.25)는 **임시값**이다(적합 전 · 카드가 적는다)
    tilt = 0.0
    if h is not None and a is not None:
        tilt = max(-0.4, min(0.4, 0.25 * (float(h) - float(a))))
    lam_h = float(base) * (0.5 + tilt / 2.0)
    lam_a = float(base) * (0.5 - tilt / 2.0)
    args = _g.sim_input(box, lam_home=lam_h, lam_away=lam_a)
    got = _sim.run(args["lam_home"], args["lam_away"],
                   late_home=args["late_home"], late_away=args["late_away"],
                   lead_mul=args["lead_mul"])
    return {"home": got.home, "draw": got.draw, "away": got.away,
            "over": got.over, "first_wins": got.first_wins,
            "scores": dict(list(got.scores.items())[:40]),
            "lam": [args["lam_home"], args["lam_away"]],
            "tilt": round(tilt, 3),
            "why": (f"총골 기준 {base} → λ {args['lam_home']}/"
                    f"{args['lam_away']}(폼 차로 기울임 {tilt:+.2f} · "
                    f"{_g.PROVISIONAL}) · {args['why']} · {got.why}")}
