"""[BAT-4] 오늘 타순 9명의 **최근 5경기 타석 기록**. 자료3 을 채운다.

🔴 **왜 (실측 2026-09-08).** 재료가 비대칭이었다.

    투수 축  자료4(개인 경기별 로그 ×5) · 자료9(불펜 최근 3경기) · 자료10 ·
             자료14 실측의 80%가 투수·불펜
    타자 축  자료1(**팀** 3경기 합계) · 자료3(**이름·포지션뿐, 숫자 0개**)

   그래서 라인업 확정은 **판정을 개선할 재료를 주지 않으면서 판정을 다시
   열게** 만들었다. 경기 단위(`is_final`) 157경기 실측:
       잠정          27경기  70.4%    ← 투수 재료만으로 낸 1차 판정
       확정(재판정)  130경기  51.5%
       확률 이동 없음 48경기  62.5%  ·  큰 이동(≥0.10) 7경기 28.6%
   프롬프트가 그 빈자리를 "순서가 곧 정보다"로 메우고 있었다. 여기가 그
   빈자리에 숫자를 넣는다.

⚠️ **대원칙**(`app/engine/CLAUDE.md`): 최근 3~5경기만, 시즌 누적 금지.
   여기서 주는 것은 **최근 5경기 창의 합계**다 — 시즌 집계표가 아니다.
   타자는 매일 뛰므로 5경기가 곧 5일이다(선발은 15~21일이라 창이 다르다).

⚠️ **파생 지표를 만들지 않는다.** 타율·OPS 를 우리가 계산해 주면 그것은
   "다른 모델이 만든 등급"과 같은 자리에 선다. 원본 숫자만 준다
   ("수치는 있는 그대로, 분석만 AI" — 사용자 지시 2026-09-02).

⚠️ **팀이 아니라 `sport`+이름으로 조회한다.** 실측 2026-09-08 이름 일치율은
   KBO 79/80(98.8%) · NPB 36/36(100%) · MLB 240/241(99.6%) 이고 미스 둘은
   이적(박찬호)·콜업(Walker Jenkins)이었다. 팀으로 묶으면 이적한 선수의
   이력을 통째로 버린다.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: 타자 최근 창. 대원칙의 상한(5)이다. **여기 한 곳에만 적는다** —
#  테스트도 문서도 이 상수를 참조한다(사본 금지).
RECENT_GAMES = 5

#: 이 수 이하면 표본이 얇다. 지금은 **표시만** 한다 — 추천 탈락으로 쓰지
#  않는다. 투수의 `MIN_STARTS` 와 달리 타자 한 명은 경기를 좌우하지 않는다.
MIN_GAMES = 2

_FETCH = """
    SELECT a.opponent, a.ab, a.h, a.r, a.rbi, a.hr, a.bb, a.so, g.starts_at
      FROM batter_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.batter = $2
       AND g.starts_at < $3 AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""

#: DB 컬럼 → 프롬프트 표기. 없는 칸은 0으로 채우지 않고 건너뛴다.
_SUM_COLS = (("ab", "타수"), ("h", "안타"), ("hr", "홈런"), ("rbi", "타점"),
             ("r", "득점"), ("bb", "볼넷"), ("so", "삼진"))


def _aware(v) -> datetime | None:
    """`starter_recent._aware` 와 같은 일을 한다 — 그쪽이 원본이다."""
    from app.engine.starter_recent import _aware as _src

    return _src(v)


def today_names(jg: dict, side: str) -> list[str]:
    """오늘 타순의 이름들. **타순 원본을 다시 정의하지 않는다.**

    `research.today_nine` 이 원본이고, 없으면 `lineup_diff.parse_order` 로
    문자열을 푼다 — `matchup.lineups_payload` 와 같은 두 경로다.
    """
    r = jg.get("research") or {}
    nine = (r.get("today_nine") or {}).get(side)
    slots = nine.get("order") if isinstance(nine, dict) else None
    if slots:
        return [str(x.get("name") or "").strip()
                for x in slots if isinstance(x, dict) and x.get("name")]
    raw = ((r.get(f"{side}_lineup") or {}).get("order")
           or jg.get(f"lineup_{side}"))
    if isinstance(raw, str) and raw:
        from app.engine.lineup_diff import parse_order

        return [n for n, _ in parse_order(raw)]
    return []


def _sum_rows(rows) -> dict:
    """최근 창의 합계 한 줄. 창 안의 **경기 수**를 함께 준다(표본 두께)."""
    def _get(row, k):
        if isinstance(row, dict):
            return row.get(k)
        try:
            return row[k]
        except (KeyError, IndexError, TypeError):
            return None

    out: dict = {"경기": len(rows)}
    for col, label in _SUM_COLS:
        vals = [_get(r, col) for r in rows]
        vals = [v for v in vals if v is not None]
        if vals:
            out[label] = sum(int(v) for v in vals)
    return out


async def attach_batter_recent(jg: dict, pool) -> None:
    """`research.{home,away}_batter_recent` 을 채운다. 없으면 빈 객체.

    ⚠️ **기록이 없는 선수는 키를 만들지 않는다.** 0으로 채우면 판정이 그것을
       "부진"으로 읽는다 — 수집 실패와 실제 부진은 다른 사실이다.
    ⚠️ 조회가 실패해도 판정은 그대로 돈다. 프롬프트에 "어느 한쪽 재료가
       비어 있으면 없는 쪽을 나쁘다고 보지 마라"가 이미 있다.
    """
    research = jg.setdefault("research", {})
    sport = jg.get("sport") or ""
    before = _aware(jg.get("starts_at")) or datetime.now(UTC)
    filled = total = 0
    for side in ("home", "away"):
        key = f"{side}_batter_recent"
        research.setdefault(key, {})
        names = today_names(jg, side)
        total += len(names)
        if not pool or not sport or not names:
            continue
        got: dict = {}
        for name in names:
            try:
                rows = await pool.fetch(_FETCH, sport, name, before, RECENT_GAMES)
            except Exception as exc:
                logger.warning("[batter_recent] %s %s 조회 실패: %s",
                               sport, name, exc)
                continue
            if rows:
                got[name] = _sum_rows(rows)
        research[key] = got
        filled += len(got)
    if total:
        # 🔴 조용한 0을 막는다. 이름이 안 맞으면 여기서만 보인다.
        logger.info("[batter_recent] game=%s %s 타순 %d명 중 %d명에 최근%d경기 부착",
                    jg.get("game_id"), sport, total, filled, RECENT_GAMES)
