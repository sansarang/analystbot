"""🔴🔴 **경우의 수** — 사용자 지시 2026-10-06(7차) §2. **코드만**(LLM 없음).

> 이 경기 결과 3가지 × 같은 라운드 다른 경기 결과 3가지마다, 두 팀의 **순위·구역**을
> 계산한다. 두 팀 각각에 상태를 붙인다:
> `must_win` / `draw_enough` / `margin_needed` / `nothing` / `unknown`.
> 남은 경기가 있으면 *"이번 경기만 보면"* 과 *"최종 확정"* 둘을 **구분해** 적는다.

🔴 **순위를 지어내지 않는다** — 순위표를 못 받으면 전부 `unknown` 이다(금지 조항).
🔴 동률은 `config/competition_rules.yaml` 의 순서로 가른다. 확인 안 된 대회는 **가정**
   이고 그 사실을 함께 돌려준다(카드가 적는다).
⚠️ 맞대결 기준(`h2h_*`)은 **치른 경기 결과를 알 때만** 쓴다 — 조 일정에 점수가 있으면
   쓰고, 없으면 그 기준을 건너뛰며 그 사실을 사유에 남긴다.
"""
from __future__ import annotations

import logging
from itertools import product

logger = logging.getLogger(__name__)

#: 🔴 결과 세 가지 — `(홈 득점, 원정 득점)` 꼴이 아니라 **승/무/패**다
RESULTS = ("home", "draw", "away")
#: 🔴 상태 이름 — 카드·이동 규칙이 **이 글자**를 본다(자유 문자열 금지)
STATES = ("must_win", "draw_enough", "margin_needed", "nothing", "unknown")


def _row_of(rows: list[dict], name: str) -> dict:
    low = str(name or "").strip().lower()
    for r in rows:
        if str(r.get("name") or "").strip().lower() == low:
            return dict(r)
    return {}


def _apply(rows: list[dict], home: str, away: str, said: str,
           margin: int = 1) -> list[dict]:
    """🔴 한 경기 결과를 표에 **더한다**. ⚠️ 원본을 고치지 않는다(새 표를 만든다).

    ⚠️ 득실은 `margin`(기본 1골 차)으로 움직인다 — 몇 골 차인지는 모르므로 **최소**
       로 둔다. 🔴 `margin_needed` 판정은 그 최소를 키워 가며 센다.
    """
    out = [dict(r) for r in rows]
    for r in out:
        nm = str(r.get("name") or "").strip().lower()
        if nm not in (home.strip().lower(), away.strip().lower()):
            continue
        is_home = nm == home.strip().lower()
        r["played"] = int(r.get("played") or 0) + 1
        gd = int(r.get("goal_diff") or 0)
        gf = int(r.get("goals_for") or 0)
        if said == "draw":
            r["points"] = int(r.get("points") or 0) + 1
            r["draws"] = int(r.get("draws") or 0) + 1
            gf += 1                                  # 1-1 로 본다(최소 가정)
            r["goals_against"] = int(r.get("goals_against") or 0) + 1
        else:
            won = (said == "home") == is_home
            if won:
                r["points"] = int(r.get("points") or 0) + 3
                r["wins"] = int(r.get("wins") or 0) + 1
                gd += margin
                gf += margin
            else:
                r["losses"] = int(r.get("losses") or 0) + 1
                gd -= margin
                r["goals_against"] = int(r.get("goals_against") or 0) + margin
        r["goal_diff"] = gd
        r["goals_for"] = gf
    return out


def rank_of(rows: list[dict], order: list[str]) -> list[dict]:
    """🔴 표를 **그 대회 순서**로 정렬하고 순위를 다시 매긴다.

    ⚠️ `h2h_*` 기준은 여기서 **건너뛴다**(맞대결 표를 따로 받아야 한다) — 그 사실은
       `skipped` 로 호출부가 안다. 🔴 건너뛴 기준을 *"적용했다"* 고 적지 않는다.
    """
    keys = {"points": lambda r: int(r.get("points") or 0),
            "goal_diff": lambda r: int(r.get("goal_diff") or 0),
            "goals_for": lambda r: int(r.get("goals_for") or 0),
            "wins": lambda r: int(r.get("wins") or 0)}
    use = [k for k in order if k in keys] or ["points", "goal_diff", "goals_for"]
    got = sorted(rows, key=lambda r: tuple(-keys[k](r) for k in use))
    out = []
    for i, r in enumerate(got, start=1):
        said = dict(r)
        said["rank"] = i
        out.append(said)
    return out


def zone_of(rank: int, zones: dict) -> str:
    """🔴 그 순위의 **구역 글자** — fotmob legend 의 `{구역: 마지막 순위}` 로 센다."""
    best = ""
    for title, last in sorted(zones.items(), key=lambda kv: int(kv[1])):
        if rank <= int(last):
            best = str(title)
            break
    return best


def grid(standings: dict, *, home: str, away: str, order: list[str],
         other: tuple[str, str] | None = None) -> list[dict]:
    """🔴🔴 §2 — **결과 3 × 다른 경기 결과 3** 의 순위·구역 표.

    돌려주는 줄: `{"ours": 결과, "other": 결과|None, "ranks": {팀: 순위},
                  "zones": {팀: 구역}}`
    """
    rows = list(standings.get("rows") or [])
    zones = dict(standings.get("zones") or {})
    if not rows:
        return []
    out: list[dict] = []
    others = RESULTS if other else (None,)
    for ours, them in product(RESULTS, others):
        said = _apply(rows, home, away, ours)
        if other and them:
            said = _apply(said, other[0], other[1], them)
        ranked = rank_of(said, order)
        out.append({
            "ours": ours, "other": them,
            "ranks": {str(r.get("name")): int(r.get("rank") or 0)
                      for r in ranked},
            "zones": {str(r.get("name")): zone_of(int(r.get("rank") or 0), zones)
                      for r in ranked}})
    return out


def state_of(cells: list[dict], team: str, *, is_home: bool,
             zones: dict) -> tuple[str, str]:
    """🔴🔴 §2 — 그 팀의 **상태 한 줄**. `(상태, 사유)`.

    | 상태 | 뜻(지시서 원문) |
    |---|---|
    | `must_win` | 이기지 않으면 구역 악화가 **확정 또는 매우 가까움** |
    | `draw_enough` | 비기면 **현 구역 유지** |
    | `margin_needed` | **n골 차** 필요(`margin_for` 가 센다) |
    | `nothing` | 어떤 결과든 **구역 불변** |
    | `unknown` | 순위표 없음 |

    🔴 **구역과 순위를 함께** 본다 — 구역 표시가 **일부 순위에만** 있는 조가 있다
       (실측 2026-10-06 네이션스리그 C 3조: 1위 `Promotion` · 2위 `Promotion
       qualification` · 3·4위는 **표시가 없다**. 2026/27 은 League D 가 없어져
       **강등이 없다** — `config/competition_rules.yaml` 의 공식 PDF 확인).
       ⚠️ 구역만 보면 3위와 4위가 *"둘 다 없음"* 이라 **같아 보인다** — 그러면
          `must_win` 을 놓친다. 🔴 그래서 `(구역, 순위)` 쌍으로 센다.
    """
    if not cells:
        return "unknown", "순위표를 못 받았다"
    win = "home" if is_home else "away"
    lose = "away" if is_home else "home"

    def _pick(res: str) -> set[tuple[str, int]]:
        return {(str(c["zones"].get(team, "")), int(c["ranks"].get(team, 0)))
                for c in cells if c["ours"] == res}

    def _say(box: set[tuple[str, int]]) -> str:
        return " / ".join(f"{rank}위{'(' + z + ')' if z else ''}"
                          for z, rank in sorted(box, key=lambda x: x[1]))

    w, d, lo = _pick(win), _pick("draw"), _pick(lose)
    if w == d == lo:
        return "nothing", f"어떤 결과든 {_say(w)} — 바뀌는 것이 없다"
    best_w = min(r for _, r in w) if w else 99
    best_d = min(r for _, r in d) if d else 99
    if w == d:
        return "draw_enough", f"비겨도 {_say(d)} — 이긴 것과 같다"
    if best_d >= best_w and d == lo:
        return "must_win", (f"이기면 {_say(w)} · 비기면 {_say(d)} · 지면 {_say(lo)}"
                            f" — 비기는 것과 지는 것이 **같다**")
    if best_d >= best_w:
        return "must_win", (f"이기면 {_say(w)} · 비기면 {_say(d)} — 이겨야 올라간다")
    return "draw_enough", f"비기면 {_say(d)} — 지는 것({_say(lo)})보다 낫다"


def margin_for(standings: dict, *, team: str, rival: str, order: list[str],
               home: str, away: str, zones: dict, cap: int = 5
               ) -> tuple[int | None, str]:
    """🔴 §2 `margin_needed` — **몇 골 차**가 필요한가. 못 세면 `(None, 사유)`.

    🔴 1골 차부터 `cap` 까지 키워 가며, 그 팀의 **구역(없으면 순위)** 이 좋아지는
       첫 수를 찾는다. ⚠️ 1골 차로 이미 좋아지면 `margin_needed` 가 아니다.
    """
    rows = list(standings.get("rows") or [])
    if not rows:
        return None, "순위표를 못 받았다"
    is_home = str(team).strip().lower() == str(home).strip().lower()
    base = rank_of(_apply(rows, home, away, "draw"), order)
    was = _row_of(base, team).get("rank")
    for m in range(1, cap + 1):
        got = rank_of(_apply(rows, home, away, "home" if is_home else "away",
                             margin=m), order)
        now = _row_of(got, team).get("rank")
        if now is not None and was is not None and int(now) < int(was):
            if m == 1:
                return None, "1골 차로 충분하다 — 골 차 조건이 아니다"
            return m, (f"{m}골 차로 이겨야 순위가 {was}→{now} 로 올라간다"
                       f"(1골 차로는 {was} 그대로)")
    return None, f"{cap}골 차까지 봐도 순위가 안 바뀐다 — 골 차 조건이 아니다"
