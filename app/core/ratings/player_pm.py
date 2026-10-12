"""🔴🔴 **§5 선수 점수 — 플러스마이너스(릿지)** — 지시서 2026-10-12(둘째) §5.

> 구간 분할(교체·골 시점) → 응답 = 구간 **(득점−실점)/90분**, 설명 = 구간 출전
> 선수 **±1** → 릿지 회귀. 출전 분 < 300 → 리그·포지션 평균 쪽 수축
> (가중 = 분/(분+K)). 시간 감쇠 가중(§6 ξ).

🔴 왜 ± 인가 — *"선수 가치"* 를 시즌 득점+도움으로 세면 수비수·GK 가 **0** 이 되고
   (실측: 축0 이 그 병을 앓았다) 결장의 무게가 공격수만 셌다. ± 는 **그 선수가
   있을 때 팀의 골 차**를 센다 — 자리와 무관하다.
🔴 릿지인 까닭 — 한 팀의 11명은 거의 늘 함께 뛴다(**공선형**). 벌 없이 풀면 수가
   서로를 밀어내며 발산한다. ⚠️ `lam`(벌의 크기)은 **백필이 고른다**(손값 금지).
🔴 **PL1** — `as_of` 이후 경기는 안 본다(문은 `fotmob.before_as_of` 하나).
🔴 **PL2** — 모르는 선수는 **0 이 아니라 평균**이다(0 은 *"평균 이하"* 라는 말이
   되어 결장 손실을 부풀린다).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

#: 🔴 이 분 미만이면 평균 쪽으로 수축한다(지시 §5)
MIN_MINUTES = 300

#: 🔴 수축 가중의 K — `분/(분+K)`. ⚠️ `MIN_MINUTES` 와 같은 자리에서만 쓴다.
SHRINK_K = 300.0

#: 🔴 한 경기 길이(분)
FULL = 90


@dataclass
class Table:
    """🔴 선수 점수 한 판 — **수와 그 수의 출처**를 함께 든다."""

    value: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    minutes: dict = field(default_factory=dict)
    mean: float = 0.0
    as_of: object = None
    n_matches: int = 0
    shrunk: int = 0
    lam: float = 0.0
    why: str = ""


def segments(match: dict) -> list[dict]:
    """🔴🔴 §5 — 한 경기를 **교체·골 시점**으로 쪼갠다.

    한 줄: `{minutes, home_on, away_on, gf, ga, y}` — `y` 는 90분당 골 차다.
    ⚠️ 교체는 `{min, out, in, home}` 이고 골은 `{min, home}` 이다(어댑터 꼴 하나).
    """
    box = dict(match or {})
    subs = sorted((dict(s) for s in (box.get("subs") or [])),
                  key=lambda s: int(s.get("min") or 0))
    goals = sorted((dict(g) for g in (box.get("goals") or [])),
                   key=lambda g: int(g.get("min") or 0))
    cuts = sorted({int(s["min"]) for s in subs}
                  | {int(g["min"]) for g in goals} | {0, FULL})
    home_on = list(box.get("home_ids") or [])
    away_on = list(box.get("away_ids") or [])
    out: list[dict] = []
    for i in range(len(cuts) - 1):
        lo, hi = cuts[i], cuts[i + 1]
        # 🔴 그 구간 **안에서** 난 골 — 경계(lo)는 앞 구간의 끝에 센다
        gf = sum(1 for g in goals if lo < int(g["min"]) <= hi and g.get("home"))
        ga = sum(1 for g in goals
                 if lo < int(g["min"]) <= hi and not g.get("home"))
        mins = hi - lo
        if mins > 0:
            out.append({"minutes": mins, "home_on": list(home_on),
                        "away_on": list(away_on), "gf": gf, "ga": ga,
                        "y": ((gf - ga) / mins) * FULL})
        # 🔴 그 분의 교체를 **다음 구간**에 반영한다
        for s in subs:
            if int(s["min"]) != hi:
                continue
            side = home_on if s.get("home") else away_on
            if s.get("out") in side:
                side.remove(s["out"])
            if s.get("in"):
                side.append(s["in"])
    return out


def fit(matches: list[dict], *, as_of, lam: float,
        half_life: float = 365.0) -> Table:
    """🔴🔴 §5 — 릿지로 선수 점수를 적합한다. **`as_of` 이전 경기만**(PL1).

    🔴 설명변수는 구간 출전 선수의 **±1**(홈 +1 · 원정 −1), 응답은 90분당 골 차,
       가중은 `구간 분 × exp(−ξ·경과일)`(§6).
    ⚠️ `lam` 이 0 이면 **적합하지 않는다** — 벌 없는 풀이는 공선형에서 발산한다.
    """
    import numpy as np

    from app.collect import fotmob as fm
    said = fm.before_as_of(list(matches or []), as_of=as_of, key="utc")
    got = Table(as_of=as_of, n_matches=len(said), lam=float(lam))
    if not said or not float(lam):
        got.why = ("🔴 **적합 못 했다** — "
                   + ("경기가 없다" if not said else "벌(lam)이 0 이다"))
        return got
    from datetime import datetime
    ids: list[str] = []
    index: dict[str, int] = {}
    rows: list[tuple[dict, float, float]] = []
    decay = math.log(2.0) / max(1.0, float(half_life))
    minutes: dict[str, float] = {}
    for m in said:
        when = datetime.fromisoformat(str(m["utc"]).replace("Z", "+00:00"))
        if when.tzinfo is None:                 # 🔴 절대규칙 2
            continue
        w0 = math.exp(-decay * max(0, (as_of.date() - when.date()).days))
        for seg in segments(m):
            cell: dict[int, float] = {}
            for pid in seg["home_on"]:
                if pid not in index:
                    index[pid] = len(ids)
                    ids.append(pid)
                cell[index[pid]] = cell.get(index[pid], 0.0) + 1.0
                minutes[pid] = minutes.get(pid, 0.0) + seg["minutes"]
            for pid in seg["away_on"]:
                if pid not in index:
                    index[pid] = len(ids)
                    ids.append(pid)
                cell[index[pid]] = cell.get(index[pid], 0.0) - 1.0
                minutes[pid] = minutes.get(pid, 0.0) + seg["minutes"]
            rows.append((cell, float(seg["y"]), w0 * float(seg["minutes"])))
    if not rows or not ids:
        got.why = "🔴 **적합 못 했다** — 구간이 없다"
        return got
    x = np.zeros((len(rows), len(ids)))
    y = np.zeros(len(rows))
    w = np.zeros(len(rows))
    for i, (cell, yy, ww) in enumerate(rows):
        for j, v in cell.items():
            x[i, j] = v
        y[i] = yy
        w[i] = ww
    # 🔴 가중 릿지 — `(XᵗWX + λI)⁻¹ XᵗWy`
    xw = x * w[:, None]
    a = x.T @ xw + float(lam) * np.eye(len(ids))
    b = x.T @ (w * y)
    beta = np.linalg.solve(a, b)
    got.raw = {pid: float(beta[index[pid]]) for pid in ids}
    got.minutes = {pid: float(minutes.get(pid, 0.0)) for pid in ids}
    got.mean = float(sum(got.raw.values()) / len(got.raw))
    # 🔴 출전 분이 적으면 **평균 쪽으로 수축**(지시 §5)
    for pid, val in got.raw.items():
        mins = got.minutes.get(pid, 0.0)
        if mins < MIN_MINUTES:
            k = mins / (mins + SHRINK_K)
            got.value[pid] = k * val + (1.0 - k) * got.mean
            got.shrunk += 1
        else:
            got.value[pid] = val
    got.why = (f"릿지 ± (벌 λ {float(lam):g} · 구간 {len(rows)}개 · 선수 "
               f"{len(ids)}명 · 경기 {len(said)}건 · 반감기 {half_life:g}일) · "
               f"출전 분 {MIN_MINUTES} 미만 **{got.shrunk}명 수축**")
    return got


def value_of(pid: str, table: Table) -> tuple[float, str]:
    """🔴🔴 **PL2** — 그 선수 점수. 없으면 **평균**과 🔴 사유(0 이 아니다)."""
    box = dict(table.value or {})
    if str(pid) in box:
        return float(box[str(pid)]), ""
    return float(table.mean), (f"🔴 `{pid}` 는 점수 표에 **없다** — 평균 "
                               f"{table.mean:+.3f} 로 메웠다(0 으로 세지 않는다)")
