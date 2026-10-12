"""🔴🔴 **상태별 득점률 적합** — 수정 지시서 2026-10-12 [2-오프라인].

> 원천: 이미 받는 fotmob 리그 경기 **골 시간**(백필 두 시즌, 킥오프 전 자료만,
> 누설 금지). 팀마다 상태(앞섬/동점/뒤짐)별 **분당 득점률·실점률 ÷ 그 팀 평균**
> → 배율. **리그 평균 쪽으로 수축**(표본 분 수 가중).
> 리그 단위 배율(동점 후반 강도 포함). **표본 부족 팀 = 리그 배율 + 🔴.**

🔴 저장 자리는 `data/state_rates/<리그>.yaml` 이고 읽는 쪽은
   `app/core/staterates.py` 다(이 도구는 **쓰기만** 한다).
⚠️ **누설 금지** — 한 경기의 배율을 그 경기로 재면 안 된다. 그래서 이 도구는
   *"지난 시즌들"* 만 받고, 운영은 그 파일을 읽는다(경기 중 자료를 안 본다).

쓰기:
    PYTHONPATH=. uv run python tools/fit_state_rates.py 47 --name league:PL
    PYTHONPATH=. uv run python tools/fit_state_rates.py 87 --name league:PD --max 120
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fit_state_rates")

#: 🔴 상태별 **분 표본**이 이만큼은 돼야 그 팀 표를 쓴다(아니면 리그 배율 + 🔴)
MIN_MINUTES = 400
#: 🔴 수축 세기 — 표본이 이만큼일 때 팀과 리그가 **반반**이다(표본 분 수 가중)
SHRINK_HALF = 900


def _key_of(name: str) -> str:
    """🔴 팀 이름 → **우리 열쇠**. 못 풀면 빈 글자(그 경기는 안 센다)."""
    if not str(name or "").strip():
        return ""
    from app import teamref
    key, _why = teamref.key_of(str(name), sport="soccer")
    return str(key or "")


def _state(mine: int, theirs: int) -> str:
    return "lead" if mine > theirs else ("trail" if mine < theirs else "level")


def _walk(goals: list[dict]) -> list[tuple[int, str, str]]:
    """🔴 한 경기 → `[(분, 홈 상태, 원정 상태)]` 90줄. 골 시간으로 상태가 바뀐다."""
    at: dict[int, list[bool]] = {}
    for one in (goals or []):
        got = dict(one)
        minute = int(got.get("min") or got.get("minute") or 0)
        if not minute:
            continue
        # 🔴 자책골은 **상대 득점**이다(`games_of` 와 같은 규율)
        home = bool(got.get("home")) != bool(got.get("own_goal"))
        at.setdefault(minute, []).append(home)
    h = a = 0
    out: list[tuple[int, str, str]] = []
    for minute in range(1, 91):
        out.append((minute, _state(h, a), _state(a, h)))
        for home in at.get(minute, []):
            if home:
                h += 1
            else:
                a += 1
    return out


def _add(box: dict, team: str, state: str, *, minutes: int = 0,
         gf: int = 0, ga: int = 0) -> None:
    one = box.setdefault(team, {s: {"min": 0, "gf": 0, "ga": 0}
                                for s in ("lead", "level", "trail")})
    one[state]["min"] += minutes
    one[state]["gf"] += gf
    one[state]["ga"] += ga


def _rate(one: dict, key: str) -> float | None:
    n = int(one.get("min") or 0)
    return (float(one.get(key) or 0) / n) if n else None


def _shrink(team: float, league: float, minutes: int) -> float:
    """🔴 표본 분 수 가중으로 **리그 평균 쪽으로 수축**한다."""
    w = float(minutes) / (float(minutes) + SHRINK_HALF)
    return w * float(team) + (1.0 - w) * float(league)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id")
    ap.add_argument("--name", required=True,
                    help="저장 이름(예: league:PL) — 운영이 그 이름으로 읽는다")
    ap.add_argument("--max", type=int, default=200, help="받을 끝난 경기 수")
    ap.add_argument("--as-of", dest="as_of", default="",
                    help="🔴 이 시각 **이전** 경기만 적합한다(누설 금지 · L1). "
                         "비우면 **지금**이다(운영 갱신).")
    args = ap.parse_args()

    from app.collect import fotmob as fm
    from app.net import Net
    net = Net(cache=True)
    rows = await fm.league_matches(net, args.league_id)
    # 🔴🔴 **누설 금지**(사용자 지시 2026-10-12 ⓐ · 계약 L1) — as-of 이후 경기로
    #    적합하면 그 계수는 **미래를 본 값**이다. 문은 `fotmob.before_as_of` 하나다.
    from datetime import datetime, timezone
    said_cut = (datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
                if args.as_of else datetime.now(timezone.utc))
    if said_cut.tzinfo is None:
        said_cut = said_cut.replace(tzinfo=timezone.utc)
    done_all = [r for r in rows if r.get("finished")]
    done = fm.before_as_of(done_all, as_of=said_cut)[-int(args.max):]
    logger.info("[fit] 🔒 as-of %s — 끝난 경기 %d건 중 %d건만 쓴다(누설 금지)",
                said_cut.isoformat()[:16], len(done_all), len(done))
    logger.info("[fit] 리그 %s — 끝난 경기 %d건(받는다)", args.league_id, len(done))
    box: dict[str, dict] = {}
    names: dict[str, str] = {}
    miss: list[str] = []
    league = {s: {"min": 0, "gf": 0, "ga": 0}
              for s in ("lead", "level", "trail")}
    got_n = 0
    for one in done:
        page = await net.get(fm.match_url(str(one.get("id") or "")))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            continue
        goals = fm.goals_of(j)
        if not goals:
            continue
        got_n += 1
        # 🔴🔴 **열쇠로 적는다 — 이름으로 적지 않는다**(실사고 2026-10-12).
        #    ⚠️ 처음에 팀 **이름**으로 적었더니 운영이 열쇠(`team:000390`)로 찾아
        #       **전부 리그값 + 🔴** 으로 떨어졌다. 🔴 신원 계약도 이름 비교를
        #       금지한다 — 이름표(`teamref`)가 푸는 자리다.
        home = _key_of(str(one.get("home") or ""))
        away = _key_of(str(one.get("away") or ""))
        if not home or not away:
            miss.append(f"{one.get('home')} vs {one.get('away')}")
            continue
        scored: dict[int, list[bool]] = {}
        for g in goals:
            minute = int(dict(g).get("min") or dict(g).get("minute") or 0)
            if minute:
                scored.setdefault(minute, []).append(
                    bool(dict(g).get("home")) != bool(dict(g).get("own_goal")))
        names[home] = str(one.get("home") or "")
        names[away] = str(one.get("away") or "")
        for minute, st_h, st_a in _walk(goals):
            gh = sum(1 for x in scored.get(minute, []) if x)
            ga = sum(1 for x in scored.get(minute, []) if not x)
            _add(box, home, st_h, minutes=1, gf=gh, ga=ga)
            _add(box, away, st_a, minutes=1, gf=ga, ga=gh)
            for state, (f, a) in ((st_h, (gh, ga)), (st_a, (ga, gh))):
                league[state]["min"] += 1
                league[state]["gf"] += f
                league[state]["ga"] += a
    if not got_n:
        logger.info("[fit] 🔴 경기 0건 — 표를 만들지 않는다")
        return
    # ── 리그 배율: 상태별 분당 비율 ÷ 전체 평균
    tot_min = sum(int(league[s]["min"]) for s in league)
    tot_gf = sum(int(league[s]["gf"]) for s in league)
    tot_ga = sum(int(league[s]["ga"]) for s in league)
    base_f = (tot_gf / tot_min) if tot_min else 0.0
    base_a = (tot_ga / tot_min) if tot_min else 0.0
    lg_mul = {}
    for s in ("lead", "level", "trail"):
        f, a = _rate(league[s], "gf"), _rate(league[s], "ga")
        lg_mul[s] = {
            "for": round((f / base_f) if (f and base_f) else 1.0, 4),
            "against": round((a / base_a) if (a and base_a) else 1.0, 4)}
    # ── 팀 배율: 그 팀 평균으로 나누고 리그 쪽으로 수축
    teams: dict[str, dict] = {}
    thin: list[str] = []
    for team, one in box.items():
        t_min = sum(int(one[s]["min"]) for s in one)
        t_gf = sum(int(one[s]["gf"]) for s in one)
        t_ga = sum(int(one[s]["ga"]) for s in one)
        if t_min < MIN_MINUTES or not t_gf:
            thin.append(team)
            continue
        b_f, b_a = t_gf / t_min, (t_ga / t_min if t_ga else 0.0)
        said = {"minutes": t_min, "name": names.get(team, "")}
        for s in ("lead", "level", "trail"):
            f, a = _rate(one[s], "gf"), _rate(one[s], "ga")
            said[s] = {
                "for": round(_shrink((f / b_f) if (f and b_f) else 1.0,
                                     lg_mul[s]["for"], int(one[s]["min"])), 4),
                "against": round(_shrink((a / b_a) if (a and b_a) else 1.0,
                                         lg_mul[s]["against"],
                                         int(one[s]["min"])), 4)}
        teams[team] = said
    out = {
        "source": f"fotmob 리그 {args.league_id} · 끝난 경기 {got_n}건",
        "fitted_by": "tools/fit_state_rates.py",
        "min_minutes": MIN_MINUTES, "shrink_half": SHRINK_HALF,
        "league": lg_mul, "teams": teams,
        "thin_teams": sorted(thin),
        # 🔴 #3 — 이름을 못 푼 경기는 **이름으로** 남긴다(조용히 빠지지 않게)
        "unresolved": sorted(set(miss))[:20],
    }
    # 🔴🔴 **판으로 적는다**(L3) — `data/state_rates/<리그>/<as_of>.yaml`.
    #    ⚠️ 덮어쓰지 않는다 — 어제 카드를 다시 돌릴 때 **그날 이전 판**이 붙어야 한다.
    from tools.versions_write import write as _vwrite
    said_day = said_cut.date()
    _vwrite("state_rates", str(args.name), day=said_day, body=out,
              head=("# 🔴 `tools/fit_state_rates.py` 가 만든 **판**이다 — "
                    f"as-of {said_cut.isoformat()[:16]} 이전 경기만 썼다.\n"
                    "# ⚠️ 손으로 고치지 않는다 · 로더는 `versions.pick` 이다."))
    import yaml
    path = ROOT / "data" / "state_rates"
    path.mkdir(parents=True, exist_ok=True)
    key = str(args.name).replace("/", "_").replace(":", "_")
    (path / f"{key}.yaml").write_text(
        "# 🔴 이 파일은 `tools/fit_state_rates.py` 가 만든다 — 손으로 고치지 않는다.\n"
        "# ⚠️ 표본 부족 팀은 `thin_teams` 에 있고, 운영은 그 팀에 **리그 배율 + 🔴**\n"
        "#    를 쓴다(`app/core/staterates.for_team`).\n"
        + yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    logger.info("[fit] 적었다 — %s · 팀 %d개(표본 부족 %d개) · 리그 배율 %s",
                path / f"{key}.yaml", len(teams), len(thin), lg_mul)


if __name__ == "__main__":
    asyncio.run(main())
