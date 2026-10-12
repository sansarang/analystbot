"""🔴🔴 **fotmob 리그 결과로 기준선 실측** — 사용자 지시 2026-10-11 ①.

> 리그 홈 이점은 **그 리그 경기 결과로 실측**한다(자동 등록 리그 포함, fotmob 결과).
> 이번 시즌 **30경기 미만**이면 직전 시즌까지.

```
PYTHONPATH=. python tools/measure_fotmob_baselines.py 130 mls league:MLS
PYTHONPATH=. python tools/measure_fotmob_baselines.py --registered   # 손 표의 리그 전부
```

🔴 **봇은 이 파일을 읽기만 한다**(실행 중 측정 금지 — 적합과 같은 규율).
🔴 값·표본·계산일을 `config/goal_baselines.yaml` 에 적는다 — football-data 로 잰
   리그는 **건드리지 않는다**(그쪽이 더 긴 표본이다).
⚠️ fotmob 이 **중립 경기 표시를 안 준다** — 홈 몫에 중립 줄이 섞일 수 있고, 그
   한계를 `source` 에 적는다(지어내지 않는다 · #4).
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "config/goal_baselines.yaml"
#: 🔴 사용자 지시 ① — 이번 시즌이 이보다 적으면 직전 시즌까지 더한다
MIN_N = 30
#: 🔴🔴 **홈 배율은 여러 시즌으로 잰다**(사용자 지시 2026-10-12 1번) — 한 시즌
#   표본으로 **음수 홈 이점**이 나왔다(K리그1 185경기: 홈 1.1784 < 한 팀 1.2216).
#   ⚠️ K리그 홈 이점은 원래 작다 — 한 시즌 잡음을 그대로 쓰지 않는다.
MIN_N_HOME = 400
#: 🔴 수축 — 표본이 이만큼일 때 실측과 1.0 이 **반반**이다(🔴 임시 · 적합 전)
SHRINK_HALF_N = 400


async def measure(lid: str, slug: str, *, as_of=None) -> dict:
    """🔴 `as_of` — 이 시각 **이전** 경기만 센다(누설 금지 · L1).
    ⚠️ 비우면 **지금**이다(운영 갱신 때 그렇게 부른다)."""
    """🔴 `(리그 id, 슬러그)` → `{goals_per_match, home_share, n, seasons…}`."""
    from app.collect import fotmob as fm
    from app.net import Net
    net = Net(cache=True)
    page = await net.get(fm.league_matches_url(lid, slug))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    as_of = as_of or _dt.now(_tz.utc)
    rows = fm.league_results(j, as_of=as_of)
    seasons = fm.league_seasons(j)
    used = [seasons[0]] if seasons else ["이번"]
    # 🔴 이번 시즌이 얇으면 **직전 시즌까지** 받는다(지시 ①)
    i = 1
    # 🔴 홈 배율 때문에 **더 많이** 받는다(`MIN_N_HOME`) — 총골은 한 시즌이면
    #    충분하지만 홈/원정 쪼갬은 잡음이 크다(지시 1번).
    while len(rows) < max(MIN_N, MIN_N_HOME) and i < len(seasons):
        more = await net.get(fm.league_matches_url(lid, slug)
                             + f"?season={seasons[i]}")
        got = fm.league_results(
            fm.payload(getattr(more, "text", "") or "") or {}, as_of=as_of)
        if not got:
            break
        rows += got
        used.append(seasons[i])
        i += 1
    if not rows:
        return {}
    n = len(rows)
    gh = sum(r["gh"] for r in rows)
    ga = sum(r["ga"] for r in rows)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **홈 배율을 1.0 쪽으로 수축한다**(사용자 지시 2026-10-12 1번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 수축 뒤 값을 `home_share` 로 적는다 — 운영은 `home_share ÷ 한 팀 몫`
    #     으로 배율을 만들므로, **몫 자체를 당겨** 배율이 1 쪽으로 가게 한다.
    per_team = (gh + ga) / n / 2.0
    raw_home = gh / n
    w = float(n) / (float(n) + SHRINK_HALF_N)
    said_home = w * raw_home + (1.0 - w) * per_team
    return {"goals_per_match": round((gh + ga) / n, 4),
            "home_share_raw": round(raw_home, 4),
            "home_shrink_w": round(w, 4),
            "home_mul_raw": round(raw_home / per_team, 4) if per_team else None,
            "home_mul": round(said_home / per_team, 4) if per_team else None,
            # 🔴 운영이 읽는 칸은 **수축된 값**이다(위 주석 · 지시 1번)
            "home_share": round(said_home, 4),
            "n": n, "n_home": n,
            "source": (f"fotmob 리그 {lid} 결과 {used} · ⚠️ 중립 경기 표시를 "
                       f"안 준다(홈 몫에 섞일 수 있다)")}


def write(kind: str, got: dict) -> None:
    """🔴 `config/goal_baselines.yaml` 의 그 줄만 바꾼다(다른 줄은 안 건드린다)."""
    import yaml
    box = yaml.safe_load(OUT.read_text(encoding="utf-8")) or {}
    kinds = dict(box.get("kinds") or {})
    kinds[kind] = got
    box["kinds"] = dict(sorted(kinds.items()))
    box["measured_at"] = date.today().isoformat()
    OUT.write_text(yaml.safe_dump(box, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")


if __name__ == "__main__":
    lid, slug, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    said = asyncio.run(measure(lid, slug))
    if not said:
        raise SystemExit(f"🔴 `{kind}` 결과를 못 받았다 — 표를 안 건드린다")
    write(kind, said)
    print(f"적었다 — {kind}: {said}")
