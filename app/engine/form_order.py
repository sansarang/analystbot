"""[FORM-1 / STEP 1-h 2026-09-20] 폼 문자열의 **방향**을 검증한다.

🔴 왜 — 생산자 둘 다 순서를 보증하지 않는다:
     `collectors/football.py:168` football-data.org 값을 **그대로** 싣는다(가정 없음).
     `research/deep.py:33·62`     LLM 에게 "최신부터"를 **요구**할 뿐 확인하지 않는다.
   소스가 뒤집어 주면 "직전 승"이 "직전 패"로 읽혀 **정반대 판정**이 된다.
   값이 그럴듯해서 아무도 모른다.

🔴 실측(딥서치 2026-09-13 J리그): `jleague.jp` 표만으로는 방향을 알 수 없었고
   기사의 "고베 4연승"과 표 `L W W W W` 를 대조해서야 오래된→최신임을 확정했다.

🔴 대조 상대는 **우리 DB**(`games(final)` 의 그 팀 최근 1경기)다.
   외부 소스를 또 부르지 않는다 — 이미 아는 사실이다.

⚠️ **순수 함수다.** DB·HTTP·LLM 을 부르지 않는다. 최근 결과는 호출부가 넘긴다.
⚠️ v1.4 흐름은 이 함수가 필요 없다 — `n05` 의 폼은 `_LAST3_SQL`
   (`ORDER BY starts_at DESC`)로 만들어 날짜가 순서를 정한다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 폼 글자. 🔴 여기 말고 다른 곳에서 다시 적지 않는다.
MARKS = "WLD"

#: 검증 결과. 🔴 값 목록은 여기 하나다 — 보고·집계가 이 이름으로 센다.
DATED = "dated_items"          # 날짜가 붙어 있어 정렬로 확정했다(DB 미사용)
VERIFIED = "verified"          # 최신 쪽이 DB 최근 결과와 맞다
FLIPPED = "flipped"            # 최근 2경기가 연속 역순 일치 → 뒤집어 쓴다
DB_STALE = "db_stale"          # DB 가 낡았다 — 대조 자체가 불가능하다
NO_SCHEDULE = "no_schedule"    # 일정 표에 그 팀 경기가 없다
UNVERIFIED = "unverified"      # 그 밖의 확인 실패

ORDERS = (DATED, VERIFIED, FLIPPED, DB_STALE, NO_SCHEDULE, UNVERIFIED)

#: 사유 문자열. 🔴 호출부가 손으로 적지 않게 여기 둔다.
REASON_UNVERIFIED = "form_order_unverified"
REASON_STALE = "form_db_stale"
REASON_NO_SCHEDULE = "form_no_schedule"

#: DB 신선도 판정 값(호출부가 넘긴다).
DB_OK, DB_LAG, DB_NONE = "ok", "stale", "none"


def _clean(form) -> str:
    """W/L/D 만 남긴다. 공백·쉼표·괄호 설명을 버린다."""
    return "".join(c for c in str(form or "").upper() if c in MARKS)


def from_dated(items) -> str:
    """[가드 1] 날짜가 붙은 항목 → **날짜로 정렬한** 최신부터 문자열.

    🔴 이 경우 DB 대조를 하지 않는다 — 순서가 자료 안에 이미 있다.
    항목 모양: `{"date": …, "result": "W"|"L"|"D"}`. 날짜가 없는 항목은 버린다.
    """
    rows = [x for x in (items or [])
            if isinstance(x, dict) and x.get("date") and _clean(x.get("result"))]
    rows.sort(key=lambda x: x["date"], reverse=True)
    return "".join(_clean(x["result"])[:1] for x in rows)


async def verify(form, *, last_result: str | None = None, recent=None,
                 dated_items=None, db_state: str = DB_OK) -> dict:
    """폼 문자열의 방향을 확인한다.

    반환 `{"form", "order", "reason"}`.

    가드(사용자 결정 2026-09-20):
      1) `dated_items` 가 있으면 **날짜로 정렬**해 확정한다. DB 대조 없음.
      2) 날짜 없는 문자열만 DB 와 대조한다. **대조 전에 DB 신선도를 본다** —
         낡았으면(`db_state="stale"`) 대조하지 않고 폼을 버린다. 일정 표에
         그 팀 경기가 없으면(`"none"`) 같은 방식으로 버린다.
      3) **1경기 대조로 뒤집지 않는다.** 뒤집기는 최근 **2경기가 연속으로
         역순 일치**할 때만이다. 1경기만 있고 정순 일치 → 사용,
         1경기만 있고 불일치 → 버린다.

    🔴 버린 폼은 `None` 이고 ⑥ 이 **미상**으로 센다. 모르는 값을 안다고 쓰지 않는다.
    ⚠️ 빈 문자열을 `verified` 로 적지 않는다 — 그것도 거짓이다.
    """
    # ── 가드 1: 날짜가 있으면 그것으로 끝이다
    dated = from_dated(dated_items)
    if dated:
        return {"form": dated, "order": DATED, "reason": None}

    seq = _clean(form)
    if not seq:
        return {"form": None, "order": UNVERIFIED, "reason": REASON_UNVERIFIED}

    # ── 가드 2: DB 가 대조할 만한 상태인가
    if db_state == DB_NONE:
        logger.info("[form] 일정 표에 경기가 없다 — 대조 불가, 폼을 버린다")
        return {"form": None, "order": NO_SCHEDULE, "reason": REASON_NO_SCHEDULE}
    if db_state == DB_LAG:
        logger.info("[form] DB 가 낡았다(끝난 경기가 미기록) — 대조하지 않는다")
        return {"form": None, "order": DB_STALE, "reason": REASON_STALE}

    # 최근 결과 목록(최신부터). `last_result` 는 한 건짜리 옛 호출 모양이다.
    marks = [_clean(x)[:1] for x in (recent or []) if _clean(x)]
    if not marks and last_result:
        marks = [_clean(last_result)[:1]]
    if not marks:
        return {"form": None, "order": UNVERIFIED, "reason": REASON_UNVERIFIED}

    if seq[0] == marks[0]:
        return {"form": seq, "order": VERIFIED, "reason": None}

    # ── 가드 3: 뒤집기는 **2경기 연속 역순 일치**일 때만
    if len(marks) >= 2 and len(seq) >= 2 and seq[-1] == marks[0] and seq[-2] == marks[1]:
        logger.info("[form] 최근 2경기가 연속 역순 일치 — 뒤집어 쓴다 (%s → %s)",
                    seq, seq[::-1])
        return {"form": seq[::-1], "order": FLIPPED, "reason": None}

    logger.info("[form] 방향을 확인할 수 없다 (%s vs 최근 %s) — 폼을 버린다",
                seq, "".join(marks))
    return {"form": None, "order": UNVERIFIED, "reason": REASON_UNVERIFIED}


def last_result_of(rows, team: str) -> str | None:
    """`games(final)` 행 목록 → 그 팀의 **가장 최근** 결과 한 글자."""
    got = recent_results_of(rows, team, limit=1)
    return got[0] if got else None


def recent_results_of(rows, team: str, *, limit: int = 2) -> list:
    """그 팀의 최근 결과를 **최신부터** 최대 `limit` 개.

    🔴 승패 판정은 `pick_ledger._last3_line` 과 같은 규칙(점수 비교)이다.
    ⚠️ 행이 최신순이라고 **가정하지 않고** `starts_at` 으로 직접 정렬한다.
    """
    got = []
    for r in rows or []:
        get = r.get if hasattr(r, "get") else None
        if get is None:
            continue
        hs, as_ = get("home_score"), get("away_score")
        if hs is None or as_ is None:
            continue
        ours, theirs = (hs, as_) if get("home") == team else (as_, hs)
        mark = "W" if ours > theirs else ("L" if ours < theirs else "D")
        got.append((get("starts_at"), mark))
    got.sort(key=lambda x: (x[0] is not None, x[0]), reverse=True)
    return [m for _, m in got[:max(1, int(limit))]]
