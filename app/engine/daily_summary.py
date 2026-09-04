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


#: 설계 동결 해제 조건 — 리그별 채점 완료 건수.
FREEZE_TARGET = 50

#: 리그별 **집계 시작 슬레이트**. 판정 입력이 실질적으로 바뀐 날 이후만 센다 —
#  재료가 다른 판정을 같은 표본에 섞으면 50건을 채워도 무엇의 성적인지 모른다.
#
#  기본 `2026-09-03` 은 v1.3 동결 시작일이다.
#  ⚠️ **MLB 만 근거가 다르다.** 09-03 슬레이트부터인 것은 같지만 이유가
#     "동결 시작"이 아니라 **자료9(불펜) 주입 개시**다. 자료9 수집기는
#     `5cd2ba8`(2026-09-03 08:59 KST)에 태어났고, 그 시각 이전에 판정이 끝난
#     MLB 슬레이트 `2026-09-02` 는 불펜 없이 판정됐다(카드가 "불펜 자료가
#     없어…"라고 직접 적었다). 재료가 다르므로 같은 표본에 넣지 않는다.
#  ⚠️ MLB 의 `date` 는 **미 동부 슬레이트 날짜**다(KST 날짜가 아니다).
#     슬레이트 2026-09-03 의 판정은 전부 위 배포 이후에 일어난다.
#  ⚠️ KBO·NPB 는 무관하다 — 두 리그는 이미 자료9 를 갖고 있었다.
FREEZE_START = {}
FREEZE_START_DEFAULT = "2026-09-04"

#: 표본을 다시 세는 사유. 요약 카드가 이 문장을 그대로 낸다 — 숫자가 왜
#  0 부터 시작하는지 사람이 물어보기 전에 답해야 한다.
FREEZE_RESTART_REASON = "변수 정량화 반영 (자료10 신설 · 변수 출력 명세 개정)"

#: 🔴 **이 재시작이 마지막이다.** 다음 재시작은 50건 리포트 이후에만 가능하다.
#   재료를 바꿀 때마다 표본을 버리면 영원히 50건에 도달하지 못한다.
FREEZE_RESTART_IS_FINAL = True


def freeze_start(sport: str) -> str:
    """이 리그의 집계 시작 슬레이트 날짜."""
    return FREEZE_START.get(sport, FREEZE_START_DEFAULT)


async def freeze_progress_lines(pool, sports: tuple[str, ...]) -> list[str]:
    """[v1.3 D] `리그별 graded 누적 N/50` — 설계 동결 해제까지의 진행률.

    🔴 표본이 없으면 무엇을 고쳐야 할지 알 수 없다. 고치면 그때까지 쌓은
       표본이 통째로 무효가 된다 — 그래서 50건까지 손대지 않는다.
    ⚠️ **집계 시작일은 리그마다 다르다** — `FREEZE_START` 가 원본이다.
       그 전 기록은 재료나 설계가 달라 같은 시스템의 성적이 아니다.
    """
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """SELECT l.sport, count(*) AS n FROM pick_ledger l
                JOIN unnest($1::text[], $2::text[]) AS f(sport, since)
                  ON f.sport = l.sport
                WHERE l.is_final AND l.graded_at IS NOT NULL AND NOT l.void
                  AND l.date >= f.since
                GROUP BY l.sport ORDER BY l.sport""",
            list(sports), [freeze_start(sp) for sp in sports])
    except Exception as exc:
        logger.debug("[daily-summary] 동결 진행률 조회 실패: %s", exc)
        return []
    if not rows:
        return []
    bits = [f"{_SPORT_KR.get(r['sport'], r['sport'])} {r['n']}/{FREEZE_TARGET}"
            for r in rows]
    done = all(int(r["n"]) >= FREEZE_TARGET for r in rows)
    tail = " — 해제 조건 충족" if done else ""
    return [f"🔒 v1.3 동결 진행률: {' · '.join(bits)}{tail}",
            f"   표본 재시작 {FREEZE_START_DEFAULT}: {FREEZE_RESTART_REASON}"]


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


async def scout_lines(redis, sports: tuple[str, ...]) -> list[str]:
    """[정찰 C4] 정찰 한 줄 — **무엇을 아직 모르는가**.

        🔭 정찰 KBO: 5경기 · 라인업 확정 2 / 잠정 1 / 없음 2 · 배당 5/5 ·
           최초 공시 T-63분(중앙값)

    🔴 재료가 없으면 **빈 목록**이다. 매일 "정찰 0"을 보내면 휴면과 정상을
       구분할 수 없다 — 감시 줄과 같은 규칙이다.
    ⚠️ 이 줄은 **운영 요약**에만 붙는다. 분석 카드 텍스트는 건드리지 않는다.
    ⚠️ 시장 값(배당 숫자 자체)은 싣지 않는다 — 몇 건 들어왔는지만 센다.
       배당은 판정·서술에 흐르지 않는다는 절대 규칙이 정찰 카드에도 적용된다.
    """
    import json as _json

    from app.engine.scout import LINEUP_CONFIRMED, LINEUP_NONE, LINEUP_PARTIAL

    if redis is None:
        return []
    out: list[str] = []
    for sport in sports:
        try:
            keys = await redis.keys(f"scout:{sport}:*")
            recs = []
            for k in keys or []:
                raw = await redis.get(k)
                if raw:
                    recs.append(_json.loads(raw))
        except Exception as exc:
            logger.debug("[scout] 요약 조회 실패 %s: %s", sport, exc)
            continue
        if not recs:
            continue
        cnt = {LINEUP_CONFIRMED: 0, LINEUP_PARTIAL: 0, LINEUP_NONE: 0}
        for r in recs:
            st = (r.get("lineup") or {}).get("state") or LINEUP_NONE
            cnt[st] = cnt.get(st, 0) + 1
        with_odds = sum(1 for r in recs if (r.get("market") or {}).get("rows"))
        leads = sorted(x for x in
                       ((r.get("lineup") or {}).get("lead_min") for r in recs)
                       if isinstance(x, (int, float)))
        part = (f"🔭 정찰 {sport.upper()}: {len(recs)}경기 · 라인업 "
                f"확정 {cnt[LINEUP_CONFIRMED]} / 잠정 {cnt[LINEUP_PARTIAL]} / "
                f"없음 {cnt[LINEUP_NONE]} · 배당 {with_odds}/{len(recs)}")
        if leads:
            part += f" · 최초 공시 T-{leads[len(leads) // 2]:.0f}분(중앙값)"
        out.append(part)
    return out


async def monitor_lines(pool, redis, sports: tuple[str, ...],
                        date: str) -> list[str]:
    """[감시 C3] 감시 3층 + 계측을 한 줄로.

        🔍 감시: 사실 v/d/nf/m · 검사역 이의 k(유효 j) · 패널 편차>8%p m건
           · 계측: 역행 r건, 타순 주입 p%

    ⚠️ 이 줄은 **운영 요약**에만 붙는다. 분석 카드 텍스트는 건드리지 않는다 —
       감시 결과를 카드에 표기하는 것은 v1.4 승격 때다.
    🔴 재료가 하나도 없으면 **빈 목록**이다. "감시: 0/0/0/0"을 매일 보내면
       휴면과 정상을 구분할 수 없게 된다.
    ⚠️ 편차 임계는 config 를 읽는다 — 이 줄에 8을 손으로 적지 않는다(사본 금지).
    """
    if pool is None:
        return []
    sl = list(sports)
    parts: list[str] = []
    try:
        a = await pool.fetchrow(
            """SELECT coalesce(sum(verified_n), 0) v, coalesce(sum(derived_n), 0) d,
                      coalesce(sum(not_found_n), 0) nf, coalesce(sum(mismatch_n), 0) m,
                      count(*) n
                 FROM judgement_audit
                WHERE sport = ANY($1::text[]) AND created_at >= now() - interval '20 hours'""",
            sl)
        if a and int(a["n"]):
            parts.append(f"사실 {a['v']}/{a['d']}/{a['nf']}/{a['m']}")
    except Exception as exc:
        logger.debug("[daily-summary] L1 집계 실패: %s", exc)
    try:
        r = await pool.fetchrow(
            """SELECT coalesce(sum(objection_n), 0) k, coalesce(sum(valid_n), 0) j,
                      count(*) n
                 FROM judge_review
                WHERE sport = ANY($1::text[]) AND created_at >= now() - interval '20 hours'""",
            sl)
        if r and int(r["n"]):
            parts.append(f"검사역 이의 {r['k']}(유효 {r['j']})")
    except Exception as exc:
        logger.debug("[daily-summary] L2 집계 실패: %s", exc)
    try:
        from app.config import get_settings

        thr = float(get_settings().shadow_diverge_pp)
        sp = await pool.fetchrow(
            """SELECT count(*) FILTER (WHERE abs(divergence) >= $2) m, count(*) n
                 FROM shadow_panel
                WHERE sport = ANY($1::text[]) AND created_at >= now() - interval '20 hours'""",
            sl, thr)
        if sp and int(sp["n"]):
            parts.append(f"패널 편차>{thr * 100:.0f}%p {sp['m']}건")
    except Exception as exc:
        logger.debug("[daily-summary] L3 집계 실패: %s", exc)

    # 계측 — M-1·M-2 는 Redis 카운터, M-3 는 lineups 테이블이 원본이다.
    from app.engine.monitor_metrics import summary as _mon

    tot = inj = regress = 0
    for sp_ in sports:
        d = date
        if sp_ == "mlb":
            from app.pipeline import mlb_slate_date

            d = mlb_slate_date()
        m = await _mon(redis, sp_, d)
        tot += m["mat_total"]
        inj += m["mat_injected"]
        regress += m["regress"]
    met = []
    if regress or tot:
        met.append(f"역행 {regress}건")
    if tot:
        met.append(f"타순 주입 {inj / tot:.0%}")
    try:
        # 🔴 [2026-09-03 교정] **확정 상태만 센다.** `save_lineup` 은 라인업
        #    공시 **전**(`predicted`)에도 저장하고, 그때 타순이 9명이 아닌 것은
        #    정상이다 — 아직 발표가 안 됐을 뿐이다.
        #    실측: 30시간 창에서 확정 이상 0건 / 잠정 이상 20건. 종전 집계는
        #    저 20건을 매일 "이상"으로 찍었을 것이고, 정상을 결함으로 세는
        #    지표는 **진짜 결함을 그 속에 묻는다.**
        an = await pool.fetchval(
            """SELECT count(*) FROM lineups
                WHERE jsonb_array_length(batting_order) <> 9
                  AND status = 'confirmed'
                  AND captured_at >= now() - interval '20 hours'""")
        if an:
            met.append(f"타순 길이 이상 {an}건")
    except Exception as exc:
        logger.debug("[daily-summary] M-3 집계 실패: %s", exc)
    if met:
        parts.append("계측: " + ", ".join(met))
    return [f"🔍 감시: {' · '.join(parts)}"] if parts else []


async def variable_lines(pool, sports: tuple[str, ...]) -> list[str]:
    """[C3] `📐 변수: 정량 k/전체 n · 현실화 r · 검증불가 u`.

    ⚠️ 재료가 없으면 줄이 없다 — 매일 0 을 보내면 휴면과 정상을 구분 못 한다.
    """
    from app.engine.variable_ledger import summary as _vsum

    row = await _vsum(pool, sports)
    if not row:
        return []
    return [f"📐 변수: 정량 {row['quant']}/{row['n']} · "
            f"현실화 {row['realized']} · 검증불가 {row['unver']}"]


async def market_lines(pool, sports: tuple[str, ...]) -> list[str]:
    """[시장 기준선] `🎯 시장 N승M패 · 우리 N승M패 · 이견 k건 중 j적중`.

    🔴 **벤치마크지 게이트가 아니다.** 이 숫자가 추천을 바꾸지 않는다.
       50건 리포트 1번 항목이 여기서 나온다 — "시장을 이기고 있는가".
    ⚠️ 확정분만(`graded_at` 있음 · `void` 아님). 재료 없으면 줄도 없다.
    ⚠️ 이견 기준은 **close 값** 기준 `divergence` 다 — 발송 시점이 아니라
       마감 대비여야 "시장이 최종적으로 어떻게 봤는가"와 비교가 된다.
    """
    from app.engine.market_baseline import summary as _msum

    row = await _msum(pool, sports)
    if not row:
        return []
    return [f"🎯 시장 {row['m_w']}승{row['m_l']}패 · "
            f"우리 {row['o_w']}승{row['o_l']}패 · "
            f"이견 {row['diverged']}건 중 {row['diverged_hit']}적중"]


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
    kl = await market_lines(pool, sports)
    if kl:
        out += kl
    vl = await variable_lines(pool, sports)
    if vl:
        out += vl
    ml = await monitor_lines(pool, redis, sports, date)
    if ml:
        out += ml
    # [정찰 C4] 무엇을 아직 모르는가. 재료 없으면 줄 자체가 없다.
    try:
        sl = await scout_lines(redis, sports)
    except Exception as exc:                       # 요약이 정찰 때문에 죽지 않는다
        logger.warning("[scout] 요약 줄 생성 실패: %s", exc)
        sl = []
    if sl:
        out += sl
    fl = await freeze_progress_lines(pool, sports)
    if fl:
        out += fl
    out += ["", TICKET_RULE]
    return "\n".join(out)
