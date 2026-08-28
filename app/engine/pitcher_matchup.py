"""[§9-투수 맞대결] 오늘 나올 투수 × 상대 확정 9명 — 사실만. λ 계수 없음.

왜 필요한가 (2026-08-28 실측 후 설계):
  시즌 팀 ERA vs 시즌 팀 OBP는 **오늘의 대결이 아니다.** 감독이 보는 것은
  이 투수가 최근 등판에서 상대 타선을 어떻게 상대했는가다.
  타석 단위(누가 누구에게)는 KBO 공식·네이버 record·NPB Yahoo `/stats` 어디에도
  없다. 있는 것은 **등판 단위**(이닝·상대 타자 수·자책)와, 그날 상대 선발 9명이다.

규칙:
  · 오늘 경기(`starts_at` 이상)는 한 줄도 넣지 않는다.
  · 표본 3등판 미만이면 비율(ERA)을 산출하지 않는다. 나열만.
  · `era_vs_opponent`(Yahoo 対戦)는 **시즌 상대팀**이지 last-5 vs 오늘 9명이 아니다.
  · 오늘 9명과 7명 이상 겹친 등판이 3회 미만이면 `era_vs_similar_nine`을 만들지 않는다.
  · 측정된 `adj_*`가 없다 — DISCIPLINE 5-1. 판정이 읽고 λ는 안 건드린다.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.collectors.lineup_history import _as_dt
from app.engine.lineup_diff import canon_name, parse_order
from app.engine.lineup_record import names_of

logger = logging.getLogger(__name__)

LOOKBACK_APPS = 5
MIN_RATE_APPS = 3
MIN_SIMILAR_NINE = 7          # lineup_record MIN_NAME_OVERLAP과 같음
SOURCE_BOXSCORE = "boxscore"
SEASON_VS_TEAM_LABEL = "시즌 상대팀 방어율"   # last-5·오늘 9명 오표기 금지

_FETCH_TEAM = """
    SELECT a.game_id, a.pitcher, a.team, a.opponent, a.is_starter,
           a.innings, a.batters, a.hits, a.hr, a.k, a.bb, a.r, a.er,
           g.starts_at
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.team = $2
       AND g.starts_at < $3
       AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""

_FETCH_LINEUPS = """
    SELECT e.game_id, e.team, e.batting_order
      FROM lineup_events e
     WHERE e.game_id = ANY($1::bigint[])
       AND e.source = $2
"""


def _aware(v) -> datetime | None:
    dt = _as_dt(v)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def era_from_apps(apps: list[dict]) -> float | None:
    """등판 합산 ERA. IP < 1.0 이면 미산출. 0이닝은 분모에 안 넣는다."""
    ip = er = 0.0
    for a in apps or []:
        inn = a.get("innings")
        e = a.get("er")
        if inn is None or inn <= 0 or e is None:
            continue
        ip += float(inn)
        er += float(e)
    if ip < 1.0:
        return None
    return round(9.0 * er / ip, 2)


def _empty_pitcher(name: str, role: str, note: str) -> dict:
    return {"name": name, "role": role, "n": 0, "appearances": [],
            "era_window": None, "era_vs_similar_nine": None,
            "n_similar": 0, "note": note}


def from_rows(pitcher: str, role: str, today_opp_nine: list[str],
              rows: list[dict], lineups_by_game: dict, before) -> dict:
    """DB 없이 테스트하는 집계. 오늘 경기·미래는 제외."""
    cutoff = _aware(before)
    if cutoff is None:
        return _empty_pitcher(pitcher, role, "경기 시각 없음 — 등판 조회 안 함")
    want = canon_name(pitcher)
    if not want:
        return _empty_pitcher(pitcher, role, "투수 이름 없음")
    opp_today = {canon_name(n) for n in today_opp_nine if canon_name(n)}

    eligible: list[tuple[datetime, dict]] = []
    for row in rows or []:
        st = _aware(row.get("starts_at"))
        if st is None or st >= cutoff:
            continue
        if canon_name(row.get("pitcher") or "") != want:
            continue
        eligible.append((st, row))
    eligible.sort(key=lambda x: x[0], reverse=True)

    seen: set = set()
    picked: list[dict] = []
    for st, row in eligible:
        gid = row.get("game_id")
        if gid in seen:
            continue
        seen.add(gid)
        order = parse_order(lineups_by_game.get(gid) or [])
        past_nine = set(names_of(order)) if order else set()
        n_shared = len(opp_today & past_nine) if opp_today and past_nine else 0
        picked.append({
            "game_id": gid,
            "opponent": row.get("opponent"),
            "is_starter": bool(row.get("is_starter")),
            "innings": row.get("innings"),
            "batters": row.get("batters"),
            "hits": row.get("hits"),
            "hr": row.get("hr"),
            "k": row.get("k"),
            "bb": row.get("bb"),
            "r": row.get("r"),
            "er": row.get("er"),
            "n_shared": n_shared,
            "starts_at": st.isoformat(),
        })
        if len(picked) >= LOOKBACK_APPS:
            break

    n = len(picked)
    similar = [a for a in picked if int(a.get("n_shared") or 0) >= MIN_SIMILAR_NINE]
    era_window = era_from_apps(picked) if n >= MIN_RATE_APPS else None
    era_sim = era_from_apps(similar) if len(similar) >= MIN_RATE_APPS else None
    notes = []
    if n == 0:
        notes.append("최근 등판 로그 없음")
    elif n < MIN_RATE_APPS:
        notes.append(f"표본 {n}등판 — ERA 미산출")
    if opp_today and n and era_sim is None:
        notes.append(
            f"오늘 9명과 {MIN_SIMILAR_NINE}명 이상 겹친 등판 "
            f"{len(similar)}회 — 맞대결 ERA 미산출")
    if not opp_today:
        notes.append("상대 확정 9명이 없어 겹침을 계산하지 않음")
    return {
        "name": pitcher, "role": role, "n": n,
        "appearances": picked,
        "era_window": era_window,
        "era_vs_similar_nine": era_sim,
        "n_similar": len(similar),
        "note": " · ".join(notes) if notes else "",
        "window_label": f"최근 {n}등판 (상대 타선은 그때그때 다름)" if n else "",
    }


def format_pitcher(p: dict | None) -> str:
    """판정·카드용 한 줄. 표본 부족이면 ERA를 쓰지 않는다."""
    p = p or {}
    name = p.get("name") or "?"
    n = int(p.get("n") or 0)
    if n <= 0:
        return p.get("note") or f"{name} 등판 로그 없음"
    bits = [f"{name} 최근 {n}등판"]
    if p.get("era_window") is None:
        bits.append("표본 부족, ERA 미산출")
    else:
        bits.append(f"창 ERA {p['era_window']:.2f} (상대 타선은 그때그때 다름)")
    n_sim = int(p.get("n_similar") or 0)
    if p.get("era_vs_similar_nine") is None:
        if n_sim:
            bits.append(f"오늘 9명과 겹친 등판 {n_sim}회, 맞대결 ERA 미산출")
    else:
        bits.append(f"오늘 9명과 유사한 타선 {n_sim}회 ERA {p['era_vs_similar_nine']:.2f}")
    return " — ".join(bits)


def format_season_vs_team(blk: dict | None) -> str | None:
    """Yahoo 対戦. last-5가 아님을 문장에 박는다."""
    if not isinstance(blk, dict) or blk.get("era") is None:
        return None
    return f"{SEASON_VS_TEAM_LABEL} {float(blk['era']):.2f} (시즌 누적, 오늘 9명 아님)"


def _staff_from_roster(roster: str) -> list[str]:
    out = []
    for part in (roster or "").split(","):
        nm = part.split("(")[0].strip()
        if nm:
            out.append(nm)
    return out


def today_pitchers(res: dict, side: str) -> list[tuple[str, str]]:
    """오늘 나올 후보. 선발 + (KBO 핵심 구원 / NPB 불펜 명단). 역할 추정 없음."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(name: str, role: str) -> None:
        key = canon_name(name)
        if not key or key in seen:
            return
        seen.add(key)
        out.append((name.strip(), role))

    starter = (res.get(f"{side}_pitcher") or {}).get("name")
    if starter:
        add(starter, "starter")
    usage = res.get(f"{side}_usage") or {}
    for n in usage.get("key_relievers") or []:
        add(str(n), "reliever")
    for n in res.get(f"{side}_bullpen_staff") or []:
        add(str(n), "reliever")
    for n in _staff_from_roster((res.get(f"{side}_bullpen") or {}).get("roster") or ""):
        add(n, "reliever")
    return out


def today_nine(res: dict, side: str) -> list[str]:
    order = parse_order((res.get(f"{side}_lineup") or {}).get("order"))
    return names_of(order)


def season_vs_team_of(res: dict, side: str) -> dict | None:
    p = res.get(f"{side}_pitcher") or {}
    era = p.get("era_vs_opponent")
    if era is None:
        return None
    try:
        return {"era": float(era), "label": SEASON_VS_TEAM_LABEL,
                "scope": "season_vs_team"}
    except (TypeError, ValueError):
        return None


def build_side(pitchers: list[tuple[str, str]], opp_nine: list[str],
               rows: list[dict], lineups_by_game: dict, before,
               season_vs_team: dict | None) -> dict:
    logs = [from_rows(name, role, opp_nine, rows, lineups_by_game, before)
            for name, role in pitchers]
    return {
        "pitchers": logs,
        "season_vs_team": season_vs_team,
        "season_vs_team_line": format_season_vs_team(season_vs_team),
    }


async def lookup_team(pool, sport: str, team: str, before, limit: int = 80
                      ) -> list[dict]:
    before = _aware(before)
    if not pool or not team or before is None:
        return []
    try:
        rows = await pool.fetch(_FETCH_TEAM, sport, team, before, int(limit))
    except Exception as exc:
        logger.warning("[투수맞대결] 등판 조회 실패 %s/%s: %s", sport, team, exc)
        return []
    return [dict(r) for r in rows]


async def _lineups_for(pool, game_ids: list[int]) -> dict[int, dict[str, object]]:
    """game_id → {team: batting_order}."""
    if not pool or not game_ids:
        return {}
    try:
        rows = await pool.fetch(_FETCH_LINEUPS, game_ids, SOURCE_BOXSCORE)
    except Exception as exc:
        logger.warning("[투수맞대결] 타순 조회 실패: %s", exc)
        return {}
    out: dict[int, dict[str, object]] = {}
    for r in rows:
        out.setdefault(int(r["game_id"]), {})[r["team"]] = r["batting_order"]
    return out


async def attach(pool, jg: dict, sport: str) -> None:
    """research.pitcher_matchup. 실패해도 분석은 산다. λ는 건드리지 않는다."""
    if sport not in ("kbo", "npb"):
        return
    res = jg.setdefault("research", {})
    before = jg.get("starts_at")
    blob: dict = {}
    for side, opp_side in (("home", "away"), ("away", "home")):
        staff = today_pitchers(res, side)
        opp_nine = today_nine(res, opp_side)
        rows = await lookup_team(pool, sport, jg.get(side), before)
        gids = []
        want = {canon_name(n) for n, _ in staff}
        for r in rows:
            if canon_name(r.get("pitcher") or "") in want:
                gids.append(int(r["game_id"]))
        by_game_team = await _lineups_for(pool, list(dict.fromkeys(gids)))
        lineups_for_pitcher: dict = {}
        for r in rows:
            gid = int(r["game_id"])
            opp = r.get("opponent")
            order = (by_game_team.get(gid) or {}).get(opp)
            if order is not None:
                lineups_for_pitcher[gid] = order
        blob[side] = build_side(
            staff, opp_nine, rows, lineups_for_pitcher, before,
            season_vs_team_of(res, side))
    res["pitcher_matchup"] = blob
    jg["pitcher_matchup"] = blob
