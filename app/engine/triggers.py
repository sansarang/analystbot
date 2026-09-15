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

#: 🔴 [U1 2026-09-15] **행동 트리거 8종.** S4~S11 이 붙을 시각이다.
#   ⚠️ `KINDS` 와 **반드시 분리한다.** `_triggers_tick` 은 발사할 때 `kind` 를
#      그대로 `snap_tag` 에 넣는다. 여기 이름이 `snap_tag` 로 새면
#      `odds_move.BASELINE_ORDER` 에 없는 값이 되어
#      `pick_ledger.record_move` 의 `order.index()` 가 ValueError 로 터진다
#      — 이동 분석이 통째로 죽는다. 계약이 그 자리를 잠근다.
#   ⚠️ 지금 이 여덟은 **자리만 만든다.** 실제 동작은 U5~U11 이 붙인다.
ACTIONS: dict[str, timedelta] = {
    "model":          timedelta(hours=-24),    # 모델예측 (S2·S3)
    "recheck":        timedelta(hours=-3),     # 재확인 (S5~S7)
    "lineup_poll":    timedelta(minutes=-90),  # 라인업 폴링
    "rejudge":        timedelta(minutes=-60),  # 재판정 (S10)
    "card":           timedelta(minutes=-30),  # 첫 카드 (S11)
    "satellite_stop": timedelta(minutes=-10),  # 위성 마감
    "kickoff":        timedelta(0),            # 마감
    "result":         timedelta(hours=3),      # 결과 채점 (S12)
}

#: 계획에 쓰는 전체 목록. **이름표에는 `KINDS` 만 쓴다.**
ALL_KINDS: dict[str, timedelta] = {**KINDS, **ACTIONS}


def is_snapshot(kind: str) -> bool:
    """이 트리거가 **스냅샷 이름표**를 붙이는 종류인가.

    🔴 `KINDS` 가 원본이다 — 목록을 손으로 적지 않는다.
    """
    return str(kind or "") in KINDS


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
    # 🔴 [U1] 스냅샷 5 + 행동 8 = **13행**. `ALL_KINDS` 가 원본이다.
    #    ⚠️ **시간순으로 낸다.** 두 표를 합치면 사전 순서가 시간 순서가 아니다
    #       (KINDS 먼저 · ACTIONS 나중). 계약이 시간순을 요구한다.
    rows = [{"kind": k, "due_at": kickoff + off} for k, off in ALL_KINDS.items()]
    return sorted(rows, key=lambda r: (r["due_at"], r["kind"]))


def prioritize(rows: list[dict]) -> list[dict]:
    """|gap| 큰 순(Part 4 7-3). 괴리를 모르는 경기는 뒤로."""
    return sorted(rows or [],
                  key=lambda r: (r.get("gap_pp") is None,
                                 -abs(float(r.get("gap_pp") or 0.0))))


# ═══════════════ [U1 2026-09-15] 적재 자기검증
#
# 🔴 왜: J1·K리그1·ACL 이 **18일간 0건**이었는데 아무도 몰랐다(P2-0 —
#    배당 차단기가 2026-08-27 에 내려간 뒤 09-14 까지). 매 실행 로그는
#    "축구 일정 소스 실패" 한 줄뿐이었고, 그 한 줄이 "경기가 없다"와
#    구분되지 않았다.
# ⚠️ **경고만 한다. 자동 복구하지 않는다** — 차단기와 같은 태도다.

#: 차이가 이 값보다 크면 경고한다. 0 이면 "하나라도 빠지면 경고".
INGEST_GAP_MIN = 0


def ingest_gap(src_counts: dict, db_counts: dict) -> list[dict]:
    """소스 건수 vs DB 건수 → 부족한 리그 목록.

    `src_counts`·`db_counts` 는 `{리그: 건수}`. 반환은
    `[{"league","src_n","db_n","missing"}, …]` 이고 **차이가 없으면 빈 목록**이다.

    🔴 소스에 있는데 DB 에 없는 것만 본다. 반대(DB 가 더 많다)는 다른 소스가
       넣었을 수 있어 경고하지 않는다 — 오탐은 감시를 무디게 만든다
       (실사고 2026-09-05: 규칙을 넓혔다가 검증 184→137 로 악화).
    """
    out: list[dict] = []
    for league, src_n in (src_counts or {}).items():
        db_n = int((db_counts or {}).get(league, 0))
        missing = int(src_n) - db_n
        if missing > INGEST_GAP_MIN:
            out.append({"league": league, "src_n": int(src_n),
                        "db_n": db_n, "missing": missing})
    return sorted(out, key=lambda x: -x["missing"])


def ingest_gap_note(gaps: list[dict]) -> str:
    """원장·로그 한 줄. 빈 목록이면 빈 문자열(조용한 0 금지의 반대 — 없으면 없다)."""
    if not gaps:
        return ""
    return " · ".join(f"{g['league']} 소스{g['src_n']}/DB{g['db_n']}"
                      f"(−{g['missing']})" for g in gaps)
