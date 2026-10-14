"""🔴🔴 **축 척도 판**(후보 ④a · 지시 2026-10-14e ④).

```
PYTHONPATH=. python tools/fit_axis_scale.py --upto 2025/2026
```

🔴 리그마다 **축 차의 표준편차**를 적는다 — 축0 원값이 17~19 라 차가 ±1.4 인데
   축3 은 ±0.15 다. 같은 가중 0.3 을 줘도 축0 이 종합을 혼자 정한다(백필 57.6%).
🔴 **누설 금지** — `--upto` 까지의 시즌만 쓴다(채점 시즌을 넣지 않는다).
⚠️ 값을 손으로 고르지 않는다 — 표본에서 나온 표준편차 그대로다.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

AXES = ("axis0", "axis1", "axis2", "axis3")


def main(argv: list[str]) -> int:
    import yaml

    import replays

    ap = argparse.ArgumentParser()
    ap.add_argument("--upto", default="", help="이 시즌까지만 쓴다(누설 금지)")
    args = ap.parse_args(argv[1:])

    rows, said_load = replays.load()
    print(said_load)
    print()
    box: dict[str, dict] = {}
    for r in rows:
        lg = str(r.get("league") or "")
        se = str(r.get("season") or "")
        if args.upto and se > args.upto:
            continue
        got = dict(r.get("gaps") or {})
        for a in AXES:
            if got.get(a) is None:
                continue
            box.setdefault(lg, {}).setdefault(a, []).append(float(got[a]))
    print(f"# 🔴🔴 축 척도 판 — 리그 {len(box)}개"
          + (f" · `{args.upto}` 까지" if args.upto else " · 전 시즌"))
    print()
    print("| 리그 | 축0 sd | 축1 sd | 축2 sd | 축3 sd | 표본 |")
    print("|---|---|---|---|---|---|")
    out_dir = ROOT / "data/axis_scale"
    out_dir.mkdir(parents=True, exist_ok=True)
    for lg, said in sorted(box.items()):
        one = {}
        for a in AXES:
            xs = said.get(a) or []
            if len(xs) < 30:
                continue
            one[a] = {"sd": round(st.pstdev(xs), 4), "n": len(xs),
                      "seasons": f"≤{args.upto}" if args.upto else "전부"}
        if not one:
            continue
        path = out_dir / f"{lg.replace(':', '_')}.yaml"
        path.write_text(yaml.safe_dump(one, allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
        print(f"| {lg} | " + " | ".join(
            (f"{one[a]['sd']:.3f}" if a in one else "⬜") for a in AXES)
            + f" | {max(v['n'] for v in one.values())} |")
    print()
    print(f"🔴 판을 적었다 — `data/axis_scale/<리그>.yaml`(후보 ④a 가 읽는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
