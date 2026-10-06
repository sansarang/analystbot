"""🔴🔴 **② 환산 계수 적합** — `ΔS`(로그 가치 합) → **Elo 점수**. 사용자 승인 ②.

> eloratings 과거 결과 + fotmob 경기 페이지 가치로 **횡단 회귀**(1회, fetch 상한 80,
> 캐시). 계수·표본·R² 를 config 에. 이후 ② 가 **%p** 를 낸다.

```
PYTHONPATH=. python tools/fit_ds_to_dr.py            # 상한 80
PYTHONPATH=. python tools/fit_ds_to_dr.py --cap 40
```

## 어떻게 자료를 모으나 — **검색 없이**

🔴 경기 페이지는 `teamForm` 에 **그 두 팀의 과거 경기 링크**를 들고 있다. 그래서
   아는 경기 몇 개에서 **링크를 타고 퍼지면**(너비 우선) 검색 한 번 없이 대표팀 경기
   페이지를 모을 수 있다. 한 쪽당 **fetch 하나**이고 상한이 80 이다.
🔴 각 쪽에서 얻는 것: 날짜 · 두 팀 이름 · **선발 11명의 `marketValue`** →
   `S = Σ log(가치)`(② 와 **같은 식**).
🔴 Elo 는 `eloratings.net/{연}_results.tsv` 의 **경기 전 등급**(11·12열)에서 온다 —
   날짜와 두 나라 코드로 맞춘다. ⚠️ 날짜가 하루 어긋나는 일이 있어 **±1일**까지 본다.

## 무엇을 재나

`dr = a + b · (S_home − S_away)` 를 최소제곱으로 적합한다. `b` 가 **ΔS 1 단위당 Elo
점수**이고, 그것이 `ds_to_dr` 다. ⚠️ `R²` 가 낮으면 **쓰지 않는다** — 그때는 ② 가
전력 변화율만 말한다(지금과 같다).

🔴 **클럽 경기는 섞지 않는다** — eloratings 는 대표팀만 들고, 클럽 Elo 는 우리가
   따로 굴린다(`leagueelo`). 섞으면 두 등급 체계가 한 계수에 들어간다.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

OUT = "config/base_model.yaml"
CACHE = pathlib.Path(__file__).resolve().parents[1] / "var" / "dsfit"
#: 🔴 승인된 fetch 상한(사용자 지시 2026-10-06(6차) ②)
CAP = 80
#: 🔴 적합에 쓰려면 적어도 이만큼은 맞아야 한다 — 그 아래면 **적지 않는다**
MIN_ROWS = 20


def _norm(said: str) -> str:
    return " ".join(str(said or "").lower().split())


async def name_to_code(net) -> dict[str, str]:
    """🔴 `en.teams.tsv` → `{이름: ISO2}`. ⚠️ 못 받으면 빈 표(그러면 적합을 멈춘다)."""
    from app.collect import elo
    url = elo.file_of("teams")
    got = await net.get(url)
    out: dict[str, str] = {}
    for line in (getattr(got, "text", "") or "").splitlines():
        col = [c.strip() for c in line.split("\t")]
        if len(col) < 2 or len(col[0]) != 2:
            continue
        for nm in col[1:]:
            if nm:
                out[_norm(nm)] = col[0].upper()
    return out


async def elo_rows(net, years: list[int]) -> dict[tuple, tuple[float, float]]:
    """🔴 `{(날짜, 홈코드, 원정코드): (홈 Elo, 원정 Elo)}` — **경기 전** 등급이다."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from fit_base_model import parse_results           # 적합 전용 파서(같은 폴더)
    out: dict[tuple, tuple[float, float]] = {}
    from app.collect import elo
    for year in years:
        got = await net.get(elo.file_of("results", year=year))
        for r in parse_results(getattr(got, "text", "") or ""):
            out[(r.when, r.home, r.away)] = (r.home_elo, r.away_elo)
    return out


def _page(url: str) -> str | None:
    p = CACHE / f"{abs(hash(url)) % (10 ** 16)}.html"
    return p.read_text(encoding="utf-8") if p.is_file() else None


def _keep(url: str, text: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{abs(hash(url)) % (10 ** 16)}.html").write_text(text,
                                                               encoding="utf-8")


def seeds() -> list[str]:
    """🔴 출발점 — **이미 받아 둔 쪽들**의 주소(하루 캐시·녹화본에서 긁는다)."""
    out: list[str] = []
    root = pathlib.Path(__file__).resolve().parents[1]
    # 🔴 녹화본이 **주소를 들고 있다** — 하루 캐시 파일은 주소를 안 적는다(해시 이름).
    for p in (root / "tests" / "fixtures" / "cassettes").rglob("*.json"):
        try:
            box = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        url = str(box.get("url") or "")
        if "fotmob.com/match" in url and url not in out:
            out.append(url)
    # 🔴🔴 **대표팀 경기를 앞에 둔다** — eloratings 는 대표팀만 들고, 클럽 쪽으로
    #    번지면 받은 쪽의 절반이 **맞출 수 없는 경기**가 된다(실측 2026-10-06:
    #    80쪽을 받아 47경기를 얻었는데 Elo 와 맞은 것은 19경기였다 — 씨앗에
    #    USL 클럽 경기가 섞여 있었다).
    from app import rules as _rules
    said = {str(w).lower() for w in
            ((_rules._load("config/nations.yaml") or {}).get("fifa_names") or [])}
    def _nat(u: str) -> int:
        low = u.lower()
        hit = any(w and w.replace(" ", "-") in low for w in said)
        return 0 if hit else 1
    out.sort(key=_nat)
    return out[:16]


async def collect(net, cap: int) -> list[dict]:
    """🔴 경기 쪽을 **링크 타고** 모은다. ⚠️ `cap` 번만 받는다(승인 상한)."""
    from app.collect import fotmob
    queue = list(seeds())
    seen: set[str] = set()
    rows: list[dict] = []
    spent = 0
    while queue and spent < cap:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        text = _page(url)
        if text is None:
            got = await net.get(url)
            if not getattr(got, "ok", False):
                continue
            text = str(getattr(got, "text", "") or "")
            _keep(url, text)
            spent += 1
        j = fotmob.payload(text)
        if not j:
            continue
        g = (fotmob._page(j).get("general") or {})
        when = fotmob.kickoff(j)
        home = str((g.get("homeTeam") or {}).get("name") or "")
        away = str((g.get("awayTeam") or {}).get("name") or "")
        vals = []
        for side in ("homeTeam", "awayTeam"):
            box = fotmob._side(j, side) or {}
            said = [p.get("value") for p in fotmob.players_of(box)]
            vals.append([float(v) for v in said if v])
        if when and home and away and len(vals[0]) >= 9 and len(vals[1]) >= 9:
            rows.append({"when": when.date().isoformat(), "home": home,
                         "away": away, "s_home": float(np.log(vals[0]).sum()),
                         "s_away": float(np.log(vals[1]).sum()),
                         "n_home": len(vals[0]), "n_away": len(vals[1])})
        # 🔴 이 쪽이 가리키는 **다른 경기들**을 큐에 넣는다(검색 없이 퍼진다)
        for nxt in fotmob.prev_match_urls(j, _Q(home),  # type: ignore[arg-type]
                                          limit=5) + \
                fotmob.prev_match_urls(j, _Q(away),  # type: ignore[arg-type]
                                       limit=5):
            if nxt not in seen:
                queue.append(nxt)
    print(f"[dsfit] 쪽 {len(seen)}개 중 새로 받은 것 {spent}개(상한 {cap}) · "
          f"쓸 수 있는 경기 {len(rows)}개")
    return rows


class _Q:
    """🔴 `prev_match_urls` 가 보는 칸만 든 **최소 질문**(그 함수는 팀 이름만 쓴다)."""

    def __init__(self, team: str) -> None:
        self.team = team
        self.local = ""
        self.id = "dsfit"


def join(rows: list[dict], codes: dict[str, str],
         elos: dict[tuple, tuple[float, float]]) -> list[tuple[float, float]]:
    """🔴 `(dr, ΔS차)` 쌍 — 날짜 ±1일과 두 나라 코드로 맞춘다. ⚠️ 못 맞추면 버린다."""
    out: list[tuple[float, float]] = []
    for r in rows:
        a, b = codes.get(_norm(r["home"])), codes.get(_norm(r["away"]))
        if not a or not b:
            continue
        day = date.fromisoformat(r["when"])
        hit = False
        for off in (0, -1, 1, -2, 2):
            got = elos.get((day + timedelta(days=off), a, b))
            if got:
                out.append((got[0] - got[1], r["s_home"] - r["s_away"]))
                hit = True
                break
        if hit:
            continue
        # 🔴 **뒤바뀐 꼴도 본다** — 중립 경기는 eloratings 가 결과순으로 적어서
        #    우리가 아는 홈/원정과 **순서가 다르다**(그 줄의 등급은 그대로 쓴다).
        for off in (0, -1, 1, -2, 2):
            got = elos.get((day + timedelta(days=off), b, a))
            if got:
                out.append((got[1] - got[0], r["s_home"] - r["s_away"]))
                break
    return out


def fit(pairs: list[tuple[float, float]]) -> dict:
    """🔴 최소제곱 `dr = a + b·ΔS차`. `b` 가 `ds_to_dr` 다. ⚠️ `R²` 를 함께 돌려준다."""
    x = np.array([p[1] for p in pairs], dtype=float)
    y = np.array([p[0] for p in pairs], dtype=float)
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"ds_to_dr": round(float(b), 4), "intercept": round(float(a), 4),
            "n": int(len(pairs)), "r2": round(float(r2), 4),
            "fitted_at": date.today().isoformat(),
            "x_std": round(float(x.std()), 4), "y_std": round(float(y.std()), 4)}


async def main(argv: list[str]) -> int:
    cap = int(argv[argv.index("--cap") + 1]) if "--cap" in argv else CAP
    from app import net as _net_mod
    net = _net_mod.Net()
    codes = await name_to_code(net)
    if not codes:
        print("🔴 나라 이름표를 못 받았다 — 멈춘다")
        return 1
    # 🔴 다섯 해를 본다 — 맞는 경기가 적으면 계수를 못 적는다(실측: 3해로 19개)
    years = [datetime.now(timezone.utc).year - i for i in range(5)]
    elos = await elo_rows(net, years)
    rows = await collect(net, cap)
    pairs = join(rows, codes, elos)
    print(f"[dsfit] Elo 와 맞은 경기 {len(pairs)}개 / 모은 {len(rows)}개")
    if len(pairs) < MIN_ROWS:
        print(f"🔴 표본 {len(pairs)}개 < {MIN_ROWS} — **계수를 적지 않는다**"
              f"(② 는 전력 변화율만 말한다)")
        return 1
    got = fit(pairs)
    print(f"[dsfit] ds_to_dr={got['ds_to_dr']} Elo/ΔS · n={got['n']} · "
          f"R²={got['r2']}")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from fit_base_model import _write
    # 🔴 대표팀 두 유형에 **같은 계수**를 넣는다 — 가치·Elo 관계는 대회 유형이
    #    아니라 **대표팀 전체**에서 쟀다(그 사실을 `ds_fit_note` 로 적는다)
    import yaml as _yaml
    box = dict((_yaml.safe_load(pathlib.Path(OUT).read_text(encoding="utf-8"))
                or {}).get("models") or {})
    mine: dict[str, dict] = {}
    for kind in ("national_friendly", "national_official"):
        said = dict(box.get(kind) or {})
        if not said:
            continue
        said["ds_to_dr"] = got["ds_to_dr"]
        said["ds_fit"] = {k: got[k] for k in ("n", "r2", "intercept",
                                              "fitted_at", "x_std", "y_std")}
        said["ds_fit_note"] = ("대표팀 경기 횡단 회귀(fotmob 선발 가치 vs eloratings "
                               "경기 전 Elo) — 대회 유형을 가르지 않았다")
        mine[kind] = said
    _write(mine, head_extra="")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
