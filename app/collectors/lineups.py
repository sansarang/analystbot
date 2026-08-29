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

    async def fetch_roster(self, team_id: int) -> dict:
        """팀 로스터 + 상태 — 부상자 명단(IL)을 여기서 얻는다.

        boxscore의 info 섹션은 실전에서 비어 있어 결장자를 못 준다(2026-08-25 확인).
        roster의 status.code가 D7/D10/D15/D60이면 부상자 리스트다.
        """
        if self.mock:
            return {"roster": []}
        return await self._get(f"/teams/{team_id}/roster", params={"rosterType": "fullSeason"})


IL_CODES = ("D7", "D10", "D15", "D60", "DL")   # statsapi 부상자 리스트 코드


def parse_roster_names(roster: dict) -> dict[int, str]:
    """로스터 전원 id→이름. 결장 대조가 Statcast 타석 id를 이름으로 바꿀 때 쓴다."""
    out: dict[int, str] = {}
    for entry in (roster or {}).get("roster") or []:
        person = entry.get("person") or {}
        pid, name = person.get("id"), (person.get("fullName") or "").strip()
        if pid is None or not name:
            continue
        try:
            out[int(pid)] = name
        except (TypeError, ValueError):
            continue
    return out


def parse_injured(roster: dict) -> list[dict]:
    """로스터에서 부상자만 추출 → [{name, position, status}]."""
    out = []
    for entry in (roster or {}).get("roster") or []:
        status = (entry.get("status") or {})
        code = str(status.get("code") or "")
        if not any(code.startswith(c) for c in IL_CODES):
            continue
        name = ((entry.get("person") or {}).get("fullName") or "").strip()
        if not name:
            continue
        out.append({
            "id": (entry.get("person") or {}).get("id"),   # MLBAM id — Statcast와 동일 체계
            "name": name,
            "position": ((entry.get("position") or {}).get("abbreviation") or "").strip(),
            "status": status.get("description") or code,
        })
    return out


def injury_sentences(injured: list[dict], team: str) -> list[str]:
    """부상자 목록 → performance.absences가 읽는 문장으로 변환.

    역할(마무리/선발/주전)을 문장에 넣어야 조정 계수가 제대로 잡힌다.
    """
    role = {"P": "투수", "RP": "불펜", "SP": "선발", "C": "포수",
            "1B": "주전 내야", "2B": "주전 내야", "3B": "주전 내야", "SS": "주전 내야",
            "LF": "주전 외야", "CF": "주전 외야", "RF": "주전 외야", "DH": "주전 타자"}
    return [
        f"{team}의 {p['name']}({role.get(p['position'], p['position'] or '선수')}) "
        f"{p['status']}로 결장"
        for p in injured
    ]


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
        order_names, starter = [], None
        id_names: dict[int, str] = {}
        for key, pdata in players.items():
            person = (pdata or {}).get("person") or {}
            nm = (person.get("fullName") or "").strip()
            pid = person.get("id")
            if pid is None:
                raw = str(key).replace("ID", "")
                pid = int(raw) if raw.isdigit() else None
            if pid is not None and nm:
                try:
                    id_names[int(pid)] = nm
                except (TypeError, ValueError):
                    pass
        for pid in order_ids:
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            person = (players.get(key) or {}).get("person") or {}
            if person.get("fullName"):
                order_names.append(person["fullName"])
        for pid in team.get("pitchers") or []:
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            person = (players.get(key) or {}).get("person") or {}
            if person.get("fullName"):
                starter = person["fullName"]
                break
        # boxscore info 섹션은 실전에서 비어 있다 — 결장자는 roster(IL)에서 따로 받는다
        scratches = []
        for note in team.get("info") or []:
            if str(note.get("label", note.get("title", ""))).upper().startswith("NOT"):
                scratches += [f.get("value", "") for f in note.get("fieldList") or []]
        out[side] = {"starter": starter, "batting_order": order_names,
                     # id로도 남긴다 — 결장 판정은 이름이 아니라 id로 대조한다
                     "batting_order_ids": [int(str(p).replace("ID", "")) for p in order_ids
                                           if str(p).replace("ID", "").isdigit()],
                     "names": id_names,
                     "scratches": scratches,
                     "team_id": ((team.get("team") or {}).get("id"))}
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
                             client: MLBLineupClient | None = None,
                             redis=None, date: str | None = None) -> dict:
    """경기 1건의 라인업을 갱신하고 상태를 반환.

    반환: {status, changed: bool, notes: [str], starters: {home, away}}
    redis·date가 있으면 KBO 크롤러와 같은 `crawl:mlb:{date}:latest`에 쓴다.
    """
    client = client or MLBLineupClient()
    try:
        box = await client.fetch_boxscore(game["ext_id"])
    except Exception as exc:
        logger.warning("[lineup] boxscore 실패 game=%s: %s", game.get("id"), exc)
        return {"status": game.get("lineup_status") or STATUS_NONE,
                "changed": False, "notes": [], "starters": {}, "injuries": {}}

    parsed = parse_boxscore(box)
    status = STATUS_CONFIRMED if parsed.get("confirmed") else STATUS_PREDICTED
    notes: list[str] = []
    starters: dict[str, str | None] = {}
    injuries: dict[str, list[str]] = {}
    conflict = False

    # 부상자 명단 — boxscore가 아니라 roster에서 (info 섹션은 비어 있다)
    for side, team_key in (("home", "home"), ("away", "away")):
        team_id = (parsed.get(side) or {}).get("team_id")
        if not team_id:
            continue
        try:
            roster = await client.fetch_roster(team_id)
        except Exception as exc:
            logger.warning("[lineup] roster 실패 team=%s: %s", team_id, exc)
            continue
        injured = parse_injured(roster)
        if injured:
            injuries[side] = injury_sentences(injured, game.get(team_key) or side)
            logger.info("[lineup] game=%s %s 부상자 %d명", game.get("id"), side, len(injured))

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
    if pool:
        from app.collectors.lineup_history import record as record_hist

        for side, team_key in (("home", "home"), ("away", "away")):
            block = parsed.get(side) or {}
            order = "-".join(block.get("batting_order") or [])
            if not order:
                continue
            try:
                await record_hist(
                    pool, game["id"], side, game.get(team_key), order,
                    starter=starters.get(side) or block.get("starter"),
                    source="crawler",
                    is_final=(status == STATUS_CONFIRMED),
                )
            except Exception as exc:
                logger.warning("[lineup] 이력 기록 실패 game=%s %s: %s",
                               game.get("id"), side, exc)
    if redis is not None and date:
        from app.collectors.crawler_feed import upsert_snapshot_game

        try:
            await upsert_snapshot_game(redis, "mlb", date, {
                "away": game.get("away"), "home": game.get("home"),
                "home_pitcher": starters.get("home") or game.get("home_pitcher"),
                "away_pitcher": starters.get("away") or game.get("away_pitcher"),
                "lineup_status": status,
                "status": game.get("status") or "scheduled",
                "research": {
                    "home_lineup": {"order": "-".join(
                        (parsed.get("home") or {}).get("batting_order") or [])},
                    "away_lineup": {"order": "-".join(
                        (parsed.get("away") or {}).get("batting_order") or [])},
                    "home_pitcher": {"name": starters.get("home")},
                    "away_pitcher": {"name": starters.get("away")},
                },
            })
        except Exception as exc:
            logger.warning("[lineup] 스냅샷 기록 실패 game=%s: %s", game.get("id"), exc)
    return {"status": status, "changed": changed, "notes": notes,
            "starters": starters, "injuries": injuries}


def pick_state(lineup_status: str | None) -> tuple[str, str]:
    """[2-1] 픽 상태 라벨 — 예비/최종. 불일치는 최종 자격이 없다."""
    if lineup_status == STATUS_CONFIRMED:
        return "final", "✅ 최종 — 라인업 확정 반영"
    if lineup_status == STATUS_CONFLICT:
        return "preliminary", "🕐 잠정 — 선발 정보 불일치, 확정 대기"
    return "preliminary", "🕐 잠정 — 라인업 확정 전"
