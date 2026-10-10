"""🔴🔴 **상성 모형 적합** — 상성 엔진 지시서(2026-10-10 여섯째) 3-5.

```
PYTHONPATH=. python tools/fit_matchup_model.py backfill --league 9080 --n 200
PYTHONPATH=. python tools/fit_matchup_model.py fit
```

> 자료: 백필(K리그1·J1 두 시즌부터). 각 과거 경기에서 S1·S1V·S2 를 **그 경기 킥오프
> 전 시각**으로 재현해 특징을 만들고 스코어를 정답으로.
> 적합 대상: β(축별·특징별), 축 종합 비중, 운 요소 할인율, r 가중 형태, 호흡 효과,
> 시간대·상태 배율, 대회 유형 상수, 저득점 보정.
> **누설 금지**(C11) · **시간순 분할** · 보고: 로그 손실·브라이어·보정표, **Elo 기준
> 모델과 비교**, 축별 기여 비중.
> 채택: 검증 구간 로그 손실이 **Elo 기준 모델 이하**면 "적합 모드". 미달이면 결과
> 보고 + **"임시 모드" 유지**(사용자 판단).

🔴 이 도구는 **값을 스스로 쓰지 않는다** — 결과를 찍고, 채택 여부는 사용자가 정한다
   (`config/matchup_model.yaml` 을 손으로 바꾸는 것은 사용자 결정이다).
🔴 robots 허용 경로만 쓴다(`/leagues/{id}/matches/x`·경기 페이지 HTML).
⚠️ **기사 변수는 백필에 없다** — 과거 기사를 다시 모으는 통로가 없다. 그래서 적합은
   **구조 특징**(축0·축1·축2·축3)으로만이고, 보고서가 그 한계를 적는다.
"""
from __future__ import annotations

import asyncio
import json
import math
import pathlib
import sys

OUT = pathlib.Path("var/fit")
#: 🔴 시간순 분할 — 앞 70% 학습, 뒤 30% 검증(미래로 과거를 맞추지 않는다)
SPLIT = 0.7


def _say(msg: str) -> None:
    print(msg, flush=True)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ① 백필 — 경기 목록 → 특징 줄
# ══════════════════════════════════════════════════════════════════

async def backfill(league: str, *, limit: int) -> list[dict]:
    """🔴 그 리그의 **끝난 경기**를 시간순으로 돌며 특징 줄을 만든다.

    🔴🔴 **누설 금지**(C11): 경기 `m` 의 특징은 **그 전 경기들**로만 만든다 —
       아래 `seen` 에는 `m` 이전 것만 들어가고, `m` 을 넣는 것은 **특징을 만든
       뒤**다. ⚠️ 그 순서를 바꾸면 자기 경기가 자기 특징에 들어간다.
    """
    from app import rules
    from app.collect import fotmob as fm
    from app.core import backfill as _bf
    from app.net import Net
    net = Net(cache=True)
    rows = await fm.league_matches(net, league)
    done = sorted([r for r in rows if r.get("finished") and r.get("utc")],
                  key=lambda r: str(r["utc"]))[:limit]
    _say(f"[백필] 리그 {league} — 끝난 경기 {len(done)}건을 돈다")
    mean = rules.goal_share("league")
    seen: dict[str, list] = {}
    out: list[dict] = []
    for i, m in enumerate(done, 1):
        url = str(m.get("page") or "")
        if url.startswith("/"):
            url = fm.BASE + url
        got = await net.get(url)
        j = fm.payload(getattr(got, "text", "") or "") or {}
        if not j:
            continue
        score = _bf.score_of(j)
        if score is None:
            continue
        prior = {"home": list(seen.get(str(m["home"]), [])),
                 "away": list(seen.get(str(m["away"]), []))}
        gaps, why = _bf.features(j, prior=prior, league_mean=mean)
        one = _bf.Row(match_id=str(m["id"]), utc=str(m["utc"]),
                      league=str(league), home=str(m["home"]),
                      away=str(m["away"]), goals_home=score[0],
                      goals_away=score[1], gaps=gaps, mean=mean,
                      gaps_why=why)
        out.append(one.as_dict())
        # 🔴 **특징을 만든 뒤에** 이 경기를 과거로 넣는다(C11)
        _remember(seen, j, m, score)
        if i % 25 == 0:
            _say(f"[백필] {i}/{len(done)} · 특징 있는 줄 "
                 f"{sum(1 for r in out if r['gaps'])}건")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"rows_{league}.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    _say(f"[백필] ✅ {len(out)}줄 → {path}")
    return out


def _remember(seen: dict, j: dict, m: dict, score: tuple) -> None:
    """🔴 그 경기를 **두 팀의 과거 목록**에 넣는다(다음 경기의 재료다)."""
    from app.collect import fotmob as fm
    lu = ((fm._page(j).get("content") or {}).get("lineup") or {})
    goals = fm.goals_of(j)
    stats = fm.stats_of(j)
    for side, which, gf, ga in (("home", "homeTeam", score[0], score[1]),
                                ("away", "awayTeam", score[1], score[0])):
        team = str(m["home"] if side == "home" else m["away"])
        opp = str(m["away"] if side == "home" else m["home"])
        seen.setdefault(team, []).append({
            "home_name": str(m["home"]), "away_name": str(m["away"]),
            "mine_home": (side == "home"), "goals": goals, "stats": stats,
            "gf": gf, "ga": ga, "opp": opp,
            "starters": [r["name"] for r in
                         fm.players_of(dict(lu.get(which) or {}))]})


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ② 적합 — β 와 축 비중
# ══════════════════════════════════════════════════════════════════

def _lam(row: dict, beta: float, weights: dict, cap: float) -> tuple:
    gaps = dict(row.get("gaps") or {})
    tilt = sum(float(weights.get(k) or 0.0) * float(v) for k, v in gaps.items())
    move = max(-cap, min(cap, beta * tilt))
    mean = float(row["mean"])
    mul = float(row.get("home_mul") or 1.0)
    return mean * mul * math.exp(move), mean * math.exp(-move)


def _poisson_ll(rows: list[dict], beta: float, weights: dict,
                cap: float) -> float:
    """🔴 포아송 **로그 가능도** — 적합은 이것을 크게 한다."""
    out = 0.0
    for row in rows:
        lh, la = _lam(row, beta, weights, cap)
        for lam, k in ((lh, int(row["goals_home"])), (la, int(row["goals_away"]))):
            out += k * math.log(max(lam, 1e-9)) - lam - math.lgamma(k + 1)
    return out


def _probs(row: dict, beta: float, weights: dict, cap: float) -> tuple:
    """🔴 그 줄의 승무패 — **운영과 같은 시뮬**로 센다(사본 금지)."""
    from app.core import sim as _sim
    lh, la = _lam(row, beta, weights, cap)
    got = _sim.run(lh, la)
    return got.home, got.draw, got.away


def _logloss(rows: list[dict], beta: float, weights: dict,
             cap: float) -> tuple[float, float]:
    """🔴 보고용 — `(로그 손실, 브라이어)`(승무패 셋)."""
    ll = br = 0.0
    for row in rows:
        p = _probs(row, beta, weights, cap)
        h, a = int(row["goals_home"]), int(row["goals_away"])
        y = (1, 0, 0) if h > a else (0, 1, 0) if h == a else (0, 0, 1)
        ll -= sum(yi * math.log(max(pi, 1e-9)) for yi, pi in zip(y, p))
        br += sum((pi - yi) ** 2 for yi, pi in zip(y, p))
    n = max(1, len(rows))
    return ll / n, br / n


def _elo_baseline(rows: list[dict]) -> tuple[float, float]:
    """🔴🔴 **Elo 기준 모델** — 비교 상대다(지시서 3-5 보고 항목).

    🔴 우리 저장소의 Elo 를 과거 시점으로 되돌릴 통로가 없다 — 그래서 기준 모델은
       **리그 평균만**(두 팀 같은 λ)이다. ⚠️ 그 사실을 보고서가 적는다: 이것은
       *"정보 없는 기준"* 이고 Elo 보다 **약한** 상대다.
    """
    rows = [r for r in rows if r.get("mean")]
    ll = br = 0.0
    from app.core import sim as _sim
    for row in rows:
        mean = float(row["mean"])
        got = _sim.run(mean, mean)
        p = (got.home, got.draw, got.away)
        h, a = int(row["goals_home"]), int(row["goals_away"])
        y = (1, 0, 0) if h > a else (0, 1, 0) if h == a else (0, 0, 1)
        ll -= sum(yi * math.log(max(pi, 1e-9)) for yi, pi in zip(y, p))
        br += sum((pi - yi) ** 2 for yi, pi in zip(y, p))
    n = max(1, len(rows))
    return ll / n, br / n


def fit() -> None:
    """🔴🔴 3-5 — **시간순 분할** 적합과 보고. ⚠️ 값을 **쓰지 않는다**(보고만)."""
    from app.core import matchup as _mu
    rows: list[dict] = []
    for path in sorted(OUT.glob("rows_*.json")):
        rows += json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in rows if r.get("gaps") and r.get("mean")]
    rows.sort(key=lambda r: str(r.get("utc") or ""))
    if len(rows) < 50:
        _say(f"🔴 적합할 줄이 {len(rows)}건뿐이다 — **적합하지 않는다**"
             "(지어낸 계수보다 임시값이 낫다). 먼저 `backfill` 을 더 돌려라.")
        return
    cut = int(len(rows) * SPLIT)
    train, test = rows[:cut], rows[cut:]
    conf = dict(_mu.table().get("lambda_model") or {})
    cap = float(conf.get("cap_pct") or 35.0) / 100.0
    base_w = dict(_mu.table().get("weights") or {})
    _say(f"[적합] 줄 {len(rows)}건 — 학습 {len(train)} · 검증 {len(test)}"
         f"(시간순 {SPLIT:.0%} 분할)")
    # ── β 를 **격자**로 찾는다(한 변수라 격자가 충분하다)
    best = (None, -1e18)
    for i in range(0, 121):
        beta = i * 0.01
        ll = _poisson_ll(train, beta, base_w, cap)
        if ll > best[1]:
            best = (beta, ll)
    beta = float(best[0])
    _say(f"[적합] β = {beta:.3f}(격자 0~1.20 · 포아송 로그 가능도 {best[1]:.1f})")
    # ── 축 비중을 **좌표 하강**으로 다듬는다(합을 1 로 둔다)
    weights = dict(base_w)
    for _round in range(3):
        for key in ("axis0", "axis1", "axis2", "axis3"):
            best_w = (weights[key], _poisson_ll(train, beta, weights, cap))
            for cand in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
                said = dict(weights)
                said[key] = cand
                ll = _poisson_ll(train, beta, said, cap)
                if ll > best_w[1]:
                    best_w = (cand, ll)
            weights[key] = best_w[0]
    _say(f"[적합] 축 비중 = {weights}")
    ll_t, br_t = _logloss(test, beta, weights, cap)
    ll_b, br_b = _elo_baseline(test)
    _say("")
    _say("══ 보고(검증 구간) ══")
    _say(f" 상성 모형 — 로그 손실 {ll_t:.4f} · 브라이어 {br_t:.4f}")
    _say(f" 기준 모형 — 로그 손실 {ll_b:.4f} · 브라이어 {br_b:.4f}"
         "  ⚠️ 이 기준은 **리그 평균만**이다(과거 Elo 를 되돌릴 통로가 없다)")
    _say(_calib(test, beta, weights, cap))
    adopt = ll_t <= ll_b
    _say("")
    _say(f" 채택 판정 — {'✅ **적합 모드**' if adopt else '🔴 **임시 모드 유지**'}"
         f"(검증 로그 손실 {ll_t:.4f} {'≤' if adopt else '>'} 기준 {ll_b:.4f})")
    _say(" 🔴 값은 **자동으로 쓰지 않는다** — 사용자가 "
         "`config/matchup_model.yaml` 에 넣을지 정한다(P4·§6).")
    _say(" ⚠️ 한계 — 백필에 **기사 변수·새 사실이 없다**(과거 기사를 다시 모으는 "
         "통로가 없다). 그래서 이 적합은 **구조 특징**(축0·축1·축2·축3)만 센다.")


def _calib(rows: list[dict], beta: float, weights: dict, cap: float) -> str:
    """🔴 보정표 — 홈 승 확률 구간마다 **실제 홈 승 비율**."""
    box: dict[int, list] = {}
    for row in rows:
        p = _probs(row, beta, weights, cap)[0]
        key = min(9, int(p * 10))
        box.setdefault(key, []).append(
            1 if int(row["goals_home"]) > int(row["goals_away"]) else 0)
    out = [" 보정표(홈 승) — 구간 | 예측 | 실제 | 표본"]
    for key in sorted(box):
        got = box[key]
        out.append(f"   {key * 10:>2}~{key * 10 + 10:<3}% | "
                   f"{key * 10 + 5:>3}% | {sum(got) / len(got):>6.1%} | "
                   f"{len(got):>4}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("backfill", "fit"):
        _say(__doc__ or "")
        return 2
    if argv[1] == "fit":
        fit()
        return 0
    league = "9080"
    limit = 400
    if "--league" in argv:
        league = argv[argv.index("--league") + 1]
    if "--n" in argv:
        limit = int(argv[argv.index("--n") + 1])
    asyncio.run(backfill(league, limit=limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
