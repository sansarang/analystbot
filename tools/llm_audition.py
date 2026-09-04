"""[오디션] 무료 LLM 판정 후보 실측 — 기준 5종 채점.

🔴 **Anthropic 을 쓰지 않는다.** 프롬프트는 순수 함수로 렌더하고(무료),
   기준값은 어제 리허설이 남긴 소네트 판정 p 다. 크레딧 0으로 돈다.

⚠️ 격리: 판정 결과를 캐시·ledger 에 **쓰지 않는다.** 보고서 파일과 로그뿐.
⚠️ 배선 전환은 **이 결과를 보고 승인받은 뒤** 별도 사이클이다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)
L = logger.info

#: 어제 MLB 리허설(소네트)의 기준 p — `docs/REHEARSAL_MLB_2026-09-04.md`.
BASELINE = {2559: 0.47, 2560: 0.37, 2561: 0.52, 2562: 0.56, 2563: 0.61,
            2564: 0.62}

#: 후보. **모델 ID 는 각 provider `/models` 실조회로 확인한 것만 쓴다.**
#  ⚠️ 지시서의 `GLM-5.2` 는 NVIDIA 목록에 **없어** 제외했다.
#  ⚠️ Mistral 은 `mistral-large` 가 없어 최상위 `mistral-medium-latest` 로 대체.
CANDIDATES = [
    ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra"),
    ("nvidia", "deepseek-ai/deepseek-v4-pro-0813", "DeepSeek V4 Pro (GLM 대체)"),
    ("mistral", "mistral-medium-latest", "Mistral Medium 3.5 (large 부재)"),
    ("openrouter", "deepseek/deepseek-r1", "DeepSeek R1 (맛보기)"),
]


async def run(pool, inner_redis) -> None:
    try:
        await _run(pool, inner_redis)
    except Exception as exc:
        logger.error("[audition] 실패: %r", exc, exc_info=True)


async def _run(pool, inner_redis) -> None:
    from app.engine.matchup import (
        boxscore_payload, news_payload, prev_verdict, render_matchup_prompt,
    )
    from app.pipeline import mlb_slate_date

    date = mlb_slate_date()
    raw = await inner_redis.get(f"analysis:mlb:{date}")
    if not raw:
        L("[audition] 🔴 MLB 캐시 없음 — 오디션 불가")
        return
    games = [g for g in (json.loads(raw) or {}).get("games") or []
             if g.get("game_id") in BASELINE]
    L("[audition] ═══ 후보 %d · 경기 %d ═══", len(CANDIDATES), len(games))

    prompts = {}
    for jg in games:
        try:
            # ⚠️ 뉴스는 팀 평가서에서 오는데, 그건 Anthropic 호출이 필요하다.
            #    오디션은 크레딧 0으로 돌아야 하므로 **뉴스 없이** 렌더한다 —
            #    소네트 기준값도 뉴스가 있었으므로 이 차이를 보고서에 적는다.
            prompts[jg["game_id"]] = render_matchup_prompt(
                jg, boxscore_payload(jg), {}, prev_verdict(jg))
        except Exception as exc:
            L("[audition] game=%s 프롬프트 렌더 실패: %r", jg.get("game_id"), exc)
    L("[audition] 프롬프트 렌더 %d건 (Anthropic 0콜)", len(prompts))

    report = {"date": date, "candidates": []}
    for provider, model, label in CANDIDATES:
        report["candidates"].append(
            await _audition_one(provider, model, label, prompts))
    L("[audition] REPORT_JSON %s",
      json.dumps(report, ensure_ascii=False, default=str))


async def _audition_one(provider: str, model: str, label: str,
                        prompts: dict) -> dict:
    from app.llm.openai_compat import available, complete

    out = {"provider": provider, "model": model, "label": label,
           "games": [], "calls": 0}
    if not available(provider):
        out["skipped"] = f"{provider} 키 없음"
        L("[audition] %s 건너뜀 — 키 없음", label)
        return out
    L("[audition] ── %s (%s) ──", label, model)
    for gid, prompt in prompts.items():
        r = await complete(provider, model, prompt)
        out["calls"] += 1
        rec = {"game_id": gid, "ok": r["ok"], "status": r["status"],
               "elapsed": r["elapsed"], "retries": r["retries"],
               "error": r["error"], "usage": r.get("usage")}
        if r["ok"]:
            rec.update(_score(r["text"], gid))
        out["games"].append(rec)
        L("[audition] %s game=%s ok=%s %.1fs p=%s json=%s 정량=%s%s",
          label, gid, r["ok"], r["elapsed"], rec.get("p"),
          rec.get("json_ok"), rec.get("var_quant"),
          f" err={r['error'][:80]}" if r["error"] else "")
        for i, b in enumerate(rec.get("reasons") or [], 1):
            L("[audition]    근거%d %s", i, b)
    _tally(out)
    return out


def _score(text: str, gid: int) -> dict:
    """기준 ①~④ 채점. 관대 파싱 **1회**만 — 내용은 고치지 않는다."""
    from app.engine.matchup import clip_p_home
    from app.engine.variable_parse import parse_all
    from app.llm.gemini import parse_json_lenient

    rec = {"json_ok": False, "p": None, "dev": None,
           "reasons": [], "var_total": 0, "var_quant": 0}
    d = parse_json_lenient(text)
    if not isinstance(d, dict):
        return rec
    rec["json_ok"] = True
    p = d.get("p_home")
    if isinstance(p, (int, float)):
        rec["p"] = clip_p_home(float(p))
        rec["dev"] = round(abs(rec["p"] - BASELINE[gid]), 3)
    rec["reasons"] = [str(x) for x in (d.get("근거") or [])][:3]
    rows = parse_all(d)
    rec["var_total"] = len(rows)
    rec["var_quant"] = sum(1 for r in rows if r["parsed"])
    return rec


def _tally(out: dict) -> None:
    g = out["games"]
    okj = [x for x in g if x.get("json_ok")]
    devs = [x["dev"] for x in g if x.get("dev") is not None]
    vt = sum(x.get("var_total", 0) for x in g)
    vq = sum(x.get("var_quant", 0) for x in g)
    out["summary"] = {
        "json_ok": f"{len(okj)}/{len(g)}",
        "dev_avg": round(sum(devs) / len(devs), 3) if devs else None,
        "dev_max": max(devs) if devs else None,
        "var_rate": round(vq / vt, 2) if vt else None,
        "elapsed_avg": round(sum(x["elapsed"] for x in g) / len(g), 1) if g else None,
        "errors": sum(1 for x in g if x.get("error")),
        "retries": sum(x.get("retries", 0) for x in g),
    }
    L("[audition] %s 요약 %s", out["label"], out["summary"])
