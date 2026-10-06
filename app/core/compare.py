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


def move_rules() -> dict:
    """🔴 ① 이동 규칙 표 — `config/interpret_rules.yaml` 의 `our_prob` 하나다."""
    from app import rules
    return dict((rules._load("config/interpret_rules.yaml")
                 .get("our_prob") or {}))


def our_prob(hypo: HypoSet | None, *, start: ProbTriple | None = None,
             variables: list[Variable] | None = None,
             adjusted: bool = False, ref: MatchRef | None = None
             ) -> tuple[ProbTriple | None, str]:
    """🔴🔴 ③ 우리 확률 — **기준에서 출발한다**(사용자 지시 2026-10-06(6차) ①).

    ══════════════════════════════════════════════════════════════════
    🔴 바뀐 것 — 시나리오 비율이 **출발점이 아니다**
    ══════════════════════════════════════════════════════════════════

    > OurProb = ①②의 `AdjProb` 를 **출발점**으로, ③ 변수 중 ① 이 이미 반영하지 않는
    > 종류만 **로그 오즈**를 움직인다. 이동량 = **변수 무게 × k**(k=config, 초기 0.15),
    > 한 결과의 총 이동은 **±0.5 로그 오즈** 상한.
    > ①②가 없는 경기만 **지금의 시나리오 비율**을 쓰고 카드에 *"기준 없음 — 시나리오
    > 비율"* 표시.

    🔴 어느 쪽으로 움직이나 — 변수의 `favors` 가 말한다(`home`·`away`·`both`).
       ⚠️ `both` 는 **무승부 쪽**으로 본다(양쪽에 다 유리하다는 말은 승자를 가리지
          않는다는 뜻이다). 🔴 `goals` 는 승무패를 안 움직인다(총점 마켓의 말이다).
    ⚠️ 시나리오 세트·생존 판정은 **그대로다** — 이 함수는 **카드의 우리 열**과 방향
       판정에만 쓰인다(지시서 ① 마지막 줄).
    """
    box = move_rules()
    if start is None:
        got, why = _from_scenarios(hypo)
        return got, (f"**기준 없음 — 시나리오 비율**({why})" if got else why)
    k = float(box.get("k") or 0.15)
    cap = float(box.get("cap_logodds") or 0.5)
    movers = {str(x) for x in (box.get("movers") or [])}
    skip = {str(x) for x in (box.get("skip") or [])}
    if adjusted:
        skip |= {str(x) for x in (box.get("skip_when_adjusted") or [])}
    shift = {"home": 0.0, "draw": 0.0, "away": 0.0}
    used: list[str] = []
    MOVES.clear()
    for v in (variables or []):
        if v.type in skip or v.type not in movers:
            continue
        step = float(v.weight or 0.0) * k
        if step <= 0:
            continue
        side = {"home": "home", "away": "away", "both": "draw"}.get(v.favors)
        if side is None:
            continue
        shift[side] += step
        used.append(f"{v.id}({v.type}·{v.favors}·{step:+.3f})")
        # 🔴 카드 7b 의 *"③ 이 움직인 양"* 줄이 이 목록을 그대로 적는다(지시 ③)
        MOVES.append({"id": v.id, "type": v.type, "favors": v.favors,
                      "side": side, "weight": float(v.weight or 0.0),
                      "logodds": round(step, 4)})
    # 🔴 **상한**(±0.5 로그 오즈) — 한 결과가 통째로 뒤집히지 않게
    capped = {k2: max(-cap, min(cap, val)) for k2, val in shift.items()}
    hit = [k2 for k2, val in shift.items() if abs(val) > cap]
    got = _apply(start, capped)
    why = (f"기준({start.home:.0%}/{start.draw:.0%}/{start.away:.0%})에서 출발 · "
           f"이동 {len(used)}개(k={k})"
           + (f" · 🔴 상한 ±{cap} 에 닿은 결과 {hit}" if hit else "")
           + (f" · {' '.join(used[:4])}" if used else " · **움직인 변수 없음**"))
    return got, why


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
    lead_b, lead_o, lead_m = _leader(base.probs), _leader(ours), _leader(said)
    if lead_o != lead_b and lead_b == lead_m:
        return "우리만 반대", lines + [f"앞세우는 쪽 — 기준·시장 {lead_b} / 우리 {lead_o}"]
    if lead_m != lead_o and lead_o == lead_b:
        return "시장만 반대", lines + [f"앞세우는 쪽 — 기준·우리 {lead_b} / 시장 {lead_m}"]
    if far_us and far_mk:
        return "세 열 불일치", lines + [f"우리 치우침 {far_us} · 시장 치우침 {far_mk}"]
    if far_us:
        return "우리만 튄다", lines + [f"기준 대비 우리 치우침 — {' · '.join(far_us)}"]
    if far_mk:
        return "시장만 튄다", lines + [f"우리 대비 시장 치우침 — {' · '.join(far_mk)}"]
    return "세 열 일치", lines


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
                   variables: list[Variable], ref: MatchRef) -> list[str]:
    """🔴 §6-4 — *"시장이 우세로 보는 쪽의 근거 후보"* 를 ①② 에서 뽑는다.

    각 후보가 **우리 변수에 들어 있는지**(있음/없음/무게 낮음) 적는다.
    """
    said = _market_triple(market)
    if said is None:
        return []
    side = "home" if said.home >= said.away else "away"
    name = ref.home_name if side == "home" else ref.away_name
    out: list[str] = []
    has = {v.type for v in variables}
    weak = {v.type for v in variables if v.weight and v.weight < 1.0}

    def _in(kinds: tuple[str, ...]) -> str:
        if any(k in has for k in kinds):
            return "무게 낮음" if any(k in weak for k in kinds) else "있음"
        return "없음"

    if base.dr is not None:
        out.append(f"Elo 차 {base.dr:+.0f}점({base.home_elo:.0f} vs "
                   f"{base.away_elo:.0f}) — 우리 변수: {_in(('strength_gap',))}")
    if adj.strength_pct:
        got = " · ".join(f"{k} {v:+.1f}%" for k, v in adj.strength_pct.items())
        out.append(f"라인업 전력 {got} — 우리 변수: {_in(ABSENCE_TYPES)}")
    out.append(f"홈 — 우리 변수: {_in(('home_field',))}")
    return [f"시장은 **{name}** 쪽을 앞세운다({max(said.home, said.away):.0%})"] + out


def grade_step(verdict: str, *, found_new: bool) -> tuple[int, str]:
    """🔴🔴 §7 — 세 열 규칙은 **등급을 내리기만** 한다. `(내릴 칸 수, 사유)`.

    | 상황 | 등급 | 사유 |
    |---|---|---|
    | 세 열 일치 | 유지 | `세 열 일치` |
    | 우리만 반대 | **없음** | `우리만 반대 — 치우친 이유` |
    | 시장만 반대 · 이유 못 찾음 | **한 단계 내림** | `시장만 반대 — 이유 못 찾음` |
    | 시장만 반대 · 새 사실 | 재판정 | `시장 반대 → 새 사실` |
    | 기준 없음 | 우리·시장 둘로 같은 규칙 | `기준 없음` |
    | 시장 없음 | 기존 판정 그대로 | `시장 없음 — 사유` |

    🔴 돌아오는 수는 **0 이상**이다 — 올리는 길이 없다(계약이 그것을 센다).
    """
    if verdict == "우리만 반대":
        return 99, "우리만 반대(기준·시장은 같은 쪽) — 등급 **없음**(§7)"
    if verdict == "시장만 반대":
        if found_new:
            return 0, "시장 반대 → 새 사실을 반영해 다시 판정했다(§7)"
        return 1, "시장만 반대 — 이유 못 찾음(한 단계 내림 · §7)"
    if verdict == "세 열 불일치":
        return 1, "세 열 불일치 — 두 이유 블록을 본다(§7)"
    # 🔴 **"튄다"는 등급을 건드리지 않는다** — §6 은 이유를 찾으라 했고, §7 의 등급
    #    표는 *"반대"* 일 때만 내린다. ⚠️ 이 구분이 없으면 무승부 18%p 차이로 등급이
    #    사라진다(실측 2026-10-06 한국–우즈벡).
    if verdict in ("우리만 튄다", "시장만 튄다", "세 열 일치"):
        return 0, verdict
    return 0, verdict


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
