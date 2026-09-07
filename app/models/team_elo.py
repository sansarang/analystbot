"""자료12 — 팀 실력 레이팅 (ELO, 최근 가중).

🔴 [v1.4 2026-09-07 사용자 지시] **실력 축 복원.**
   620행 원장 분석: 시장 p ↔ 시즌 실력 r=+0.707(MLB +0.809)인데
   우리 p ↔ 시즌 실력은 r=+0.279 뿐이었다. 괴리 ↔ 최근5 는 r=+0.099(≈0),
   괴리 ↔ 시즌 실력은 r=−0.408. 괴리는 "우리가 최근 폼을 본다"가 아니라
   **"우리가 팀 실력을 안 본다"** 에서 왔다.

🔴 **이것은 시즌 누적 통계가 아니다.** 대원칙(`app/engine/CLAUDE.md`)이
   금지하는 것은 타율·ERA·승패표 같은 **집계표**다. 레이팅은 경기마다
   갱신되는 **오늘 시점 상태값 하나**이고, 그래서 자료12 로 허용됐다.
   ⚠️ 이 구분이 무너지면(레이팅 옆에 시즌 타율을 얹는 등) 대원칙 위반이다.

원천은 **우리 `games` 테이블뿐이다** — 외부 API 를 부르지 않는다.
그래서 리그 안에서만 의미가 있다(리그 간 비교 불가).
"""
from __future__ import annotations

import logging

from app.models.elo_core import replay

logger = logging.getLogger(__name__)

#: Redis 키. 슬레이트마다 새로 계산한다 — 어제 레이팅으로 오늘을 판정하지 않는다.
CACHE_KEY = "elo:{sport}:{date}"
CACHE_TTL = 26 * 3600

#: 🔴 **표본 하한.** 이보다 적게 뛴 팀은 레이팅을 내보내지 않는다.
#   1500 근처 값은 "평균 실력"이 아니라 "아직 모른다"인데, 판정이 그것을
#   실력으로 읽으면 없느니만 못하다. 자료4 의 `2경기 이하` 규칙과 같은 정신이다.
MIN_GAMES = 10

#: 야구 홈 이점(ELO 점수). 실측 홈 승률 MLB 51.9% · KBO 50.7% · NPB 53.0%
#  (우리 DB 종료 746경기) → 대략 +15점이면 52% 다. 리그별로 나누지 않는다 —
#  표본이 그만큼 못 된다.
HOME_ADV = 15.0
K_FACTOR = 20.0


def _decay_weight(decay: float, latest_ts, ts) -> float:
    """오래된 경기일수록 K 를 줄인다 — "최근 가중"의 정의다.

    경과 **경기 수**가 아니라 **경과일** 기준이다: 우천취소로 일정이 밀려도
    시간이 지난 만큼만 잊는다.
    """
    if latest_ts is None or ts is None:
        return 1.0
    try:
        days = (latest_ts - ts).total_seconds() / 86400.0
    except TypeError:
        return 1.0
    if days <= 0:
        return 1.0
    return float(decay) ** days


def _rows_to_matches(rows) -> list[dict]:
    """`games` 행 → 커널 입력. 무승부는 `D` 로 넘긴다(KBO·NPB 에 있다)."""
    out = []
    for r in rows:
        hs, as_ = r.get("home_score"), r.get("away_score")
        if hs is None or as_ is None:
            continue
        out.append({"home": r["home"], "away": r["away"],
                    "res": "H" if hs > as_ else "A" if as_ > hs else "D",
                    "ts": r.get("starts_at")})
    return out


def compute(rows, *, decay: float = 0.9, k: float = K_FACTOR,
            home_adv: float = HOME_ADV) -> dict:
    """종료 경기 행들 → `{team: {"레이팅", "리그평균대비", "경기수"}}`.

    `rows` 는 **시간 오름차순**이어야 한다 — walk-forward 라 순서가 곧 의미다.
    """
    matches = _rows_to_matches(rows)
    if not matches:
        return {}
    latest = matches[-1].get("ts")
    ratings, _ = replay(matches, home_adv=home_adv, k=k,
                        weight=lambda m: _decay_weight(decay, latest, m.get("ts")))
    played: dict[str, int] = {}
    for m in matches:
        played[m["home"]] = played.get(m["home"], 0) + 1
        played[m["away"]] = played.get(m["away"], 0) + 1
    # 🔴 표본이 얇은 팀은 **빼고** 평균을 낸다 — 잡음이 기준선을 흔들지 않게.
    solid = {t: v for t, v in ratings.items() if played.get(t, 0) >= MIN_GAMES}
    if not solid:
        logger.info("[elo] 표본 %d경기 이상인 팀이 없다 — 레이팅 생략", MIN_GAMES)
        return {}
    mean = sum(solid.values()) / len(solid)
    return {t: {"레이팅": round(v, 1),
                "리그평균대비": round(v - mean, 1),
                "경기수": played.get(t, 0)}
            for t, v in solid.items()}


async def refresh(pool, redis, sport: str, date: str, *, settings=None) -> dict:
    """그 종목의 레이팅을 다시 계산해 캐시한다. 외부 호출 0."""
    import json

    from app.config import get_settings

    s = settings or get_settings()
    rows = await pool.fetch(
        """SELECT home, away, home_score, away_score, starts_at
             FROM games
            WHERE sport = $1 AND status = 'final'
              AND home_score IS NOT NULL AND away_score IS NOT NULL
            ORDER BY starts_at""", sport)
    out = compute([dict(r) for r in rows], decay=float(s.elo_decay))
    if redis is not None and out:
        try:
            await redis.set(CACHE_KEY.format(sport=sport, date=date),
                            json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
        except Exception as exc:
            logger.warning("[elo] %s 캐시 실패: %s", sport, exc)
    logger.info("[elo] %s %s — 팀 %d개 (종료 %d경기 · 감쇠 %.2f)",
                sport, date, len(out), len(rows), float(s.elo_decay))
    return out


async def load(redis, sport: str, date: str) -> dict:
    """캐시된 레이팅. 없으면 빈 dict — 자료12 없이 판정한다."""
    import json

    if redis is None:
        return {}
    try:
        raw = await redis.get(CACHE_KEY.format(sport=sport, date=date))
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.warning("[elo] %s 조회 실패: %s", sport, exc)
        return {}
