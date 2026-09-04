"""[리허설 · KBO] 오늘 저녁 슬레이트 **사전 예측** — 공시 전 시점.

🔴 MLB 리허설과 **시점 규칙이 반대다.**
   MLB 는 이미 끝난 경기라 "지금 긁으면 안 됐다"(컷오프 과거).
   KBO 는 **아직 안 한 경기**라 지금 재료가 곧 그 시점 재료다 —
   수집·시즌 라인·배당 전부 누수가 아니다.

⚠️ 그래서 캐시가 없으면 **격리 안에서 수집한다.** `tools/rehearsal` 의
   `build_analysis` 경로를 쓰되, 접두 키·발송 차단·전량 삭제는 그대로다.
⚠️ 저녁 17:00~ 실슬레이트가 **정본**이다. 이 예측은 참고이고, 클린
   카운터·ledger 에 넣지 않는다.
⚠️ 라인업 미공시면 **잠정 기반**임을 결과에 명시한다 — 그 사실을 숨기면
   저녁에 판정이 움직였을 때 "왜 달라졌나"를 설명할 수 없다.
"""
from __future__ import annotations

import json
import logging
import time

from tools.rehearsal import (
    RehearsalRedis, _cleanup, _install_guards, _remove_guards,
)

logger = logging.getLogger(__name__)
L = logger.info

REPORT: dict = {"games": [], "cost": {"gemini": 0}, "provisional": 0}

#: L2 는 비용 때문에 상위 몇 건만 — 확신 높은 순.
L2_LIMIT = 2


async def run(pool, inner_redis) -> None:
    try:
        await _run(pool, inner_redis)
    except Exception as exc:
        logger.error("[reh-kbo] 실패: %r", exc, exc_info=True)


async def _run(pool, inner_redis) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.pipeline import today_kst

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.hour >= 17:
        L("[reh-kbo] 17:00 이후 — 실슬레이트가 정본이다. 리허설 생략")
        return
    date = today_kst()
    rredis = RehearsalRedis(inner_redis)
    guards = _install_guards()
    L("[reh-kbo] ═══ KBO %s 사전 예측 (공시 전) ═══", date)
    try:
        rows = await pool.fetch(
            """SELECT id, home, away, starts_at, status, lineup_status
                 FROM games WHERE sport='kbo' AND starts_at > now()
                  AND starts_at < now() + interval '18 hours'
                ORDER BY starts_at""")
        L("[reh-kbo] 대상 %d경기", len(rows))
        for r in rows:
            L("[reh-kbo]   game=%s %s @ %s %s status=%s lineup=%s",
              r["id"], r["away"], r["home"], f"{r['starts_at']:%H:%M}Z",
              r["status"], r["lineup_status"])
        if not rows:
            L("[reh-kbo] 오늘 KBO 미시작 경기 0건 — 종료")
            return

        # 캐시가 있으면 재사용, 없으면 **격리 안에서 수집**한다.
        raw = await rredis.get(f"analysis:kbo:{date}")
        if not raw:
            L("[reh-kbo] 격리 캐시 없음 — build_analysis 1회 (수집·판정, 유료 발생)")
            t0 = time.monotonic()
            from app.pipeline import build_analysis

            analysis = await build_analysis(pool, "kbo", date, redis=rredis,
                                            sequential_research=True)
            L("[reh-kbo] build_analysis 완료 %.0f초",
              time.monotonic() - t0)
        else:
            analysis = json.loads(raw)
        games = (analysis or {}).get("games") or []
        L("[reh-kbo] 판정 대상 %d경기", len(games))

        ranked = sorted(
            [g for g in games if (g.get("matchup") or {}).get("p_home") is not None],
            key=lambda g: abs(float(g["matchup"]["p_home"]) - 0.5), reverse=True)
        l2_ids = {g.get("game_id") for g in ranked[:L2_LIMIT]}
        for jg in games:
            await _one(pool, rredis, jg, jg.get("game_id") in l2_ids)
        L("[reh-kbo] 발송 캡처 %d건 (실발송 0)", guards["sent"]["n"])
        _summarise()
    finally:
        _remove_guards(guards)
        left = await _cleanup(inner_redis)
        L("[reh-kbo] ══ 종료 · 격리 잔여 키 %s ══", left)


async def _one(pool, rredis, jg: dict, do_l2: bool) -> None:
    from app.config import get_settings
    from app.engine.deepsearch import _gate_threshold
    from app.engine.market_baseline import SEND, market_line, p_market
    from app.engine.matchup import (
        bullpen_payload, lineup_season_payload, lineups_payload,
    )
    from app.engine.value_gate import required_odds, value

    gid = jg.get("game_id")
    m = jg.get("matchup") or {}
    p = m.get("p_home")
    rec = {"game_id": gid, "away": jg.get("away"), "home": jg.get("home"),
           "p": p, "favored": m.get("우세"), "conf": m.get("확신도")}
    m3 = lineups_payload(jg)
    slots = min(len(((m3.get(s_) or {}).get("타순") or []))
                for s_ in ("home", "away")) if m3 else 0
    rec["slots"] = slots
    rec["provisional"] = slots < 9
    if rec["provisional"]:
        REPORT["provisional"] += 1
    L("[reh-kbo] ── game=%s %s @ %s ──", gid, rec["away"], rec["home"])
    L("[reh-kbo] ① [materials] 자료3=%s(타순 %d명) 자료8=%s 자료9=%s 자료10=%s",
      "Y" if slots >= 9 else "N", slots,
      "Y" if lineup_season_payload(jg) else "N",
      "Y" if bullpen_payload(jg) else "N",
      jg.get("material10_status") or "해당없음")
    if p is None:
        L("[reh-kbo] ② 판정 없음 — 건너뜀")
        REPORT["games"].append(rec)
        return
    L("[reh-kbo] ② p_home=%s 우세=%s 확신도=%s%s", p, rec["favored"],
      rec["conf"], " (잠정 라인업 기반)" if rec["provisional"] else "")
    for i, b in enumerate(m.get("근거") or [], 1):
        L("[reh-kbo]    근거%d %s", i, b)
    from app.engine.variable_parse import check_budget, parse_all

    vrows = parse_all(m)
    rec["var_total"], rec["var_quant"] = len(vrows), sum(
        1 for r in vrows if r["parsed"])
    rec["var_budget"] = check_budget(m, vrows)
    for r in vrows:
        L("[reh-kbo]    변수 %s | 정량=%s", r["raw"][:130], bool(r["parsed"]))

    s = get_settings()
    if rec["favored"] in ("home", "away"):
        ours = float(p) if rec["favored"] == "home" else 1.0 - float(p)
        need = _gate_threshold("kbo", rec["favored"], s)
        rec.update(ours=round(ours, 4), need=need, prob_pass=ours >= need)
        L("[reh-kbo] ③ 확률 %.2f vs 필요 %.2f → %s", ours, need,
          "통과" if ours >= need else "탈락")
        odds = (jg.get("best_odds") or {}).get(
            jg.get("home") if rec["favored"] == "home" else jg.get("away"))
        if odds:
            rec["odds"] = float(odds)
            rec["value"] = round(value(ours, float(odds)), 3)
            L("[reh-kbo] ③ 가치 %.2f (배당 %s)", rec["value"], odds)
        else:
            rec["need_odds"] = round(required_odds(ours), 2)
            L("[reh-kbo] ③ 배당 미부착 — 필요배당 %.2f", rec["need_odds"])

    snap = await p_market(pool, {**jg, "id": gid, "sport": "kbo"}, purpose=SEND)
    rec["p_market"] = snap.get("p")
    rec["market_line"] = market_line(snap.get("p"), p)
    if rec["market_line"]:
        L("[reh-kbo] ④ %s", rec["market_line"])
    else:
        L("[reh-kbo] ④ 시장 줄 없음 (사유=%s)", snap.get("reason"))

    await _monitor(rredis, jg, rec, do_l2)
    REPORT["games"].append(rec)


async def _monitor(rredis, jg: dict, rec: dict, do_l2: bool) -> None:
    from app.engine.fact_audit import PROMPT_KEY, audit
    from app.engine.starter_recent import pitcher_name

    gid = jg.get("game_id")
    prompt = await rredis.get(PROMPT_KEY.format(game_id=gid))
    if not prompt:
        L("[reh-kbo] ⑤ L1 프롬프트 없음 — 대조 불가")
        return
    names = {}
    for side in ("home", "away"):
        nm = pitcher_name(jg, side)
        if nm:
            names[nm] = side
    res = audit(jg.get("matchup") or {}, prompt, names=names or None)
    rec["l1"] = {k: res[k] for k in
                 ("verified_n", "derived_n", "not_found_n", "mismatch_n")}
    L("[reh-kbo] ⑤ L1 v=%s d=%s nf=%s m=%s", res["verified_n"],
      res["derived_n"], res["not_found_n"], res["mismatch_n"])
    for d in (res.get("mismatch_detail") or [])[:5]:
        L("[reh-kbo] ⑤ L1 불일치 %s", json.dumps(d, ensure_ascii=False))
    from app.llm.gemini import is_available

    if not is_available():
        return
    from app.config import get_settings
    from app.engine.matchup import clip_p_home
    from app.engine.shadow_panel import (
        _is_valid, build_independent_prompt, build_reviewer_prompt,
    )
    from app.llm.gemini import generate, parse_json_lenient

    s = get_settings()
    m = jg.get("matchup") or {}
    if do_l2:
        raw = await generate(build_reviewer_prompt(m, prompt),
                             max_tokens=s.shadow_review_max_tokens)
        REPORT["cost"]["gemini"] += 1
        objs = parse_json_lenient(raw)
        objs = objs if isinstance(objs, list) else []
        rec["l2"] = [{"o": o, "valid": _is_valid(o, prompt)} for o in objs[:5]]
        L("[reh-kbo] ⑤ L2 [rehearsal] 이의 %d건", len(objs))
        for o in rec["l2"]:
            L("[reh-kbo] ⑤ L2 valid=%s %s", o["valid"],
              json.dumps(o["o"], ensure_ascii=False))
    raw = await generate(build_independent_prompt(prompt),
                         max_tokens=s.shadow_judge_max_tokens)
    REPORT["cost"]["gemini"] += 1
    d = parse_json_lenient(raw)
    if isinstance(d, dict) and d.get("p_home") is not None and rec.get("p"):
        ps = clip_p_home(float(d["p_home"]))
        rec["l3"] = {"p_shadow": ps, "div": round(abs(float(rec["p"]) - ps), 3)}
        L("[reh-kbo] ⑤ L3 주심=%.2f 독립=%.2f 편차=%.3f",
          float(rec["p"]), ps, rec["l3"]["div"])


def _summarise() -> None:
    g = REPORT["games"]
    L("[reh-kbo] ═══ 요약 %d경기 · 잠정 기반 %d ═══", len(g), REPORT["provisional"])
    L("[reh-kbo] 비용 Gemini %d콜 · 유료 검색 0", REPORT["cost"]["gemini"])
    L("[reh-kbo] REPORT_JSON %s",
      json.dumps(REPORT, ensure_ascii=False, default=str))
