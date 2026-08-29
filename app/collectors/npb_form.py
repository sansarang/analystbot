"""NPB 최근 3경기 폼 — Yahoo 일정 점수 + `/stats` 선발 이닝·실점.

DISCIPLINE 1-A-1: 시즌 ERA·xwOBA는 넣지 않는다. 상대 순위·승률 1줄만 허용.
`npb_last3_verified`가 False인 동안 추천 게이트는 NPB를 자동 탈락한다
(보드는 발송). True는 라이브 Yahoo HTML 측정 후에만 켠다.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from datetime import timedelta

from app.collectors.last3 import attach_opponent_context
from app.collectors.yahoo_npb import (
    YahooNPBClient,
    parse_finals,
    parse_pitching_stats,
    score_card_html,
)

logger = logging.getLogger(__name__)

RECENT_GAMES = 3
CACHE_TTL = 48 * 3600  # 폼 패킷. 스펙 TTL 48h


def _key(date: str) -> str:
    return f"npb_form:{date}"


def _pitch_for_side(pits: dict, side: str) -> list[dict]:
    return list(pits.get(side) or [])


def summarize_pitching(pitchers: list[dict]) -> dict:
    """시즌 防御率는 넣지 않는다. 이 경기 이닝·실점·불펜 인원만."""
    starter = next((p for p in pitchers if p.get("is_starter")), None)
    relievers = [p for p in pitchers if not p.get("is_starter")]
    out = {
        "starter_name": (starter or {}).get("name"),
        "starter_ip": (starter or {}).get("innings"),
        "starter_r": (starter or {}).get("r"),
        "starter_pitches": (starter or {}).get("pitches"),
        "bullpen_count": len(relievers),
    }
    return {k: v for k, v in out.items() if v is not None or k == "bullpen_count"}


def parse_recent_form(finals: list[dict], *, before: str | None = None,
                      standings: dict | None = None) -> dict[str, dict]:
    """종료 경기 목록 → 팀별 최근 3경기. `before`(YYYY-MM-DD) 당일은 창에서 뺀다.

    당일 결과를 넣으면 누출이다(KBO usage와 같은 계약).
    """
    done = [
        g for g in finals
        if g.get("home_score") is not None
        and g.get("away_score") is not None
        and (not before or (g.get("date") or "") < before)
    ]
    teams: set[str] = set()
    for g in done:
        teams.add(g["home"])
        teams.add(g["away"])
    out: dict[str, dict] = {}
    for team in teams:
        mine = [g for g in done if g["home"] == team or g["away"] == team]
        mine.sort(key=lambda g: (g.get("date") or "", g.get("game_id") or ""),
                  reverse=True)
        games = []
        for g in mine[:RECENT_GAMES]:
            is_home = g["home"] == team
            runs, opp = (g["home_score"], g["away_score"]) if is_home \
                else (g["away_score"], g["home_score"])
            try:
                runs_i, opp_i = int(runs), int(opp)
            except (TypeError, ValueError):
                continue
            if runs_i > opp_i:
                result = "W"
            elif runs_i < opp_i:
                result = "L"
            else:
                result = "D"
            row = {
                "date": g.get("date"),
                "game_id": g.get("game_id"),
                "opponent": g["away"] if is_home else g["home"],
                "home": is_home,
                "runs": runs_i,
                "opp_runs": opp_i,
                "result": result,
            }
            attach_opponent_context(row, standings)
            for k in ("starter_name", "starter_ip", "starter_r", "bullpen_count"):
                if k in g and g[k] is not None:
                    row[k] = g[k]
            # 경기 단위로 붙여 둔 사이드별 투수 요약
            box = g.get("box") or {}
            side = "home" if is_home else "away"
            if isinstance(box.get(side), dict):
                row.update({k: v for k, v in box[side].items() if v is not None
                            or k == "bullpen_count"})
            games.append(row)
        if not games:
            continue
        n = len(games)
        out[team] = {
            "runs_l3": sum(s["runs"] for s in games),
            "runs_allowed_l3": sum(s["opp_runs"] for s in games),
            "runs_per_game_l3": round(sum(s["runs"] for s in games) / n, 2),
            "results_l3": "".join(s["result"] for s in games),
            "score_games": n,
            "games": games,
        }
    return out


def apply_boxscores(form: dict[str, dict], by_gid: dict[str, dict]) -> None:
    """parse_pitching_stats 결과를 팀 패킷에 얹는다. 시즌 ERA 키는 버린다."""
    for team, pkt in form.items():
        for row in pkt.get("games") or []:
            gid = row.get("game_id")
            pits = by_gid.get(gid) if gid else None
            if not pits:
                continue
            side = "home" if row.get("home") else "away"
            row.update(summarize_pitching(_pitch_for_side(pits, side)))


async def fetch_recent_form(date: str, client: YahooNPBClient | None = None,
                            days: int = 14,
                            standings: dict | None = None) -> dict[str, dict]:
    """`date` **이전** 종료 경기에서 팀별 최근 3경기를 모은다."""
    client = client or YahooNPBClient()
    day = date_cls.fromisoformat(date)
    collected: list[dict] = []
    seen: set[str] = set()
    for back in range(1, days + 1):
        d = (day - timedelta(days=back)).isoformat()
        try:
            html = score_card_html(await client.schedule(d))
            finals = parse_finals(html)
        except Exception as exc:
            logger.warning("[npb_form] 일정 %s 실패: %s", d, exc)
            continue
        for g in finals:
            gid = g.get("game_id")
            if not gid or gid in seen:
                continue
            seen.add(gid)
            collected.append({**g, "date": d})
    form = parse_recent_form(collected, before=date, standings=standings)
    need: set[str] = set()
    for pkt in form.values():
        for row in pkt.get("games") or []:
            if row.get("game_id"):
                need.add(row["game_id"])
    by_gid: dict[str, dict] = {}
    for gid in need:
        try:
            pits = parse_pitching_stats(await client.stats(gid))
        except Exception as exc:
            logger.debug("[npb_form] /stats %s 실패: %s", gid, exc)
            continue
        if pits.get("home") or pits.get("away"):
            by_gid[gid] = pits
    apply_boxscores(form, by_gid)
    logger.info("[npb_form] %s 기준 %d팀 · 박스 %d경기",
                date, len(form), len(by_gid))
    return form


async def refresh(redis, date: str, client: YahooNPBClient | None = None,
                  standings: dict | None = None) -> dict:
    import json

    data = await fetch_recent_form(date, client, standings=standings)
    if not data:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="NPB 최근 3경기", ok=0, total=1, cause="missing",
            detail=f"{date} 이전 Yahoo 종료 경기에서 폼 산출 실패",
            impact="NPB는 검증 전까지 추천 게이트에서 탈락합니다"))
    await redis.set(_key(date), json.dumps(data, ensure_ascii=False), ex=CACHE_TTL)
    return {"teams": len(data)}


async def load(redis, date: str) -> dict[str, dict]:
    import json

    raw = await redis.get(_key(date))
    return json.loads(raw) if raw else {}


def merge_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """팀별 3경기 폼을 research에 얹는다. 시즌 지표 키는 복사하지 않는다."""
    filled = []
    banned = ("era", "era_season", "xwoba", "woba", "ops", "obp")
    for side in ("home", "away"):
        row = (table or {}).get(jg.get(side) or "")
        if not row:
            continue
        blk = research.setdefault(f"{side}_usage", {})
        for k, v in row.items():
            if k in banned:
                continue
            if blk.get(k) != v:
                blk[k] = v
                filled.append(f"{side}_usage.{k}")
    return filled
