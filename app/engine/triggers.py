"""[TRG-1] 경기별 시점 트리거 (Part A).

⚠️ **Part A 사양을 받은 적이 없다.** 두 지시문이 참조하는 것에서 최소 사양만
   도출했다 — 5시점 · 1분 due 루프 · 동시 상한 3 · 우선순위 |gap| 큰 순.
   그 이상은 만들지 않는다.

🔴 **트리거는 시각만 관리한다.** 무엇을 할지는 호출부가 정한다. 여기에
   수집·검색·판정을 넣으면 트리거가 곧 파이프라인이 되고, 그때부터 시점을
   바꿀 때마다 수집이 깨진다(계약이 임포트를 잠근다).
"""
from __future__ import annotations

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

#: 스냅샷 5시점. 이름은 Part 1-B-1 의 `snap_tag` 와 **같다** —
#  두 이름표를 만들면 대조가 깨진다. 값은 킥오프 기준 오프셋이다.
KINDS: dict[str, timedelta] = {
    "open":   timedelta(hours=-24),    # 괴리 기준선. 돈이 들어오기 전
    "pre":    timedelta(hours=-3),     # 초기 이동 · 딥서치 시점
    "lineup": timedelta(minutes=-60),  # 라인업 발표 직후 — 가장 중요
    "late":   timedelta(minutes=-10),  # 막판
    "close":  timedelta(0),            # 마감. CLV 기준
}

#: 동시 실행 상한(Part 4 7-3). 토요일 15:00 동시 킥오프 대비.
MAX_CONCURRENT = 3

#: 아직 안 쏜 것 중 시각이 된 것. 🔴 `fired_at IS NULL` 이 빠지면 재발사한다.
DUE_SQL = """
    SELECT t.id, t.game_id, t.kind, t.due_at, t.attempts,
           g.sport, g.league, g.home, g.away, g.starts_at
      FROM game_triggers t JOIN games g ON g.id = t.game_id
     WHERE t.fired_at IS NULL AND t.due_at <= $1
     ORDER BY t.due_at
     LIMIT $2
"""

UPSERT_SQL = """
    INSERT INTO game_triggers (game_id, kind, due_at)
    VALUES ($1, $2, $3)
    ON CONFLICT (game_id, kind) DO UPDATE SET due_at = EXCLUDED.due_at
     WHERE game_triggers.fired_at IS NULL
"""

MARK_SQL = """
    UPDATE game_triggers SET fired_at = $2, attempts = attempts + 1
     WHERE id = $1
"""


def plan(kickoff) -> list[dict]:
    """킥오프 → 5시점 계획. 킥오프가 없으면 **빈 목록**(시각을 지어내지 않는다).

    ⚠️ 이미 지난 시점도 남긴다 — 빼면 늦게 등록된 경기가 `open` 을 영영 못
       받는다. 지났는지는 `DUE_SQL` 이 판단할 일이다.
    """
    if kickoff is None:
        return []
    return [{"kind": k, "due_at": kickoff + off} for k, off in KINDS.items()]


def prioritize(rows: list[dict]) -> list[dict]:
    """|gap| 큰 순(Part 4 7-3). 괴리를 모르는 경기는 뒤로."""
    return sorted(rows or [],
                  key=lambda r: (r.get("gap_pp") is None,
                                 -abs(float(r.get("gap_pp") or 0.0))))
