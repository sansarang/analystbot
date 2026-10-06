"""🔴🔴 **s2b — ① 기준 확률 + ② 라인업 보정.** 네 층 지시서 §3·§4.

```
MatchRef + Facts → (BaseProb, AdjProb)
```

🔴 **LLM 을 부르지 않는다**(§1). 🔴 **실행 중 적합하지 않는다**(§3-2 · 계수는 config).
⚠️ 한 층이 못 돌아도 다른 층을 막지 않는다 — 못 만든 층은 `why` 를 들고 빈 채로 간다.
"""
from __future__ import annotations

import logging
from datetime import date

from app.core import base
from app.core.schema import AdjProb, BaseProb, Facts, LineupDelta, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 등급표를 하루에 한 번만 받는다(§3 캐시) — `{날짜: 표}`
_CACHE: dict[str, dict[str, float]] = {}


async def run(ref: MatchRef, facts: Facts, *, state: RunState, net,
              when: date | None = None) -> tuple[BaseProb, AdjProb]:
    """🔴 ①② 를 만든다. ⚠️ 못 만든 사유는 **전부 `why` 에** 남는다(조용한 0 금지)."""
    got = await _base(ref, facts, state=state, net=net, when=when)
    said = _adjust(ref, facts, got, state=state)
    return got, said


async def _base(ref: MatchRef, facts: Facts, *, state: RunState, net,
                when: date | None) -> BaseProb:
    """🔴 ① — eloratings 등급 → 승·무·패. ⚠️ 축구가 아니면 **안 만든다**."""
    from app import rules
    from app.collect import elo
    from app.core.stages.s5_verify import comp_kind
    kind = comp_kind(ref, facts)
    if ref.sport != "soccer":
        return BaseProb(why=f"종목이 `{ref.sport}` 다 — ① 은 축구만(§0 범위)",
                        comp_kind=kind)
    neutral, why_n = rules.neutral_venue(ref.competition)
    day = (when or date.today()).isoformat()
    table = _CACHE.get(day)
    source = "eloratings.net"
    if table is None:
        table, why = await elo.ratings(net, when=when or date.today())
        if not table:
            state.note(f"s2b ① 등급표를 못 받았다 — {why}")
            return BaseProb(why=f"기준 없음 — {why}", comp_kind=kind,
                            source=source, data_date=day)
        _CACHE[day] = table
        state.note(f"s2b ① 등급표 {why}")
    home, away = _code_of(ref.home), _code_of(ref.away)
    got = base.base_prob(kind=kind,
                         home_elo=table.get(home) if home else None,
                         away_elo=table.get(away) if away else None,
                         neutral=bool(neutral), source=source, data_date=day)
    if got.probs is None:
        state.note(f"s2b ① 기준 없음 — {got.why}"
                   + (f"(중립 판정: {why_n})" if neutral else ""))
    else:
        state.note(f"s2b ① 홈 {got.home_elo:.0f} · 원정 {got.away_elo:.0f} · "
                   f"dr {got.dr:+.0f} → 홈 {got.probs.home:.3f} 무 "
                   f"{got.probs.draw:.3f} 원정 {got.probs.away:.3f} · {got.why}")
    return got


def _code_of(key: str) -> str:
    """🔴 팀 열쇠 → **ISO2 코드**. ⚠️ 이름표에 코드가 없으면 빈 글자(대표팀이 아니다).

    🔴 `_from_cldr` 이 대표팀 이름표에 `iso:KR` 을 붙여 뒀다 — 그것을 그대로 쓴다
       (나라 이름 표를 여기 베끼지 않는다 · #1).
    """
    from app import teamref
    box = teamref.registry().teams.get(str(key))
    if box is None:
        return ""
    for names in box.names.values():
        for nm in names:
            if teamref.is_code(nm) and nm.startswith("iso:"):
                return nm.split(":", 1)[1].upper()
    return ""


def usual_sample(facts: Facts) -> int:
    """🔴 §4-1 — 평소 XI 를 센 **경기 수**. ⚠️ 지금은 0 또는 1 이다.

    🔴 `facts.last_xi` 는 **직전 경기 하나**만 든다(`_follow_once` 가 링크를 한 번
       따라간다 · 사용자 지시 2026-10-06(3차) ⑦). 그래서 §4-1 의 *"최근 5경기 선발
       빈도 상위 11명"* 을 만들 재료가 아직 **모자란다**.
    ⚠️ 그 사실을 숫자로 돌려주고, 판단은 `_adjust` 가 한다(조용히 넘기지 않는다).
    """
    return 1 if any((v.lineup or v.players) for v in (facts.last_xi or {}).values()) else 0


def _adjust(ref: MatchRef, facts: Facts, got: BaseProb, *,
            state: RunState) -> AdjProb:
    """🔴 ② — 오늘 XI 가 평소 XI 보다 얼마나 약/강한가(§4).

    ⚠️ **평소 XI 표본이 3경기 미만이면 건너뛴다**(§4-1 원문) — 1경기를 "평소"라고
       부르면 로테이션 한 번이 전력 급락으로 읽힌다. 🔴 지금은 거의 늘 건너뛴다.
    """
    from app.core.stages.s5_verify import comp_kind
    kind = comp_kind(ref, facts)
    values = dict(facts.player_value or {})
    sample = usual_sample(facts)
    if not values:
        why = "② 없음 — 선수 가치를 한 명도 못 받았다"
        state.note(f"s2b {why}")
        return AdjProb(why=why)
    if sample < base.MIN_USUAL_SAMPLE:
        why = (f"② 건너뜀 — 평소 XI 표본이 **{sample}경기**다(최소 "
               f"{base.MIN_USUAL_SAMPLE}경기 · §4-1) · 경기 페이지에서 직전 경기 "
               f"하나까지만 따라간다")
        state.note(f"s2b {why} · 선수 가치 {len(values)}명은 받았다")
        return AdjProb(why=why)
    usual = {str(k): [p.name for p in (v.lineup or [])] or list(v.players or [])
             for k, v in (facts.last_xi or {}).items()}
    today = {str(k): [p.name for p in (v.lineup or [])] or list(v.players or [])
             for k, v in (facts.xi or {}).items()}
    ds, pct, deltas, est = _deltas(usual, today, values)
    if est > base.MAX_ESTIMATED:
        why = (f"② 표시만 — 값 없는 선수를 {est}명 채웠다(>{base.MAX_ESTIMATED}) → "
               f"**판정에 쓰지 않는다**(§4-3)")
        state.note(f"s2b {why}")
        return AdjProb(why=why, deltas=deltas, delta_s=ds, strength_pct=pct,
                       estimated_players=est)
    return base.adjust(got, kind=kind, delta_s=ds, strength_pct=pct,
                       deltas=deltas, home=ref.home, away=ref.away,
                       estimated=est, why=f"② 평소 XI {sample}경기 · 가치 {len(values)}명")


def _deltas(usual: dict[str, list[str]], today: dict[str, list[str]],
            values: dict[str, float]
            ) -> tuple[dict[str, float], dict[str, float], list[LineupDelta], int]:
    """🔴 §4-4·§4-6 — `ΔS` 와 **선수별 기여표**. `(ΔS, 변화율, 기여, 채운 수)`.

    🔴 `S = Σ log(가치)` 이고 `ΔS = S(오늘) − S(평소)` 다(포지션 가중 없이 시작 · §4-4).
    ⚠️ 값 없는 선수는 **그 팀 평소 XI 가치의 하위 25%** 로 채우고 채운 수를 센다(§4-3).
    """
    ds: dict[str, float] = {}
    pct: dict[str, float] = {}
    out: list[LineupDelta] = []
    est = 0
    for team, usual_names in usual.items():
        now = today.get(team) or []
        if not now or not usual_names:
            continue
        pool = [v for nm, v in values.items() if nm in usual_names] or \
               list(values.values())
        a, est_a, _ = base.fill_values(list(usual_names), values, pool)
        b, est_b, _ = base.fill_values(list(now), values, pool)
        if not a or not b:
            continue
        s_usual, s_now = base.strength_of(a), base.strength_of(b)
        ds[team] = round(s_now - s_usual, 4)
        pct[team] = base.pct_change(s_now, s_usual)
        est += est_a + est_b
        gone = [nm for nm in usual_names if nm not in now]
        came = [nm for nm in now if nm not in usual_names]
        floor = base.fill_values(["?"], {}, pool)[0]
        for i, nm in enumerate(gone):
            to = came[i] if i < len(came) else ""
            v_out = values.get(nm) or (floor[0] if floor else 0.0)
            v_in = values.get(to) or (floor[0] if floor else 0.0)
            out.append(LineupDelta(
                team=team, out_name=nm, in_name=to,
                delta_s=round(base.strength_of([v_in]) - base.strength_of([v_out]), 4),
                estimated=nm not in values or (bool(to) and to not in values)))
    return ds, pct, out, est
