"""🔴🔴 **경기 우선순위 지수** — 수정 지시서 2026-10-12 [1a]·[1b].

> 우선순위 지수 = **오늘 XI 가치 합 ÷ 최강 XI 가치 합**(0~1+).
> 전략 판정 입력에 넣는다(로테이션·체력 관리 판정의 근거 숫자).
> **LLM 판정이 지수와 반대면 ④ 검사처럼 버리고 코드 판정.**

⚠️⚠️ **시즌 출전 시간은 어디에도 없다** — 실측 2026-10-12: fotmob 선수단 페이지의
   `minutes_played`·`started` 는 **번역 사전 열쇠**였고(같은 함정을 선수 xG 에서도
   한 번 밟았다) 선수 줄에 **수로 된 출전 기록이 0건**이다.
🔴 그래서 "최강 XI" 는 **창 10경기 선발 빈도 상위 11명**의 가치 합으로 센다 —
   그 사실을 사유에 적는다(#3·#4: 없는 자료를 있는 척하지 않는다).
🔴 **확률에 닿지 않는다**(P1): 축0 은 이미 오늘 XI 가치를 쓰므로 지수를 거기 또
   곱하지 않는다. 지수는 **축0 근거 줄**과 **K5 반증 조건**으로만 간다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 한 팀의 선발 수 — `lineupgate.XI_N` 하나가 든다(사본 금지)
#: 🔴🔴 **아꼈다고 보는 문턱** — `s6_hypo.PRIORITY_LOW` 하나가 든다(K5 와 같은 수다)


def _xi_n() -> int:
    from app.core.lineupgate import XI_N
    return int(XI_N)


def _low() -> float:
    from app.core.stages.s6_hypo import PRIORITY_LOW
    return float(PRIORITY_LOW)


def best_xi(*, starts: dict, value: dict) -> tuple[float | None, str]:
    """🔴🔴 [1a] — **최강 XI 가치 합**과 사유. 재료가 없으면 `(None, 사유)`.

    `starts` 는 `{선수: 선발 경기 수}`(창 10경기 · `s2e_matchup.usual_starts`),
    `value` 는 `{선수: 선수 가치}`(`facts.player_value`).

    ⚠️ **포지션 틀은 아직 못 맞춘다** — 포지션별 가치 분포를 재는 통로가 없다.
       🔴 그래서 선발 빈도 상위 11명을 그대로 더하고 그 사실을 적는다(지어내지
       않는다 · 지시서 [1a] 의 *"포지션 틀"* 은 자료가 서면 얹는다).
    """
    rows = {str(k): float(v) for k, v in dict(starts or {}).items()}
    vals = {str(k): float(v) for k, v in dict(value or {}).items()
            if isinstance(v, (int, float))}
    if not rows or not vals:
        return None, (f"🔴 최강 XI 를 못 만들었다 — 선발 빈도 {len(rows)}명 · "
                      f"선수 가치 {len(vals)}명")
    n = _xi_n()
    order = sorted(rows.items(), key=lambda kv: (-kv[1], str(kv[0])))
    took, hit = 0.0, 0
    missing: list[str] = []
    for name, _k in order:
        if hit >= n:
            break
        got = vals.get(name)
        if got is None:
            missing.append(name)
            continue
        took += float(got)
        hit += 1
    if hit < n:
        return None, (f"🔴 최강 XI {hit}/{n} 명만 값이 있다(가치 없는 선수 "
                      f"{len(missing)}명) — 지수를 안 센다")
    return round(took, 4), (
        f"최강 XI {n}명 가치 합 {took:.1f} — 🔴 **선발 빈도(창 10경기)** 로 골랐다"
        "(시즌 출전 시간 자료가 없다 · 포지션 틀도 아직 못 맞춘다)")


def today_xi(*, lineup: list, value: dict) -> tuple[float | None, str]:
    """🔴 [1b] 재료 — **오늘 XI 가치 합**. 못 세면 `(None, 사유)`."""
    names = [str(getattr(p, "name", "") or p) for p in (lineup or [])]
    vals = {str(k): float(v) for k, v in dict(value or {}).items()
            if isinstance(v, (int, float))}
    got = [vals[nm] for nm in names if nm in vals]
    if len(got) < _xi_n():
        return None, (f"🔴 오늘 XI 가치 {len(got)}/{_xi_n()} 명 — 지수를 안 센다")
    return round(sum(got), 4), f"오늘 XI {len(got)}명 가치 합 {sum(got):.1f}"


def index_of(*, today: float | None, best: float | None
             ) -> tuple[float | None, str]:
    """🔴🔴 [1b] — **지수 = 오늘 ÷ 최강**(0~1+). ⚠️ 1 을 넘어도 **자르지 않는다**.

    🔴 1 을 넘는 것은 *"평소보다 강한 XI 를 냈다"* 는 뜻이다 — 그것도 정보다.
    """
    if today is None or not best:
        return None, "🔴 지수를 못 셌다 — 오늘·최강 중 한쪽이 **없다**"
    got = float(today) / float(best)
    return round(got, 4), f"지수 {got:.2f} = 오늘 {today:.1f} ÷ 최강 {best:.1f}"


def said_of(index: float | None) -> str:
    """🔴 카드 1겹 줄 — *"🎯 우선순위 홈 0.94"* 의 그 수."""
    return "⬜ 없다" if index is None else f"{float(index):.2f}"


#: 🔴 지수가 말하는 **아낌** 판정 — 전략 판정 글자와 같은 말을 쓴다
SAVED = "로테이션·체력 관리"
FULL = "평소 그대로"


def verdict_check(said: str, *, index: float | None) -> tuple[str, str]:
    """🔴🔴 [1b] — **LLM 판정이 지수와 반대면 버린다**(④ 검사와 같은 규율).

    🔴 지수가 문턱 아래인데 `평소 그대로` 라고 하면 그 말은 **행동과 반대**다 —
       코드 판정(`로테이션·체력 관리`)으로 바꾼다. 거꾸로도 같다.
    ⚠️ 지수가 없으면 **아무것도 바꾸지 않는다**(없는 수로 판정을 흔들지 않는다).
    """
    now = str(said or "")
    if index is None:
        return now, "⬜ 지수가 없다 — LLM 판정을 그대로 둔다"
    low = _low()
    got = float(index)
    if got < low and now == FULL:
        return SAVED, (f"🔴 LLM 판정 `{FULL}` 을 **버렸다** — 지수 {got:.2f} < "
                       f"{low:.2f}(아꼈다)")
    if got >= low and now == SAVED:
        return FULL, (f"🔴 LLM 판정 `{SAVED}` 을 **버렸다** — 지수 {got:.2f} ≥ "
                      f"{low:.2f}(안 아꼈다)")
    return now, f"판정 `{now}` 과 지수 {got:.2f} 가 **맞는다**"


def word_vs_action(*, index: float | None, v3: list | None = None,
                   v4: list | None = None) -> str:
    """🔴 [1d] — ⑫ 가 적는 **"말·일정 ↔ 행동"** 한 줄.

    > 예: "다음 경기 결승(V3) — 오늘 지수 0.71로 아꼈다(행동 일치)".

    ⚠️ 확률에 닿지 않는다(C1·C7) — 이 글자는 **검증표의 한 줄**이다.
    """
    said = [str(x) for x in (list(v3 or []) + list(v4 or [])) if str(x)]
    if index is None:
        return ("말·일정 ↔ 행동 — ⬜ **지수가 없다**"
                + (f"(말: {said[0][:40]})" if said else ""))
    got = float(index)
    low = _low()
    act = "아꼈다" if got < low else "안 아꼈다"
    if not said:
        return f"말·일정 ↔ 행동 — 말 없음 · 오늘 지수 {got:.2f}({act})"
    fit = ("행동 일치" if (got < low) else "행동 불일치")
    return (f"말·일정 ↔ 행동 — {said[0][:60]} · 오늘 지수 {got:.2f}"
            f"({act}) → **{fit}**")
