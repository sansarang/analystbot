"""[2] 확정 라인업 수집 — 예상(predicted)과 확정(confirmed)을 반드시 구분한다.

야구: MLB StatsAPI boxscore가 1순위. 경기 시작 전 boxscore에 battingOrder가 채워지면
      그 시점이 '확정'이다. probablePitcher(예고)와 실제 등판 선발은 다를 수 있다.
축구: 킥오프 60분 전 공식 라인업 — Grok(구단 X 계정)·Perplexity 보조 수집.

원칙:
- **예상을 확정으로 취급 금지.** status는 'predicted' | 'confirmed'만 쓴다.
- StatsAPI와 research의 선발이 다르면 StatsAPI 우선, 양쪽을 모두 보존하고 conflict 표기.
  불일치 상태에서는 예비 픽만 허용하고 최종 픽 자격을 주지 않는다.
"""

import json
import logging

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

STATUS_NONE, STATUS_PREDICTED, STATUS_CONFIRMED, STATUS_CONFLICT = (
    "none", "predicted", "confirmed", "conflict")


class MLBLineupClient(BaseAPIClient):
    """statsapi boxscore — 확정 선발·타순·결장자."""

    name = "mlb_lineup"
    base_url = "https://statsapi.mlb.com/api/v1"

    def __init__(self, mock: bool | None = None):
        super().__init__(get_settings().mock_mlb if mock is None else mock)

    async def fetch_boxscore(self, game_pk: str | int) -> dict:
        if self.mock:
            return {"teams": {}}
        return await self._get(f"/game/{game_pk}/boxscore")


def parse_boxscore(data: dict) -> dict:
    """boxscore → {'home': {...}, 'away': {...}, 'confirmed': bool}.

    battingOrder가 9명 채워져야 확정으로 본다 (그 전에는 예상 단계).
    """
    out: dict = {}
    teams = (data or {}).get("teams") or {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        players = team.get("players") or {}
        order_ids = team.get("battingOrder") or []
        names, starter = [], None
        for pid in order_ids:
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            person = (players.get(key) or {}).get("person") or {}
            if person.get("fullName"):
                names.append(person["fullName"])
        for pid in team.get("pitchers") or []:
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            person = (players.get(key) or {}).get("person") or {}
            if person.get("fullName"):
                starter = person["fullName"]
                break
        scratches = []
        for note in team.get("info") or []:
            if str(note.get("title", "")).upper().startswith("NOT"):
                scratches += [f.get("value", "") for f in note.get("fieldList") or []]
        out[side] = {"starter": starter, "batting_order": names, "scratches": scratches}
    out["confirmed"] = all(len(out[s]["batting_order"]) >= 9 for s in ("home", "away"))
    return out


def resolve_starter(statsapi_name: str | None, research_name: str | None) -> tuple[str | None, bool]:
    """[2-4] 소스 불일치 해소 — StatsAPI 우선. 반환 (채택값, 불일치 여부)."""
    if statsapi_name and research_name and not _same_person(statsapi_name, research_name):
        return statsapi_name, True
    return statsapi_name or research_name, False


def _same_person(a: str, b: str) -> bool:
    """성만 같아도 같은 사람으로 보지 않는다 — 정규화 후 비교."""
    norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
    na, nb = norm(a), norm(b)
    return na == nb or (len(na) > 4 and len(nb) > 4 and (na in nb or nb in na))


async def save_lineup(pool: asyncpg.Pool, game_id: int, side: str, status: str,
                      source: str, parsed: dict) -> None:
    await pool.execute(
        """
        INSERT INTO lineups (game_id, side, status, source, starter, batting_order, scratches)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
        ON CONFLICT (game_id, side, source, status) DO UPDATE
          SET starter = EXCLUDED.starter, batting_order = EXCLUDED.batting_order,
              scratches = EXCLUDED.scratches, captured_at = now()
        """,
        game_id, side, status, source, parsed.get("starter"),
        json.dumps(parsed.get("batting_order") or [], ensure_ascii=False),
        json.dumps(parsed.get("scratches") or [], ensure_ascii=False),
    )


async def refresh_mlb_lineup(pool: asyncpg.Pool, game: dict,
                             client: MLBLineupClient | None = None) -> dict:
    """경기 1건의 라인업을 갱신하고 상태를 반환.

    반환: {status, changed: bool, notes: [str], starters: {home, away}}
    """
    client = client or MLBLineupClient()
    try:
        box = await client.fetch_boxscore(game["ext_id"])
    except Exception as exc:
        logger.warning("[lineup] boxscore 실패 game=%s: %s", game.get("id"), exc)
        return {"status": game.get("lineup_status") or STATUS_NONE,
                "changed": False, "notes": [], "starters": {}}

    parsed = parse_boxscore(box)
    status = STATUS_CONFIRMED if parsed.get("confirmed") else STATUS_PREDICTED
    notes: list[str] = []
    starters: dict[str, str | None] = {}
    conflict = False

    for side, col in (("home", "home_pitcher"), ("away", "away_pitcher")):
        block = parsed.get(side) or {}
        await save_lineup(pool, game["id"], side, status, "statsapi", block)
        chosen, clash = resolve_starter(block.get("starter"), game.get(col))
        starters[side] = chosen
        if clash:
            conflict = True
            notes.append(f"{side} 선발 정보 불일치 — statsapi {block['starter']} "
                         f"vs 예고/리서치 {game[col]} (statsapi 채택, 확정 대기)")
        elif chosen and chosen != game.get(col):
            notes.append(f"{side} 선발 변경: {game.get(col) or '미정'} → {chosen}")

    if conflict:
        status = STATUS_CONFLICT

    prev = game.get("lineup_status") or STATUS_NONE
    changed = status != prev or bool(notes)
    await pool.execute(
        "UPDATE games SET lineup_status = $2, "
        "lineup_confirmed_at = CASE WHEN $2 = 'confirmed' THEN now() ELSE lineup_confirmed_at END, "
        "home_pitcher = COALESCE($3, home_pitcher), away_pitcher = COALESCE($4, away_pitcher) "
        "WHERE id = $1",
        game["id"], status, starters.get("home"), starters.get("away"),
    )
    if changed:
        logger.info("[lineup] game=%s %s → %s %s", game["id"], prev, status, notes or "")
    return {"status": status, "changed": changed, "notes": notes, "starters": starters}


def pick_state(lineup_status: str | None) -> tuple[str, str]:
    """[2-1] 픽 상태 라벨 — 예비/최종. 불일치는 최종 자격이 없다."""
    if lineup_status == STATUS_CONFIRMED:
        return "final", "✅ 최종 — 라인업 확정 반영"
    if lineup_status == STATUS_CONFLICT:
        return "preliminary", "🕐 잠정 — 선발 정보 불일치, 확정 대기"
    return "preliminary", "🕐 잠정 — 라인업 확정 전"
