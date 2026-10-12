"""🔴🔴 **라인업이 확률을 얼마나 움직이나 — 분포** (사용자 지시 2026-10-13 추가).

```
PYTHONPATH=. python tools/xi_delta.py
```

> 라인업 지시서 3·4절(pdiff_⊥·absΔ_⊥·L-a·L-b·L-c)을 M1 위에서 시험할 때,
> **확정 XI 판 vs 예상 XI 판 확률 차이의 분포**도 함께 보고
> (지금은 대부분 ±2%p 안 — 채택 판에서 이 분포가 **넓어져야** 라인업이 실제로
> 반영되는 것).

🔴 **무엇을 "예상 XI" 로 두나** — 과거 경기의 *그때 예상 XI* 는 어디에도 저장돼 있지
   않다(fotmob 은 스냅샷 하나다). 그래서 **평소 XI**(`lineup_strength.usual_xi` ·
   그 경기 **앞** 경기들의 출전 분 가중 상위 11명)를 예상 XI 로 둔다 — 봇이 확정 XI
   전에 실제로 쓰는 그 대용이다. ⚠️ 그 사실을 보고가 **매번** 적는다(#4).
🔴 두 판의 차이는 **라인업뿐**이다(Elo·리그 평균·홈 배율·일정 전부 같다).
🔴 지금 운영 경로(M1 축0 = 선발 **로그 가치 합**)로 재고, 라인업 지시서가 채택 판을
   내면 같은 도구로 다시 재서 **분포가 넓어졌는지** 본다.
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _logsum(ids: list[str], value: dict) -> float | None:
    got = [float(value[i]) for i in ids if value.get(i)]
    if len(got) < 8:
        return None
    return sum(math.log(v) for v in got if v > 0)


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    rows = json.loads((ROOT / (said[0] if said
                               else "var/judge/lineup_rows.json")
                       ).read_text(encoding="utf-8"))
    from app.core import matchup as _mu
    from app.core import sim as _sim
    from app.core.ratings import lineup_strength as _ls
    conf = dict(_mu.table().get("weights") or {})
    beta = float(dict(_mu.table().get("lambda_model") or {}).get("beta") or 0.25)
    w0 = float(conf.get("axis0") or 0.0)
    print("# 🔴🔴 라인업이 확률을 얼마나 움직이나 — 분포")
    print()
    print("🔴 *예상 XI* 자리에 **평소 XI**(그 경기 앞 경기의 출전 분 가중 상위 11명)를"
          " 둔다 — 과거의 *그때 예상 XI* 는 저장돼 있지 않다(#4).")
    print()
    # 🔴 선수 가치는 **그 경기 페이지**에서 온다(as-of 정합) — 여기서는 덤프에 없으니
    #    **같은 리그 안의 출전 빈도**를 대용 가치로 쓰지 않는다. 대신 **로그 가치 합의
    #    차이 분포**를 못 재면 그 사실을 적는다.
    hist: dict[str, list[dict]] = {}
    got: list[float] = []
    same = 0
    skipped = 0
    for r in sorted(rows, key=lambda x: str(x["utc"])):
        as_of = datetime.fromisoformat(str(r["utc"]).replace("Z", "+00:00"))
        for side in ("home", "away"):
            team = r[side]
            past = [{"utc": x["utc"], "comp": "league",
                     "minutes": {p: 90 for p in x[f"{side}_ids"]}}
                    for x in hist.get(team, [])]
            usual, _w = _ls.usual_xi(past, as_of=as_of)
            today = list(r[f"{side}_ids"])
            if not usual or len(usual) < 11:
                skipped += 1
                continue
            # 🔴 **바뀐 자리 수**만으로는 확률을 못 센다 — 그래서 축0 이 쓰는 꼴
            #    (로그 가치 합)의 **차이**를 센다. 가치가 없으므로 **사람 수**로
            #    대신하고 그 사실을 이름으로 남긴다(#3).
            changed = len(set(usual) - set(today))
            got.append(float(changed))
            if changed == 0:
                same += 1
        hist.setdefault(r["home"], []).append(r)
        hist.setdefault(r["away"], []).append(r)
    if not got:
        print("🔴 평소 XI 를 만들 수 있는 경기가 없다 — 분포를 못 센다")
        return 1
    print("## 지금 경로에서 — **바뀐 자리 수** 분포(평소 XI → 확정 XI)")
    print()
    print("| 수 | 값 |")
    print("|---|---|")
    print(f"| 팀·경기 쌍 | {len(got)} |")
    print(f"| 평균 바뀐 자리 | **{st.fmean(got):.2f}명** |")
    print(f"| 중앙값 | {st.median(got):.1f}명 |")
    print(f"| 표준편차 | {st.pstdev(got):.2f} |")
    print(f"| 그대로(0명) | {same}쌍({same / len(got):.1%}) |")
    print(f"| 평소 XI 를 못 만든 쌍 | {skipped} |")
    print()
    # 🔴 그 자리 수가 **지금 축0·λ 로 얼마나** 움직이는가 — 측정한 민감도로 환산
    #    (실측 2026-10-13: 9자리 변경 → 축0 차 0.018 → 0.051, λ 이동 0.004)
    print("## 그 변화가 **지금** 확률을 얼마나 움직이나(실측 민감도로 환산)")
    print()
    print("🔴 실측(토리노–우디네세 · 2026-10-13): 양 팀 합 **9자리**가 바뀌었을 때")
    print("   선발 로그 가치 합 차 **+0.018 → +0.051**(Δ 0.033) →")
    print(f"   λ 이동 = β({beta:g}) × 비중({w0:g}) × 0.033 = "
          f"**{beta * w0 * 0.033:+.4f}** → λ 비 "
          f"{math.exp(beta * w0 * 0.033):.4f} → 확률 **~0.7%p**")
    print()
    out = _sim.run(1.6, 1.2)
    bent = _sim.run(1.6 * math.exp(beta * w0 * 0.033),
                    1.2 * math.exp(-beta * w0 * 0.033))
    print(f"   (시뮬로 확인: 홈 {out.home:.3%} → {bent.home:.3%} · "
          f"차 **{(bent.home - out.home) * 100:+.2f}%p**)")
    print()
    print("🔴 **그래서 지금은 라인업이 확률에 거의 안 닿는다** — 11명 **로그 합의 수준**"
          "이 입력이라 한두 자리 교체가 합의 0.3% 밖에 못 만든다.")
    print("⚠️ 라인업 지시서의 채택 판(`pdiff_⊥`·`absΔ_⊥`)이 서면 **이 분포가 넓어져야**"
          " 한다 — 같은 도구로 다시 재서 전후를 나란히 적는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
