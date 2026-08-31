"""[v1.1 5단계 조기 분리] 일일 픽 요약 카드.

하루치 판정을 한 장으로 묶어 "오늘 무엇을 걸 수 있는가"를 답한다.

⚠️ **`pick_ledger`를 단일 소스로 읽는다.** 카드·분석 캐시를 다시 훑지 않는다 —
   요약과 개별 카드가 서로 다른 숫자를 말하면 둘 다 못 믿게 되고, 레저는
   이미 "판정 전건"을 담도록 만들어져 있다.

⚠️ 배당 자동 수집 전이므로 **가치 판정은 "필요배당" 표기까지만** 한다.
   사용자가 보드와 대조한다. 4·5단계가 완성되면 이 카드에 배당·기대값·
   엣지 라벨이 붙는 구조로 확장한다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TICKET_RULE = ("🎫 티켓 규칙: 엣지·추천끼리만 묶을 것. 다리 후보 1건 이하면 "
               "베팅 비권장. 보드만·가치주의·무판정 경기를 다리로 쓰지 말 것.")

_SPORT_KR = {"mlb": "MLB", "kbo": "KBO", "npb": "NPB", "soccer": "축구"}


def stars(p: float | None) -> str:
    """야구 기준 별표. 축구 카드는 자체 별표를 쓰므로 여기서는 승률 기준이다."""
    if p is None:
        return ""
    return ("★★★★★" if p >= 0.68 else "★★★★" if p >= 0.63 else
            "★★★" if p >= 0.58 else "★★" if p >= 0.53 else "★")


def _side_label(row) -> str:
    fav = row["favored"]
    if fav == "home":
        return row["home"] or "홈"
    if fav == "away":
        return row["away"] or "원정"
    return "박빙"


def _p_of(row) -> float | None:
    from app.engine.pick_ledger import predicted_side

    p = row["p_home"]
    if p is None:
        return None
    return float(p) if predicted_side(row["favored"], p) == "home" else 1.0 - float(p)


async def build(pool, sports: tuple[str, ...], title: str, date: str) -> str:
    """요약 카드 1장. 판정이 없으면 그 사실을 말한다 — 빈 카드를 보내지 않는다."""
    if pool is None:
        return ""
    rows = await pool.fetch(
        """SELECT l.sport, l.league, l.p_home, l.favored, l.gate_result,
                  l.lineup_status, l.trial, l.market_prob, l.divergence_pp,
                  l.edge_status, g.home, g.away, g.starts_at
             FROM pick_ledger l JOIN games g ON g.id = l.game_id
            WHERE l.is_final AND l.date = $1 AND l.sport = ANY($2::text[])
            ORDER BY g.starts_at""", date, list(sports))
    from app.engine.pick_ledger import (
        GATE_EDGE, GATE_RECOMMENDED, GATE_VALUE_WARN,
    )
    from app.engine.value_gate import required_odds

    edge, rec, warn, board, prov = [], [], [], [], []
    for r in rows:
        p = _p_of(r)
        name = _side_label(r)
        if r["gate_result"] in (GATE_EDGE, GATE_RECOMMENDED, GATE_VALUE_WARN):
            mk = ""
            if r["market_prob"] is not None:
                mk = f" vs 시장 {float(r['market_prob']):.0%}"
                if r["divergence_pp"] is not None:
                    mk += f" ({float(r['divergence_pp']):+.1f}%p)"
            need = ""
            if p and r["market_prob"] is None:
                need = f" (필요배당 {required_odds(p):.2f})"
            row = f"  · {name} {p:.0%} {stars(p)}{mk}{need}" if p else f"  · {name}"
            if r["gate_result"] == GATE_EDGE:
                edge.append(row)
            elif r["gate_result"] == GATE_VALUE_WARN:
                warn.append(row)
            else:
                rec.append(row)
        elif (r["lineup_status"] or "") not in ("confirmed",):
            prov.append(name)
        else:
            board.append(name)
    if not rows:
        return (f"{title}\n\n오늘 픽 없음 — 판정된 경기가 없습니다.\n"
                f"({'·'.join(_SPORT_KR.get(s, s) for s in sports)})")
    out = [title, ""]
    if edge:
        out.append(f"🎯 엣지 {len(edge)}건:")
        out += edge
        out.append("")
    if rec:
        out.append(f"✅ 추천 {len(rec)}건:")
        out += rec
    elif not edge:
        out.append("✅ 추천 0건 — 오늘 픽 없음")
    if warn:
        out += ["", f"⚠️ 가치주의 {len(warn)}건 (확률 통과·가치 미달, 추천 아님):"]
        out += warn
    tail = []
    if board:
        tail.append(f"⬜ 보드만 {len(board)}건: {' · '.join(board)}")
    if prov:
        tail.append(f"⏳ 잠정 {len(prov)}건: {' · '.join(prov)}")
    if tail:
        out += [""] + tail
    out += ["", TICKET_RULE]
    return "\n".join(out)
