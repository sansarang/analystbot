"""🔴🔴 **③ 우리 확률 · 세 열 비교 · 이유 찾기** — 네 층 지시서 §5·§6·§7.

## 세 열은 **섞지 않는다**

> 카드의 세 열: 기준(데이터) · 우리(분석) · 시장(배당). 세 열을 합쳐 **한 숫자로
> 만들지 않는다** — 나란히 놓고 차이를 설명한다.

🔴 그래서 이 파일에 **가중 평균이 없다.** 하는 일은 셋뿐이다:
   ① 시나리오 무게 → 우리 확률(`our_prob`)
   ② 세 열의 차이를 재고 **누가 튀는지** 가른다(`verdict_of`)
   ③ 시장이 우세로 보는 쪽의 **근거 후보**를 ①② 에서 뽑는다(`market_reasons`)

🔴 **금지**(§6 마지막 · §7): 시장과 다르다는 이유로 우리 수를 고치기 · 시장 확률을
   등급 계산에 직접 넣기 · 이 규칙으로 등급 **올리기** · 기대값·금액.
"""
from __future__ import annotations

import logging

from app.core.schema import (AdjProb, BaseProb, HypoSet, MarketProb, MatchRef,
                             ProbTriple, Variable)

logger = logging.getLogger(__name__)

#: 🔴 §6 — 시장과 우리가 이만큼 다르면 **이유를 찾는다**
GAP_MARKET = 0.10
#: 🔴 §5 마지막 — 우리가 기준과 이만큼 다르면 **치우친 이유**를 적는다
GAP_BASE = 0.15
#: 🔴 §6 — 재분석에서 배당이 이만큼 움직였으면 "시장 이동"을 적는다
GAP_MOVE = 0.05
#: 🔴 §7 방향 판정 — 세 열 중 둘 이상이 한 팀을 이만큼 앞세우면 그 팀
LEAD = 0.15

#: 🔴🔴 **③ 이 움직인 양**(사용자 지시 2026-10-06(6차) ③) — 마지막 `our_prob` 의 기록
#
#  ⚠️ 글자로 적어 둔 사유를 카드가 **다시 파싱하면** 그 글자가 계약이 된다. 🔴 그래서
#     구조로 남긴다. 한 분석에 `our_prob` 는 한 번 돈다(카드가 그 결과를 쓴다).
MOVES: list[dict] = []

#: 🔴 §5 중복 금지 — ② 가 돌면 결장 계열 변수 무게는 **0**
ABSENCE_TYPES = ("absence", "def_absence", "absence_att", "suspension")
#: 🔴 §5 — ① 이 이미 머금은 성격의 변수는 무게 **절반**
HALF_TYPES = ("strength_gap", "recent_pattern", "h2h_pattern")


def _apply(start: ProbTriple, shift: dict[str, float]) -> ProbTriple:
    """🔴 로그 오즈를 더하고 다시 **합 1** 로 만든다(소프트맥스와 같은 꼴).

    ⚠️ 확률에 바로 더하면 0 밖으로 나가거나 합이 깨진다 — 로그 오즈에서 움직인다.
    """
    import math

    base = {"home": start.home, "draw": start.draw, "away": start.away}
    raw = {}
    for key, p in base.items():
        lo = math.log(max(p, 1e-9) / max(1.0 - p, 1e-9)) + shift.get(key, 0.0)
        raw[key] = math.exp(lo) / (1.0 + math.exp(lo))
    tot = sum(raw.values()) or 1.0
    home = round(raw["home"] / tot, 6)
    draw = round(raw["draw"] / tot, 6)
    return ProbTriple(home=home, draw=draw, away=round(1.0 - home - draw, 6))


def _from_scenarios(hypo: HypoSet | None) -> tuple[ProbTriple | None, str]:
    """🔴 ①② 가 **없는 경기**의 우리 확률 — 시나리오 무게 비율(종전 방식).

    ⚠️ 스코어 단위로 센다(섞인 스코어의 무게를 버리지 않는다 · 5차 ① 실측).
    """
    rows = list(getattr(hypo, "scenarios", []) or [])
    if not rows:
        return None, "시나리오가 없다"
    from app import rules
    tot = {"home": 0.0, "draw": 0.0, "away": 0.0}
    seen = 0.0
    for sc in rows:
        w = float(sc.strength or 0.0)
        pairs = list(sc.outcomes or [])
        if w <= 0 or not pairs:
            continue
        share = w / len(pairs)
        for h, a in pairs:
            said = rules.direction_of([f"{h}-{a}"])
            if said not in tot:
                continue
            tot[said] += share
            seen += share
    if seen <= 0:
        return None, "시나리오 무게가 0 이다"
    home = round(tot["home"] / seen, 6)
    draw = round(tot["draw"] / seen, 6)
    got = ProbTriple(home=home, draw=draw, away=round(1.0 - home - draw, 6))
    return got, f"시나리오 {len(rows)}개 · 스코어 단위 무게 비율(합 {seen:.2f})"


def weight_rules(variables: list[Variable], *, measured: bool
                 ) -> tuple[dict[str, float], list[str]]:
    """🔴🔴 §5 중복 금지 — ② 가 **센 것을 또 세지 않는다**. `(변수별 배수, 사유들)`.

    > ② 가 계산된 경기에서: 결장 계열 변수는 시나리오 driver 로 남되 **무게 0**
    > (②가 이미 셌다). 팀 전력 차·최근 폼은 ① 이 이미 반영한 성격이라 **무게 절반**.

    ⚠️ ② 가 없으면 **사람이 정한 무게표를 그대로** 쓴다(지시서 §4 마지막 줄).
    🔴 카드의 결장 변수 줄 끝에 `[②로 측정: −x%p]` 또는 `[②없음: 무게표 …]` 를 적는다.
    """
    out: dict[str, float] = {}
    notes: list[str] = []
    for v in variables:
        if measured and v.type in ABSENCE_TYPES:
            out[v.id] = 0.0
            notes.append(f"{v.id}({v.type}) 무게 0 — ② 가 이미 셌다")
        elif v.type in HALF_TYPES:
            out[v.id] = 0.5
            notes.append(f"{v.id}({v.type}) 무게 절반 — ① 이 머금은 성격이다")
    return out, notes


def verdict_of(base: BaseProb, ours: ProbTriple | None, market: MarketProb,
               ) -> tuple[str, list[str]]:
    """🔴 §6 — 세 열을 나란히 놓고 **누가 튀는지**. `(판정, 설명들)`.

    판정 글자: `세 열 일치` · `우리만 튄다` · `시장만 튄다` · `세 열 불일치` ·
    `기준 없음` · `시장 없음`.
    """
    said = _market_triple(market)
    if ours is None:
        return "우리 없음", ["우리 확률을 못 만들었다(시나리오 없음)"]
    if base.probs is None and said is None:
        return "기준·시장 없음", [f"기준 없음 — {base.why}", f"시장 없음 — {market.why}"]
    if said is None:
        return "시장 없음", [f"시장 없음 — {market.why}"]
    if base.probs is None:
        return "기준 없음", [f"기준 없음 — {base.why}"]
    lines: list[str] = []
    far_us: list[str] = []
    far_mk: list[str] = []
    for name, key in (("홈승", "home"), ("무", "draw"), ("원정승", "away")):
        b = getattr(base.probs, key)
        o = getattr(ours, key)
        m = getattr(said, key)
        lines.append(f"{name} — 기준 {b:.0%} · 우리 {o:.0%} · 시장 {m:.0%}")
        if abs(o - b) >= GAP_BASE and abs(m - b) < GAP_BASE:
            far_us.append(f"{name} {o - b:+.0%}")
        if abs(m - o) >= GAP_MARKET and abs(m - b) >= GAP_MARKET:
            far_mk.append(f"{name} {m - o:+.0%}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **"튄다"와 "반대"를 가른다**(§6 표현 vs §7 표현)
    # ══════════════════════════════════════════════════════════════════
    #
    #  §6 은 *"우리만 튄다"*(= 수가 많이 다르다 → **이유를 찾는다**)라고 적고,
    #  §7 의 등급 표는 *"우리만 **반대**"*(= 다른 팀을 앞세운다 → **등급 없음**)라고
    #  적는다. 🔴 그 둘은 **다른 상황**이다 — 무승부가 18%p 다른 것과 이기는 팀을
    #  반대로 보는 것을 한 글자로 묶으면 등급이 엉뚱하게 거둬진다.
    #  ⚠️ 그래서 **앞세우는 쪽**(`_leader`)을 따로 본다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시장은 참고용이다**(사용자 지시 2026-10-06(8차) ① — 원칙 수정)
    # ══════════════════════════════════════════════════════════════════
    #
    # > §7 판정 규칙에서 *"시장만 반대 → 한 단계 내림"* 을 **삭제한다.** 시장 열은
    # > **어떤 경우에도 등급·확률을 바꾸지 않는다.** *"우리만 반대"*(기준과 다름)
    # > 규칙만 남긴다 — **기준은 시장이 아니라 우리 데이터다.**
    #
    # ⚠️ 종전 `우리만 반대` 는 *"기준·시장이 같은 쪽"* 일 때만 걸렸다 — 그 조건이
    #    시장을 판정에 끼워 넣고 있었다. 🔴 지금은 **기준 대비**만 본다.
    lead_b, lead_o, lead_m = _leader(base.probs), _leader(ours), _leader(said)
    if lead_o != lead_b:
        return "우리만 반대", lines + [
            f"앞세우는 쪽 — **기준 {lead_b} / 우리 {lead_o}**"
            f"(시장 {lead_m} 는 **참고용** · 판정에 안 쓴다)"]
    if far_us:
        return "우리만 튄다", lines + [f"기준 대비 우리 치우침 — {' · '.join(far_us)}"]
    if far_mk:
        # 🔴 시장이 다른 것은 **우리 판정이 아니다** — 이유 후보만 적는다(②)
        return "시장이 다르다", lines + [
            f"시장이 우리와 다르다 — {' · '.join(far_mk)} · 🔴 등급·확률은 "
            f"**그대로**(시장은 참고용)"]
    return "기준과 맞는다", lines


def _leader(p: ProbTriple | None) -> str:
    """🔴 그 열이 **앞세우는 쪽** — 가장 큰 칸. ⚠️ 없으면 `?`(모른다)."""
    if p is None:
        return "?"
    return max((("home", p.home), ("draw", p.draw), ("away", p.away)),
               key=lambda kv: kv[1])[0]


def tilt_reasons(ours: ProbTriple | None, base: BaseProb, hypo: HypoSet | None,
                 variables: list[Variable], *, measured: bool) -> list[str]:
    """🔴 §5 마지막 — *"우리가 기준보다 X쪽으로 치우친 이유"*.

    > 그 결과 쪽 시나리오 driver 를 **무게 순으로 셋까지**, 각 변수가 ② 로 측정
    > 가능한 종류인지 표시. 측정 가능한 종류인데 ② 가 작게 잡았으면 **무게표가
    > 과하다는 신호**다.
    """
    if ours is None or base.probs is None:
        return []
    out: list[str] = []
    from app import rules
    by_id = {v.id: v for v in variables}
    for name, key, want in (("홈승", "home", "home"), ("무", "draw", "draw"),
                            ("원정승", "away", "away")):
        gap = getattr(ours, key) - getattr(base.probs, key)
        if abs(gap) < GAP_BASE:
            continue
        rows = [sc for sc in (getattr(hypo, "scenarios", []) or [])
                if rules.direction_of([f"{a}-{b}" for a, b in sc.outcomes]) == want]
        rows.sort(key=lambda s: -float(s.strength or 0.0))
        said: list[str] = []
        for sc in rows[:3]:
            for vid in sc.driver_vars[:2]:
                v = by_id.get(vid)
                if v is None or vid in [x.split()[0] for x in said]:
                    continue
                tag = "②로 측정 가능" if v.type in ABSENCE_TYPES else "②가 못 재는 종류"
                said.append(f"{vid}({v.type} · {tag})")
        out.append(f"{name} {gap:+.0%} — 치우친 이유: "
                   + (" · ".join(said[:3]) or "driver 를 못 찾았다")
                   + ("" if measured else " · ⚠️ ② 가 없어 무게표를 그대로 썼다"))
    return out


def market_reasons(base: BaseProb, adj: AdjProb, market: MarketProb,
                   variables: list[Variable], ref: MatchRef,
                   *, ours: ProbTriple | None = None) -> list[str]:
    """🔴 §6-4 — *"시장이 우세로 보는 쪽의 근거 후보"* 를 ①② 에서 뽑는다.

    각 후보가 **우리 변수에 들어 있는지**(있음/없음/무게 낮음) 적는다.

    🔴🔴 **근거 검열**(사용자 지시 2026-10-11 ④): `ours` 를 주면 *"우리 판단
    유지"* 의 근거가 **우리 결론과 같은 방향**인지 본다 — 아니면 그 문장을 내지
    않고 *"근거 부족 — 시장과 갈림"* 으로 적는다.
    """
    said = _market_triple(market)
    if said is None:
        return []
    side = "home" if said.home >= said.away else "away"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ④ **우리 결론의 방향** — 인용 근거는 이 방향과 같아야 한다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 인용 근거의 방향이 우리 결론과 같아야 한다. 우세 팀의 결장·상대 우세
    #  > 맞대결을 우세 근거로 쓰면 **실패**. 같은 방향 근거가 없으면 "우리 판단
    #  > 유지"를 내지 않고 **"근거 부족 — 시장과 갈림"** 으로 적는다.
    #
    #  ⚠️ 실사고 2026-10-11(LAFC–밴쿠버): 우리 수는 **밴쿠버(원정) 43%** 였는데
    #     카드는 *"우리 판단 유지 — 근거: IR02-home(LAFC 결장)"* 을 적었다. 그
    #     결장은 **밴쿠버 쪽을 미는** 사실이므로 "LAFC 가 낫다"의 근거가 될 수
    #     없다. 🔴 그래서 `favors` 가 **우리 쪽**인 변수만 근거로 쓴다.
    #  🔴 `ours` 를 못 받으면 **시장이 미는 쪽의 반대**를 우리 결론으로 본다
    #     (갈림이 있다는 전제 — 그 사실을 사유에 적는다).
    mine = ("home" if float(ours.home) >= float(ours.away) else "away"
            ) if ours is not None else ("away" if side == "home" else "home")
    name = ref.home_name if side == "home" else ref.away_name
    out: list[str] = []
    has = {v.type for v in variables}
    weak = {v.type for v in variables if v.weight and v.weight < 1.0}

    def _in(kinds: tuple[str, ...]) -> str:
        if any(k in has for k in kinds):
            return "무게 낮음" if any(k in weak for k in kinds) else "있음"
        return "없음"

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이유 후보와 "우리 정보에 있나"만 적는다**(8차 ②)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 시장과 차이가 나면 카드에 *"시장이 다르게 보는 이유 후보"* 와 *"우리 정보에
    # > 있나(있음/없음)"* **만** 적는다. 이유를 찾았는데 **우리 판단 근거가 더 강하면**
    # > *"우리 판단 유지 — 근거: …"* 로 적는다.
    #
    # 🔴 이 목록은 **설명**이고, 어떤 수도 바꾸지 않는다(①).
    found: list[str] = []
    if base.dr is not None:
        said_in = _in(("strength_gap",))
        # 🔴 ④ — Elo 가 **우리와 같은 방향**이면 *"시장이 다르게 보는 까닭"* 이
        #    아니다(우리 편인 사실을 시장의 근거로 적는 것은 거짓이다)
        elo_side = "home" if float(base.dr) > 0 else "away"
        agrees = (elo_side == mine)
        out.append(f"Elo 차 {base.dr:+.0f}점({base.home_elo:.0f} vs "
                   f"{base.away_elo:.0f}) — 우리 정보에: **{said_in}**"
                   + (f" · 🔴 방향은 **우리와 같다**({elo_side}) — 시장이 "
                      f"다르게 보는 까닭이 아니다" if agrees else ""))
        if said_in == "없음" and not agrees:
            found.append("Elo 차")
    if adj.strength_pct:
        got = " · ".join(f"{k} {v:+.1f}%" for k, v in adj.strength_pct.items())
        said_in = _in(ABSENCE_TYPES)
        out.append(f"라인업 전력 {got} — 우리 정보에: **{said_in}**")
        if said_in == "없음":
            found.append("라인업 전력")
    said_in = _in(("home_field",))
    out.append(f"홈 — 우리 정보에: **{said_in}**")
    # 🔴 **우리 근거가 더 강한가** — 우리 쪽을 민 변수 중 `hard`·근거 가능한 것을 센다
    # 🔴 ④ — **우리 결론과 같은 방향**인 hard 근거만 센다(반대 방향은 근거가 아니다)
    strong = [v for v in variables
              if v.hardness == "hard" and v.usable_as_basis
              and v.favors == mine]
    against = [v for v in variables
               if v.hardness == "hard" and v.usable_as_basis
               and v.favors in ("home", "away") and v.favors != mine]
    if against:
        out.append(f"⚠️ 반대 방향 근거 {len(against)}건은 **우리 근거로 쓰지 "
                   f"않았다**(④ 검열): "
                   + " · ".join(f"`{v.id}`({v.type}·{v.favors} 쪽)"
                                for v in against[:3]))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ④ **"유지"는 같은 방향 근거가 있을 때만** — 사용자 지시 2026-10-11 ④
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 같은 방향 근거가 없으면 "우리 판단 유지"를 내지 않고 **"근거 부족 —
    #  > 시장과 갈림"** 으로 적는다.
    #
    #  ⚠️ 그래서 *"시장이 앞세우는 까닭이 우리 정보에 다 들어 있다"* 도 **혼자서는
    #     근거가 아니다**(그것은 "새 사실이 없다"는 말이지 "우리 쪽이 낫다"는
    #     근거가 아니다 — 실사고 2026-10-11 의 그 문장이다).
    who = ref.home_name if mine == "home" else ref.away_name
    if strong:
        out.append(f"🔴 **우리 판단 유지**(우리 결론 **{who}** 쪽) — 근거: "
                   + " · ".join(f"`{v.id}`({v.type}·{v.hardness}·무게 {v.weight})"
                                for v in strong[:3])
                   + (f" — 시장이 다르게 보는 까닭({', '.join(found)})은 우리 "
                      f"정보에 없지만, 위 근거가 **인용까지 검증된 사실**이다"
                      if found else
                      " — 그리고 시장이 앞세우는 까닭은 우리 정보에 **다 들어 "
                      "있다**(새 사실이 없다)"))
    else:
        out.append(f"🔴 **근거 부족 — 시장과 갈림**: 우리 결론은 **{who}** 쪽인데"
                   f" 그 방향의 `hard` 근거가 **없다**"
                   + (f"(반대 방향 근거만 {len(against)}건)" if against else "")
                   + (f" · 시장이 다르게 보는 까닭({', '.join(found)})도 우리 "
                      f"정보에 없다" if found else
                      " · 시장이 앞세우는 까닭은 우리 정보에 다 들어 있다")
                   + " · 🔴 그래도 등급·확률은 **그대로 둔다**(시장은 참고용) · "
                     "다음 재분석에서 그 사실을 찾아본다")
    return [f"시장은 **{name}** 쪽을 앞세운다({max(said.home, said.away):.0%}) — "
            f"🔴 **참고용**(판정에 안 쓴다)"] + out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`grade_step` 을 지웠다** — 지시서 2026-10-11 F4
# ══════════════════════════════════════════════════════════════════
#
#  > `compare.grade_step` 에서 시장(V6) 입력 삭제 · `s7_judge` 의 `_lower`
#  > (세 열 규칙) 삭제. 등급 조정은 ⑫ 검증 규칙만.
#
#  🔴 그 함수는 **세 열 규칙** 자체였다(표의 절반이 시장이었다). 등급을 내리는
#     자리는 이제 `pipeline._grade_by_check` 하나이고, 그 입력은 ⑫ 검증의
#     `grade_move` 다. ⚠️ 세 열 **비교**(`verdict_of`)는 남는다 — 카드 표시용이다.

def direction_line(base: BaseProb, ours: ProbTriple | None, market: MarketProb,
                   ref: MatchRef) -> str:
    """🔴 §7 방향 판정 — 세 열의 홈승·원정승을 **다 적고**, 둘 이상이 한 팀을
    `LEAD`(0.15) 이상 앞세우면 그 팀. 아니면 *"반반, 기울기 …"*.
    """
    cols: list[tuple[str, ProbTriple]] = []
    if base.probs is not None:
        cols.append(("기준", base.probs))
    if ours is not None:
        cols.append(("우리", ours))
    said = _market_triple(market)
    if said is not None:
        cols.append(("시장", said))
    if not cols:
        return "방향: 못 정한다 — 세 열이 다 비었다"
    body = " · ".join(f"{nm} 홈 {p.home:.0%}/원정 {p.away:.0%}" for nm, p in cols)
    votes = {"home": 0, "away": 0}
    for _, p in cols:
        if p.home - p.away >= LEAD:
            votes["home"] += 1
        elif p.away - p.home >= LEAD:
            votes["away"] += 1
    for side, n in votes.items():
        if n >= 2:
            who = ref.home_name if side == "home" else ref.away_name
            return f"방향: **{who}** (세 열 중 {n}열이 0.15 이상 앞세운다) — {body}"
    return f"방향: **반반**(0.15 이상 앞세운 열이 2개 미만) — 기울기: {body}"


def moved(before: MarketProb, now: MarketProb) -> list[str]:
    """🔴 §6 배당 움직임 — 같은 마켓이 `GAP_MOVE`(5%p) 이상 움직였으면 적는다."""
    out: list[str] = []
    for key, val in (now.probs or {}).items():
        old = (before.probs or {}).get(key)
        if old is None:
            continue
        if abs(val - old) >= GAP_MOVE:
            out.append(f"시장 이동: {key} {old:.0%}→{val:.0%}")
    return out


def _market_triple(market: MarketProb) -> ProbTriple | None:
    """🔴 시장 승무패 셋 — 하나라도 없으면 `None`(지어내지 않는다)."""
    from app.core.odds import key_of
    got = [(market.probs or {}).get(key_of("win", s))
           for s in ("home", "draw", "away")]
    if any(v is None for v in got):
        return None
    tot = sum(float(v) for v in got)                        # type: ignore[arg-type]
    if tot <= 0:
        return None
    home = round(float(got[0]) / tot, 6)                    # type: ignore[arg-type]
    draw = round(float(got[1]) / tot, 6)                    # type: ignore[arg-type]
    return ProbTriple(home=home, draw=draw, away=round(1.0 - home - draw, 6))


def _low_block(team: str, variables: list[Variable], *,
               ref: MatchRef | None = None) -> bool:
    """🔴 그 팀이 **5백·3센터백**으로 나오나(IR01) — 7차 §4 의 "한 번 더" 조건.

    🔴 **열쇠로 센다**(이름이 claim 에 있는지 보지 않는다) — 경우의 수는 팀 **이름**을
       쓰고 변수는 **열쇠**를 쓰므로 `ref` 로 옮겨 맞춘다.
    ⚠️ 실측 2026-10-06: claim 글자에 팀 이름이 없으면 ×2 가 **조용히 빠졌다**.
       🔴 `ref` 가 없을 때만 옛 길(글자 비교)로 떨어진다.
    """
    want = norm_name(team)
    for v in variables:
        if not _is_low_block_var(v):
            continue
        if ref is not None:
            if norm_name(_team_in(v, ref)) == want:
                return True
            continue
        if want and (want in norm_name(v.claim) or want in norm_name(v.quote)):
            return True
    return False


def norm_name(said: str) -> str:
    """🔴 팀 이름 비교용 — 경우의 수는 **이름**으로, 변수는 **열쇠**로 온다."""
    from app.core.stages.s5_verify import norm
    return norm(str(said or ""))


def _is_low_block_var(v: Variable) -> bool:
    """🔴 그 변수가 **5백 선언**(IR01)인가 — 규칙 id 로 센다(글자 추측 없이)."""
    return v.type == "lineup_intent" and str(v.from_rule or "").startswith("IR01")


def _team_in(v: Variable, ref: MatchRef | None) -> str:
    """🔴 그 변수가 말하는 팀의 **이름** — 열쇠를 이름으로 바꾼다(경우의 수와 맞춘다)."""
    if ref is None:
        return ""
    if str(v.subject) == str(ref.home):
        return ref.home_name
    if str(v.subject) == str(ref.away):
        return ref.away_name
    return ""


def _strategy_moves(strategy: object, ref: MatchRef | None) -> list[dict]:
    """🔴🔴 §3-2 — 전략 판정 → **③ 이동 줄들**. 판정이 없으면 빈 목록.

    한 줄 꼴은 `MOVES` 와 같다(`id`·`type`·`favors`·`side`·`weight`·`logodds`) —
    카드 7b 의 *"③ 이 움직인 양"* 이 그 목록을 그대로 적는다.

    🔴 `own_win`·`own_loss`·`draw` 를 **그 팀 자리로** 옮긴다: 홈 팀의 `own_win` 은
       `home`, `own_loss` 는 `away`(상대가 이긴다는 뜻이다), `draw` 는 `draw`.
    ⚠️ **판정이 `통과` 가 아니면 아무것도 안 움직인다**(버려진 판정·확정 XI 전).
    """
    from app.core import strategy as _st
    if str(getattr(strategy, "audit", "") or "") != "통과":
        return []
    out: list[dict] = []
    for line in (getattr(strategy, "lines", None) or []):
        side = str(getattr(line, "side", ""))
        said = str(getattr(line, "strategy", ""))
        box, why = _st.move_of(said)
        if not box:
            continue
        other = "away" if side == "home" else "home"
        for key, where in (("own_win_logodds", side),
                           ("own_loss_logodds", other),
                           ("draw_logodds", "draw")):
            step = float(box.get(key) or 0.0)
            if step == 0.0 or where not in ("home", "draw", "away"):
                continue
            out.append({"id": f"전략:{side}", "type": "strategy_intent",
                        "favors": ("both" if where == "draw" else where),
                        "side": where, "weight": 1.0,
                        "logodds": round(step, 4), "why": why,
                        "strategy": said})
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`our_prob()` 을 지웠다** — 상성 엔진 지시서 §2·C7(2026-10-10 여섯째)
# ══════════════════════════════════════════════════════════════════
#
#  > 변수가 로그 오즈를 직접 미는 ③ 이동 경로(k=0.15·mover 목록·이동 상한)를
#  > **확률 경로에서 뺀다** → 변수는 V-3 배치표대로 ①②③에.
#  > C7 변수가 확률에 닿는 길은 **① 상성 축뿐**이다(로그 오즈 직접 이동 코드 0).
#
#  🔴 우리 열은 이제 **S3**(`app/core/probmodel.py`)이 낸다 — 상성 축 넷이 λ 를
#     정하고 시뮬이 승무패로 바꾼다.
#  ⚠️ 이 파일에 남은 것은 **세 열 비교·기울기 사유·시장 사유·무게 규칙**이다
#     (그것들은 확률을 만들지 않는다).
