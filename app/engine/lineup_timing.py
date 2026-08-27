"""[라인업 발표 시각] "아직 발표 전"과 "수집 실패"를 가른다.

🔴 종전에는 킥오프 6시간 전에 라인업 0건인 것도 **실패**로 분류돼, 매일 한 번씩
   거짓 실패 알림이 나갔다. 0건은 두 가지를 뜻할 수 있다 —
   ① 아직 발표 전(정상) ② 수집기가 깨짐(실패). 시각으로만 구분할 수 있다.

⚠️ 기준은 **리그 관행**이지 실측이 아니다. `observe()`가 경기별로
   (첫 라인업 수집 시각 ↔ 킥오프) 차이를 쌓는다. 2주 치가 모이면 그 분포로
   config 값을 교체한다 — **그 전까지 이 숫자로 "수집이 늦다"고 결론짓지 마라.**
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

OBS_KEY = "lineup_lead_observed"     # sport → [{game_id, lead_hours, at}]
OBS_MAX = 500                        # 종목당 관측 상한
OBS_TTL = 30 * 24 * 3600


def lead_hours(sport: str, settings=None) -> float:
    """그 종목에서 킥오프 몇 시간 전부터 라인업이 있어야 하는가."""
    from app.config import get_settings

    s = settings or get_settings()
    return float(getattr(s, f"lineup_lead_{(sport or '').lower()}", None)
                 or s.lineup_lead_soccer)


def _parse(dt) -> datetime | None:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    try:
        d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def before_announcement(games: list[dict], sport: str, now: datetime | None = None,
                        settings=None) -> bool:
    """**전 경기가** 아직 발표 시각 전인가. 그렇다면 0건은 정상이다.

    ⚠️ '전 경기'인 이유: 한 경기라도 발표 시각을 지났는데 라인업이 0건이면
       수집기를 의심해야 한다. 하나라도 늦었으면 정상이라고 말하지 않는다.
    ⚠️ 킥오프 시각을 모르는 경기는 판단에서 뺀다 — 모르는 것을 정상의 근거로
       쓰면 시각 파싱이 깨진 날 전부 '정상'이 된다.
    """
    now = now or datetime.now(UTC)
    lead = lead_hours(sport, settings)
    known = [d for d in (_parse(g.get("starts_at")) for g in games) if d]
    if not known:
        return False
    return all((d - now).total_seconds() / 3600 > lead for d in known)


def classify(games: list[dict], ok: int, sport: str, now: datetime | None = None,
             settings=None) -> tuple[bool, str]:
    """(정상으로 볼 것인가, 사람이 읽을 사유)."""
    if ok:
        return True, ""
    if before_announcement(games, sport, now, settings):
        return True, f"아직 발표 전 (킥오프 {lead_hours(sport, settings):g}시간 전 공시 관행)"
    return False, "발표 시각이 지났는데 0건 — 수집 실패"


async def observe(redis, sport: str, game_id, starts_at, now: datetime | None = None) -> None:
    """경기별 **첫** 라인업 수집 시각과 킥오프의 차이를 쌓는다.

    이것이 관행값을 실측으로 바꿀 유일한 재료다. 같은 경기는 한 번만 센다 —
    폴링이 반복 기록하면 분포가 '마지막 관측'으로 쏠린다.
    """
    if redis is None or not game_id:
        return
    start = _parse(starts_at)
    if start is None:
        return
    now = now or datetime.now(UTC)
    try:
        field = f"{sport}:{game_id}"
        if await redis.hexists(OBS_KEY, field):
            return                      # 이미 첫 관측이 있다
        lead = round((start - now).total_seconds() / 3600, 2)
        await redis.hset(OBS_KEY, field, json.dumps(
            {"lead_hours": lead, "at": now.isoformat(timespec="seconds")}))
        await redis.expire(OBS_KEY, OBS_TTL)
        logger.info("[라인업관측] %s game=%s — 킥오프 %.2f시간 전 첫 수집",
                    sport, game_id, lead)
    except Exception as exc:            # 관측이 본체를 죽이지 않는다
        logger.debug("[라인업관측] 기록 실패: %s", exc)


async def observed(redis, sport: str | None = None) -> list[float]:
    """쌓인 리드타임(시간). 표본이 얇으면 **아무 결론도 내지 마라.**"""
    if redis is None:
        return []
    out = []
    try:
        for field, raw in (await redis.hgetall(OBS_KEY) or {}).items():
            if sport and not field.startswith(f"{sport}:"):
                continue
            try:
                out.append(float(json.loads(raw)["lead_hours"]))
            except (ValueError, KeyError, TypeError):
                continue
    except Exception as exc:
        logger.debug("[라인업관측] 조회 실패: %s", exc)
    return out


def summarize(leads: list[float], sport: str = "") -> str:
    """관측 요약. **표본 20 미만이면 숫자를 쓰지 않는다** — 얇은 표본의 중앙값이
    관행값을 갈아치우는 근거로 쓰이면 안 된다."""
    if not leads:
        return f"라인업 리드타임 관측 없음{f' ({sport})' if sport else ''}"
    if len(leads) < 20:
        return (f"라인업 리드타임 {len(leads)}건 — 표본 부족 "
                f"(20건 이상에서 관행값 교체 검토)")
    v = sorted(leads)
    mid = len(v) // 2
    med = v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2
    return (f"라인업 리드타임 {len(leads)}건 · 중앙값 {med:.1f}시간 전 "
            f"(최소 {v[0]:.1f} · 최대 {v[-1]:.1f})")
