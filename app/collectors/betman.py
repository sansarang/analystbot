"""[무과금 전환 1c] 배트맨(스포츠토토 공식) 프로토 배당 — KBO·NPB.

국내 유일 합법 공개 배당이고 야구 국내외(KBO·NPB·MLB)를 함께 낸다.
Go 크롤러가 평시 60분 주기로 스냅샷을 Redis 에 넣고, 여기서 읽어 DB 로 옮긴다.
(naver_kbo·yahoo_npb 와 같은 패턴 — 파이썬이 HTML 을 직접 때리지 않는다.)

🔴 **고정배당이 아니다.** 프로토는 발매식이라 공표 시점과 마감이 있고,
   그 사이 배당이 갱신된다. 그래서 스냅샷 **시각을 함께 저장**하고,
   시장 괴리는 `captured_at` 이 판정 시각과 가까운 것만 쓴다 —
   마감 직전 배당을 몇 시간 전 판정과 견주면 그 괴리는 우리 것이 아니다.

⚠️ 배당은 판정 입력에 흐르지 않는다. 여기서 온 값도 가치 게이트·시장
   괴리·레저에서만 쓰인다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

PROVIDER = "betman"
KEY = "betman:{sport}:{date}"
#: 프로토 배당은 분 단위로 안 움직인다. 크롤러 주기와 맞춘다.
TTL = 3 * 3600


async def load_snapshot(redis, sport: str, date: str) -> dict | None:
    """크롤러가 넣은 스냅샷. 없으면 None — 빈 dict 를 만들지 않는다."""
    if redis is None:
        return None
    try:
        raw = await redis.get(KEY.format(sport=sport, date=date))
    except Exception as exc:
        logger.debug("[betman] 스냅샷 조회 실패 %s: %s", sport, exc)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[betman] 스냅샷 파싱 실패 %s %s", sport, date)
        return None


def to_rows(game: dict) -> list[dict]:
    """스냅샷 1경기 → 적재 행. 승·패만. 무승부 칸은 야구에 없다.

    크롤러 계약: {"home","away","home_odds","away_odds","captured_at","round"}
    ⚠️ 배당이 한쪽만 있으면 **그 한쪽만** 넣는다. 반대쪽을 역산하지 않는다 —
       프로토 공제율은 우리가 모른다.
    """
    out = []
    for key, side in (("home_odds", game.get("home")),
                      ("away_odds", game.get("away"))):
        try:
            v = float(game.get(key))
        except (TypeError, ValueError):
            continue
        if v > 1.0 and side:
            out.append({"book": "betman", "market": "h2h", "side": side,
                        "line": None, "odds": round(v, 3)})
    return out
