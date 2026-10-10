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
    offs = {side: _style.off_weapons(reads[side], styles[side])
            for side in ("home", "away")}
    late = {side: _style.late_weapons(reads[side]) for side in ("home", "away")}
    fired2 = _style.fire(styles["home"], styles["away"], off=offs)
    out.update({"style": styles, "fired2": fired2, "off": offs, "late": late,
                "axis2_why": (
                    " · ".join(f"{s} {one.why}" for s, one in styles.items())
                    + f" · 발동 {len(fired2)}건"
                    + (f" · 꺼진 무기 {offs}" if any(offs.values()) else "")
                    + (f" · 후반 무기 {late}" if any(late.values()) else ""))})
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
    # 🔴🔴 §5 — 긴 카드가 적는 **골 목록 표**(분·유형·상태·xG). 같은 함수들로
    #    세므로 표와 비중이 어긋나지 않는다(`goals.table_of`).
    out["table"] = {side: _goals.table_of(rows[side])
                    for side in ("home", "away")}
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
            out.append({"home_name": m["home"], "away_name": m["away"],
                        "mine_home": (mine if mine != them else None),
                        "goals": fm.goals_of(j),
                        # 🔴 §2 — **6축 재료**(경기 통계 · 같은 페이지에서 온다)
                        "stats": fm.stats_of(j)})
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


def _lams(base: float, tilt: float) -> tuple[float, float]:
    """🔴 기준 총골을 기울기로 **둘로 나눈다**."""
    t = max(TILT_LO, min(TILT_HI, float(tilt)))
    return float(base) * (0.5 + t / 2.0), float(base) * (0.5 - t / 2.0)


def _sim_at(box: dict, base: float, tilt: float, *, axis2: bool, axis3: bool):
    """🔴 그 기울기에서의 시뮬 산출(`sim.Out`) + 쓰인 인자."""
    from app.core import goals as _g
    from app.core import sim as _sim
    lam_h, lam_a = _lams(base, tilt)
    args = _g.sim_input(box, lam_home=lam_h, lam_away=lam_a,
                        axis2=axis2, axis3=axis3)
    got = _sim.run(args["lam_home"], args["lam_away"],
                   late_home=args["late_home"], late_away=args["late_away"],
                   lead_mul=args["lead_mul"])
    return got, args


def solve_tilt(box: dict, base: float, want: float) -> float:
    """🔴🔴 ④ — **홈/원정 비 `want` 를 내는 기울기**를 이분법으로 찾는다.

    `want` = 확률층이 말한 `p_home / p_away`. 🔴 규칙은 **끈 채로** 푼다 — 그래야
    규칙의 몫이 기울기에 흡수되지 않고 **최종을 실제로 움직인다**.
    ⚠️ 비가 0 이하·무한이면 기울기를 **안 바꾼다**(0 을 돌려준다).
    """
    if not want or want <= 0 or want != want:            # NaN 포함
        return 0.0
    lo, hi = TILT_LO, TILT_HI

    def ratio(t: float) -> float:
        got, _ = _sim_at(box, base, t, axis2=False, axis3=False)
        return (got.home / got.away) if got.away > 0 else float("inf")

    # 🔴 단조다(기울기가 커지면 홈 비가 커진다) — 바깥이면 끝값으로 잘린다
    if ratio(lo) >= want:
        return lo
    if ratio(hi) <= want:
        return hi
    for _ in range(SOLVE_STEPS):
        mid = (lo + hi) / 2.0
        if ratio(mid) < want:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def form_tilt(box: dict) -> float:
    """🔴 축1 — **보정 폼 차이**가 만드는 기울기. ⚠️ 계수 0.25 는 **임시값**이다."""
    form = dict(box.get("form") or {})
    h = form.get("home").index() if form.get("home") else None
    a = form.get("away").index() if form.get("away") else None
    if h is None or a is None:
        return 0.0
    return max(-0.4, min(0.4, 0.25 * (float(h) - float(a))))


def final_sim(ref: MatchRef, facts: Facts, box: dict, *, state: RunState,
              ours, before, turnover: dict | None = None) -> dict:
    """🔴🔴 ④ — **최종 확률을 내는 시뮬레이션** + 축별 기여(합이 정확히 맞는다).

    돌려주는 것: `s2e` 의 `sim` 칸에 그대로 들어가는 표. 🔴 그 안의 `home/draw/
    away` 가 **최종 확률**이고, `share` 가 `잠정→최종` 의 축별 분해다.

    ⚠️ `ours` 가 없으면 **기울기를 폼으로만** 세운다(옛 모양) — 그 사실을 적는다.
    """
    base = dict(getattr(facts, "standings", None) or {}).get(
        "match_total_baseline")
    if base is None:
        said = "🔴 이 경기 총골 기준이 없다 — §4 시뮬레이션을 안 돈다"
        state.note(f"s2e {said}")
        return {"why": said}
    base = float(base)
    f_tilt = form_tilt(box)
    t_fin = (solve_tilt(box, base, _ratio(ours)) if ours is not None else 0.0)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **선수단 교체 — 기준 약함**(사용자 지시 2026-10-10 지적 ③)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 기준(Elo)·폼·골 내용은 **전역 이전 기록**이므로 "선수단 교체 — 기준 약함"
    #  > 표시, **가중을 낮춘다**(적합 전 임시값 표시).
    #
    #  🔴 낮추는 자리는 **기울기**다 — 기울기가 ①②③ 전부(Elo·라인업·변수·전략)를
    #     한 수로 들고 있으므로, 그것을 0 쪽으로 당기면 *"기준이 약하다"* 가 그대로
    #     확률에 들어간다. ⚠️ 비율은 **임시값**이고 카드가 그 사실을 적는다.
    weak_said = ""
    box_t = dict(turnover or {})
    if any(dict(v).get("on") for v in box_t.values()):
        from app.core import turnover as _turn
        w = _turn.weaken()
        keep = float(w.get("elo") or 1.0)
        t_fin, f_tilt = t_fin * keep, f_tilt * keep
        who = [k for k, v in box_t.items() if dict(v).get("on")]
        weak_said = (f" · {_turn.WEAK_MARK}({who}) — 기울기를 ×{keep} 로 "
                     f"낮췄다 · {_turn.PROVISIONAL}: {w.get('why')}")
        state.note(f"§4 선수단 교체 — 기준 약함{weak_said}")
    t_bef = (solve_tilt(box, base, _ratio(before)) if before is not None
             else t_fin)
    # 🔴 단계를 쌓는다 — 합이 정확히 맞는 기여 분해가 여기서 나온다
    p0, _ = _sim_at(box, base, t_bef, axis2=False, axis3=False)   # 잠정
    p1, _ = _sim_at(box, base, t_bef + f_tilt, axis2=False, axis3=False)
    p2, _ = _sim_at(box, base, t_fin + f_tilt, axis2=False, axis3=False)
    p3, _ = _sim_at(box, base, t_fin + f_tilt, axis2=True, axis3=False)
    got, args = _sim_at(box, base, t_fin + f_tilt, axis2=True, axis3=True)
    share = {"폼": round((p1.home - p0.home) * 100.0, 2),
             "전술": round((p3.home - p1.home) * 100.0, 2),
             "골 내용": round((got.home - p3.home) * 100.0, 2)}
    state.note(
        f"§4 확률 한 곳 — 시뮬이 최종이다 · 홈 {got.home:.1%} · 기울기 "
        f"확률 {t_fin:+.3f} + 폼 {f_tilt:+.3f} · 기여 {share}"
        f"(합 {sum(share.values()):+.2f}%p = 잠정→최종)")
    logger.info("[s2e] ④ 최종=시뮬 — 홈 %.3f 무 %.3f 원정 %.3f · 기여 %s",
                got.home, got.draw, got.away, share)
    return {"home": got.home, "draw": got.draw, "away": got.away,
            "over": got.over, "first_wins": got.first_wins,
            "scores": dict(list(got.scores.items())[:40]),
            "lam": [args["lam_home"], args["lam_away"]],
            "tilt": round(t_fin + f_tilt, 3),
            "tilt_prob": round(t_fin, 3), "tilt_form": round(f_tilt, 3),
            "before": {"home": p0.home, "draw": p0.draw, "away": p0.away},
            "share": share,
            "why": (f"총골 기준 {base} → λ {args['lam_home']}/"
                    f"{args['lam_away']} · 기울기 확률 {t_fin:+.3f}"
                    f"(③ 비를 맞춰 풀었다) + 폼 {f_tilt:+.3f}"
                    f"(임시값 0.25) · {args['why']} · {got.why}{weak_said}"),
            "weak": weak_said}


def _ratio(p) -> float:
    """🔴 그 확률의 **홈/원정 비**. ⚠️ 원정이 0 이면 비를 못 만든다(0)."""
    if p is None:
        return 0.0
    away = float(getattr(p, "away", 0.0) or 0.0)
    return (float(getattr(p, "home", 0.0) or 0.0) / away) if away > 0 else 0.0
