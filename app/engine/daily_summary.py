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


async def dispatch_lines(redis, sports: tuple[str, ...], date: str) -> list[str]:
    """[운영 안정화 1] 종목별 발송률 줄. 재료가 없으면 빈 목록.

    ⚠️ **"조용한 0"은 결함이다.** 미발송이 있으면 전건에 사유가 붙는다.
       MLB 는 슬레이트 날짜가 미 동부 기준이라 KST 날짜와 다르다 —
       종목마다 제 날짜로 조회한다.
    """
    from app.engine.dispatch_stats import render, summary

    out: list[str] = []
    for sp in sports:
        if sp not in ("mlb", "kbo", "npb"):
            continue
        d = date
        if sp == "mlb":
            from app.pipeline import mlb_slate_date

            d = mlb_slate_date()
        out += render(await summary(redis, sp, d), _SPORT_KR.get(sp, sp))
    return out


async def cost_lines(redis, sports: tuple[str, ...], date: str) -> list[str]:
    """[무과금 전환 3] 비용 실측 — 유료 호출을 **숫자로** 낸다.

    ⚠️ "0원으로 바꿨다"는 주장이 아니라 관측이어야 한다. 유료 경로를 실제로
       안 탔는지는 카운터로만 확인된다.
    """
    if redis is None:
        return []
    out = []
    try:
        from app.config import get_settings
        from app.engine.deepsearch import PAID_KEY

        paid = int(await redis.get(PAID_KEY.format(date=date)) or 0)
        cap = int(getattr(get_settings(), "deepsearch_paid_cap", 0) or 0)
        provider = (get_settings().odds_provider or "free").lower()
        theodds = 0 if provider != "theodds" else -1
        out.append("💸 유료 호출: "
                   + (f"The Odds API {theodds}콜" if theodds >= 0
                      else "The Odds API 사용중(유료 모드)")
                   + f" · web_search {paid}/{cap}콜")
    except Exception as exc:
        logger.debug("[daily-summary] 비용 집계 실패: %s", exc)
    # 사본 금지 — 감시 종목은 레지스트리가 원본이다.
    from app.registry import watched_sports

    covered = watched_sports()
    for sp in sports:
        if sp not in covered:
            continue
        d = date
        if sp == "mlb":
            from app.pipeline import mlb_slate_date

            d = mlb_slate_date()
        try:
            import json as _json

            raw = await redis.get(f"odds_coverage:{sp}:{d}")
            if not raw:
                continue
            c = _json.loads(raw)
            if c.get("total"):
                out.append(f"   배당 커버리지 {_SPORT_KR.get(sp, sp)} "
                           f"{c['with_odds']}/{c['total']} "
                           f"({(c.get('rate') or 0):.0%})")
        except Exception as exc:
            logger.debug("[daily-summary] 커버리지 %s 실패: %s", sp, exc)
    return out


async def build(pool, sports: tuple[str, ...], title: str, date: str,
                *, window_hours: int = 18, redis=None) -> str:
    """요약 카드 1장. 판정이 없으면 그 사실을 말한다 — 빈 카드를 보내지 않는다.

    🔴 **날짜가 아니라 킥오프로 고른다.** 종전에는 `l.date = today_kst()`로
       조회했는데, 레저의 date는 **종목별 슬레이트 날짜**다. MLB는 미 동부
       날짜라 KST 날짜와 어긋나고(실측 2026-08-31: 09/01 04:30에 생성된
       판정의 date가 2026-08-31), 그 결과 **MLB 판정이 해외판 요약에
       영원히 나타나지 않았다.**

       앞으로 `window_hours` 안에 시작하는 경기를 고른다 — "오늘 밤 걸 수
       있는 것"이 이 카드의 질문이므로, 날짜보다 킥오프가 맞는 기준이다.

    ⚠️ 이미 시작한 경기는 뺀다. 걸 수 없는 것을 목록에 올리지 않는다.
    """
    if pool is None:
        return ""
    rows = await pool.fetch(
        """SELECT l.sport, l.league, l.p_home, l.favored, l.gate_result,
                  l.lineup_status, l.trial, l.market_prob, l.divergence_pp,
                  l.edge_status, g.home, g.away, g.starts_at
             FROM pick_ledger l JOIN games g ON g.id = l.game_id
            WHERE l.is_final AND l.sport = ANY($1::text[])
              AND g.starts_at > now()
              AND g.starts_at <= now() + make_interval(hours => $2)
            ORDER BY g.starts_at""", list(sports), window_hours)
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
        head = (f"{title}\n\n오늘 픽 없음 — 판정된 경기가 없습니다.\n"
                f"({'·'.join(_SPORT_KR.get(s, s) for s in sports)})")
        # 🔴 픽이 없는 날일수록 **왜 없는지**가 중요하다. 가동률을 함께 낸다 —
        #    "판정된 경기가 없다"만 보내면 고장과 한산한 날을 구분할 수 없다.
        dl = await dispatch_lines(redis, sports, date)
        return head + ("\n\n" + "\n".join(dl) if dl else "")
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
    dl = await dispatch_lines(redis, sports, date)
    if dl:
        out += [""] + dl
    cl = await cost_lines(redis, sports, date)
    if cl:
        out += [""] + cl
    out += ["", TICKET_RULE]
    return "\n".join(out)
