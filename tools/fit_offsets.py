"""🔴🔴 **§5-3-a 리그 오프셋 · 5-3-c 대회 홈 이점** 적합 도구.

```
PYTHONPATH=. python tools/fit_offsets.py --comp league:UCL --collect
PYTHONPATH=. python tools/fit_offsets.py --comp league:UCL --fit
```

> (a) 대륙 대회의 **리그 간 맞대결** 결과(as_of 이전, 최근 3시즌)로 리그별
>     오프셋을 추정 → 팀 점수 = 리그 내 Elo + 리그 오프셋.
>     판 `data/league_offsets/<대륙>/<as_of>.yaml`(리그별 값·표본 수·구간).
> (c) 홈 이점: **그 대회 자체 실측**(최근 3시즌 · 대회별 판).

🔴 **적합 꼴** — 브래들리–테리(승=1·무=0.5·패=0):
   `s ~ logistic((dr_국내 + off_홈 − off_원정 + H) · ln10 / 400)`
   · `dr_국내` 는 **각 팀의 국내 리그 안에서 굴린 Elo** 차다(리그 안에서만 비교
     가능한 수 — 그래서 오프셋이 필요하다).
   · 식별을 위해 **오프셋 평균 0** 으로 묶는다(`H` 가 대회 홈 이점을 흡수한다).
🔴 **CC2** — `--as-of` **이전** 경기만 적합에 쓴다(판 이름이 그 날짜다).
🔴 **MIN_GAMES(20) 미달 리그는 판에 값을 안 적는다** — `n` 만 적고 `value` 를
   비운다(그 팀이 낀 경기는 **레이팅 비교 미산출** · `offsets.of` 가 그 말을 한다).
⚠️ `app/` 은 yaml 을 쓰지 않는다 — **판을 적는 것은 이 도구**다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 모은 경기를 적어 두는 곳(같은 수집을 두 번 돌리지 않는다)
def box_of(comp: str) -> Path:
    return ROOT / f"var/judge/offsets_{comp.replace(':', '_')}.json"


K_ELO = 20.0


async def collect_fast(comp: str, *, seasons: int) -> int:
    """🔴🔴 **빠른 수집**(P1) — 대회 **일정 한 장**(시즌당) + 팀 페이지의 국내 리그.

    🔴 경기 페이지를 받지 않는다 — 일정의 `scoreStr` 로 스코어가 온다(247경기
       통신 → **시즌 수 + 팀 수**로 줄었다). ⚠️ 그래서 ACL 도 몇 분에 끝난다.
    """
    import json as _json

    from fit_comp_record import rows_of as _rows
    from fit_league_elo import domestic_of as _dom
    from app.net import Net
    net = Net(cache=True, day_cache=True)
    rows, why = await _rows(comp, seasons=seasons)
    print(f"{comp} — 일정에서 끝난 경기 **{len(rows)}건**({why})", flush=True)
    # 🔴 팀 번호는 일정 줄에 없다(이름만) — 팀 페이지는 이름으로 찾는다
    seen: dict[str, tuple[str, str]] = {}
    out: list[dict] = []
    gone: dict[str, int] = {}
    for i, r in enumerate(rows, 1):
        if i % 50 == 0:
            print(f"   … {i}/{len(rows)}", flush=True)
        box: dict[str, str] = {}
        for side in ("home", "away"):
            name = str(r.get(side) or "")
            if name not in seen:
                key, said, _why = await _dom(net, name, "")
                seen[name] = (key, said)
            box[side] = seen[name][0]
        if not (box.get("home") and box.get("away")):
            gone["국내 리그를 못 찾았다"] = gone.get("국내 리그를 못 찾았다", 0) + 1
        out.append({"day": str(r.get("season") or ""), "season": r.get("season"),
                    "home": r.get("home"), "away": r.get("away"),
                    "hg": r.get("hg"), "ag": r.get("ag"),
                    "stage": r.get("stage"),
                    "home_league": box.get("home") or "",
                    "away_league": box.get("away") or ""})
    box_of(comp).write_text(_json.dumps(out, ensure_ascii=False),
                            encoding="utf-8")
    print(f"🔴 {len(out)}경기를 적었다 — {box_of(comp).relative_to(ROOT)}")
    print("🔴 **버린 것** — "
          + (" · ".join(f"{k} {v}건" for k, v in sorted(gone.items()))
             if gone else "없다"))
    return 0


async def collect(comp: str, *, seasons: int) -> int:
    """🔴 그 대회의 끝난 경기 + **각 팀의 국내 리그**를 받아 적는다."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.net import Net
    one = _cp.row_of(comp)
    ids = [str(x) for x in ((one.get("sources") or {}).get("fotmob_ids") or [])]
    if not ids:
        print(f"🔴 `{comp}` 의 fotmob id 가 표에 없다 — 받을 수 없다")
        return 2
    net = Net(cache=True)
    rows = await fm.league_matches(net, ids[0])
    page0 = await net.get(fm.league_matches_url(ids[0], "x"))
    said_seasons = fm.league_seasons(
        fm.payload(getattr(page0, "text", "") or "") or {})
    for r in rows:
        r["season"] = str(said_seasons[0] if said_seasons else "")
    for season in said_seasons[1:max(1, int(seasons))]:
        more = await net.get(fm.league_matches_url(ids[0], "x")
                             + f"?season={season}")
        pp = (((fm.payload(getattr(more, "text", "") or "") or {})
               .get("props") or {}).get("pageProps") or {})
        for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
            st = m.get("status") or {}
            rows.append({"season": str(season), "id": str(m.get("id") or ""),
                         "home": str((m.get("home") or {}).get("name") or ""),
                         "away": str((m.get("away") or {}).get("name") or ""),
                         "utc": str(st.get("utcTime") or ""),
                         "finished": bool(st.get("finished"))})
    done = sorted([r for r in rows if r.get("finished") and r.get("utc")],
                  key=lambda r: str(r["utc"]))
    print(f"{comp} — 끝난 경기 {len(done)}건 · 시즌 "
          f"{said_seasons[:max(1, int(seasons))]}", flush=True)
    out: list[dict] = []
    gone: dict[str, int] = {}
    seen: dict[str, dict] = {}
    for i, m in enumerate(done, 1):
        if i % 25 == 0:
            print(f"   … {i}/{len(done)}", flush=True)
        page = await net.get(fm.match_url(str(m.get("id") or "")))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            gone["경기 페이지 못 읽었다"] = gone.get("경기 페이지 못 읽었다", 0) + 1
            continue
        goals = fm.goals_of(j) or []
        h = sum(1 for x in goals
                if bool(x.get("home")) != bool(x.get("own_goal")))
        a = len(goals) - h
        # 🔴 **스코어가 0-0 인 경기도 센다** — `goals` 가 비면 0-0 이다
        said_ids = fm.side_ids(j)
        box_side = {}
        for which, tid in zip(("home", "away"), said_ids, strict=False):
            said_lg, why_lg = await _domestic_of(net, tid, seen)
            box_side[which] = {"id": str(tid), "league": said_lg,
                               "why": why_lg}
        if not all(box_side.get(k, {}).get("league") for k in ("home", "away")):
            gone["국내 리그를 못 찾았다"] = gone.get("국내 리그를 못 찾았다", 0) + 1
        out.append({"id": str(m.get("id") or ""), "season": m.get("season"),
                    "day": str(m.get("utc"))[:10], "utc": str(m.get("utc")),
                    "home": m.get("home"), "away": m.get("away"),
                    "hg": h, "ag": a,
                    "stage": str(fm.round_note(j) or ""),
                    "home_league": box_side.get("home", {}).get("league") or "",
                    "away_league": box_side.get("away", {}).get("league") or ""})
    box_of(comp).write_text(json.dumps(out, ensure_ascii=False),
                            encoding="utf-8")
    print(f"🔴 {len(out)}경기를 적었다 — {box_of(comp).relative_to(ROOT)}")
    print("🔴 **버린 것** — "
          + (" · ".join(f"{k} {v}건" for k, v in sorted(gone.items()))
             if gone else "없다"))
    return 0


async def _domestic_of(net, team_id: object, seen: dict) -> tuple[str, str]:
    """🔴 그 팀의 **국내 리그 열쇠** — 팀 페이지의 순위표 리그에서 온다."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    key = str(team_id or "")
    if key in seen:
        return seen[key]["league"], seen[key]["why"]
    got = await net.get(fm.team_fixtures_url(key, "x"))
    j = fm.payload(getattr(got, "text", "") or "") or {}
    said = ""
    why = "⬜ 팀 페이지에서 국내 리그를 못 읽었다"
    # 🔴🔴 **받아서 확인한 자리**(2026-10-13): 국내 리그는
    #    `props.pageProps.fallback["team-<id>"].table[*].data` 에 있다
    #    (`leagueId` 55 · `leagueName` "Serie A" · `ccode` ITA).
    #  ⚠️ 내가 처음 본 자리(`pageProps.team.table`)는 **없는 칸**이었고, 그래서
    #     396경기 전부 *"국내 리그를 못 찾았다"* 가 됐다 — 받아서 확인했다(#4).
    box = (((j.get("props") or {}).get("pageProps") or {})
           .get("fallback") or {}).get(f"team-{key}") or {}
    rows = box.get("table")
    rows = rows if isinstance(rows, list) else [rows]
    for one in rows:
        data = (one or {}).get("data") if isinstance(one, dict) else None
        # ⚠️ 대륙 대회 칸은 `tables`(여러 조)로 들어온다 — 그것도 본다
        for r in ([data] if isinstance(data, dict) else []) + \
                 list((data or {}).get("tables") or []
                      if isinstance(data, dict) else []):
            if not isinstance(r, dict):
                continue
            lid = r.get("leagueId")
            lname = str(r.get("leagueName") or "")
            if lid is None and not lname:
                continue
            k2, w2 = _cp.key_of(competition=lname, league_id=lid)
            if k2 and _cp.kind_require(k2)[0] == "domestic_league":
                said, why = k2, f"팀 페이지 순위표 `{lname}`({lid}) · {w2}"
                break
        if said:
            break
    seen[key] = {"league": said, "why": why}
    return said, why


def domestic_elo() -> tuple[dict, str]:
    """🔴 국내 리그 **Elo**(그 리그 재생 덤프로 굴린다 · 리그 안에서만 비교)."""
    # 🔴 덤프 목록은 `replays` 하나가 든다(손으로 들지 않는다 · #1)
    from replays import load as _replays
    rows, why = _replays()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **P1 — 자동 등록 리그의 Elo 판도 읽는다**(수정 지시 2026-10-13 밤)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 `tools/fit_league_elo.py` 가 적은 `data/league_elo_auto/*.yaml` 이다
    #     (사우디·중국·태국·V리그 등 **백필이 없는 리그**의 팀별 Elo).
    #  ⚠️ 재생 덤프로 굴린 Elo 와 **같은 잣대가 아니다**(리그 안에서만 비교 가능).
    #     오프셋이 하는 일이 바로 그 잣대 맞추기다.
    auto: dict[str, float] = {}
    said_auto: list[str] = []
    box_auto = ROOT / "data/league_elo_auto"
    if box_auto.is_dir():
        import yaml
        for path in sorted(box_auto.glob("*.yaml")):
            got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            teams = dict(got.get("teams") or {})
            for k, v in teams.items():
                auto.setdefault(str(k), float(v))
            said_auto.append(f"{got.get('league')} {len(teams)}팀")
    elo: dict[str, float] = {}
    n = 0
    for r in sorted(rows, key=lambda x: str(x.get("day"))):
        if r.get("hg") is None or r.get("ag") is None:
            continue
        home, away = str(r.get("home")), str(r.get("away"))
        dr = float(elo.get(home, 1500.0)) - float(elo.get(away, 1500.0))
        exp = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        got = (1.0 if int(r["hg"]) > int(r["ag"])
               else (0.5 if int(r["hg"]) == int(r["ag"]) else 0.0))
        elo[home] = float(elo.get(home, 1500.0)) + K_ELO * (got - exp)
        elo[away] = float(elo.get(away, 1500.0)) - K_ELO * (got - exp)
        n += 1
    # 🔴 **재생 Elo 가 먼저**(같은 잣대의 표본이 크다) · 없는 팀만 자동 판으로
    said_more = 0
    for k, v in auto.items():
        if k not in elo:
            elo[k] = v
            said_more += 1
    return elo, (f"{why} → **국내 Elo** {n}경기로 굴렸다 · 팀 {len(elo)}개"
                 f"(자동 등록 판에서 **{said_more}팀** 보탰다 — "
                 + " · ".join(said_auto[:6])
                 + (f" 외 {len(said_auto) - 6}" if len(said_auto) > 6 else "")
                 + ")")


def fit(comp: str, *, as_of: str) -> int:
    """🔴🔴 브래들리–테리로 **리그 오프셋 + 대회 홈 이점**을 적합한다."""
    import numpy as np
    from scipy.optimize import minimize

    from app.core import competition as _cp
    from app.core import offsets as off
    # 🔴🔴 **같은 대륙의 대회를 함께 적합한다**(P1) — ACL Elite + ACL2 를 한 판으로
    #    보면 리그 쌍 표본이 커진다(V리그처럼 Elite 에 거의 안 오는 리그가 산다).
    #    ⚠️ 판은 **대륙별 한 장**이므로 섞어야 맞다(안 섞으면 뒤에 돈 쪽이 덮는다).
    from app.core import competition as _cp0
    said_conf = str(_cp0.row_of(comp).get("confederation") or "").upper()
    rows: list[dict] = []
    said_from: list[str] = []
    for key, one in sorted(_cp0.rows().items()):
        if str(one.get("confederation") or "").upper() != said_conf:
            continue
        if _cp0.kind_require(key)[0] != "club_continental":
            continue
        path = box_of(key)
        if not path.exists():
            continue
        got = [r for r in json.loads(path.read_text(encoding="utf-8"))
               if str(r.get("day") or "") < str(as_of)]
        rows += got
        said_from.append(f"{key} {len(got)}경기")
    if not rows:
        print(f"🔴 모은 경기가 없다 — 먼저 `--collect --fast` 를 돌린다"
              f"({box_of(comp).name})")
        return 2
    print(f"- 섞은 대회 — {' · '.join(said_from)}")
    elo, why_elo = domestic_elo()
    print(f"# 🔴🔴 {comp} 리그 오프셋 · 대회 홈 이점")
    print()
    print(f"- 모은 경기 **{len(rows)}건**(as-of {as_of} **이전** · CC2) · "
          f"{why_elo}")
    use: list[dict] = []
    gone: dict[str, int] = {}
    for r in rows:
        lh, la = str(r.get("home_league") or ""), str(r.get("away_league") or "")
        if not lh or not la:
            gone["국내 리그 모름"] = gone.get("국내 리그 모름", 0) + 1
            continue
        if lh == la:
            gone["같은 리그 맞대결(오프셋에 못 쓴다)"] = gone.get(
                "같은 리그 맞대결(오프셋에 못 쓴다)", 0) + 1
            continue
        # ⚠️ 수집 판이 두 꼴이다 — `{"home": {"name": …}}`(옛) 와 `{"home": 글자}`
        #    (새 `fit_comp_record` 꼴). 🔴 둘 다 받는다.
        def _nm(one) -> str:
            return str(one.get("name") or "") if isinstance(one, dict) \
                else str(one or "")
        home, away = _nm(r.get("home")), _nm(r.get("away"))
        if home not in elo or away not in elo:
            gone["국내 Elo 없다"] = gone.get("국내 Elo 없다", 0) + 1
            continue
        use.append({"lh": lh, "la": la, "dr": elo[home] - elo[away],
                    "s": (1.0 if int(r["hg"]) > int(r["ag"])
                          else (0.5 if int(r["hg"]) == int(r["ag"]) else 0.0)),
                    "neutral": bool(_cp.neutral_of(
                        comp, stage=str(r.get("stage") or ""))[0])})
    print("- **버린 것** — "
          + (" · ".join(f"{k} {v}건" for k, v in sorted(gone.items()))
             if gone else "없다"))
    if len(use) < 10:
        print(f"🔴 **적합 못 한다** — 리그 간 맞대결이 {len(use)}건이다")
        return 0
    keys = sorted({x["lh"] for x in use} | {x["la"] for x in use})
    idx = {k: i for i, k in enumerate(keys)}
    cnt = {k: sum(1 for x in use if k in (x["lh"], x["la"])) for k in keys}
    scale = math.log(10.0) / 400.0

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **수축**(P1 · 수정 지시 2026-10-13 밤) — 표본이 얇은 리그는 0 쪽으로
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-13: 수축이 없으면 **4경기짜리 리그가 폭주**한다(−8,171점)
    #     — 그 한 줄이 평균 0 식별을 끌어가 나머지 전부가 +600 쪽으로 밀렸다.
    #  🔴 벌은 `K/(n+K)` 가중 L2 다(K = `MIN_GAMES`) — 표본이 많으면 벌이 작고,
    #     적으면 0 에 붙는다. **새 계수를 만들지 않는다**(문턱 20 을 그대로 쓴다).
    ridge = np.array([off.MIN_GAMES / (cnt[k] + off.MIN_GAMES) for k in keys])

    def loss(theta) -> float:
        offv = np.array(theta[:len(keys)])
        offv = offv - offv.mean()              # 🔴 식별 — 평균 0
        h = float(theta[len(keys)])
        tot = 0.0
        for x in use:
            d = (x["dr"] + offv[idx[x["lh"]]] - offv[idx[x["la"]]]
                 + (0.0 if x["neutral"] else h))
            p = 1.0 / (1.0 + math.exp(-d * scale))
            p = min(1 - 1e-9, max(1e-9, p))
            tot -= x["s"] * math.log(p) + (1 - x["s"]) * math.log(1 - p)
        # 🔴 수축 벌 — 400점(한 눈금)을 단위로 재서 손실과 같은 자리에 둔다
        pen = float(np.sum(ridge * (offv / 400.0) ** 2))
        return tot / len(use) + pen

    got = minimize(loss, [0.0] * len(keys) + [40.0], method="Powell")
    vals = np.array(got.x[:len(keys)])
    vals = vals - vals.mean()
    home_elo = float(got.x[len(keys)])
    print()
    print(f"- 수축 — 벌 `K/(n+K)` · K={off.MIN_GAMES}(표본이 얇으면 0 쪽으로)")
    print()
    print("| 리그 | 오프셋 | 리그 간 맞대결 | 수축 가중 | 판에 적나 |")
    print("|---|---|---|---|---|")
    box: dict[str, dict] = {}
    for k in keys:
        n = cnt[k]
        ok = n >= off.MIN_GAMES
        box[k] = ({"value": round(float(vals[idx[k]]), 2), "n": n}
                  if ok else {"n": n})
        print(f"| {k} | {vals[idx[k]]:+.1f} | {n} | "
              f"{off.MIN_GAMES / (n + off.MIN_GAMES):.2f} | "
              + ("✅" if ok else f"🔴 ⬜ (< {off.MIN_GAMES} — 미산출)") + " |")
    print()
    print(f"- **대회 홈 이점**(Elo 점수) **{home_elo:+.1f}** · 적합 로그 손실 "
          f"{float(got.fun):.4f} · 쓴 경기 {len(use)}건")
    import yaml
    conf = str(_cp.row_of(comp).get("confederation") or "").upper()
    said_path = off.BOX / conf / f"{as_of}.yaml"
    said_path.parent.mkdir(parents=True, exist_ok=True)
    said_path.write_text(yaml.safe_dump(
        {"대회": comp, "as_of": as_of, "n": len(use),
         "home_elo": round(home_elo, 2), "leagues": box,
         "왜": "브래들리–테리 · 오프셋 평균 0 · 중립 경기는 홈 이점 0(CC3)"},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"🔴 **판을 적었다** — `{said_path.relative_to(ROOT)}`")
    # 🔴 **대회 홈 이점 배율**(골 기준) — 그 대회 자체 실측(5-3-c)
    hg = [int(r["hg"]) for r in rows if r.get("hg") is not None
          and not _cp.neutral_of(comp, stage=str(r.get("stage") or ""))[0]]
    ag = [int(r["ag"]) for r in rows if r.get("ag") is not None
          and not _cp.neutral_of(comp, stage=str(r.get("stage") or ""))[0]]
    if len(hg) >= 20:
        mean = (sum(hg) + sum(ag)) / (2.0 * len(hg))
        mul = (sum(hg) / len(hg)) / mean if mean else 1.0
        said_home = off.HOME_BOX / comp.replace(":", "_") / f"{as_of}.yaml"
        said_home.parent.mkdir(parents=True, exist_ok=True)
        said_home.write_text(yaml.safe_dump(
            {"대회": comp, "home_mul": round(float(mul), 4),
             "goals_per_match": round(float(mean) * 2, 4), "n": len(hg),
             "왜": "그 대회 자체 실측(중립 경기 제외) — 국내 리그 값을 빌리지 "
                   "않는다(CC1)"},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"🔴 **대회 홈 이점 판** — `{said_home.relative_to(ROOT)}` · "
              f"×{mul:.3f} · 경기당 {mean * 2:.3f}골 · 표본 {len(hg)}")
    else:
        print(f"🔴 **대회 홈 이점 미산출** — 중립 아닌 경기가 {len(hg)}건이다"
              f"(< 20 · 손값 금지)")
    # 🔴 운영이 그 판을 어떻게 보는가(엄격히 `as_of` 이전이라 그날은 **없다**)
    from datetime import datetime, timezone
    at = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)
    print()
    said_plate, why_plate = off.plate_of(confederation=conf, as_of=at)
    print(f"- 운영이 보는 오프셋 판 — {why_plate}"
          + (f" · 리그 {len(dict(said_plate.get('leagues') or {}))}개"
             if said_plate else ""))
    for k in keys[:3]:
        _v, why_v = off.of(k, confederation=conf, as_of=at)
        _s, why_s = off.score_of(elo=1500.0, league=k, confederation=conf,
                                 as_of=at)
        print(f"  · {k} — {why_v} / 점수 {why_s}")
    _h, why_h = off.home_of(comp, as_of=at, stage="league phase")
    print(f"- 운영이 보는 대회 홈 이점 — {why_h}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True, help="대회 열쇠(예: league:UCL)")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--seasons", type=int, default=3)
    ap.add_argument("--fast", action="store_true",
                    help="일정 한 장으로 모은다(경기 페이지 안 받는다 · P1)")
    ap.add_argument("--as-of", default="2026-10-13")
    args = ap.parse_args(argv[1:])
    if args.collect:
        return asyncio.run(collect_fast(args.comp, seasons=args.seasons)
                           if args.fast
                           else collect(args.comp, seasons=args.seasons))
    if args.fit:
        return fit(args.comp, as_of=args.as_of)
    print("🔴 `--collect` 또는 `--fit` 중 하나를 준다")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
