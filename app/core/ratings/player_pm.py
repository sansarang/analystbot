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

#: 🔴🔴 **팀 항의 벌 비율** — 선수 벌의 1/100 이다.
#   ⚠️ 실측(계약 `test_team_strength_does_not_leak_into_player_scores`): 같은 벌을
#      주면 팀 항과 선수 열이 **완전 공선형**이라 릿지가 수를 **똑같이 쪼갠다**
#      (22명 전부 +0.042 · 팀 항도 +0.042) → 팀의 힘이 선수 점수로 **샌다**.
#   🔴 팀 고정효과는 *"없애야 할 귀찮은 모수"* 이므로 거의 벌하지 않는다. 0 은
#      쓰지 않는다 — 팀 열들의 합이 어느 줄에서나 0 이어서 벌이 없으면 특이행렬이다.
TEAM_LAM = 0.01


@dataclass
class Table:
    """🔴 선수 점수 한 판 — **수와 그 수의 출처**를 함께 든다."""

    value: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    minutes: dict = field(default_factory=dict)
    pos: dict = field(default_factory=dict)
    mean: float = 0.0
    as_of: object = None
    n_matches: int = 0
    shrunk: int = 0
    lam: float = 0.0
    why: str = ""


def segments(match: dict) -> list[dict]:
    """🔴🔴 §2 — 한 경기를 **출전 구간·골 분**으로 쪼갠다.

    한 줄: `{minutes, home_on, away_on, gf, ga, y, coarse}` — `y` 는 90분당 골 차.
    🔴 `home_box`/`away_box`(`{선수: [들어온 분, 나간 분]}`)가 있으면 **그것이
       구간의 자른 자리**다(§1 이 실측으로 받은 분). 없으면 `subs` 로 간다.
    ⚠️ 둘 다 없으면 **거친 판**이다(선발 11명 90분) — `coarse` 가 그렇게 적는다.
    """
    box = dict(match or {})
    goals = sorted((dict(g) for g in (box.get("goals") or [])),
                   key=lambda g: int(g.get("min") or 0))
    spans: dict[str, dict[str, tuple[int, int]]] = {}
    for side in ("home", "away"):
        said = dict(box.get(f"{side}_box") or {})
        spans[side] = {str(k): (int(tuple(v)[0]), int(tuple(v)[1]))
                       for k, v in said.items()}
    coarse = not (spans["home"] or spans["away"])
    if coarse:
        # 🔴 구간이 없다 — `subs` 가 있으면 그것으로 만들고, 없으면 선발 90분
        subs = sorted((dict(x) for x in (box.get("subs") or [])),
                      key=lambda x: int(x.get("min") or 0))
        for side in ("home", "away"):
            spans[side] = {str(p): (0, FULL)
                           for p in (box.get(f"{side}_ids") or [])}
            for one in subs:
                if bool(one.get("home")) != (side == "home"):
                    continue
                at = int(one.get("min") or 0)
                who = str(one.get("out") or "")
                if who in spans[side]:
                    spans[side][who] = (spans[side][who][0], at)
                if one.get("in"):
                    spans[side][str(one["in"])] = (at, FULL)
            coarse = coarse and not subs
    cuts = sorted({0, FULL} | {int(g["min"]) for g in goals}
                  | {m for side in spans.values() for span in side.values()
                     for m in span if 0 < int(m) < FULL})
    out: list[dict] = []
    for lo, hi in zip(cuts, cuts[1:]):
        mins = hi - lo
        if mins <= 0:
            continue
        gf = sum(1 for g in goals if lo < int(g["min"]) <= hi and g.get("home"))
        ga = sum(1 for g in goals
                 if lo < int(g["min"]) <= hi and not g.get("home"))
        on = {side: [p for p, (a, b) in sorted(spans[side].items())
                     if a <= lo and b >= hi]
              for side in ("home", "away")}
        out.append({"minutes": mins, "home_on": on["home"],
                    "away_on": on["away"], "gf": gf, "ga": ga,
                    "y": ((gf - ga) / mins) * FULL, "coarse": coarse})
    return out


def fit(matches: list[dict], *, as_of, lam: float,
        half_life: float = 365.0, teams: bool = True) -> Table:
    """🔴🔴 §5 — 릿지로 선수 점수를 적합한다. **`as_of` 이전 경기만**(PL1).

    🔴 설명변수는 구간 출전 선수의 **±1**(홈 +1 · 원정 −1), 응답은 90분당 골 차,
       가중은 `구간 분 × exp(−ξ·경과일)`(§6).
    🔴🔴 **팀 고정효과**(`teams=True`) — `team:<이름>` 열을 함께 푼다. 그래야
       *"팀이 좋아서 생긴 ±"* 가 선수 점수로 **새지 않는다**(§2). 그 열은
       `raw` 에만 있고 `value`(선수 점수)에는 **없다**.
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
    pos: dict[str, str] = {}
    coarse = 0
    for m in said:
        pos.update({str(k): str(v) for k, v in
                    dict(m.get("pos") or {}).items() if v})
        when = datetime.fromisoformat(str(m["utc"]).replace("Z", "+00:00"))
        if when.tzinfo is None:                 # 🔴 절대규칙 2
            continue
        w0 = math.exp(-decay * max(0, (as_of.date() - when.date()).days))
        box = segments(m)
        coarse += 1 if (box and box[0].get("coarse")) else 0
        for seg in box:
            cell: dict[int, float] = {}
            if teams:
                # 🔴 팀 항 — 홈 +1 · 원정 −1(그 경기의 두 팀 이름으로)
                for side, sign in (("home", 1.0), ("away", -1.0)):
                    key = f"team:{m.get(side) or side}"
                    if key not in index:
                        index[key] = len(ids)
                        ids.append(key)
                    cell[index[key]] = cell.get(index[key], 0.0) + sign
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
    pen = np.array([float(lam) * (TEAM_LAM if p.startswith("team:") else 1.0)
                    for p in ids])
    a = x.T @ xw + np.diag(pen)
    b = x.T @ (w * y)
    beta = np.linalg.solve(a, b)
    got.raw = {pid: float(beta[index[pid]]) for pid in ids}
    # 🔴 팀 항은 **선수가 아니다** — 점수 표에서 가른다
    only = {pid: v for pid, v in got.raw.items() if not pid.startswith("team:")}
    got.minutes = {pid: float(minutes.get(pid, 0.0)) for pid in only}
    got.pos = {pid: pos[pid] for pid in only if pid in pos}
    got.mean = float(sum(only.values()) / len(only)) if only else 0.0
    # 🔴 출전 분이 적으면 **리그·포지션 평균 쪽으로 수축**(§2)
    got.value, said_shrink = shrink(only, minutes=got.minutes, pos=got.pos)
    got.shrunk = sum(1 for pid in only
                     if got.minutes.get(pid, 0.0) < MIN_MINUTES)
    got.why = (f"릿지 ± (벌 λ {float(lam):g} · 구간 {len(rows)}개 · 선수 "
               f"{len(only)}명"
               + (f" · 팀 항 {len(got.raw) - len(only)}개" if teams
                  else " · 🔴 팀 항 **없다**")
               + f" · 경기 {len(said)}건 · 반감기 {half_life:g}일) · "
               + said_shrink
               + (f" · ⚠️ **거친 판 {coarse}경기**(교체 시각이 없어 선발 90분으로"
                  f" 셌다)" if coarse else ""))
    return got


def shrink(raw: dict, *, minutes: dict, pos: dict | None = None,
           floor: float = MIN_MINUTES, k: float = SHRINK_K
           ) -> tuple[dict, str]:
    """🔴🔴 §2 — 출전 **300분 미만**은 **리그·포지션 평균** 쪽으로 수축한다.

    🔴 왜 포지션인가 — GK·수비수의 ± 는 공격수와 **분포가 다르다**. 전체 평균으로
       끌면 자리 때문에 생긴 차가 "적게 뛴 탓"으로 섞인다.
    ⚠️ 포지션을 모르는 선수는 **리그 평균** 쪽이고, 사유가 그렇게 **적는다**.
    🔴 `floor`·`k` 는 **부르는 쪽이 정한다** — 선수 가치 v2 는 450분이다(사용자
       결정 2026-10-13 저녁). ⚠️ 두 문턱을 두 모듈에 베끼지 않는다(#1).
    """
    got = {str(k): float(v) for k, v in dict(raw or {}).items()}
    if not got:
        return {}, "🔴 수축할 선수가 없다"
    said_pos = {str(k): str(v) for k, v in dict(pos or {}).items() if v}
    # 🔴🔴 **그 선수를 뺀 평균**(leave-one-out)으로 끌어당긴다 — 자기 값이 섞인
    #    평균으로 끌면 수축이 **자기 자신에게** 끌려 효과가 줄어든다.
    total = sum(got.values())
    by_pos: dict[str, list[float]] = {}
    for pid, val in got.items():
        if pid in said_pos:
            by_pos.setdefault(said_pos[pid], []).append(val)
    sums = {k: (sum(v), len(v)) for k, v in by_pos.items() if v}

    def _mean_without(pid: str, val: float) -> tuple[float, bool]:
        key = said_pos.get(pid, "")
        if key in sums and sums[key][1] > 1:
            s0, n0 = sums[key]
            return (s0 - val) / (n0 - 1), True
        if len(got) > 1:
            return (total - val) / (len(got) - 1), False
        return val, False
    out: dict[str, float] = {}
    n_pos = n_lg = 0
    for pid, val in got.items():
        mins = float(dict(minutes or {}).get(pid, 0.0))
        if mins >= float(floor):
            out[pid] = val
            continue
        to, by_position = _mean_without(pid, val)
        if by_position:
            n_pos += 1
        else:
            n_lg += 1
        share = mins / (mins + float(k))
        out[pid] = share * val + (1.0 - share) * to
    why = (f"출전 분 {float(floor):g} 미만 **{n_pos + n_lg}명 수축**"
           + (f"(포지션 평균 {n_pos}명" if n_pos else "(")
           + (f" · 🔴 **리그 평균** {n_lg}명 — 포지션을 모른다)" if n_lg
              else ")"))
    return out, why


def pick_lam(matches: list[dict], *, as_of, lams=(1.0, 10.0, 100.0),
             half_life: float = 365.0) -> tuple[float, str]:
    """🔴🔴 §2 — 벌(λ)을 **시즌 교차**로 고른다(손값 금지).

    한 시즌으로 적합해 **다른 시즌**의 구간 골 차를 맞추고, 가중 제곱 오차가
    가장 작은 λ 를 고른다. ⚠️ 시즌이 하나뿐이면 **고르지 않는다**(사유를 적는다).
    """
    from app.collect import fotmob as fm
    said = fm.before_as_of(list(matches or []), as_of=as_of, key="utc")
    by: dict[str, list[dict]] = {}
    for m in said:
        by.setdefault(str(m.get("season") or str(m["utc"])[:4]), []).append(m)
    if len(by) < 2:
        return (float(lams[len(lams) // 2]),
                f"🔴 **시즌이 하나뿐**이라 교차를 못 했다(시즌 {list(by)}) — "
                f"가운데 λ {float(lams[len(lams) // 2]):g} 로 간다")
    seasons = sorted(by)
    score: dict[float, float] = {}
    for lam in lams:
        total = 0.0
        for i, train in enumerate(seasons):
            table = fit(by[train], as_of=as_of, lam=float(lam),
                        half_life=half_life)
            if not table.value:
                continue
            for test in seasons[:i] + seasons[i + 1:]:
                for m in by[test]:
                    for seg in segments(m):
                        got = (sum(value_of(p, table)[0]
                                   for p in seg["home_on"])
                               - sum(value_of(p, table)[0]
                                     for p in seg["away_on"]))
                        total += (float(seg["minutes"])
                                  * (float(seg["y"]) - got) ** 2)
        score[float(lam)] = total
    best = min(score, key=lambda k: score[k])
    return best, ("시즌 교차 — " + " · ".join(
        f"λ {k:g} 오차 {v:,.0f}" for k, v in sorted(score.items()))
        + f" → **λ {best:g}**")


def stability(a: dict, b: dict) -> tuple[float, str]:
    """🔴🔴 §2 — 시즌 **반분** 두 추정의 상관. 0.3 미만이면 **"신뢰 낮음"**."""
    import numpy as np
    keys = sorted(set(dict(a or {})) & set(dict(b or {})))
    if len(keys) < 3:
        return 0.0, f"🔴 겹치는 선수가 {len(keys)}명뿐이라 **못 쟀다**"
    x = np.array([float(a[k]) for k in keys])
    y = np.array([float(b[k]) for k in keys])
    if x.std() == 0 or y.std() == 0:
        return 0.0, "🔴 한쪽이 전부 같은 값이라 **못 쟀다**"
    r = float(np.corrcoef(x, y)[0, 1])
    return r, (f"반분 상관 **{r:+.2f}**(선수 {len(keys)}명)"
               + (" — 🔴 **신뢰 낮음**(0.3 미만)" if r < 0.3 else ""))


def save(path, *, value: dict, minutes: dict, pos: dict | None = None,
         raw: dict | None = None) -> str:
    """🔴 판을 `.parquet` 로 적는다 — `data/player_pm/<league>/<as_of>.parquet`."""
    from pathlib import Path as _P

    import pyarrow as pa
    import pyarrow.parquet as pq
    said = _P(path)
    said.parent.mkdir(parents=True, exist_ok=True)
    box = dict(value or {})
    keys = sorted(box)
    table = pa.table({
        "player_id": [str(k) for k in keys],
        "value": [float(box[k]) for k in keys],
        "minutes": [float(dict(minutes or {}).get(k, 0.0)) for k in keys],
        "pos": [str(dict(pos or {}).get(k, "") or "") for k in keys],
        "raw": [float(dict(raw or {}).get(k, box[k])) for k in keys]})
    pq.write_table(table, said)
    return f"판 `{said.stem}` 에 선수 {len(keys)}명을 적었다"


def load(box, *, as_of) -> tuple[Table, str]:
    """🔴🔴 **L3** — `as_of` **이전** 최신 판(엄격히 이전). 없으면 빈 표 + 🔴."""
    import pyarrow.parquet as pq

    from app.core import versions
    said, why = versions.pick_file(box, as_of=as_of, ext="parquet")
    if said is None:
        return Table(as_of=as_of, why=why), why
    df = pq.read_table(said).to_pydict()
    got = Table(as_of=as_of, why=why)
    rows = list(zip(df["player_id"], df["value"], df["minutes"], df["pos"],
                    df["raw"]))
    got.value = {str(a): float(b) for a, b, _c, _d, _e in rows}
    got.minutes = {str(a): float(c) for a, _b, c, _d, _e in rows}
    got.pos = {str(a): str(d) for a, _b, _c, d, _e in rows if d}
    got.raw = {str(a): float(e) for a, _b, _c, _d, e in rows}
    got.mean = (float(sum(got.value.values()) / len(got.value))
                if got.value else 0.0)
    return got, why


def value_of(pid: str, table: Table) -> tuple[float, str]:
    """🔴🔴 **PL2** — 그 선수 점수. 없으면 **평균**과 🔴 사유(0 이 아니다)."""
    box = dict(table.value or {})
    if str(pid) in box:
        return float(box[str(pid)]), ""
    return float(table.mean), (f"🔴 `{pid}` 는 점수 표에 **없다** — 평균 "
                               f"{table.mean:+.3f} 로 메웠다(0 으로 세지 않는다)")
