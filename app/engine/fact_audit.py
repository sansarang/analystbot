"""[감시 L1] 사실 감시 — 판정이 인용한 수치가 **원문 자료에 실재하는가.**

🔴 **판정을 건드리지 않는다.** 판정 JSON 이 캐시에 저장된 **뒤에** 읽는다.
   결과는 `judgement_audit` 에만 쌓이고 판정·게이트·카드로 되돌아가지 않는다 —
   되먹이는 순간 감시가 아니라 입력이 된다.

⚠️ **오탐이 이 층의 최대 리스크다.** 그래서 추출을 좁게 잡았다:
   · 근거1~3·변수1~2 **텍스트만** 본다. 카드 헤더(p·별점·필요배당)는 모델
     산출물이지 인용이 아니다.
   · **단위가 붙은 수치만** 뽑는다. 맨숫자·날짜·"2경기" 같은 배수·백분율은
     제외한다 — 그것들은 원문에 없어도 정상이다.
   · 판정을 4분류한다:
       verified          원문에 같은 값이 있다
       verified(derived) 평균 등 계산값을 원본 배열에서 재계산해 맞았다
       not_found         원문에 그 단위 수치가 아예 없다 (환각 **후보**, 확정 아님)
       mismatch          같은 단위 수치가 원문에 있는데 값이 다르다  ← 이것만 경보
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

#: 인용 대상 필드. 헤더는 보지 않는다.
CLAIM_FIELDS = ("근거", "변수")

#: 단위 사전 — `(정규식, 단위키, 원문에서 찾을 키들)`.
#  🔴 여기 없는 패턴은 **추출하지 않는다.** 넓히면 오탐이 는다.
UNIT_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (r"(\d+(?:\.\d+)?)\s*이닝", "ip", ("innings", "starter_ip", "이닝")),
    (r"(\d+(?:\.\d+)?)\s*실점", "r", ("r", "starter_r", "opp_runs", "runs_allowed_l3")),
    (r"(\d+(?:\.\d+)?)\s*자책", "er", ("er", "자책")),
    (r"ERA\s*(?:환산\s*)?(?:약\s*)?(\d+(?:\.\d+)?)", "era", ("ERA", "era")),
    (r"WHIP\s*(\d+(?:\.\d+)?)", "whip", ("WHIP", "whip")),
    (r"(?:가중)?OPS\s*(\d+(?:\.\d+)?)", "ops", ("OPS", "가중OPS")),
    (r"(\d+(?:\.\d+)?)\s*득점", "runs", ("runs", "runs_l3", "runs_per_game_l3")),
    (r"(\d+(?:\.\d+)?)\s*안타", "hits", ("hits", "H")),
    (r"(\d+(?:\.\d+)?)\s*홈런", "hr", ("hr", "HR")),
    (r"(\d+(?:\.\d+)?)\s*볼넷", "bb", ("bb", "BB", "四球")),
    (r"(\d+(?:\.\d+)?)\s*삼진", "so", ("k", "K", "SO", "三振")),
)

#: 계산값 표현 — 이 말이 붙으면 원본 배열에서 재계산해 본다.
DERIVED_MARKERS = ("평균", "경기당", "/경기", "환산")


def extract_claims(verdict: dict) -> list[dict]:
    """판정 JSON → [{text, unit, value}]. 단위 없는 수치는 뽑지 않는다."""
    out: list[dict] = []
    for field in CLAIM_FIELDS:
        for line in verdict.get(field) or []:
            s = str(line)
            for pat, unit, _keys in UNIT_PATTERNS:
                for m in re.finditer(pat, s):
                    try:
                        val = float(m.group(1))
                    except (TypeError, ValueError):
                        continue
                    out.append({"text": s[:200], "unit": unit, "value": val,
                                "derived": any(k in s for k in DERIVED_MARKERS)})
    return out


def numbers_in_prompt(prompt: str, unit: str) -> set[float]:
    """프롬프트 원문에서 그 단위에 해당하는 값들을 모은다.

    ⚠️ 원문은 JSON 이 섞인 텍스트다. 키 이름 옆의 숫자와, 사람이 읽는
       표기(`5.13이닝`) 둘 다 잡는다.
    """
    keys = next((k for p, u, k in UNIT_PATTERNS if u == unit), ())
    found: set[float] = set()
    for key in keys:
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*"?(-?\d+(?:\.\d+)?)',
                             prompt):
            try:
                found.add(round(float(m.group(1)), 3))
            except ValueError:
                continue
    for pat, u, _ in UNIT_PATTERNS:
        if u != unit:
            continue
        for m in re.finditer(pat, prompt):
            try:
                found.add(round(float(m.group(1)), 3))
            except ValueError:
                continue
    return found


def classify(claim: dict, prompt: str, tolerance: float) -> tuple[str, dict | None]:
    """한 인용의 판정. 반환 (verified|derived|not_found|mismatch, 상세|None)."""
    pool = numbers_in_prompt(prompt, claim["unit"])
    val = round(float(claim["value"]), 3)
    if not pool:
        return "not_found", None
    if any(abs(val - x) <= 1e-6 for x in pool):
        return "verified", None
    if claim.get("derived"):
        # 평균·경기당 표현은 원본 값들의 산술평균과 맞는지 본다.
        vals = sorted(pool)
        if vals:
            avg = sum(vals) / len(vals)
            if abs(val - avg) <= tolerance:
                return "derived", None
        # 재계산이 안 맞아도 **불일치로 단정하지 않는다** — 어느 부분집합의
        # 평균인지 알 수 없다. 이 층의 목적은 환각 탐지이지 산수 검사가 아니다.
        return "not_found", None
    near = min(pool, key=lambda x: abs(x - val))
    if abs(near - val) <= tolerance:
        return "verified", None
    return "mismatch", {"claim": claim["text"], "unit": claim["unit"],
                        "claimed": val, "nearest_in_source": near}


def audit(verdict: dict, prompt: str, *, tolerance: float | None = None) -> dict:
    """판정 1건 감사. 순수 함수 — I/O 없음."""
    from app.config import get_settings

    tol = tolerance if tolerance is not None else get_settings().fact_audit_tolerance
    out = {"verified_n": 0, "derived_n": 0, "not_found_n": 0,
           "mismatch_n": 0, "mismatch_detail": []}
    for c in extract_claims(verdict):
        kind, detail = classify(c, prompt, tol)
        out[f"{kind}_n"] += 1
        if detail:
            out["mismatch_detail"].append(detail)
    return out


PROMPT_KEY = "judge_prompt:{game_id}"


async def load_prompt(redis, game_id) -> str | None:
    """판정 **시점의** 프롬프트. 재렌더하지 않는다 — 그 사이 재료가 바뀐다."""
    if redis is None:
        return None
    try:
        return await redis.get(PROMPT_KEY.format(game_id=game_id))
    except Exception as exc:
        logger.debug("[fact-audit] 프롬프트 조회 실패 game=%s: %s", game_id, exc)
        return None


async def run(pool, redis, jg: dict) -> dict | None:
    """훅 진입점. **어떤 예외도 밖으로 던지지 않는다** (P4).

    실패는 조용히 삼키지 않는다 — `W-MONITOR-DOWN` 한 줄 + skip 기록.
    """
    from app.config import get_settings

    if not get_settings().fact_audit_enabled:
        return None
    gid = jg.get("game_id")
    try:
        verdict = jg.get("matchup") or {}
        if not verdict.get("근거"):
            return None
        prompt = await load_prompt(redis, gid)
        if not prompt:
            logger.info("[fact-audit] game=%s 프롬프트 원문 없음 — skip", gid)
            return None
        res = audit(verdict, prompt)
        res.update(game_id=gid, sport=jg.get("sport") or "")
        await _store(pool, res)
        logger.info("[fact-audit] game=%s v=%d d=%d nf=%d mismatch=%d",
                    gid, res["verified_n"], res["derived_n"],
                    res["not_found_n"], res["mismatch_n"])
        if res["mismatch_n"]:
            await _alert(res)
        return res
    except Exception as exc:
        logger.warning("[fact-audit] game=%s 감사 실패 — 판정·발송은 계속: %s",
                       gid, exc)
        await _monitor_down("fact_audit", gid, exc)
        return None


async def _store(pool, res: dict) -> None:
    if pool is None:
        return
    try:
        await pool.execute(
            """INSERT INTO judgement_audit
                   (game_id, sport, judged_at, verified_n, derived_n,
                    not_found_n, mismatch_n, mismatch_detail)
               VALUES ($1,$2, now(), $3,$4,$5,$6,$7::jsonb)""",
            int(res["game_id"]), res["sport"], res["verified_n"],
            res["derived_n"], res["not_found_n"], res["mismatch_n"],
            json.dumps(res["mismatch_detail"], ensure_ascii=False))
    except Exception as exc:
        logger.warning("[fact-audit] 저장 실패: %s", exc)


async def _alert(res: dict) -> None:
    """기존 워치독 억제 체계를 **재사용**한다 (P5) — 새로 만들지 않는다."""
    try:
        from app.alerts import watchdog

        first = (res["mismatch_detail"] or [{}])[0]
        await watchdog("W-FACT-MISMATCH",
                       f"{res['mismatch_n']}건 — 예: {first.get('unit')} "
                       f"주장 {first.get('claimed')} vs 원문 "
                       f"{first.get('nearest_in_source')}",
                       target=f"game={res['game_id']}")
    except Exception as exc:
        logger.warning("[fact-audit] 경보 실패: %s", exc)


async def _monitor_down(layer: str, gid, exc: Exception) -> None:
    try:
        from app.alerts import watchdog

        await watchdog("W-MONITOR-DOWN",
                       f"{layer} 실패 — {type(exc).__name__}: {exc}"[:180],
                       target=f"game={gid}")
    except Exception:
        pass
