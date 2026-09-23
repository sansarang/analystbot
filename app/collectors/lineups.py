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


#: 🔴 [XI-1 2026-09-23] **축구 선발 XI 가 공식 발표분인가.**
#
#   실측 — flashscore 라인업 122행 전수:
#     수집시각 − 킥오프   최소 -48분 · 중앙 -15분 · 최대 -3분
#     킥오프 60분+ 전 0행 · 60~0분 전 122행 · 킥오프 후 0행
#     명단 인원 11명 → 122행 (다른 값 없음)
#   축구 공식 XI 는 킥오프 약 1시간 전에 발표된다. 우리 자료는 전건이 그 창
#   안이고 인원도 정확히 11명이다 — **예상이 아니라 공식 발표분**이다.
#
#   종전에는 적재기가 `"predicted"` 를 **손으로 박고** 있었고, 그래서
#   `xi_confirmed` 가 최근 3일 305건 전건 미상이었다(⑦은 confirmed 에만
#   조정을 건다).
#
# 🔴 **적재기와 ⑤가 이 함수 하나를 본다.** 두 벌이면 어긋나고, 어긋나면
#    "표에는 confirmed 인데 ⑤는 아니라고 한다"가 된다.
# ⚠️ **모르면 낮은 쪽이다** — 킥오프·수집시각을 모르면 `predicted` 다.
#    확정이라고 올려 부르면 확신이 부풀고, 그 방향이 더 위험하다.
#    판정 규율 "예상을 확정으로 취급 금지"(CLAUDE.md)는 그대로다.
def xi_status_of(*, source: str, n_players: int,
                 captured_at, kickoff) -> str:
    """축구 선발 명단 한 벌의 상태. `confirmed` | `predicted`."""
    from app.engine import rules as R

    try:
        window = float(R.get("lineups.official_window_min", 60) or 60)
    except Exception:
        window = 60.0
    if int(n_players or 0) != 11:
        return STATUS_PREDICTED
    if captured_at is None or kickoff is None:
        return STATUS_PREDICTED
    try:
        mins = (captured_at - kickoff).total_seconds() / 60.0
    except (TypeError, AttributeError):
        return STATUS_PREDICTED
    return STATUS_CONFIRMED if -window <= mins <= 0 else STATUS_PREDICTED


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


#: 🔴 [SP-3 2026-09-23] 판정 캐시의 **예고선발**을 `games` 로. 모양은 종목
#   공통이라(`games[].home_pitcher`) 한 함수가 kbo·npb·mlb 를 다 덮는다.
# ⚠️ **COALESCE** 다. 예고 전에는 이름이 없고, 그 빈 값이 어제 채운 값을
#    덮으면 안 된다(SP-1 과 같은 규약).
_SET_STARTERS = """
    UPDATE games
       SET home_pitcher = COALESCE($2, home_pitcher),
           away_pitcher = COALESCE($3, away_pitcher),
           updated_at   = now()
     WHERE id = $1
"""


async def upsert_probables_from_analysis(pool, redis, sport: str,
                                         date: str) -> dict:
    """[SP-3] `analysis:{sport}:{date}` 의 선발 이름을 `games` 에 옮긴다.

    🔴 **왜 필요한가.** 흐름 ⑤의 `_starter_recent3` 는 `games.home_pitcher` 를
       읽는다. 그 칸이 비면 선발 축이 통째로 미상이고, 핵심 변수 셋 중 둘이
       미상이면 ⑥이 "모름과반"으로 멈춘다.
       실측 2026-09-23: NPB 6경기가 전부 그 자리에서 멈췄는데, 같은 시각 캐시
       에는 이름이 있었다(`away_pitcher "髙橋 遥人"` · `home_pitcher "奥川 恭伸"`).
       `games.home_pitcher` 에 쓰는 코드가 저장소 전체에서 `naver_kbo` 하나
       (KBO 전용)뿐이었다 — KBO 와 똑같은 "만들어 놓고 안 이음"이다.

    🔴 **종목을 가리지 않는다**(CLAUDE.md "페이블식 흐름은 모든 스포츠에 적용").
    ⚠️ 어제 캐시로 내려가지 않는다 — 오늘 선발을 어제 것으로 채우면 안 된다.
    ⚠️ 한 경기가 실패해도 나머지는 간다. 조용한 0 을 만들지 않는다.
    """
    import json as _j

    out = {"games": 0, "failed": 0, "seen": 0}
    if pool is None or redis is None:
        return out
    try:
        raw = await redis.get(f"analysis:{sport}:{date}")
    except Exception as exc:
        logger.info("[lineups] 판정 캐시 조회 실패 %s %s: %s", sport, date, exc)
        return out
    if not raw:
        return out
    try:
        doc = _j.loads(raw)
    except ValueError:
        return out
    for g in (doc.get("games") or []):
        if not isinstance(g, dict):
            continue
        out["seen"] += 1
        gid = g.get("game_id")
        hp = str(g.get("home_pitcher") or "").strip() or None
        ap = str(g.get("away_pitcher") or "").strip() or None
        if gid is None or not (hp or ap):
            continue                       # 예고 전 — 빈 값으로 덮지 않는다
        try:
            await pool.execute(_SET_STARTERS, int(gid), hp, ap)
            out["games"] += 1
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[lineups] 선발 적재 실패 game=%s: %s", gid, exc)
    logger.info("[lineups] 예고선발 %s %s: %s", sport, date, out)
    return out


async def save_lineup(pool: asyncpg.Pool, game_id: int, side: str, status: str,
                      source: str, parsed: dict, *, caller: str = "?") -> None:
    """[M-3 계측] 타순 길이가 9가 아니면 **누가 넣었는지** 남긴다.

    🔴 `lineups` 테이블의 길이 이상이 08-26 이후 계속 늘고 있다
       (2026-09-02 84건 → 09-03 101건). `lineup_events` 는 0건이라 판정
       경로는 깨끗하지만, 어느 호출자가 쌓는지 모른다.
    ⚠️ 호출자는 **명시 인자**로 받는다 — `inspect` 로 스택을 뒤지면
       느리고, 데코레이터·태스크 경계에서 엉뚱한 이름이 나온다.
    """
    order = parsed.get("batting_order") or []
    if len(order) != 9:
        logger.info("[lineups-anomaly] caller=%s game=%s side=%s len=%d "
                    "status=%s source=%s", caller, game_id, side, len(order),
                    status, source)
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
        await save_lineup(pool, game["id"], side, status, "statsapi", block,
                          caller="refresh_mlb_lineup")
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
                "ext_id": game.get("ext_id"),
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
            "starters": starters, "injuries": injuries,
            "orders": {
                "home": list((parsed.get("home") or {}).get("batting_order") or []),
                "away": list((parsed.get("away") or {}).get("batting_order") or []),
            }}


def apply_lineup_poll_to_research(research: dict, jg: dict, lineup: dict) -> list[str]:
    """폴링이 가져온 타순·선발을 research에 직접 넣는다.

    KBO는 크롤러 스냅샷의 `lineup_home`이 같은 일을 한다. MLB 폴링 반환에는
    타순이 빠져 `confirmed`만 찍히고 `today_nine`은 비었다
    (실측 2026-08-29 아침 카드: ✅ 최종인데 확정 9명 없음).
    9명이 아니면 타순을 쓰지 않는다 — 부분 명단을 확정처럼 남기지 않는다.
    """
    filled: list[str] = []
    starters = lineup.get("starters") or {}
    orders = lineup.get("orders") or {}
    for side in ("home", "away"):
        name = (starters.get(side) or "").strip()
        if name:
            blk = research.setdefault(f"{side}_pitcher", {})
            prev = (blk.get("name") or "").strip()
            if prev != name:
                if prev:
                    for k in ("era_season", "whip", "ip_avg_recent", "era_vs_opponent"):
                        blk.pop(k, None)
                blk["name"] = name
                filled.append(f"{side}_pitcher.name")
            jg[f"{side}_pitcher"] = name
        names = orders.get(side) or []
        if isinstance(names, str):
            parts = [p for p in names.replace("|", "-").split("-") if p.strip()]
        else:
            parts = [str(n).strip() for n in names if str(n).strip()]
        if len(parts) < 9:
            continue
        order_s = "-".join(parts)
        blk = research.setdefault(f"{side}_lineup", {})
        if blk.get("order") != order_s:
            blk["order"] = order_s
            blk["source"] = "statsapi"
            filled.append(f"{side}_lineup.order")
    return filled


def pick_state(lineup_status: str | None) -> tuple[str, str]:
    """[2-1] 픽 상태 라벨 — 예비/최종. 불일치는 최종 자격이 없다."""
    if lineup_status == STATUS_CONFIRMED:
        return "final", "✅ 최종 — 라인업 확정 반영"
    if lineup_status == STATUS_CONFLICT:
        return "preliminary", "🕐 잠정 — 선발 정보 불일치, 확정 대기"
    return "preliminary", "🕐 잠정 — 라인업 확정 전"
