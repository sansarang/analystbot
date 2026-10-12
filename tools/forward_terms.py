"""🔴🔴 **§9 이변 신호 → 확률 후보(전진 선택)** — 지시서 2026-10-12(둘째) §9.

```
PYTHONPATH=. python tools/forward_terms.py var/judge/replay_big.json
```

> 한 항씩 추가 → 로그 손실 **구간상 이득**이면 채택 → 다음 항은 채택된 식 위에서
> 비교. 순서: `restΔ → loadΔ·cupΔ → pb_home(c3) → absΔ → form3Δ → benchΔ`.
> 항마다 **그룹 효과**도 보고: 그 신호가 켜진 경기들의 방향 적중률·로그 손실.

🔴 판정은 `app/core/metrics.verdict_of` **하나다**(결과를 보고 고치지 않는다).
🔴 **E1** — 시즌 교차: 계수는 평가 시즌 **밖**에서 적합한다(`check_split`).
🔴 공변량을 만드는 곳은 `app/core/context.covariates` 하나다(사본 금지).
⚠️ 이 재생에는 **리그 경기만** 들어 있다 — 그래서 `cupΔ` 는 구조적으로 0 이고,
   `absΔ`·`benchΔ` 는 §8(선수 점수)이 서기 전까지 **못 만든다**. 🔴 그 사실을
   보고가 그대로 적는다(없는 수를 0 으로 세지 않는다 · #3).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 지시가 정한 **순서** — 앞 항이 채택되면 그 위에서 다음을 센다
ORDER: tuple[tuple[str, ...], ...] = (
    ("rest_d",), ("load_d", "cup_d"), ("pb_home",), ("abs_d",), ("form3_d",),
)


def _ctx_rows(prior: list[dict], *, as_of):
    """🔴 그 팀의 지난 경기 → `ContextRow`. 목록은 **백필이 쌓은 그 목록**이다."""
    from app.core import context as _ctx
    said = [{"utc": r["utc"], "comp": r.get("comp") or "league",
             "gf": r["gf"], "ga": r["ga"]} for r in prior if r.get("utc")]
    return _ctx.row_of("", said, as_of=as_of)


def fit(rows: list[dict], *, adopted: set) -> tuple[dict, float]:
    """🔴 그 구간에서 계수를 적합한다 — 식은 `probfloor.compute` 하나다."""
    import numpy as np
    from scipy.optimize import minimize

    from app.core import probfloor as _pf
    names = ["b0", "b1", "h_league", "rho"] + [
        _pf.TERM_COEF[t] for t in _pf.TERMS if t in adopted]

    def nll(p):
        c = dict(zip(names, (float(v) for v in p), strict=True))
        out = 0.0
        for one in rows:
            lam, _why = _pf.compute(one["cov"], coef=c, adopted=adopted)
            lh, la = lam["home"], lam["away"]
            hg, ag = one["hg"], one["ag"]
            ll = (-lh + hg * math.log(lh) - math.lgamma(hg + 1)
                  - la + ag * math.log(la) - math.lgamma(ag + 1))
            rho = float(c.get("rho") or 0.0)
            if (hg, ag) == (0, 0):
                tau = 1.0 - lh * la * rho
            elif (hg, ag) == (0, 1):
                tau = 1.0 + lh * rho
            elif (hg, ag) == (1, 0):
                tau = 1.0 + la * rho
            elif (hg, ag) == (1, 1):
                tau = 1.0 - rho
            else:
                tau = 1.0
            out -= float(one.get("w") or 1.0) * (ll + math.log(max(1e-9, tau)))
        return out

    start = np.array([0.2, 0.3, 0.1, -0.05] + [0.0] * (len(names) - 4))
    got = minimize(nll, start, method="Nelder-Mead",
                   options={"maxiter": 40000, "xatol": 1e-6, "fatol": 1e-7})
    return (dict(zip(names, (float(v) for v in got.x), strict=True)),
            float(got.fun) / max(1, len(rows)))


def probs_of(rows: list[dict], *, coef: dict, adopted: set) -> list[list[float]]:
    from app.core import probfloor as _pf
    out = []
    for one in rows:
        lam, _why = _pf.compute(one["cov"], coef=coef, adopted=adopted)
        grid = _pf.score_grid(lam_home=lam["home"], lam_away=lam["away"],
                              rho=float(coef.get("rho") or 0.0))
        mk = _pf.markets_of(grid)
        out.append([mk["home"], mk["draw"], mk["away"]])
    return out


def main(argv: list[str]) -> int:
    said = argv[1] if len(argv) > 1 else "var/judge/replay_big.json"
    raw = json.loads(Path(said).read_text(encoding="utf-8"))
    from app.core import context as _ctx
    from app.core import metrics as _me
    # ── 🔴 공변량을 만든다 — 목록은 **그 경기 앞**까지만(L1)
    rows: list[dict] = []
    hist: dict[str, list[dict]] = {}
    for r in sorted(raw, key=lambda x: str(x.get("day") or "")):
        if r.get("dr") is None or r.get("hit") is None:
            continue
        day = str(r.get("day") or "")
        if not day:
            continue
        as_of = datetime.fromisoformat(f"{day}T00:00:00+00:00").replace(
            tzinfo=timezone.utc)
        home, away = str(r.get("home") or "H"), str(r.get("away") or "A")
        h_row = _ctx_rows(hist.get(home, []), as_of=as_of)
        a_row = _ctx_rows(hist.get(away, []), as_of=as_of)
        cov = dict(_ctx.covariates(h_row, a_row))
        cov["diff"] = float(r["dr"]) / 100.0      # 🔴 Elo 점수 → 100점 단위
        cov["pdiff"] = 0.0                        # ⚠️ §8 전까지 0(없는 수다)
        cov["abs_d"] = 0.0
        hit = int(r["hit"])
        # 🔴 **실제 스코어**를 쓴다 — 포아송 적합은 승무패가 아니라 골 수를 본다.
        #    ⚠️ 덤프에 스코어가 없으면 그 줄은 **버린다**(승무패 꼴로 지어내지
        #    않는다 · #4 추측 금지).
        if r.get("hg") is None or r.get("ag") is None:
            continue
        hg, ag = int(r["hg"]), int(r["ag"])
        rows.append({"cov": cov, "hg": hg, "ag": ag, "hit": hit,
                     "season": str(r.get("season") or ""),
                     "league": str(r.get("league") or ""),
                     "w": 1.0})
        for team, mine in ((home, True), (away, False)):
            hist.setdefault(team, []).append({
                "utc": f"{day}T00:00:00Z", "comp": "league",
                "gf": (hg if mine else ag), "ga": (ag if mine else hg)})
    print("# 🔴🔴 §9 전진 선택 — 이변 신호를 **확률 항**으로 시험한다")
    print()
    print(f"재생 {len(raw)}줄 → 공변량을 만든 경기 **{len(rows)}건**")
    print("⚠️ 이 재생에는 **리그 경기만** 있다 — `cupΔ` 는 구조적으로 0 이고 "
          "`absΔ`·`benchΔ` 는 §8(선수 점수) 전까지 **만들 수 없다**(0 으로 둔다).")
    print()
    seasons = sorted({r["season"] for r in rows if r["season"]})
    print(f"시즌 {seasons}")
    print()
    adopted: set[str] = set()
    for group in ORDER:
        # ── 🔴 시즌 교차 — 평가 시즌마다 그 **밖**에서 적합한다(E1)
        base_ll: list[float] = []
        cand_ll: list[float] = []
        on_rows: list[int] = []
        for s in seasons:
            ev = [r for r in rows if r["season"] == s]
            fi = [r for r in rows if r["season"] != s]
            if len(ev) < 30 or len(fi) < 80:
                continue
            _me.check_split(fit={r["season"] for r in fi}, eval={s})
            c_base, _n1 = fit(fi, adopted=adopted)
            c_cand, _n2 = fit(fi, adopted=adopted | set(group))
            p_base = probs_of(ev, coef=c_base, adopted=adopted)
            p_cand = probs_of(ev, coef=c_cand, adopted=adopted | set(group))
            for one, pb, pc in zip(ev, p_base, p_cand, strict=True):
                base_ll.append(_me.logloss(pb, one["hit"]))
                cand_ll.append(_me.logloss(pc, one["hit"]))
                if any(abs(float(one["cov"].get(t) or 0.0)) > 1e-9
                       for t in group):
                    on_rows.append(len(base_ll) - 1)
        if not base_ll:
            print(f"- `{'·'.join(group)}` — ⬜ **표본 부족**으로 못 쟀다")
            continue
        got = _me.paired(cand_ll, base_ll)
        verdict = _me.verdict_of(got)
        print(f"## 항 `{'·'.join(group)}`")
        print()
        print(f"- 로그 손실 후보 {sum(cand_ll) / len(cand_ll):.4f} vs 기준 "
              f"{sum(base_ll) / len(base_ll):.4f} · 짝지은 차 "
              f"**{got['mean']:+.4f}**(95% {got['lo']:+.4f}~{got['hi']:+.4f})"
              f" → **{verdict}**")
        if on_rows:
            a = sum(cand_ll[i] for i in on_rows) / len(on_rows)
            b = sum(base_ll[i] for i in on_rows) / len(on_rows)
            print(f"- 그 신호가 **켜진 경기 {len(on_rows)}건** — 로그 손실 후보 "
                  f"{a:.4f} vs 기준 {b:.4f}")
        else:
            print("- ⚠️ 그 신호가 **켜진 경기가 0건**이다 — 이 재생으로는 못 센다")
        print()
        if verdict == "채택":
            adopted |= set(group)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§12 하위 그룹 보정표** — 어디가 치우쳤나(직접 보정은 **안 한다**)
    # ══════════════════════════════════════════════════════════════════
    from app.core import groups as _gr
    said_rows = []
    for one in rows:
        tags = _gr.group_of({
            "pb_home": one["cov"].get("pb_home"),
            "load_14d": max(0, int(one["cov"].get("load_d") or 0)),
            "streak_len": None, "streak_kind": "",
        })
        if not tags:
            continue
        # 🔴 그 경기의 **마지막 채택 식**으로 만든 확률로 센다
        said_rows.append({"p": None, "hit": one["hit"], "tags": tags,
                          "row": one})
    if said_rows:
        for s in seasons:
            ev = [x for x in said_rows if x["row"]["season"] == s]
            fi = [r for r in rows if r["season"] != s]
            if not ev or len(fi) < 80:
                continue
            c, _n = fit(fi, adopted=adopted)
            p = probs_of([x["row"] for x in ev], coef=c, adopted=adopted)
            for x, pp in zip(ev, p, strict=True):
                x["p"] = pp
        got_bias = _gr.bias([x for x in said_rows if x["p"]])
        print("## §12 하위 그룹 보정표 — 홈 승 칸(평균 예측 − 실제)")
        print()
        print("| 그룹 | n | 편향 | 95% 구간 | 조치 |")
        print("|---|---|---|---|---|")
        for name, box in sorted(got_bias.items()):
            print(f"| {name}({_gr.GROUPS[name]}) | {box['n']} | "
                  f"{box['bias']:+.4f} | {box['lo']:+.4f}~{box['hi']:+.4f} | "
                  f"**{_gr.verdict_of(box)}** |")
        print()
    else:
        print("## §12 하위 그룹 보정표 — ⬜ **그룹에 든 경기가 없다**")
        print()
    print("## 🔴🔴 채택된 항")
    print()
    print(("`" + "` · `".join(sorted(adopted)) + "`") if adopted
          else "**없다** — 어느 항도 구간상 이득을 보이지 않았다(단순한 쪽 유지)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
