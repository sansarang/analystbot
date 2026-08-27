"""[§9-라인업 의도] 변경점 → 칸 배분 · 득점 방향 · 핸디캡 근거 · 채점 적재.

⚠️ **새 칸을 만들지 않는다.** 변경 유형에 따라 기존 다섯 칸에 배분한다
   (타순·결장 → 타선 / 불펜 엔트리 → 불펜 가용 / 주전 대거 휴식 → 무게).

⚠️ **사실과 해석을 끝까지 분리한다.** 변경점(무엇이 바뀌었나)은 코드가 만들어
   `research`에 넣고, 그러면 카드의 사실 층에 자연히 실린다. 부호(왜 그랬을까)는
   2단이 매기고 **따로** 저장한다. 섞으면 3단이 추측을 사실로 읽는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 득점 방향을 합칠 때의 규율 — 양쪽이 반대면 상쇄한다.
_SCORE_VALUE = {"다득점": 1, "저득점": -1, "중립": 0, "보류": 0}

# 한쪽만 주전이 빠지면 점수차가 벌어질 수 있다 [7].
_GAP_TYPES = ("regular_out", "new_starter")


def merge_changes_into_research(research: dict, side: str,
                                changes: list[dict], headline: str) -> list[str]:
    """변경점을 **사실로** research에 얹는다. 반환: 채운 필드.

    카드 빌더가 이것을 읽어 해당 칸의 사실 목록에 덧붙인다 — LLM은 여기에
    쓰기 접근이 없다.
    """
    by_cell: dict[str, list[str]] = {}
    for c in changes or []:
        by_cell.setdefault(c.get("cell") or "batting", []).append(c["detail"])
    research[f"{side}_lineup_changes"] = by_cell
    research[f"{side}_lineup_headline"] = headline
    return [f"{side}_lineup_changes"] if by_cell else []


def scoring_direction(items_home: list[dict], items_away: list[dict]) -> dict:
    """양 팀 변경점의 득점 방향을 합친다.

    반환 {"dir": "다득점"|"저득점"|"중립"|"보류", "detail": str}.

    ⚠️ **양쪽이 반대면 상쇄해 중립이다.** 한쪽만 보고 방향을 정하면 상대의
       같은 크기 변화를 무시하게 된다.
    ⚠️ 판단된 항목이 하나도 없으면 '보류'다 — 중립과 다르다.
    """
    votes, bits = [], []
    for label, items in (("홈", items_home), ("원정", items_away)):
        for it in items or []:
            v = _SCORE_VALUE.get(it.get("scoring_dir"), 0)
            if it.get("scoring_dir") in ("다득점", "저득점"):
                votes.append(v)
                bits.append(f"{label} {it['change_type']}→{it['scoring_dir']}")
    if not votes:
        return {"dir": "보류", "detail": "라인업발 득점 방향 판단 없음"}
    total = sum(votes)
    d = "다득점" if total > 0 else "저득점" if total < 0 else "중립"
    if d == "중립":
        return {"dir": "중립", "detail": "양 팀 변경이 상쇄 — " + " · ".join(bits)}
    return {"dir": d, "detail": " · ".join(bits)}


def handicap_note(changes_home: list[dict], changes_away: list[dict]) -> dict:
    """핸디캡 근거 [7]. 반환 {"support", "detail"}.

    - 한쪽만 주전 결장이 크면 점수차 확대 가능성 → -1.5 검토 근거
    - 양쪽 다 주전급 결장이면 상쇄 → 핸디캡 근거 없음
    """
    def _n(items):
        return sum(1 for c in items or [] if c.get("type") in _GAP_TYPES)

    h, a = _n(changes_home), _n(changes_away)
    if h and a:
        return {"support": None,
                "detail": f"양 팀 모두 주전 이탈(홈 {h}건·원정 {a}건) — 상쇄, 핸디 근거 없음"}
    if h and not a:
        return {"support": "away",
                "detail": f"홈만 주전 이탈 {h}건 — 원정 쪽 점수차 확대 가능성"}
    if a and not h:
        return {"support": "home",
                "detail": f"원정만 주전 이탈 {a}건 — 홈 쪽 점수차 확대 가능성"}
    return {"support": None, "detail": ""}


async def record_verdicts(pool, game_id, side: str, team: str | None,
                          items: list[dict]) -> int:
    """유형별 판정을 적재한다. **보류는 적재하지 않는다** — 채점 대상이 아니다."""
    if not pool or not game_id or not items:
        return 0
    rows = [(int(game_id), side, team, it["change_type"], it["cell"],
             it["symbol"], it["scoring_dir"], (it.get("reason") or "")[:500])
            for it in items if it.get("symbol") in ("▲", "▼", "=")]
    if not rows:
        return 0
    try:
        async with pool.acquire() as con:
            await con.executemany("""
                INSERT INTO lineup_verdicts (game_id, side, team, change_type,
                                             cell, symbol, scoring_dir, detail)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (game_id, side, change_type) DO UPDATE
                   SET symbol = EXCLUDED.symbol,
                       scoring_dir = EXCLUDED.scoring_dir,
                       cell = EXCLUDED.cell, detail = EXCLUDED.detail,
                       created_at = now()
            """, rows)
    except Exception as exc:
        logger.warning("[라인업의도] 기록 실패 %s/%s: %s", game_id, side, exc)
        return 0
    return len(rows)


def render(jg: dict) -> list[str]:
    """라인업 의도 출력. 변경이 없으면 그 사실도 쓴다 — 변화 없음도 정보다."""
    intent = jg.get("lineup_intent") or {}
    if not intent:
        return []
    out = []
    for side in ("away", "home"):
        name = jg.get(f"{side}_kr") or jg.get(side)
        head = (intent.get("headline") or {}).get(side)
        if head:
            out.append(f"  {name}: {head}")
        for it in (intent.get("items") or {}).get(side) or []:
            mark = it["symbol"] if it["symbol"] != "보류" else "❓"
            out.append(f"    {mark} {it['reason']}"
                       + (f" [득점 {it['scoring_dir']}]"
                          if it["scoring_dir"] in ("다득점", "저득점") else ""))
    if not out:
        return []
    sc = intent.get("scoring") or {}
    if sc.get("dir") in ("다득점", "저득점", "중립"):
        out.append(f"  → 라인업발 득점 방향: {sc['dir']} ({sc.get('detail', '')[:60]})")
    hc = intent.get("handicap") or {}
    if hc.get("detail"):
        out.append(f"  → 핸디캡: {hc['detail']}")
    return ["📋 라인업 의도 (평소 대비)"] + out
