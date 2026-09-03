"""[감시 L2·L3] 검사역과 독립 판정 — **발송이 끝난 뒤** 도는 그림자 패널.

L2 검사역   주심 판정 + 자료를 주고 **결함을 찾게** 한다 (동의를 구하지 않는다)
L3 독립 판정 **자료만** 주고 스스로 p_home 을 내게 한다 (주심 판정은 안 보여준다)

🔴 **판정·게이트·카드에 되먹이지 않는다.** 결과는 `judge_review`·`shadow_panel`
   테이블에만 쌓인다. 카드 표기는 v1.4 승격 때다.
🔴 **L3 프롬프트에 주심 판정을 넣지 않는다.** 넣는 순간 독립 판정이 아니라
   추인이 된다. 그래서 조립 함수를 L2 와 **분리**했다 — 같은 함수에 플래그로
   분기하면 언젠가 그 분기가 잘못 탄다.
⚠️ 실행은 **발송 완료 후**다. T-차감 시간에 LLM 왕복을 넣지 않는다.
⚠️ Gemini 키가 없으면 전체 휴면. 조용히 꺼지지 않고 로그 한 줄을 남긴다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────── 프롬프트 ───────────────────────────

REVIEWER_PROMPT = """당신은 이 야구 판정의 **검사역**이다.

동의하려 하지 마라. 결함을 찾는 것이 당신의 일이다. 아래 네 가지만 본다:
① 근거가 제공된 원문 자료와 **모순**된다
② 반대 방향을 가리키는 증거를 **무시**했다
③ 표본 크기에 비해 **과신**한다
④ 근거들끼리 **자기모순**이다

[판정 전문]
{verdict}

[그 판정이 받은 자료 1~9 원문]
{materials}

[규칙]
- **새 사실을 지어내지 마라.** 제공된 자료 안에서만 논증한다.
- 이의마다 어느 자료를 인용했는지 밝힌다.
- 유효한 이의가 없으면 **빈 배열 `[]` 만** 출력한다. 억지로 만들지 마라.

[출력] JSON 배열만. 다른 텍스트·백틱 금지.
[{{"유형": "모순|무시|과신|자기모순", "자료": "자료N", "설명": "한 줄"}}]
"""

INDEPENDENT_PROMPT = """당신은 야구 매치업 판정가다. 홈팀이 이길 확률을 산출한다.

[자료]
{materials}

[규칙]
- 근거는 위 자료 안에서만 찾는다. 배당·팀 명성·사전 지식은 쓰지 않는다.
- 3경기는 작은 표본이다. 상대 수준을 감안하고 단정하지 마라.
- 자료가 팽팽하면 억지로 차이를 만들지 말고 0.50 부근으로 낸다.

[출력] JSON 만. 다른 텍스트·백틱 금지.
{{"p_home": 0.00, "한줄근거": "..."}}
"""


def _cfg():
    from app.config import get_settings

    return get_settings()


def build_reviewer_prompt(verdict: dict, materials: str) -> str:
    """L2 전용. 주심 판정을 **넣는다** — 검사 대상이기 때문이다."""
    return REVIEWER_PROMPT.format(
        verdict=json.dumps({k: verdict.get(k) for k in
                            ("p_home", "우세", "근거", "변수", "확신도")},
                           ensure_ascii=False),
        materials=materials)


def build_independent_prompt(materials: str) -> str:
    """L3 전용. **주심 판정을 받지 않는다** — 인자에 아예 없다.

    🔴 이 함수는 `verdict` 를 매개변수로 갖지 않는다. 플래그 분기가 아니라
       **시그니처로** 오염을 막는다. 실수로 넘길 방법이 없다.
    """
    return INDEPENDENT_PROMPT.format(materials=materials)


# ─────────────────────────── 대상 선정 ───────────────────────────

def pick_targets(games: list[dict], *, limit: int | None = None) -> list[dict]:
    """게이트 통과 판정만, 슬레이트당 상한까지. **확신 높은 순**으로 자른다.

    ⚠️ 상한은 config 에서 읽는다(사본 금지).
    """
    from app.config import get_settings

    cap = limit if limit is not None else int(get_settings().shadow_max_per_slate)
    from app.engine.pick_ledger import GATE_EDGE, GATE_RECOMMENDED

    ok = [g for g in games
          if (g.get("gate_result") in (GATE_EDGE, GATE_RECOMMENDED))
          and (g.get("matchup") or {}).get("p_home") is not None]

    def confidence(g):
        m = g.get("matchup") or {}
        p = float(m.get("p_home"))
        return abs(p - 0.5)          # 0.5 에서 멀수록 확신이 높다

    ok.sort(key=confidence, reverse=True)
    return ok[:cap]


# ─────────────────────────── 실행 ───────────────────────────

async def run_panel(pool, redis, games: list[dict]) -> dict:
    """발송 후 호출. **어떤 예외도 밖으로 던지지 않는다** (P4)."""
    from app.llm.gemini import is_available

    out = {"targets": 0, "reviewed": 0, "shadowed": 0, "skipped": 0}
    if not is_available():
        logger.info("[shadow] gemini 미설정 — L2·L3 휴면")
        return out
    try:
        targets = pick_targets(games)
        out["targets"] = len(targets)
        logger.info("[shadow] 대상 %d경기 (게이트 통과·확신 높은 순)", len(targets))
        for jg in targets:
            try:
                out["reviewed"] += await _review_one(pool, redis, jg)
                out["shadowed"] += await _shadow_one(pool, redis, jg)
            except Exception as exc:
                out["skipped"] += 1
                logger.warning("[shadow] game=%s skip: %s", jg.get("game_id"), exc)
    except Exception as exc:
        logger.warning("[shadow] 패널 실패 — 판정·발송과 무관: %s", exc)
        await _monitor_down(exc)
    return out


async def _materials(redis, jg) -> str | None:
    from app.engine.fact_audit import load_prompt

    return await load_prompt(redis, jg.get("game_id"))


async def _review_one(pool, redis, jg: dict) -> int:
    """L2 — 검사역."""
    from app.llm.gemini import generate, parse_json_lenient

    mats = await _materials(redis, jg)
    if not mats:
        return 0
    raw = await generate(build_reviewer_prompt(jg.get("matchup") or {}, mats),
                         max_tokens=_cfg().shadow_review_max_tokens)
    objections = parse_json_lenient(raw)
    if objections is None:
        logger.info("[shadow] game=%s L2 파싱 실패 — skip", jg.get("game_id"))
        return 0
    if not isinstance(objections, list):
        return 0
    valid = sum(1 for o in objections if _is_valid(o, mats) is True)
    await _store_review(pool, jg, objections, valid)
    if objections:
        await _alert("W-JUDGE-OBJECTION", jg,
                     f"이의 {len(objections)}건 (기계 대조 유효 {valid})")
    return 1


def _is_valid(objection: dict, materials: str) -> bool | None:
    """이의가 **기계 대조 가능하고 실제로 모순**일 때만 True.

    · 이의 설명에서 단위 붙은 수치를 뽑아 원문과 대조한다(L1 의 규칙 재사용).
    · 수치가 원문과 **다르면** 이의가 맞다 → True
    · 수치가 원문과 **같으면** 이의가 틀렸다 → False
    · 뽑을 수치가 없거나 인용 위치를 못 찾으면 **None** —
      "틀렸다"가 아니라 **"사람이 봐야 한다"** 다. 기계가 단정하지 않는다.
    """
    from app.config import get_settings
    from app.engine.fact_audit import classify, extract_claims

    if not isinstance(objection, dict):
        return None
    if not str(objection.get("자료") or ""):
        return None                  # 어느 자료를 인용했는지 안 밝혔다
    claims = extract_claims({"근거": [str(objection.get("설명") or "")]})
    if not claims:
        return None                  # 대조할 수치가 없다
    tol = float(get_settings().fact_audit_tolerance)
    kinds = [classify(c, materials, tol)[0] for c in claims]
    if any(k == "mismatch" for k in kinds):
        return True                  # 이의가 지적한 수치가 실제로 원문과 다르다
    if all(k in ("verified", "derived") for k in kinds):
        return False                 # 이의가 든 수치가 원문 그대로다 — 이의가 틀렸다
    return None


async def _shadow_one(pool, redis, jg: dict) -> int:
    """L3 — 독립 판정. 주심 판정을 **보지 않는다**."""
    from app.engine.matchup import clip_p_home
    from app.llm.gemini import generate, parse_json_lenient

    mats = await _materials(redis, jg)
    if not mats:
        return 0
    raw = await generate(build_independent_prompt(mats),
                         max_tokens=_cfg().shadow_judge_max_tokens)
    data = parse_json_lenient(raw)
    if not isinstance(data, dict) or data.get("p_home") is None:
        logger.info("[shadow] game=%s L3 파싱 실패 — skip", jg.get("game_id"))
        return 0
    # 클립은 **주심의 함수를 그대로** 쓴다 (사본 금지).
    p_shadow = clip_p_home(data.get("p_home"))
    p_main = float((jg.get("matchup") or {}).get("p_home") or 0)
    div = round(abs(p_main - p_shadow), 4)
    await _store_shadow(pool, jg, p_main, p_shadow, div)
    from app.config import get_settings

    if div >= float(get_settings().shadow_diverge_pp):
        await _alert("W-PANEL-DIVERGE", jg,
                     f"주심 {p_main:.2f} vs 독립 {p_shadow:.2f} "
                     f"편차 {div * 100:.1f}%p")
    return 1


# ─────────────────────────── 저장·경보 ───────────────────────────

async def _store_review(pool, jg, objections, valid) -> None:
    if pool is None:
        return
    try:
        await pool.execute(
            """INSERT INTO judge_review
                   (game_id, sport, objections, objection_n, valid_n)
               VALUES ($1,$2,$3::jsonb,$4,$5)""",
            int(jg["game_id"]), jg.get("sport") or "",
            json.dumps(objections, ensure_ascii=False), len(objections), valid)
    except Exception as exc:
        logger.warning("[shadow] 검사역 저장 실패: %s", exc)


async def _store_shadow(pool, jg, p_main, p_shadow, div) -> None:
    if pool is None:
        return
    try:
        await pool.execute(
            """INSERT INTO shadow_panel
                   (game_id, sport, p_main, p_shadow, divergence)
               VALUES ($1,$2,$3,$4,$5)""",
            int(jg["game_id"]), jg.get("sport") or "", p_main, p_shadow, div)
    except Exception as exc:
        logger.warning("[shadow] 독립 판정 저장 실패: %s", exc)


async def _alert(code: str, jg, detail: str) -> None:
    """기존 워치독 억제 체계 재사용 (P5)."""
    try:
        from app.alerts import watchdog

        await watchdog(code, detail,
                       target=f"game={jg.get('game_id')}")
    except Exception as exc:
        logger.warning("[shadow] 경보 실패: %s", exc)


async def _monitor_down(exc: Exception) -> None:
    try:
        from app.alerts import watchdog

        await watchdog("W-MONITOR-DOWN",
                       f"shadow_panel — {type(exc).__name__}: {exc}"[:180],
                       target="shadow")
    except Exception:
        pass
