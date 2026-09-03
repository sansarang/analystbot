"""[1회성 실전 검증] MLB 1경기에 감시 3층을 직접 돌려 전 구간을 실측한다.

🔴 **섀도다.** 판정을 다시 돌리지 않고, 카드를 만들지 않고, 게이트를
   바꾸지 않는다. 읽고 · L1 대조하고 · L2·L3 를 부르고 · 로그로 낸다.

⚠️ L2 대상 선정에 **1회 예외**를 둔다(사용자 지시). 이 경기는 게이트
   통과가 아니어도 검사역을 붙인다 — 로그에 `[test]` 로 표기한다.
   정규 경로(`run_panel`)의 선정 규칙은 건드리지 않는다.

실행: 서버에서 스케줄러 기동 시 1회. 로컬은 운영 DB·Redis 에 닿지 않는다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)
L = logger.info


async def run(pool, redis) -> None:
    try:
        await _run(pool, redis)
    except Exception as exc:
        logger.error("[probe] 실패: %r", exc)


async def _run(pool, redis) -> None:
    from app.pipeline import mlb_slate_date

    date = mlb_slate_date()
    L("[probe] ═══ MLB 감시 3층 실전 검증 · 슬레이트 %s ═══", date)

    rows = await pool.fetch(
        """SELECT id, home, away, starts_at, lineup_status, status,
                  home_pitcher, away_pitcher
             FROM games WHERE sport='mlb' AND status='scheduled'
              AND starts_at > now() - interval '30 minutes'
            ORDER BY starts_at""")
    if not rows:
        rows = await pool.fetch(
            """SELECT id, home, away, starts_at, lineup_status, status,
                      home_pitcher, away_pitcher
                 FROM games WHERE sport='mlb'
                ORDER BY starts_at DESC LIMIT 3""")
        L("[probe] ⚠️ 미시작 경기 없음 — 가장 늦게 시작한 경기로 대체한다")
    for r in rows:
        L("[probe] 후보 game=%s %s @ %s start=%s(UTC) lineup=%s status=%s",
          r["id"], r["away"], r["home"], r["starts_at"], r["lineup_status"],
          r["status"])
    if not rows:
        L("[probe] 🔴 MLB 경기가 하나도 없다 — 중단")
        return
    g = rows[0]
    gid = int(g["id"])
    L("[probe] ▶ 대상 확정: game=%s %s @ %s", gid, g["away"], g["home"])

    # ── ① 판정·게이트 (pick_ledger 가 원본) ─────────────────────
    led = await pool.fetch(
        """SELECT p_home, favored, gate_result, lineup_status, is_final,
                  market_prob, divergence_pp, edge_status, judged_at
             FROM pick_ledger WHERE game_id=$1 ORDER BY judged_at""", gid)
    for r in led:
        L("[probe] ① 판정 p_home=%s 우세=%s 게이트=%s 라인업=%s final=%s "
          "시장=%s 괴리=%s 엣지=%s at=%s", r["p_home"], r["favored"],
          r["gate_result"], r["lineup_status"], r["is_final"],
          r["market_prob"], r["divergence_pp"], r["edge_status"],
          r["judged_at"])
    if not led:
        L("[probe] ① ⚠️ pick_ledger 행 없음 — 판정 미기록")

    # ── ② 배당 ────────────────────────────────────────────────
    od = await pool.fetch(
        """SELECT provider, book, market, side, odds, captured_at,
                  round(extract(epoch FROM now() - captured_at) / 60) AS age_min
             FROM odds_snapshots WHERE game_id=$1 AND market='h2h'
            ORDER BY captured_at DESC LIMIT 6""", gid)
    for r in od:
        L("[probe] ② 배당 provider=%s book=%s %s=%s at=%s (%s분 전)",
          r["provider"], r["book"], r["side"], r["odds"], r["captured_at"],
          r["age_min"])
    if not od:
        L("[probe] ② ⚠️ 배당 스냅샷 없음")

    # ── ③ 분석 캐시에서 이 경기 꺼내기 ─────────────────────────
    raw = await redis.get(f"analysis:mlb:{date}")
    jg = None
    if raw:
        for x in (json.loads(raw) or {}).get("games") or []:
            if str(x.get("game_id")) == str(gid):
                jg = x
                break
    if jg is None:
        L("[probe] 🔴 분석 캐시에 game=%s 없음 — L2·L3 불가", gid)
        return
    m = jg.get("matchup") or {}
    L("[probe] ③ 캐시 판정 p_home=%s 우세=%s 확신도=%s 게이트=%s",
      m.get("p_home"), m.get("우세"), m.get("확신도"), jg.get("gate_result"))
    for i, b in enumerate(m.get("근거") or [], 1):
        L("[probe] ③ 근거%d: %s", i, b)
    for i, b in enumerate(m.get("변수") or [], 1):
        L("[probe] ③ 변수%d: %s", i, b)

    # ── ④ L1 사실 감시 ────────────────────────────────────────
    from app.engine.fact_audit import PROMPT_KEY, audit
    import hashlib

    prompt = await redis.get(PROMPT_KEY.format(game_id=gid))
    if not prompt:
        L("[probe] ④ L1 🔴 판정 프롬프트 원문이 없다 — 이 판정은 감시 코드 "
          "배포 **이전**에 내려졌다. L1 은 이 경기를 대조할 수 없다(미완).")
    else:
        sha = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        L("[probe] ④ L1 프롬프트 %d자 sha=%s", len(prompt), sha)
        res = audit(m, prompt)
        L("[probe] ④ L1 결과 verified=%s derived=%s not_found=%s mismatch=%s",
          res.get("verified_n"), res.get("derived_n"),
          res.get("not_found_n"), res.get("mismatch_n"))
        for d in (res.get("mismatch_detail") or [])[:20]:
            L("[probe] ④ L1 상세: %s", json.dumps(d, ensure_ascii=False))
    arow = await pool.fetch(
        "SELECT * FROM judgement_audit WHERE game_id=$1 ORDER BY id", gid)
    L("[probe] ④ judgement_audit 저장행 %d건", len(arow))

    # ── ⑤ L2·L3 — 이 1건은 게이트 무관하게 붙인다([test] 예외) ──
    from app.engine.shadow_panel import _review_one, _shadow_one
    from app.llm.gemini import is_available, model_name

    L("[probe] ⑤ gemini available=%s model=%s", is_available(), model_name())
    if not prompt:
        L("[probe] ⑤ L2·L3 🔴 자료 원문이 없어 부를 수 없다(미완) — "
          "감시 배포 이후 판정부터 가능하다")
    elif is_available():
        L("[probe] ⑤ [test] 대상 선정 예외 1건 — 게이트=%s 이지만 붙인다",
          jg.get("gate_result"))
        try:
            n = await _review_one(pool, redis, jg)
            L("[probe] ⑤ L2 검사역 반환=%s", n)
        except Exception as exc:
            L("[probe] ⑤ L2 실패: %r", exc)
        try:
            n = await _shadow_one(pool, redis, jg)
            L("[probe] ⑤ L3 독립판정 반환=%s", n)
        except Exception as exc:
            L("[probe] ⑤ L3 실패: %r", exc)
        for r in await pool.fetch(
                "SELECT * FROM judge_review WHERE game_id=$1 ORDER BY id", gid):
            L("[probe] ⑤ judge_review 이의=%s 유효=%s 내용=%s",
              r["objection_n"], r["valid_n"], r["objections"])
        for r in await pool.fetch(
                "SELECT * FROM shadow_panel WHERE game_id=$1 ORDER BY id", gid):
            L("[probe] ⑤ shadow_panel 주심=%s 독립=%s 편차=%s",
              r["p_main"], r["p_shadow"], r["divergence"])

    # ── ⑥ 비용 ────────────────────────────────────────────────
    from app.config import get_settings
    from app.engine.deepsearch import PAID_KEY
    from app.utils.timez import today_kst

    paid = await redis.get(PAID_KEY.format(date=today_kst()))
    L("[probe] ⑥ 유료 web_search %s콜 (cap=%s) · The Odds API 미사용(provider=%s)",
      paid or 0, get_settings().deepsearch_paid_cap,
      get_settings().odds_provider)
    L("[probe] ═══ 검증 종료 ═══")
