"""🔴🔴 **문턱 곡선**(공격형 검증 v2 · 지시 2026-10-14f §6).

```
PYTHONPATH=. python tools/cut_curve.py
```

🔴 **단폴·다리 문턱별** 적중률과 **하루 출력 수**를 백필에서 센다 — 문턱은
   이 곡선으로만 고른다(§6 *"문턱은 시즌 교차로만 고른다"*).
🔴 줄은 운영 λ 에서 **같은 격자**로 만든다(`probfloor.markets_of` · 사본 금지).
⚠️ 다폴은 **다리끼리 독립**이라고 가정하지 않는다 — 같은 날 다른 경기의 다리를
   실제로 묶어 **그 날 전부 맞았나**로 센다(곱셈 가정 없음).
"""
from __future__ import annotations

import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# 🔴 ⚠️ 실측 2026-10-14: 경기당 **최고 줄**은 거의 핸디 +1.5(≈87%)라 0.80 아래
#    문턱은 **전부 통과**한다(곡선이 평평했다) → 문턱 범위를 올려 잡는다.
CUTS = (0.70, 0.80, 0.85, 0.88, 0.90, 0.93, 0.95)
#: 🔴🔴 **의심 후 확률 자**의 문턱 범위(§4) — 보정표에서 가장 높은 칸이 **67.1%**
#   (승무패 50%+ · 1,470경기)라 위 범위는 **전부 0건**이다(실측 2026-10-14).
#   ⚠️ 두 자를 섞으면 *"문턱이 높아 보류"* 가 아니라 **"기계가 멈춘 것"** 이 된다.
CUTS_AFTER = (0.50, 0.55, 0.58, 0.60, 0.63, 0.65, 0.70, 0.75, 0.80)


def lines_of(lam: list[float], hg: int, ag: int) -> list[tuple]:
    """🔴 그 경기의 **줄 후보** — `(이름, 확률, 맞았나)`."""
    from app.core import probfloor as _pf
    from app.core import sim as _sim
    box = _pf.markets_of(_pf.score_grid(lam_home=lam[0], lam_away=lam[1]))
    out = _sim.run(lam[0], lam[1])
    d, tot = hg - ag, hg + ag
    got = [("홈 승", out.home, d > 0), ("원정 승", out.away, d < 0),
           ("무", out.draw, d == 0)]
    for key, ok in (("home-0.5", d > 0), ("home+0.5", d >= 0),
                    ("home+1.5", d > -2), ("away+0.5", d <= 0),
                    ("away+1.5", d < 2)):
        p = dict(box.get("ah") or {}).get(key)
        if p is not None:
            got.append((f"핸디 {key}", float(p), ok))
    for x in (1.5, 2.5, 3.5):
        p = dict(box.get("over") or {}).get(x)
        if p is not None:
            got.append((f"오버 {x}", float(p), tot > x))
            got.append((f"언더 {x}", 1.0 - float(p), tot < x))
    p = box.get("btts_yes")
    if p is not None:
        got.append(("BTTS 예", float(p), hg > 0 and ag > 0))
    return got


#: 🔴🔴 **보정표가 실제로 덮는 줄**(§3-3) — 승무패 방향뿐이다.
#:
#:  ⚠️ `보드 핸디`·`보드 언오버` 칸은 **그 경기 보드의 메인 라인 하나**로 쟀다.
#:     재생 줄(`lines_of`)은 `home±0.5`·`home+1.5`·`오버 1.5/2.5/3.5` 를 **전부**
#:     늘어놓으므로, 같은 칸 값을 그 줄들에 붙이면 거짓이 된다(실측 2026-10-14:
#:     핸디가 예측 51.0% → 실측 69.8% 로 벌어졌다 — `+1.5` 줄이 섞여서다).
#:  🔴 그래서 `--after` 는 **승무패 줄만** 센다. 핸디·언오버의 의심 후 확률은
#:     보정표에서 55% 를 넘지 않으므로 어차피 확신 문턱에 닿지 않는다.
AFTER_KINDS = ("홈 승", "원정 승", "무")


def _swap(after: dict, got: list[tuple]) -> list[tuple]:
    """🔴 줄 확률을 **칸 실측**으로 바꾼다. 보정표가 안 덮는 줄은 **버린다**."""
    from app.core import doubt as _db
    out: list[tuple] = []
    for nm, p, ok in got:
        if nm not in AFTER_KINDS:
            continue
        cell = _db.cell_for(after, _db.kind_of(nm), float(p), 0)
        if cell is not None and not cell.get("보류"):
            out.append((nm, float(cell["실측"]), ok))
    return out


def main() -> int:
    import argparse

    import replays

    ap = argparse.ArgumentParser()
    # 🔴🔴 **보드 줄만**(후속 지시 2026-10-14h §1) — 국내 보드에 흔한 기준선
    #    (승무패 · 핸디 ±0.5/±1.5 · 오버언더 2.5/3.5)만 남겨 곡선을 다시 그린다.
    ap.add_argument("--board-only", action="store_true")
    # 🔴🔴 **의심 후 확률 자 위에서** 곡선을 그린다(§4 — 문턱은 이것으로 고른다)
    #    ⚠️ 봇 원확률 자와 **섞지 않는다** — 보정표에서 가장 높은 칸이 67.1% 라
    #       원확률 문턱(0.88)을 그대로 쓰면 아무것도 통과하지 못한다.
    ap.add_argument("--after", action="store_true",
                    help="줄 확률을 `data/doubt_cal` 의 **칸 실측**으로 바꿔 센다")
    args = ap.parse_args(sys.argv[1:])
    from app.core import picks as _pk
    want = set(_pk.BOARD_COMMON) if args.board_only else None

    rows, said = replays.load()
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **홀드아웃만** — 보정표가 뺀 시즌에서 문턱을 고른다(§5 누설 금지)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `fit_doubt --wide` 는 보정표를 **이 재생본으로** 적합한다. 같은
    #     재생본에서 문턱을 고르면 **표본 안**이다 — 그 문턱은 내일 안 듣는다.
    if args.after:
        import yaml
        hold: list[str] = []
        for path in sorted((ROOT / "data/doubt_cal").glob("*.yaml")):
            got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            hold = [str(x) for x in (dict(got.get("meta") or {})
                                     .get("홀드아웃") or [])]
            if hold:
                break
        if hold:
            rows = [r for r in rows
                    if str(r.get("season") or "") in set(hold)]
            said += (f" · 🔴🔴 **홀드아웃 {hold} 만**(표본 밖 · "
                     f"{len(rows)}경기)")
    print(f"# 🔴🔴 문턱 곡선 — {said}"
          + (" · **보드 줄만**" if want is not None else "")
          + (" · 🔴 **의심 후 확률 자**(승무패 줄만 — 아래 `AFTER_KINDS`)"
             if args.after else ""))
    print()
    days: dict[str, list] = {}
    best: list[tuple] = []
    # 🔴 `--after` 는 보정표를 읽어 **칸 실측**으로 바꾼다(그 식은 `core/doubt`
    #    하나다 — 여기서 다시 짜지 않는다).
    after = None
    if args.after:
        from app.core import doubt as _db
        after = _db.plates()
        if not after:
            print("🔴 보정표가 없다 — `tools/fit_doubt.py` 를 먼저 돌려라")
            return 1
    for r in rows:
        got = lines_of([float(x) for x in r["lam"][:2]], int(r["hg"]),
                       int(r["ag"]))
        if after is not None:
            got = _swap(after, got)
        if want is not None:
            got = [x for x in got if x[0] in want]
            if not got:
                continue
        top = max(got, key=lambda x: x[1])
        best.append((top[1], top[2], str(r.get("day")), str(r.get("league")),
                     top[0]))
        days.setdefault(str(r.get("day")), []).append(top)
    print("| 문턱 | 단폴 수 | 적중 | 하루 평균 | 같은 줄 상위 3 |")
    print("|---|---|---|---|---|")
    n_days = len(days) or 1
    cuts = CUTS_AFTER if args.after else CUTS
    for cut in cuts:
        part = [x for x in best if x[0] >= cut]
        if not part:
            print(f"| {cut:.2f} | 0 | ⬜ | 0.0 | ⬜ |")
            continue
        from collections import Counter
        top3 = Counter(x[4] for x in part).most_common(3)
        print(f"| **{cut:.2f}** | {len(part)} | "
              f"**{100 * sum(1 for x in part if x[1]) / len(part):.1f}%** | "
              f"{len(part) / n_days:.2f} | "
              + " · ".join(f"{k} {v}" for k, v in top3) + " |")
    print()
    print("| 다리 문턱 | 2폴 묶음 | 2폴 적중 | 3폴 묶음 | 3폴 적중 |")
    print("|---|---|---|---|---|")
    for cut in cuts:
        two = three = ok2 = ok3 = 0
        for day, got in days.items():
            legs = [x for x in got if x[1] >= cut]
            # 🔴 **같은 경기 금지** — 경기당 한 줄만 들어 있다(`best`)
            if len(legs) >= 2:
                two += 1
                ok2 += int(all(x[2] for x in legs[:2]))
            if len(legs) >= 3:
                three += 1
                ok3 += int(all(x[2] for x in legs[:3]))
        print(f"| {cut:.2f} | {two} | "
              + (f"**{100 * ok2 / two:.1f}%**" if two else "⬜")
              + f" | {three} | "
              + (f"{100 * ok3 / three:.1f}%" if three else "⬜") + " |")
    # ── 🔴 줄 **종류별 보정**(예측 대비 실측) — 어느 줄이 믿을 만한가
    print()
    print("| 줄 종류 | 경기 | 예측 평균 | 실측 | 편차 | 0.70+ 적중 | 0.85+ 적중 |")
    print("|---|---|---|---|---|---|---|")
    fam: dict[str, list] = {}
    for r in rows:
        for nm, p, ok in lines_of([float(x) for x in r["lam"][:2]],
                                  int(r["hg"]), int(r["ag"])):
            if want is not None and nm not in want:
                continue
            # 🔴 `--after` 면 **같은 자**를 쓴다 — 위 표는 의심 후인데 이 표만
            #    봇 원확률이면 두 표가 서로 다른 말을 한다(실측 10-14: 그랬다).
            if after is not None:
                swap = _swap(after, [(nm, p, ok)])
                if not swap:
                    continue
                p = swap[0][1]
            key = ("승무패" if nm in ("홈 승", "원정 승", "무")
                   else ("핸디" if nm.startswith("핸디")
                         else ("오버·언더" if nm.startswith(("오버", "언더"))
                               else "BTTS")))
            fam.setdefault(key, []).append((p, ok))
    for key, xs in sorted(fam.items()):
        pred = stat.mean(p for p, _ok in xs)
        real = sum(1 for _p, ok in xs if ok) / len(xs)
        a = [ok for p, ok in xs if p >= 0.70]
        b = [ok for p, ok in xs if p >= 0.85]
        print(f"| {key} | {len(xs)} | {100 * pred:.1f}% | {100 * real:.1f}% | "
              f"**{100 * (real - pred):+.1f}%p** | "
              + (f"{100 * sum(a) / len(a):.1f}%({len(a)})" if a else "⬜")
              + " | " + (f"{100 * sum(b) / len(b):.1f}%({len(b)})" if b
                         else "⬜") + " |")
    print()
    print(f"- 날 수 {len(days)} · 경기 {len(rows)} · 경기당 최고 줄 확률 중앙값 "
          f"{100 * stat.median([x[0] for x in best]):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
