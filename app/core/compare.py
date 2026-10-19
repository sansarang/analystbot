"""🔴🔴 **③ 우리 확률 · 두 열 비교 · 이유 찾기** — 네 층 지시서 §5·§6·§7.

## 두 열은 **섞지 않는다**

> 카드의 열: 기준(데이터) · 우리(분석). 둘을 합쳐 **한 숫자로 만들지 않는다** —
> 나란히 놓고 차이를 설명한다.

🔴🔴 **시장(배당) 열은 걷혔다 — 사용자 지시 2026-10-19**
> 시장배당은 **아예 쓰지도 않는다.**

⚠️ 종전 이 파일은 세 열이었고(`기준·우리·시장`) 시장 열이 하는 일이 둘 더 있었다 —
   *"누가 튀는지"* 판정에 시장을 끼우는 것과, *"시장이 우세로 보는 쪽의 근거
   후보"*(`market_reasons`)를 뽑는 것. 🔴 둘 다 지웠다(`moved`·`_market_triple`
   도 함께). 남은 일은 둘이다:
   ① 두 열의 차이를 재고 **우리가 튀는지** 가른다(`verdict_of`)
   ② 우리가 기준과 다르면 **치우친 이유**를 뽑는다(`tilt_reasons`)

🔴 **금지**(§6 마지막 · §7): 기대값·금액 · 등급을 이 규칙으로 **올리기**.
"""
from __future__ import annotations

import logging

from app.core.schema import (AdjProb, BaseProb, HypoSet, MatchRef,
                             ProbTriple, Variable)

logger = logging.getLogger(__name__)

#: 🔴 §5 마지막 — 우리가 기준과 이만큼 다르면 **치우친 이유**를 적는다
GAP_BASE = 0.15
#: 🔴 §7 방향 판정 — 두 열 중 둘 다 한 팀을 이만큼 앞세우면 그 팀
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


# ⚠️ **`_from_scenarios` 는 지웠다** — 시나리오 무게로 우리 확률을 만들던
#    길이다(§1 처분). 🔴 우리 확률은 ⑯ 격자 하나에서 온다.
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


def verdict_of(base: BaseProb, ours: ProbTriple | None,
               ) -> tuple[str, list[str]]:
    """🔴 §6 — 두 열을 나란히 놓고 **우리가 튀는지**. `(판정, 설명들)`.

    판정 글자: `두 열 일치` · `우리만 튄다` · `우리 없음` · `기준 없음`.
    ⚠️ 종전 글자 중 `시장만 튄다`·`세 열 불일치`·`시장 없음` 은 **걷혔다**
       (2026-10-19 — 시장 열이 없다).
    """
    if ours is None:
        return "우리 없음", ["우리 확률을 못 만들었다(시나리오 없음)"]
    if base.probs is None:
        return "기준 없음", [f"기준 없음 — {base.why}"]
    lines: list[str] = []
    far_us: list[str] = []
    for name, key in (("홈승", "home"), ("무", "draw"), ("원정승", "away")):
        b = getattr(base.probs, key)
        o = getattr(ours, key)
        lines.append(f"{name} — 기준 {b:.0%} · 우리 {o:.0%}")
        if abs(o - b) >= GAP_BASE:
            far_us.append(f"{name} {o - b:+.0%}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **"튄다"와 "반대"를 가른다**(§6 표현 vs §7 표현)
    # ══════════════════════════════════════════════════════════════════
    #
    #  §6 은 *"우리만 튄다"*(= 수가 많이 다르다 → **이유를 찾는다**)라고 적고,
    #  §7 의 등급 표는 *"우리만 **반대**"*(= 다른 팀을 앞세운다 → **등급 없음**)라고
    #  적는다. 🔴 그 둘은 **다른 상황**이다 — 무승부가 18%p 다른 것과 이기는 팀을
    #  반대로 보는 것을 한 글자로 묶으면 등급이 엉뚱하게 거둬진다.
    #  ⚠️ 그래서 **앞세우는 쪽**(`_leader`)을 따로 본다.
    #
    # 🔴 **기준은 시장이 아니라 우리 데이터다** — 종전에도 판정은 *"기준 대비"*
    #    하나였고(2026-10-06(8차) ①: *"시장 열은 어떤 경우에도 등급·확률을 바꾸지
    #    않는다"*), 시장은 글자에만 따라붙었다. ⚠️ 그 글자도 걷혔다(2026-10-19).
    lead_b, lead_o = _leader(base.probs), _leader(ours)
    if lead_o != lead_b:
        return "우리만 반대", lines + [
            f"앞세우는 쪽 — **기준 {lead_b} / 우리 {lead_o}**"]
    if far_us:
        return "우리만 튄다", lines + [f"기준 대비 우리 치우침 — {' · '.join(far_us)}"]
    return "기준과 맞는다", lines


def _leader(p: ProbTriple | None) -> str:
    """🔴 그 열이 **앞세우는 쪽** — 가장 큰 칸. ⚠️ 없으면 `?`(모른다)."""
    if p is None:
        return "?"
    return max((("home", p.home), ("draw", p.draw), ("away", p.away)),
               key=lambda kv: kv[1])[0]


def tilt_reasons(ours: ProbTriple | None, base: BaseProb,
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
        # 🔴🔴 **시나리오 driver 가 없다**(§1 처분 2026-10-12 셋째) — 그래서
        #    *"그 쪽 변수"* 를 **방향으로** 고른다(무게 큰 것부터 셋).
        #  ⚠️ 종전에는 그 쪽 시나리오의 `driver_vars` 를 읽었다.
        pick = sorted((v for v in variables if v.favors == want),
                      key=lambda v: -float(getattr(v, "weight", 0.0) or 0.0))
        said: list[str] = []
        for v in pick[:3]:
            tag = "②로 측정 가능" if v.type in ABSENCE_TYPES else "②가 못 재는 종류"
            said.append(f"{v.id}({v.type} · {tag})")
        out.append(f"{name} {gap:+.0%} — 치우친 이유: "
                   + (" · ".join(said[:3]) or "driver 를 못 찾았다")
                   + ("" if measured else " · ⚠️ ② 가 없어 무게표를 그대로 썼다"))
    return out


def direction_line(base: BaseProb, ours: ProbTriple | None,
                   ref: MatchRef) -> str:
    """🔴 §7 방향 판정 — 두 열의 홈승·원정승을 **다 적고**, 둘 다 한 팀을
    `LEAD`(0.15) 이상 앞세우면 그 팀. 아니면 *"반반, 기울기 …"*.

    ⚠️ 종전에는 **세 열**(기준·우리·시장)이었다 — 시장 열은 걷혔다(2026-10-19).
    """
    cols: list[tuple[str, ProbTriple]] = []
    if base.probs is not None:
        cols.append(("기준", base.probs))
    if ours is not None:
        cols.append(("우리", ours))
    if not cols:
        return "방향: 못 정한다 — 두 열이 다 비었다"
    body = " · ".join(f"{nm} 홈 {p.home:.0%}/원정 {p.away:.0%}" for nm, p in cols)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **열이 하나면 그 열로 정한다**(예측 지시 2026-10-13 §0)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 배당·시장 확률 쓰지 않는다 … **결론은 봇 확률(%)만으로**.
    #
    #  ⚠️ 실측 2026-10-13(ACL 세 경기): 기준(Elo)도 시장도 없어 열이 **우리
    #     하나**였고, *"둘 이상이 앞세운다"* 는 규칙은 그때 **절대 만족되지
    #     않는다** → 늘 `반반` 이다(게다가 `pipeline._direction` 이 아예 안 돌아
    #     방향 줄이 **빈 글자**였고 카드가 *"결함"* 을 찍었다).
    #  🔴 한 열뿐이면 그 열의 `LEAD`(0.15) 차로 정하고, **열이 하나라는 사실을
    #     글자에 적는다**(두 열이 동의한 것처럼 보이지 않게).
    #  ⚠️ 시장 열이 걷힌 뒤로 **열은 많아야 둘**이다 — 기준(Elo)이 없는 경기는
    #     늘 이 한 열 길로 간다(실측 ACL 이 그랬다).
    if len(cols) == 1:
        nm, one = cols[0]
        if one.home - one.away >= LEAD:
            return (f"방향: **{ref.home_name}** ({nm} 열 **하나**가 0.15 이상 "
                    f"앞세운다 · 다른 열이 없다) — {body}")
        if one.away - one.home >= LEAD:
            return (f"방향: **{ref.away_name}** ({nm} 열 **하나**가 0.15 이상 "
                    f"앞세운다 · 다른 열이 없다) — {body}")
        return (f"방향: **반반**({nm} 열 **하나**뿐이고 0.15 미만이다) — "
                f"기울기: {body}")
    votes = {"home": 0, "away": 0}
    for _, p in cols:
        if p.home - p.away >= LEAD:
            votes["home"] += 1
        elif p.away - p.home >= LEAD:
            votes["away"] += 1
    for side, cnt in votes.items():
        if cnt >= 2:
            who = ref.home_name if side == "home" else ref.away_name
            return f"방향: **{who}** (두 열이 다 0.15 이상 앞세운다) — {body}"
    return f"방향: **반반**(0.15 이상 앞세운 열이 2개 미만) — 기울기: {body}"


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
