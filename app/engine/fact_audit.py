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
    # ⚠️ [자료10 2026-09-04] 분위수·최장·회귀 참조 키를 함께 본다. 이 값들이
    #    빠지면 자료10 을 인용한 변수가 통째로 `not_found` 로 찍힌다 —
    #    실측: `"p50": 1.2` 가 프롬프트에 있는데 L1 이 ip 값을 0개로 읽었다.
    (r"(\d+(?:\.\d+)?)\s*이닝", "ip",
     ("innings", "starter_ip", "이닝", "최장", "p25", "p50", "p75",
      "다음등판_평균이닝")),
    (r"(\d+(?:\.\d+)?)\s*실점", "r",
     ("r", "starter_r", "opp_runs", "runs_allowed_l3", "다음등판_평균실점")),
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
#  🔴 [2026-09-03] **합계 표현이 빠져 있었다.** "최근 4경기 27이닝" 의 27 은
#     합계인데, 마커가 없어 `derived=False` 로 분류돼 곧장 근사 비교를 탔고
#     원문의 경기별 이닝(≈8)과 19이닝 차이로 **환각(mismatch)** 이 됐다.
#     판정은 옳았고 감시가 틀렸다 (리허설 실측 2026-09-03, NPB 2건).
DERIVED_MARKERS = ("평균", "경기당", "/경기", "환산", "합계", "총", "도합")

#: "최근 4경기" · "3등판" — 표본 크기를 명시한 표현.
SAMPLE_N_RE = re.compile(r"(\d+)\s*(?:경기|등판)")

#: 주체 귀속 — 이 말이 있으면 그쪽 진영의 배열만 본다.
SUBJECT_WORDS = {"home": ("home", "홈", "홈팀"), "away": ("away", "원정", "원정팀")}


def claim_subject(text: str) -> str | None:
    """이 인용이 누구 것인가. **모르면 None** — 추측해서 재계산하지 않는다."""
    hits = [side for side, words in SUBJECT_WORDS.items()
            if any(w in text for w in words)]
    return hits[0] if len(hits) == 1 else None


def sample_n(text: str) -> int | None:
    """"최근 N경기" 의 N. 여러 개면 **가장 앞의 것** (그 문장의 주 표본)."""
    m = SAMPLE_N_RE.search(text)
    return int(m.group(1)) if m else None


def _region(prompt: str, side: str) -> str:
    """프롬프트에서 그 진영 블록들만 이어 붙인다. 중괄호 균형으로 자른다.

    ⚠️ 원문은 JSON 이 섞인 텍스트다. `"home": {...}` 을 만나면 짝이 맞는
       닫는 괄호까지가 그 진영의 몫이다. 못 자르면 **빈 문자열**을 준다 —
       엉뚱한 범위로 재계산하느니 재계산을 포기한다.
    """
    out = []
    for m in re.finditer(rf'"{side}"\s*:\s*(\{{|\[)', prompt):
        i = m.end() - 1
        depth, opens = 0, {"{": "}", "[": "]"}
        close = opens[prompt[i]]
        for j in range(i, min(len(prompt), i + 20000)):
            if prompt[j] in "{[":
                depth += 1
            elif prompt[j] in "}]":
                depth -= 1
                if depth == 0:
                    out.append(prompt[i:j + 1])
                    break
    return "\n".join(out)


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
                                "derived": any(k in s for k in DERIVED_MARKERS),
                                "subject": claim_subject(s), "n": sample_n(s)})
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
        # ⚠️ 배열 값도 값이다 — `"이닝": [1.0, 2.0, 1.2]` (자료10 이닝 분포).
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*\[([^\]]*)\]', prompt):
            for tok in re.finditer(r"-?\d+(?:\.\d+)?", m.group(1)):
                try:
                    found.add(round(float(tok.group(0)), 3))
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


def values_in(text: str, unit: str) -> list[float]:
    """그 단위의 값들을 **순서·중복 그대로** 모은다.

    🔴 종전 `numbers_in_prompt` 는 `set` 이었다. 합계를 검증하려면 같은 값이
       두 번 나온 것도 두 번 세야 한다 — 집합으로는 합을 복원할 수 없다.
    """
    keys = next((k for p, u, k in UNIT_PATTERNS if u == unit), ())
    found: list[float] = []
    for key in keys:
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*"?(-?\d+(?:\.\d+)?)', text):
            try:
                found.append(round(float(m.group(1)), 3))
            except ValueError:
                continue
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*\[([^\]]*)\]', text):
            for tok in re.finditer(r"-?\d+(?:\.\d+)?", m.group(1)):
                try:
                    found.append(round(float(tok.group(0)), 3))
                except ValueError:
                    continue
    for pat, u, _ in UNIT_PATTERNS:
        if u != unit:
            continue
        for m in re.finditer(pat, text):
            try:
                found.append(round(float(m.group(1)), 3))
            except ValueError:
                continue
    return found


def _recompute_hits(val: float, vals: list[float], n: int | None,
                    tolerance: float) -> bool:
    """합·평균을 **명시된 표본 크기**로 맞춰 본다.

    ⚠️ 순서를 모르므로 앞 N개와 뒤 N개 둘 다 본다. 그래도 안 맞으면
       **포기한다** — 조합을 뒤지면 우연히 맞는 값이 나와 검증이 무의미해진다.
    """
    if not vals:
        return False
    cands = [vals]
    if n and 0 < n <= len(vals):
        cands += [vals[:n], vals[-n:]]
    for c in cands:
        if not c:
            continue
        if abs(val - sum(c)) <= tolerance * len(c):
            return True
        if abs(val - sum(c) / len(c)) <= tolerance:
            return True
    return False


def classify(claim: dict, prompt: str, tolerance: float) -> tuple[str, dict | None]:
    """한 인용의 판정. 반환 (verified|derived|not_found|mismatch, 상세|None).

    🔴 **`mismatch` 의 정의를 좁게 박는다** (2026-09-03):
       *동일 주체·동일 단위·동일 표본*의 값이 원문과 다를 때만 불일치다.
       주체를 모르거나(어느 팀 얘기인지 불명) 재계산이 안 맞으면 **`not_found`**
       다 — "틀렸다"가 아니라 "검증 못 했다"는 뜻이다.
       리허설 실측: 이 구분이 없어 합계 인용 2건이 환각으로 찍혔다.

    ⚠️ 그래서 `not_found` 는 **환각률이 아니라 검증 불가율**이다. 보고서에서
       그렇게 읽어야 한다.
    """
    unit = claim["unit"]
    val = round(float(claim["value"]), 3)
    pool = numbers_in_prompt(prompt, unit)
    if not pool:
        return "not_found", None
    if any(abs(val - x) <= 1e-6 for x in pool):
        return "verified", None

    # 주체가 특정되면 **그 진영의 배열만** 본다.
    # ⚠️ 모호함은 진영이 **둘 다 있을 때만** 생긴다. 원문에 진영 구조가 아예
    #    없으면(단편 자료) 헷갈릴 대상이 없으므로 전체를 쓴다.
    side = claim.get("subject")
    homes, aways = _region(prompt, "home"), _region(prompt, "away")
    structured = bool(homes or aways)
    if side and structured:
        vals = values_in(_region(prompt, side), unit)
    elif not structured:
        vals = values_in(prompt, unit)
    else:
        vals = []                          # 진영은 있는데 어느 쪽인지 모른다

    if claim.get("derived"):
        if vals and _recompute_hits(val, vals, claim.get("n"), tolerance):
            return "derived", None
        # 주체 불명이거나 재계산 실패 → **추측하지 않는다.**
        return "not_found", None

    if not vals:
        # 재계산은 못 해도 **직접 인용**은 전체 풀로 대조할 수 있다.
        # 값 하나를 그대로 적은 것이라 부분집합 모호성이 없다.
        vals = values_in(prompt, unit)
    if not vals:
        return "not_found", None
    near = min(vals, key=lambda x: abs(x - val))
    if abs(near - val) <= tolerance:
        return "verified", None
    # 합계로 읽으면 맞는 경우가 있다 — 마커가 없어도 한 번 봐준다.
    if _recompute_hits(val, vals, claim.get("n"), tolerance):
        return "derived", None
    return "mismatch", {"claim": claim["text"], "unit": unit,
                        "claimed": val, "nearest_in_source": near,
                        "subject": side, "sample_n": claim.get("n")}


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
