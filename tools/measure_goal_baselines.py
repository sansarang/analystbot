"""🔴🔴 **대회 유형별 경기당 평균 득점 실측** — 사용자 지시 2026-10-07(총평 검열 §3).

```
PYTHONPATH=. python tools/measure_goal_baselines.py            # 전부
PYTHONPATH=. python tools/measure_goal_baselines.py --national # 대표팀만
```

> *"대회 유형별 경기당 평균 득점"을 실측한다: ① 적합에 쓴 eloratings 과거 결과에서
> 대회 유형별(국가대표 친선/공식전)로, 리그는 자체 Elo에 쓴 football-data 결과에서.
> 값·표본·계산일을 `config/goal_baselines.yaml` 에.*

🔴 **봇은 이 파일을 읽기만 한다**(실행 중 측정 금지 — 적합과 같은 규율).
⚠️ 중립 경기 줄도 **총골에는 쓴다** — 그 줄의 결함은 *"이긴 팀이 먼저 적힌다"* 는
   **순서**이고(네 층 §3-2 실측), **두 팀 득점의 합**은 그 순서와 무관하다.
   🔴 그래서 홈/원정 몫은 중립 줄에서 **세지 않는다**(홈 개최 줄만).
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "config/goal_baselines.yaml"


def _mean(rows: list[int]) -> float:
    return round(sum(rows) / len(rows), 4) if rows else 0.0


async def national(span: str = "2010-2026") -> dict:
    """🔴 eloratings 과거 결과 — `national_friendly`·`national_official`."""
    from app import net as _net_mod
    from app.collect import elo
    from tools.fit_base_model import parse_results
    net = _net_mod.Net()
    a, b = (int(v) for v in span.split("-"))
    box: dict[str, list[int]] = {"national_friendly": [], "national_official": []}
    home: dict[str, list[int]] = {k: [] for k in box}
    for year in range(a, b + 1):
        url = elo.file_of("results", year=year)
        ok, why = await net.allowed(url)
        if not ok:
            print(f"[goals] {year} robots 가 막았다 — {why}", flush=True)
            continue
        got = await net.get(url)
        said = parse_results(getattr(got, "text", "") or "")
        for r in said:
            kind = ("national_friendly" if r.friendly else "national_official")
            box[kind].append(r.home_score + r.away_score)
            if r.at_home:
                home[kind].append(r.home_score)
        print(f"[goals] {year} {len(said)}경기", flush=True)
    out = {}
    for kind, rows in box.items():
        out[kind] = {"goals_per_match": _mean(rows), "n": len(rows),
                     "home_share": _mean(home[kind]), "n_home": len(home[kind]),
                     "source": f"eloratings.net {{연}}_results.tsv {span}"}
    return out


async def leagues() -> dict:
    """🔴 football-data 결과 — 리그마다, 그리고 **리그 전체 합계**."""
    from app import net as _net_mod
    from app.collect import leagueelo
    net = _net_mod.Net()
    box = leagueelo.table()
    seasons = [str(x) for x in (box.get("seasons") or [])]
    comps = [str(x) for x in (box.get("competitions") or box.get("comps") or [])]
    out: dict = {}
    every: list[int] = []
    for comp in comps:
        got, why = await leagueelo.fetch(net, comp, seasons)
        rows = leagueelo._rows(got)
        goals = [h + a for _w, _h, _a, h, a in rows]
        every += goals
        if goals:
            out[f"league:{comp}"] = {
                "goals_per_match": _mean(goals), "n": len(goals),
                "home_share": _mean([h for _w, _h, _a, h, _a2 in rows]),
                "n_home": len(rows),
                "source": f"football-data {comp} {seasons}"}
        print(f"[goals] league:{comp} {len(goals)}경기 · {why[:40]}", flush=True)
    if every:
        out["league"] = {"goals_per_match": _mean(every), "n": len(every),
                         "source": f"football-data {comps} {seasons} 합계"}
    return out


def write(box: dict) -> None:
    head = (
        "# 🔴🔴 **대회 유형별 경기당 평균 득점** — 실측(사용자 지시 2026-10-07 §3)\n"
        "#\n"
        "# ⚠️ **손으로 고치지 않는다** — `tools/measure_goal_baselines.py` 가 쓴다.\n"
        "# 🔴 쓰는 곳: `s5_verify` 가 폼 변수(`recent_pattern`)의 **득점 방향**을 이\n"
        "#    기준의 **팀당 몫**(경기당 평균 ÷ 2)과 견줘 정한다(±0.2).\n"
        f"# 측정일: {datetime.now(timezone.utc).date().isoformat()}\n"
        "#\n"
        "# | 칸 | 뜻 |\n"
        "# |---|---|\n"
        "# | `goals_per_match` | 두 팀 득점 **합**의 평균 |\n"
        "# | `home_share` | 홈 개최 경기의 **홈 팀** 평균 득점(중립 줄은 뺐다) |\n"
        "# | `n` | 표본 경기 수 |\n\n")
    lines = [head, f"measured_at: {date.today().isoformat()}\n", "kinds:\n"]
    for kind, row in sorted(box.items()):
        lines.append(f"  {kind}:\n")
        for key in ("goals_per_match", "home_share", "n", "n_home"):
            if key in row:
                lines.append(f"    {key}: {row[key]}\n")
        lines.append(f"    source: \"{row.get('source', '')}\"\n")
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"[goals] 적었다 {OUT} — {len(box)}칸", flush=True)


async def main(argv: list[str]) -> int:
    box: dict = {}
    if "--league" not in argv:
        box.update(await national())
    if "--national" not in argv:
        box.update(await leagues())
    if not box:
        print("🔴 아무것도 못 쟀다 — 쓰지 않는다")
        return 1
    write(box)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
