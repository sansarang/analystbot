"""[리허설 · MLB] 오늘 슬레이트를 **"아직 시작 안 했다"는 시점으로** 재현.

🔴 **시점 동결이 이 리허설의 성패다.** 경기가 이미 진행·종료됐으므로, 지금
   무엇이든 다시 긁으면 경기 중·후 데이터가 섞인다. 그러면 "잘 맞혔다"가
   전부 거짓이 된다 (STL 1.02 라이브 배당 사고의 재발이다).

   경기별 컷오프 = **그 경기 `starts_at`**. 규칙 셋:
     · 재료: 오늘 아침 판정에 **실제 쓰인 캐시를 재사용**한다. 재수집 금지.
     · 배당: `captured_at < starts_at` 마지막 행만 (`p_market(purpose=CLOSE)`
       가 이미 그 조건으로 조회한다 — 새로 짜지 않고 그걸 쓴다).
     · 시즌 라인: **붙이지 않는다.** 시즌 값은 언제나 "지금" 값이라 끝난
       경기가 자기 시즌 라인에 들어간다 (CLAUDE.md 판정 철학의 replay 규칙).

⚠️ 격리는 `tools/rehearsal` 의 것을 그대로 쓴다 — 접두 키·발송 2중 차단·
   ledger/audit 미기록·종료 시 전량 삭제. 두 벌 만들면 한 벌이 샌다.
"""
from __future__ import annotations

import json
import logging
import time

from tools.rehearsal import (
    PREFIX, RehearsalRedis, _cleanup, _install_guards, _remove_guards,
)

logger = logging.getLogger(__name__)
L = logger.info

#: 이 리허설의 산출물. 실 테이블에 쓰지 않는다.
REPORT: dict = {"games": [], "cost": {"judge": 0, "gemini": 0}}


def _aw(v):
    from app.engine.starter_recent import _aware

    return _aware(v)


async def run(pool, inner_redis) -> None:
    try:
        await _run(pool, inner_redis)
    except Exception as exc:
        logger.error("[reh-mlb] 실패: %r", exc, exc_info=True)


async def _run(pool, inner_redis) -> None:
    from app.pipeline import mlb_slate_date

    date = mlb_slate_date()
    rredis = RehearsalRedis(inner_redis)
    guards = _install_guards()
    L("[reh-mlb] ═══ MLB %s 시점 동결 재현 ═══", date)
    try:
        raw = await inner_redis.get(f"analysis:mlb:{date}")   # 실캐시 **읽기만**
        if not raw:
            L("[reh-mlb] 🔴 실분석 캐시 없음 — 재현 불가")
            return
        games = (json.loads(raw) or {}).get("games") or []
        L("[reh-mlb] 실캐시 %d경기 (재수집 없음 — 아침 판정이 쓴 재료 그대로)",
          len(games))
        rows = {r["id"]: r for r in await pool.fetch(
            """SELECT id, home, away, starts_at, status, home_score, away_score
                 FROM games WHERE sport='mlb'
                  AND (starts_at AT TIME ZONE 'America/New_York')::date = $1""",
            __import__("datetime").date.fromisoformat(date))}
        for jg in games:
            await _one(pool, rredis, jg, rows.get(jg.get("game_id")), date)
        L("[reh-mlb] 발송 캡처 %d건 (실발송 0)", guards["sent"]["n"])
        _summarise()
    finally:
        _remove_guards(guards)
        left = await _cleanup(inner_redis)
        L("[reh-mlb] ══ 종료 · 격리 잔여 키 %s ══", left)


async def _one(pool, rredis, jg: dict, row, date: str) -> None:
    gid = jg.get("game_id")
    if row is None:
        L("[reh-mlb] game=%s DB 행 없음 — 건너뜀", gid)
        return
    cutoff = _aw(row["starts_at"])
    rec = {"game_id": gid, "away": row["away"], "home": row["home"],
           "cutoff": str(cutoff), "violations": []}
    L("[reh-mlb] ── game=%s %s @ %s · 컷오프 %s ──",
      gid, row["away"], row["home"], cutoff)

    # ① 재료 — 캐시 그대로. 최신 시각을 증명한다.
    newest = _materials_age(jg)
    rec["materials_newest"] = str(newest) if newest else None
    if newest and cutoff and newest >= cutoff:
        rec["violations"].append(f"재료 최신 {newest} ≥ 컷오프")
    L("[reh-mlb] ① 재료 최신 시각=%s (컷오프 이전이어야 한다)", newest)

    # 자료10 — `pitcher_appearances` 는 `g.starts_at < before` 로 이미 컷오프
    #   조건을 만족한다. **시즌 라인(자료7·8)은 붙이지 않는다**(replay 규칙).
    sim = {**jg, "starts_at": cutoff}
    try:
        from app.engine.variable_ref import attach_material10

        st = await attach_material10(pool, rredis, sim)
    except Exception as exc:
        st = f"실패({exc!r})"
    rec["m10"] = st
    from app.engine.matchup import (
        bullpen_payload, lineup_season_payload, material10_payload,
    )
    L("[reh-mlb] ① [materials] 자료8=%s 자료9=%s 자료10=%s",
      "Y" if lineup_season_payload(sim) else "N",
      "Y" if bullpen_payload(sim) else "N", st)

    # ② 판정 — 격리 키로 재실행
    t0 = time.monotonic()
    try:
        from app.engine.matchup import judge_matchup

        await judge_matchup(sim, rredis, date)
        REPORT["cost"]["judge"] += 1
    except Exception as exc:
        L("[reh-mlb] ② 판정 실패 game=%s: %r", gid, exc)
    m = sim.get("matchup") or {}
    rec.update(p=m.get("p_home"), favored=m.get("우세"), conf=m.get("확신도"))
    L("[reh-mlb] ② p_home=%s 우세=%s 확신도=%s (%.0f초)",
      rec["p"], rec["favored"], rec["conf"], time.monotonic() - t0)
    for i, b in enumerate(m.get("근거") or [], 1):
        L("[reh-mlb]    근거%d %s", i, b)
    from app.engine.variable_parse import check_budget, parse_all

    vrows = parse_all(m)
    rec["var_total"] = len(vrows)
    rec["var_quant"] = sum(1 for r in vrows if r["parsed"])
    rec["var_budget"] = check_budget(m, vrows)
    for r in vrows:
        L("[reh-mlb]    변수 %s | 정량=%s", r["raw"][:120], bool(r["parsed"]))

    # ③ 게이트 — 컷오프 이전 배당으로
    from app.config import get_settings
    from app.engine.deepsearch import _gate_threshold

    if rec["p"] is not None and rec["favored"] in ("home", "away"):
        ours = (float(rec["p"]) if rec["favored"] == "home"
                else 1.0 - float(rec["p"]))
        need = _gate_threshold("mlb", rec["favored"], get_settings())
        rec.update(ours=round(ours, 4), need=need, prob_pass=ours >= need)
        L("[reh-mlb] ③ 확률 %.2f vs 필요 %.2f → %s · 확신도 %s",
          ours, need, "통과" if ours >= need else "탈락", rec["conf"])

    # ④ 시장 기준선 — **CLOSE** 가 곧 컷오프 조건이다
    from app.engine.market_baseline import CLOSE, market_line, p_market

    snap = await p_market(pool, {"id": gid, "sport": "mlb", "home": row["home"],
                                 "away": row["away"], "starts_at": cutoff},
                          purpose=CLOSE)
    rec["p_market"] = snap.get("p")
    rec["market_reason"] = snap.get("reason")
    line = market_line(snap.get("p"), rec.get("p"))
    rec["market_line"] = line
    L("[reh-mlb] ④ 시장 %s (provider=%s, 사유=%s)", snap.get("p"),
      snap.get("provider"), snap.get("reason"))
    if line:
        L("[reh-mlb] ④ 카드 줄: %s", line)

    # ⑤ 감시 3층
    await _monitor(pool, rredis, sim, rec)

    # 보너스 — 종료 경기면 즉석 채점
    if row["status"] == "final" and row["home_score"] is not None:
        h, a = int(row["home_score"]), int(row["away_score"])
        winner = "home" if h > a else "away" if a > h else "draw"
        rec.update(actual=f"{a}-{h}", winner=winner)
        if rec["favored"] in ("home", "away") and winner != "draw":
            rec["our_hit"] = rec["favored"] == winner
        mf = (None if snap.get("p") is None
              else ("home" if snap["p"] > 0.5 else "away"))
        if mf and winner != "draw":
            rec["market_hit"] = mf == winner
        L("[reh-mlb] 🎯 실결과 %s (%s 승) · 우리=%s 시장=%s",
          rec["actual"], winner, rec.get("our_hit"), rec.get("market_hit"))
    REPORT["games"].append(rec)


def _materials_age(jg: dict):
    """재료에 박힌 가장 최신 시각. 컷오프 위반을 증명하는 값이다."""
    r = jg.get("research") or {}
    best = None
    for side in ("home", "away"):
        for g in ((r.get(f"{side}_usage") or {}).get("games") or []):
            d = _aw(g.get("date"))
            if d and (best is None or d > best):
                best = d
        for s in (r.get(f"{side}_starter_recent") or []):
            d = _aw(s.get("date"))
            if d and (best is None or d > best):
                best = d
    return best


async def _monitor(pool, rredis, jg: dict, rec: dict) -> None:
    from app.engine.fact_audit import PROMPT_KEY, audit

    gid = jg.get("game_id")
    prompt = await rredis.get(PROMPT_KEY.format(game_id=gid))
    if not prompt:
        L("[reh-mlb] ⑤ L1 프롬프트 없음 — 대조 불가")
        return
    from app.engine.starter_recent import pitcher_name

    names = {}
    for side in ("home", "away"):
        nm = pitcher_name(jg, side)
        if nm:
            names[nm] = side
    res = audit(jg.get("matchup") or {}, prompt, names=names or None)
    rec["l1"] = {k: res[k] for k in
                 ("verified_n", "derived_n", "not_found_n", "mismatch_n")}
    L("[reh-mlb] ⑤ L1 v=%s d=%s nf=%s m=%s",
      res["verified_n"], res["derived_n"], res["not_found_n"], res["mismatch_n"])
    for d in (res.get("mismatch_detail") or [])[:5]:
        L("[reh-mlb] ⑤ L1 불일치 %s", json.dumps(d, ensure_ascii=False))
    from app.llm.gemini import is_available

    if not is_available():
        L("[reh-mlb] ⑤ L2·L3 휴면")
        return
    from app.config import get_settings
    from app.engine.matchup import clip_p_home
    from app.engine.shadow_panel import (
        _is_valid, build_independent_prompt, build_reviewer_prompt,
    )
    from app.llm.gemini import generate, parse_json_lenient

    s = get_settings()
    m = jg.get("matchup") or {}
    raw = await generate(build_reviewer_prompt(m, prompt),
                         max_tokens=s.shadow_review_max_tokens)
    REPORT["cost"]["gemini"] += 1
    objs = parse_json_lenient(raw)
    objs = objs if isinstance(objs, list) else []
    rec["l2"] = [{"o": o, "valid": _is_valid(o, prompt)} for o in objs[:5]]
    L("[reh-mlb] ⑤ L2 이의 %d건", len(objs))
    for o in rec["l2"]:
        L("[reh-mlb] ⑤ L2 valid=%s %s", o["valid"],
          json.dumps(o["o"], ensure_ascii=False))
    raw = await generate(build_independent_prompt(prompt),
                         max_tokens=s.shadow_judge_max_tokens)
    REPORT["cost"]["gemini"] += 1
    d = parse_json_lenient(raw)
    if isinstance(d, dict) and d.get("p_home") is not None and rec.get("p"):
        ps = clip_p_home(float(d["p_home"]))
        rec["l3"] = {"p_shadow": ps,
                     "div": round(abs(float(rec["p"]) - ps), 3)}
        L("[reh-mlb] ⑤ L3 주심=%.2f 독립=%.2f 편차=%.3f (임계 %.2f)",
          float(rec["p"]), ps, rec["l3"]["div"], s.shadow_diverge_pp)


def _summarise() -> None:
    g = REPORT["games"]
    L("[reh-mlb] ═══ 요약 %d경기 ═══", len(g))
    ok = [x for x in g if not x["violations"]]
    L("[reh-mlb] 컷오프 준수 %d/%d", len(ok), len(g))
    scored = [x for x in g if "our_hit" in x]
    if scored:
        ours = sum(1 for x in scored if x["our_hit"])
        mkt = [x for x in scored if x.get("market_hit") is not None]
        mh = sum(1 for x in mkt if x["market_hit"])
        L("[reh-mlb] 🎯 즉석 채점 우리 %d/%d · 시장 %d/%d "
          "(⚠️ 1일치 표본 — 클린 카운터에 넣지 않는다)",
          ours, len(scored), mh, len(mkt))
    L("[reh-mlb] 비용 판정 %d콜 · Gemini %d콜 · 유료 검색 0",
      REPORT["cost"]["judge"], REPORT["cost"]["gemini"])
    L("[reh-mlb] REPORT_JSON %s", json.dumps(REPORT, ensure_ascii=False,
                                             default=str))
