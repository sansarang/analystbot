"""[§8-23] Go 크롤러가 Redis에 남긴 결과를 읽는다.

왜 별도 서비스인가:
  - 크롤러가 죽어도 봇은 계속 응답한다(프로세스 분리).
  - Go는 동시 수집에 강하다 — 11경기를 goroutine으로 병렬 조회한다.
  - **LLM 0회**라 실패해도 쿼터·비용이 0이다.

⚠️ 크롤러는 **Redis에만 쓴다.** Postgres를 직접 건드리지 않으므로, 검증을 통과한
   값만 파이썬이 DB에 반영한다. 크롤러가 DB를 쓰면 미검증 값이 λ로 흘러간다.

⚠️ **크롤러가 없어도 파이프라인은 돈다.** 파이썬 쪽 naver_kbo·yahoo_npb가 같은
   소스를 직접 긁는다 — 크롤러는 그것을 **더 자주**(10분) 돌려 변화를 잡는 역할이다.
"""

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

HEARTBEAT_KEY = "crawl:heartbeat"
STALE_MINUTES = 40      # 10분 주기 × 4회 — 이보다 오래되면 죽은 것으로 본다


def _key(sport: str, date: str, suffix: str) -> str:
    return f"crawl:{sport}:{date}:{suffix}"


async def load_snapshot(redis, sport: str, date: str) -> dict:
    """최신 스냅샷 {"원정@홈": {field: value}}. 없으면 빈 dict."""
    raw = await redis.get(_key(sport, date, "latest"))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[crawler_feed] 손상된 스냅샷 %s %s", sport, date)
        return {}


async def load_changes(redis, sport: str, date: str, limit: int = 50) -> list[dict]:
    """오늘 누적된 변화 목록 (오래된 것부터).

    선발 교체·라인업 변경이 여기 쌓인다. **언제 바뀌었는지**가 정보다 —
    경기 직전 교체는 시장이 늦게 반영하는 몇 안 되는 신호다.
    """
    rows = await redis.lrange(_key(sport, date, "changes"), -limit, -1)
    out = []
    for r in rows or []:
        try:
            out.append(json.loads(r))
        except (TypeError, ValueError):
            continue
    return out


async def is_alive(redis) -> tuple[bool, str]:
    """크롤러가 살아 있는가. 반환 (살아있음, 사람이 읽을 설명).

    ⚠️ 조용한 정지가 가장 위험하다 — 데이터가 어제 값으로 굳어도 아무도 모른다.
    """
    raw = await redis.get(HEARTBEAT_KEY)
    if not raw:
        return False, "크롤러 하트비트 없음 — 미실행"
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        return False, f"하트비트 형식 오류: {raw[:40]}"
    age = (datetime.now(UTC) - at.astimezone(UTC)).total_seconds() / 60
    if age > STALE_MINUTES:
        return False, f"크롤러 {age:.0f}분째 멈춤 (마지막 {at:%H:%M})"
    return True, f"크롤러 정상 (마지막 {at:%H:%M})"


def notable_changes(changes: list[dict]) -> list[str]:
    """[§8-23] 사람이 즉시 알아야 할 변화만 한국어 한 줄로.

    ⚠️ 중요도를 점수화하지 않는다 — "무엇이 바뀌었다"만 사실로 전하고,
       경기에 어떤 영향인지는 판정이 결정한다.
    """
    label = {"home_pitcher": "홈 선발", "away_pitcher": "원정 선발",
             "lineup_home": "홈 라인업", "lineup_away": "원정 라인업",
             "starter_status": "선발 발표", "status": "경기 상태"}
    out = []
    for c in changes:
        f = c.get("field")
        if f not in label:
            continue
        at = (c.get("at") or "")[11:16]
        frm, to = c.get("from") or "없음", c.get("to") or "없음"
        out.append(f"{at} {c.get('game','?')} {label[f]}: {frm} → {to}")
    return out


def merge_into_research(research: dict, jg: dict, snap: dict) -> list[str]:
    """크롤러 스냅샷을 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ 선발 **이름만** 넘긴다. 성적(ERA·WHIP)은 파이썬 수집기가 공식 소스에서
       받은 것을 쓴다 — 크롤러는 '누가 나오나'를 가장 빨리 아는 역할이다.
    """
    game = snap.get(f"{jg.get('away')}@{jg.get('home')}")
    if not game:
        return []
    filled = []
    for side in ("home", "away"):
        name = (game.get(f"{side}_pitcher") or "").strip()
        if not name:
            continue
        blk = research.setdefault(f"{side}_pitcher", {})
        if blk.get("name") != name:
            blk["name"] = name
            # 이름이 바뀌면 이전 소스의 성적은 그 투수 것이 아니다
            for k in ("era_season", "whip", "ip_avg_recent", "era_vs_opponent"):
                blk.pop(k, None)
            filled.append(f"{side}_pitcher.name")
    # [§8-32] 라인업은 **홈·원정을 나눠서** 얹는다.
    #   실사고(2026-08-27): 크롤러가 `"lineup": 홈 | 원정` 합본을 보냈고 키는
    #   `원정@홈` 순이라 **어느 쪽이 어느 팀인지 알 수 없었다.** 게다가 이 값을
    #   읽는 코드가 앱 전체에 하나도 없어 타순 정보가 통째로 버려지고 있었다.
    #   NPB는 타순이 없는데도 같은 `lineup` 키에 "확정"/"예상"이라는 **상태값**을
    #   넣고 있어, 파이썬이 그것을 라인업으로 착각해 저장했다.
    for side in ("home", "away"):
        order = (game.get(f"lineup_{side}") or "").strip(" -")
        if not order:
            continue
        blk = research.setdefault(f"{side}_lineup", {})
        if blk.get("order") != order:
            blk["order"] = order
            blk["source"] = "크롤러"
            filled.append(f"{side}_lineup.order")
    # 선발 발표 상태(NPB 予告/확정) — 라인업과 **다른 것**이므로 다른 키에 넣는다.
    status = (game.get("starter_status") or "").strip()
    if status and status != "미상":
        if research.get("starter_status") != status:
            research["starter_status"] = status
            filled.append("starter_status")
    return filled
