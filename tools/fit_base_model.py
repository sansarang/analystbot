"""🔴🔴 **① 기준 확률의 순서형 로짓 적합** — 네 층 지시서 §3-2 · 단계 5.

```
PYTHONPATH=. python tools/fit_base_model.py --years 2010-2026
```

> 무승부를 나누려면 **순서형 로짓**을 한 번 적합한다: 입력 dr → 승/무/패.
> 계수는 `config/base_model.yaml` 에 **적합일·표본 수·로그 손실과 함께**.
> 봇은 계수만 읽는다(**실행 중 적합 금지**).

## 🔴 이 스크립트가 재는 것

| 무엇 | 어떻게 |
|---|---|
| `b_dr` | 경기 **전** Elo 차(÷100) 의 기울기 — eloratings 11·12열 |
| 홈 이점 | 🔴 **절단점이 머금는다** — 홈 개최 경기만 적합하므로(아래) |
| `c1`·`c2` | 순서형 절단점(원정승/무/홈승) |

⚠️ **홈 보정을 Elo 점수로 빌려 오지 않는다**(출처가 말하지 않는다 —
   `config/rating_sources.yaml: home_adv_why`).

🔴🔴 **중립 경기 줄은 쓸 수 없다 — 실측 2026-10-06**

   9열(개최국)이 **찬** 줄은 홈/원정이 아니라 **결과순**으로 적혀 있다:
   2010·2015·2020·2025 네 해의 중립 경기 **936건 중 원정승이 2건**이었다
   (2026년도 318건 중 1건). 즉 중립 경기에서는 **이긴 팀이 먼저** 적힌다.
   🔴 그 줄을 섞어 적합하면 모형이 *"먼저 적힌 팀이 이긴다"* 를 배운다 — 실제로
   처음 적합에서 홈 항이 **−1.10** 으로 나왔고, 그것이 이 함정의 증거였다.
   🔴 그래서 **홈 개최 경기만**(9열 빈칸) 적합하고, 홈 이점은 **절단점**이 머금는다.
   ⚠️ 그래서 이 모형은 **중립 경기에 쓰지 않는다** — 그때 ① 은 "기준 없음"이다.
   실측(홈 개최 · |dr|<50 · 330건): 홈승 **0.430** · 무 **0.342** · 원정승 **0.227**.
🔴 대회 유형을 섞지 않는다 — `national_friendly`(8열 `F`·`FFS`) 와
   `national_official`(그 밖) 을 **따로** 적합한다(§3 "다른 대회 값 금지").
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timezone

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from app.collect import elo
from typing import NamedTuple

OUT = "config/base_model.yaml"

# ══════════════════════════════════════════════════════════════════
# 🔴 과거 경기 줄 읽기 — **여기에 둔다**(봇 경로에 두지 않는다 · §3-2)
# ══════════════════════════════════════════════════════════════════

class Row(NamedTuple):
    """🔴 과거 경기 한 줄 — 적합이 쓰는 칸만(`app/` 에 없다 · §3-2)."""

    when: date
    home: str
    away: str
    home_score: int
    away_score: int
    tournament: str
    host: str
    home_elo: float
    away_elo: float

    @property
    def friendly(self) -> bool:
        return self.tournament in elo.FRIENDLY_CODES

    @property
    def at_home(self) -> bool:
        """🔴 홈 팀 나라에서 열렸나 — 9열이 비었거나 홈 코드면 그렇다."""
        return not self.host or self.host == self.home

    @property
    def outcome(self) -> int:
        """🔴 0 원정승 · 1 무 · 2 홈승 — **순서형**이다(§3-2)."""
        if self.home_score > self.away_score:
            return 2
        return 1 if self.home_score == self.away_score else 0


def parse_results(text: str) -> list[Row]:
    """🔴 `{연}_results.tsv` → 경기 줄들. ⚠️ **등급 칸이 빈 줄은 버린다**(적합 못 함)."""
    out: list[Row] = []
    for line in text.splitlines():
        col = [c.strip() for c in line.split("\t")]
        if len(col) < 12:
            continue
        try:
            when = date(int(col[0]), int(col[1]), int(col[2]))
            row = Row(when=when, home=col[3].upper(), away=col[4].upper(),
                      home_score=int(col[5]), away_score=int(col[6]),
                      tournament=col[7], host=col[8].upper(),
                      home_elo=float(col[10]), away_elo=float(col[11]))
        except (ValueError, IndexError):
            continue
        out.append(row)
    return out



def _probs(x: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """🔴 누적 로짓 → `[P(원정승), P(무), P(홈승)]` 한 줄씩.

    ⚠️ 입력은 `dr/100` **하나**다 — 홈 이점은 절단점이 머금는다(위 설명).
    """
    c1, c2, b_dr = beta
    eta = b_dr * x[:, 0]
    lo = expit(c1 - eta)
    hi = expit(c2 - eta)
    hi = np.maximum(hi, lo + 1e-9)          # 🔴 절단점 순서를 지킨다
    return np.column_stack([lo, hi - lo, 1.0 - hi])


def _nll(beta: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(_probs(x, beta), 1e-12, 1.0)
    return float(-np.log(p[np.arange(len(y)), y]).mean())


def fit(rows: list[Row]) -> dict:
    """🔴 한 대회 유형을 적합한다. ⚠️ 표본이 적으면 **그 사실을 함께** 돌려준다."""
    x = np.array([[(r.home_elo - r.away_elo) / 100.0] for r in rows], dtype=float)
    y = np.array([r.outcome for r in rows], dtype=int)
    start = np.array([-0.8, 0.6, 0.3])
    got = minimize(_nll, start, args=(x, y), method="Nelder-Mead",
                   options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-10})
    c1, c2, b_dr = (float(v) for v in got.x)
    # 🔴 **기준선**: 늘 같은 비율을 내는 모형의 손실(이것보다 나빠지면 쓸 수 없다)
    base = np.bincount(y, minlength=3) / len(y)
    dumb = float(-np.log(np.clip(base[y], 1e-12, 1.0)).mean())
    return {"c1": round(c1, 6), "c2": round(c2, 6), "b_dr": round(b_dr, 6),
            "venue": "home_only", "n": int(len(y)),
            "logloss": round(float(got.fun), 6), "logloss_base": round(dumb, 6),
            "share_home_draw_away": [round(float(base[2]), 4),
                                     round(float(base[1]), 4),
                                     round(float(base[0]), 4)],
            "fitted_at": date.today().isoformat(),
            "converged": bool(got.success)}


async def main(argv: list[str]) -> int:
    span = "2010-2026"
    if "--years" in argv:
        span = argv[argv.index("--years") + 1]
    a, b = (int(v) for v in span.split("-"))
    from app import net as _net_mod
    net = _net_mod.Net()
    rows: list[Row] = []
    for year in range(a, b + 1):
        url = elo.file_of("results", year=year)
        ok, why = await net.allowed(url)
        if not ok:
            print(f"[fit] {year} robots 가 막았다 — {why}", flush=True)
            continue
        got = await net.get(url)
        body = getattr(got, "text", "") or ""
        said = parse_results(body)
        print(f"[fit] {year} {len(said)}경기", flush=True)
        rows += said
    if not rows:
        print("🔴 과거 결과를 하나도 못 받았다 — **적합하지 않는다**(① 은 We 만)")
        return 1
    # 🔴 **홈 개최만**(중립 줄은 결과순이다 — 위 설명)
    home_rows = [r for r in rows if r.at_home]
    print(f"[fit] 홈 개최 {len(home_rows)}경기 · 중립 "
          f"{len(rows) - len(home_rows)}경기는 **버린다**(결과순 정렬)")
    kinds = {
        "national_friendly": [r for r in home_rows if r.friendly],
        "national_official": [r for r in home_rows if not r.friendly],
    }
    models: dict[str, dict] = {}
    for kind, said in kinds.items():
        if len(said) < 200:
            print(f"[fit] {kind} 표본 {len(said)}경기 — **적합하지 않는다**(너무 적다)")
            continue
        models[kind] = fit(said)
        m = models[kind]
        print(f"[fit] {kind} n={m['n']} logloss={m['logloss']} "
              f"(기준선 {m['logloss_base']}) b_dr={m['b_dr']} "
              f"c1={m['c1']} c2={m['c2']}")
    head = (
        "# ══════════════════════════════════════════════════════════════════\n"
        "# 🔴🔴 **① 기준 확률 계수** — `tools/fit_base_model.py` 가 적는다\n"
        "# ══════════════════════════════════════════════════════════════════\n"
        "#\n"
        "# 🔴 **손으로 고치지 않는다.** 네 층 지시서 §3-2: *\"봇은 계수만 읽는다\n"
        "#    (실행 중 적합 금지)\"*. 다시 재려면 위 스크립트를 돌린다.\n"
        "# 🔴 모형은 **대회 유형별**이다 — 다른 유형 계수를 빌려 쓰지 않는다.\n"
        "# 🔴 `venue: home_only` — **홈 개최 경기만** 적합했다. 중립 경기 줄은\n"
        "#    eloratings 가 **결과순**으로 적어(원정승 936건 중 2건) 쓸 수 없다.\n"
        "#    그래서 **중립 경기에는 이 계수를 쓰지 않는다**(① 기준 없음).\n"
        "#    홈 이점은 절단점(`c1`·`c2`)이 머금고 있다.\n"
        "# ⚠️ `logloss` 가 `logloss_base`(늘 같은 비율) 보다 **크면 쓸 수 없다** —\n"
        "#    그때는 모형이 자료보다 못한 것이다.\n"
        f"# 적합 자료: eloratings.net `{{연}}_results.tsv` {span} · 경기 {len(rows)}건\n"
        f"# 적합 시각: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        "\nmodels:\n")
    body_lines = []
    for kind, m in models.items():
        body_lines.append(f"  {kind}:")
        for k, v in m.items():
            body_lines.append(f"    {k}: {json.dumps(v, ensure_ascii=False)}")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(head + "\n".join(body_lines) + "\n")
    print(f"[fit] 적었다 — {OUT} ({len(models)}개 유형)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
