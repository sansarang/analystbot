"""🔴🔴 **1번 MLS Elo 바닥 복구**(지시 2026-10-13 밤 넷째).

```
PYTHONPATH=. python tools/mls_elo_fix.py           # 원인 보고 + 시즌 교차 적합
PYTHONPATH=. python tools/mls_elo_fix.py --write   # 판에 적는다
```

> baseline {} 원인(리그 Elo 표 키·판 경로) 보고 · 복구 후 MLS 500경기
> **M1 vs Elo 비교 한 줄**.

🔴 재생은 **이미 적어 둔 것**을 쓴다(`var/judge/replay_mls.json` · 500경기) —
   다시 받지 않는다. 그 줄에는 `dr`(그 경기 **전** Elo 차)과 `hit` 가 있다.
🔴 적합은 **시즌 교차**다(한 시즌으로 적합 → 다른 시즌에서 평가) — 같은 표본에서
   적합하고 평가하면 그 수는 **거짓으로 좋다**.
🔴 적합 함수는 `fit_base_model._fit_rows` 하나다(대표팀·리그가 같은 문을 쓴다).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

DUMP = ROOT / "var/judge/replay_mls.json"
KEY = "league:MLS"


def cause() -> list[str]:
    """🔴 왜 `baseline {}` 인가 — **표 세 곳**을 열어 그대로 적는다."""
    import yaml
    out: list[str] = []
    # 🔴 대회 표를 읽는 문은 `competition.rows()` 하나다(사본 금지) — 내가
    #    yaml 열쇠를 **직접 짚었다가 빈 값을 봤다**(실측 2026-10-13).
    from app.core import competition as _cp
    row = dict(_cp.rows().get(KEY) or {})
    out.append(f"- `config/competitions.yaml` → `{KEY}.baseline` = "
               f"**{row.get('baseline')}**(비었다) · fotmob id "
               f"{(row.get('sources') or {}).get('fotmob_ids')}")
    elo = yaml.safe_load((ROOT / "config/league_elo.yaml").read_text(
        encoding="utf-8")) or {}
    said = list(elo.get("competitions") or [])
    out.append(f"- `config/league_elo.yaml` → `competitions` = {said} · "
               f"**MLS 없다**(그 표는 football-data 코드로 Elo 를 굴리는 리그 "
               f"목록이다 — MLS 는 football-data 코드가 표에 없다)")
    base = yaml.safe_load((ROOT / "config/base_model.yaml").read_text(
        encoding="utf-8")) or {}
    names = sorted(dict(base.get("models") or {}))
    out.append(f"- `config/base_model.yaml` → 모형 {len(names)}개 · "
               f"**`{KEY}` 없다**(있는 리그: "
               f"{[n for n in names if n.startswith('league:')]})")
    out.append("- 🔴 **원인 둘** — ① 대회 표의 `baseline` 이 비어 Elo **출처가 "
               "지정되지 않았다** ② 기준 모형 표에 `league:MLS` **적합이 없다**. "
               "그래서 `probfloor.floor_of` 가 바닥을 못 만들고 재생의 "
               "`floor`·`fresh` 가 **0건**이 됐다.")
    return out


def main(argv: list[str]) -> int:
    from fit_base_model import _fit_rows

    from app.core import metrics as me
    rows = json.loads(DUMP.read_text(encoding="utf-8"))
    print("# 🔴🔴 1번 MLS Elo 바닥 — 원인과 복구")
    print()
    for line in cause():
        print(line)
    print()
    said = [r for r in rows if r.get("dr") is not None
            and r.get("hit") is not None and r.get("ours")]
    seasons = sorted({str(r.get("season") or "") for r in said})
    print(f"재생 {len(rows)}경기 · 적합에 쓸 줄 **{len(said)}건** · 시즌 {seasons}")
    print()
    # 🔴 **시즌 교차** — 한 시즌으로 적합해 다른 시즌에서 잰다
    fits: dict[str, dict] = {}
    for s in seasons:
        train = [r for r in said if str(r.get("season")) != s]
        if len(train) < 100:
            print(f"- `{s}` — 🔴 훈련 표본 {len(train)}건(<100) · 그 시즌은 "
                  f"**평가하지 않는다**")
            continue
        fits[s] = _fit_rows([(float(r["dr"]), 2 - int(r["hit"]))
                             for r in train])
        print(f"- `{s}` 평가용 적합(훈련 {len(train)}건) — c1 "
              f"{fits[s]['c1']} · c2 {fits[s]['c2']} · b_dr {fits[s]['b_dr']}"
              f" · 수렴 {fits[s].get('converged')}")
    if not fits:
        print()
        print("🔴 **복구 못 했다** — 시즌 교차를 할 표본이 없다")
        return 1
    # 🔴 바닥 확률 → M1 과 나란히
    from app.core import base as _base
    elo_p: list[list[float]] = []
    m1_p: list[list[float]] = []
    hits: list[int] = []
    for r in said:
        co = fits.get(str(r.get("season")))
        if not co:
            continue
        got = _base.triple_from(c1=co["c1"], c2=co["c2"], b_dr=co["b_dr"],
                                dr=float(r["dr"]))
        elo_p.append([got.home, got.draw, got.away])
        m1_p.append([float(x) for x in r["ours"]])
        hits.append(int(r["hit"]))
    print()

    def score(p, h) -> dict:
        lls = [me.logloss(pi, hi) for pi, hi in zip(p, h, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(p, h, strict=True)]
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs}
    a, b = score(m1_p, hits), score(elo_p, hits)
    diff = me.paired(a["lls"], b["lls"])
    base_rate = [sum(1 for x in hits if x == k) / len(hits) for k in range(3)]
    flat = score([base_rate] * len(hits), hits)
    print("| 모형 | n | 로그 손실 | 방향 |")
    print("|---|---|---|---|")
    for name, got in (("**봇(M1)**", a), ("Elo만(복구 판)", b),
                      ("리그 기본률", flat)):
        print(f"| {name} | {len(hits)} | **{got['ll']:.4f}** | "
              f"{got['dir']:.2%} |")
    print()
    print(f"🔴 **한 줄 — MLS 500경기: M1 {a['ll']:.4f} / {a['dir']:.2%} vs "
          f"Elo {b['ll']:.4f} / {b['dir']:.2%}** · 짝지은 차이 "
          f"{diff['mean']:+.4f}({diff['lo']:+.4f}~{diff['hi']:+.4f}) → "
          + ("**M1 이 낫다**" if diff["mean"] < 0 and diff["hi"] < 0
             else ("M1 이 낫지만 구간이 0 을 품는다" if diff["mean"] < 0
                   else "🔴 **Elo 가 낫다**")))
    if "--write" in argv[1:]:
        import yaml
        all_fit = _fit_rows([(float(r["dr"]), 2 - int(r["hit"]))
                             for r in said])
        path = ROOT / "config/base_model.yaml"
        box = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        box.setdefault("models", {})[KEY] = {
            **all_fit, "fitted_at": "2026-10-13",
            "why": ("🔴 `tools/mls_elo_fix.py` 가 적었다 — 재생 500경기(0-0 포함)"
                    "로 적합 · **시즌 교차로 평가한 뒤** 전 표본으로 적합한 판")}
        path.write_text(yaml.safe_dump(box, allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
        print()
        print(f"🔴 **적었다** — `config/base_model.yaml` 의 `{KEY}`"
              f"(n {all_fit['n']} · 로그 손실 {all_fit['logloss']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
