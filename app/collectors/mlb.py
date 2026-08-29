"""statsapi.mlb.com 수집기 — 일정+선발투수, 투수 시즌 스탯, 순위, 최종 스코어.

CLI: python -m app.collectors.mlb --date 2026-08-22
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings
from app.db import close_pool, get_pool

logger = logging.getLogger(__name__)

PITCHER_CHUNK = 10

# 슬레이트 파이프라인이 모은 순위·폼·ERA·날씨·결장.
# 라인업 폴링은 HTTP를 다시 치지 않고 이 캐시만 읽는다 (KBO kbo_stats와 같음).
CTX_TTL = 26 * 3600


def _ctx_key(date: str) -> str:
    return f"mlb:ctx:{date}"


def _gid_keys(raw: dict | None) -> dict[int, dict]:
    """JSON 왕복으로 문자열이 된 game_id를 int로 되돌린다."""
    out: dict[int, dict] = {}
    for k, v in (raw or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


async def save_ctx(redis, date: str, ctx: dict) -> None:
    """build_analysis가 모은 재료를 재판정이 읽도록 남긴다."""
    if redis is None or not date:
        return
    payload = {
        "standings": ctx.get("standings") or {},
        "form": ctx.get("form") or {},
        "era": ctx.get("era") or {},
        "weather": {str(k): v for k, v in (ctx.get("weather") or {}).items()},
        "absences": {str(k): v for k, v in (ctx.get("absences") or {}).items()},
    }
    await redis.set(_ctx_key(date), json.dumps(payload, ensure_ascii=False, default=str),
                    ex=CTX_TTL)


async def load_ctx(redis, date: str) -> dict:
    """없으면 빈 dict — 없는 칸은 비운 채로 병합한다."""
    if redis is None or not date:
        return {}
    raw = await redis.get(_ctx_key(date))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[mlb] 손상된 ctx 캐시 %s", date)
        return {}
    return {
        "standings": data.get("standings") or {},
        "form": data.get("form") or {},
        "era": data.get("era") or {},
        "weather": _gid_keys(data.get("weather") or {}),
        "absences": _gid_keys(data.get("absences") or {}),
    }


def chunked(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _gb(v):
    """gamesBack: 선두는 '-' 또는 0. 없으면 None."""
    if v in (None, "", "-"):
        return 0.0 if v == "-" else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_standings(payload: dict,
                    id_to_name: dict[int, str] | None = None) -> dict[str, dict]:
    """statsapi `/standings` → {팀 정식명: rank·w·l·win_pct·games_behind}.

    `/standings`의 `team.name`은 짧은 별칭(Guardians)인 경우가 있고,
    일정·분석 카드는 정식명(Cleveland Guardians)을 쓴다. `id_to_name`은
    `/teams?sportId=1`의 id→name. 둘 다 키로 넣어 어느 쪽으로 찾아도 맞는다.
    divisionRank가 없으면 그 그룹 나열 순서를 쓴다 (API가 순위대로 준다).
    """
    id_to_name = id_to_name or {}
    out: dict[str, dict] = {}
    for rec in (payload or {}).get("records") or []:
        rows = rec.get("teamRecords") or []
        for i, tr in enumerate(rows):
            team = tr.get("team") or {}
            short = (team.get("name") or "").strip()
            tid = team.get("id")
            official = ""
            if tid is not None:
                try:
                    official = (id_to_name.get(int(tid)) or "").strip()
                except (TypeError, ValueError):
                    official = ""
            name = official or short
            if not name:
                continue
            raw_rank = tr.get("divisionRank") or tr.get("leagueRank")
            try:
                rank = int(raw_rank) if raw_rank not in (None, "") else i + 1
            except (TypeError, ValueError):
                rank = i + 1
            pct = tr.get("winningPercentage")
            try:
                win_pct = float(pct) if pct is not None else None
            except (TypeError, ValueError):
                win_pct = None
            row = {"rank": rank, "w": tr.get("wins"), "l": tr.get("losses"),
                   "d": 0}
            gb = _gb(tr.get("gamesBack"))
            if gb is not None:
                row["games_behind"] = gb
            if win_pct is not None:
                row["win_pct"] = win_pct
            out[name] = row
            if short and short != name:
                out[short] = row
    return out


def parse_recent_form(schedule: dict, before: str | None = None) -> dict[str, dict]:
    """종료 경기 스코어 → KBO usage와 같은 `results_l3`·`score_games` 키.

    최근 **3경기**(날짜가 아니라 경기 수). `before`(YYYY-MM-DD, 슬레이트)는
    그 날 경기를 창에서 빼 오늘 경기를 최근 3에 넣지 않는다.
    이닝별 역전은 일정 API에 없어 역전승·역전패는 비운다 — 없는 것을 만들지 않는다.
    """
    games = _parse_games(schedule)
    finals = [
        g for g in games
        if g.get("status") == "final"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and (not before or (g.get("official_date") or "") < before)
    ]
    teams: set[str] = set()
    for g in finals:
        teams.add(g["home"])
        teams.add(g["away"])
    out: dict[str, dict] = {}
    for team in teams:
        mine = [g for g in finals if g["home"] == team or g["away"] == team]
        mine.sort(key=lambda g: g["starts_at"], reverse=True)
        scores = []
        for g in mine[:3]:
            is_home = g["home"] == team
            runs = g["home_score"] if is_home else g["away_score"]
            opp = g["away_score"] if is_home else g["home_score"]
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
            scores.append({
                "runs": runs_i, "opp_runs": opp_i, "result": result,
                "one_run": abs(runs_i - opp_i) == 1,
                "shutout_loss": runs_i == 0 and opp_i > 0,
            })
        if not scores:
            continue
        n = len(scores)
        out[team] = {
            "runs_l3": sum(s["runs"] for s in scores),
            "runs_allowed_l3": sum(s["opp_runs"] for s in scores),
            "runs_per_game_l3": round(sum(s["runs"] for s in scores) / n, 2),
            "results_l3": "".join(s["result"] for s in scores),
            "shutout_losses_l3": sum(1 for s in scores if s["shutout_loss"]),
            "one_run_games_l3": sum(1 for s in scores if s["one_run"]),
            "score_games": n,
        }
    return out


class MLBClient(BaseAPIClient):
    name = "mlb"
    base_url = "https://statsapi.mlb.com/api/v1"

    def __init__(self, mock: bool | None = None):
        super().__init__(get_settings().mock_mlb if mock is None else mock)

    async def fetch_schedule(self, date: str) -> dict:
        """날짜별 일정 + 선발투수 (hydrate=probablePitcher)."""
        if self.mock:
            return self.load_mock("mlb_schedule.json")
        return await self._get(
            "/schedule",
            params={"sportId": 1, "date": date, "hydrate": "probablePitcher"},
        )

    async def fetch_pitcher_stats(self, person_ids: list[int]) -> list[dict]:
        """선발투수 시즌 스탯. personIds는 10명 단위로 분할 호출."""
        if self.mock:
            people = self.load_mock("mlb_pitchers.json")["people"]
            wanted = set(person_ids)
            return [p for p in people if p["id"] in wanted]
        people: list[dict] = []
        for chunk in chunked(person_ids, PITCHER_CHUNK):
            data = await self._get(
                "/people",
                params={
                    "personIds": ",".join(map(str, chunk)),
                    "hydrate": "stats(group=[pitching],type=[season])",
                },
            )
            people.extend(data.get("people", []))
        return people

    async def fetch_standings(self, season: int | None = None) -> dict:
        if self.mock:
            return self.load_mock("mlb_standings.json")
        params: dict[str, Any] = {"leagueId": "103,104"}
        if season:
            params["season"] = season
        return await self._get("/standings", params=params)

    async def fetch_teams(self) -> dict:
        """id → 정식명. 순위표 짧은 이름과 일정 정식명을 잇는다."""
        if self.mock:
            return {"teams": []}
        return await self._get("/teams", params={"sportId": 1})

    async def fetch_schedule_range(self, start: str, end: str) -> dict:
        """startDate~endDate 한 번에. 팀별 최근 3경기 폼용."""
        if self.mock:
            return self.load_mock("mlb_schedule.json")
        return await self._get(
            "/schedule",
            params={"sportId": 1, "startDate": start, "endDate": end},
        )

    async def fetch_final_scores(self, date: str) -> dict:
        """최종 스코어 포함 일정 (schedule 응답에 teams.*.score 포함)."""
        if self.mock:
            return self.load_mock("mlb_finals.json")
        return await self._get("/schedule", params={"sportId": 1, "date": date})


def _parse_games(schedule: dict) -> list[dict]:
    out = []
    for day in schedule.get("dates", []):
        for g in day.get("games", []):
            home, away = g["teams"]["home"], g["teams"]["away"]
            state = g["status"]["abstractGameState"]
            out.append({
                "ext_id": str(g["gamePk"]),
                "starts_at": datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")),
                "home": home["team"]["name"],
                "away": away["team"]["name"],
                "home_pitcher": (home.get("probablePitcher") or {}).get("fullName"),
                "away_pitcher": (away.get("probablePitcher") or {}).get("fullName"),
                "status": {"Preview": "scheduled", "Live": "live", "Final": "final"}.get(state, "scheduled"),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "official_date": g.get("officialDate") or day.get("date") or "",
            })
    return out


async def upsert_games(
    pool: asyncpg.Pool, date: str, client: MLBClient | None = None,
    schedule: dict | None = None,
) -> int:
    """일정(+최종 스코어)을 games에 upsert. 적재 행 수 반환."""
    client = client or MLBClient()
    games = _parse_games(schedule or await client.fetch_schedule(date))
    for g in games:
        await pool.execute(
            """
            INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                               home_pitcher, away_pitcher, status, home_score, away_score)
            VALUES ('mlb', 'MLB', $1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (sport, ext_id) DO UPDATE SET
                starts_at = EXCLUDED.starts_at,
                home_pitcher = coalesce(EXCLUDED.home_pitcher, games.home_pitcher),
                away_pitcher = coalesce(EXCLUDED.away_pitcher, games.away_pitcher),
                status = EXCLUDED.status,
                home_score = coalesce(EXCLUDED.home_score, games.home_score),
                away_score = coalesce(EXCLUDED.away_score, games.away_score),
                updated_at = now()
            """,
            g["ext_id"], g["starts_at"], g["home"], g["away"],
            g["home_pitcher"], g["away_pitcher"], g["status"],
            g["home_score"], g["away_score"],
        )
    logger.info("[mlb] upserted %d games for %s", len(games), date)
    return len(games)


async def upsert_final_scores(pool: asyncpg.Pool, date: str, client: MLBClient | None = None) -> int:
    """최종 스코어를 games에 반영. final 처리된 경기 수 반환."""
    client = client or MLBClient()
    finals = [g for g in _parse_games(await client.fetch_final_scores(date))
              if g["status"] == "final"]
    for g in finals:
        await pool.execute(
            """
            UPDATE games SET status = 'final', home_score = $2, away_score = $3,
                             updated_at = now()
            WHERE sport = 'mlb' AND ext_id = $1
            """,
            g["ext_id"], g["home_score"], g["away_score"],
        )
    return len(finals)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="MLB schedule collector")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    pool = await get_pool()
    try:
        n = await upsert_games(pool, args.date)
        print(f"upserted {n} games into games table for {args.date}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
