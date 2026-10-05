"""🔴🔴 **v5-A §2 — DeepSeek 클라이언트.** 도구 없음 · JSON 출력 · 장애를 삼킨다.

⚠️ **왜 `app/llm/deepseek.py` 가 아닌가**(실측 2026-10-04): 작업지시 §4-2 는
   그 경로를 적었지만 이 저장소에는 **`app/llm.py` 가 이미 있다**(로컬
   `qwen3:8b` 통로 · §17-b L1~L3). 🔴 `app/llm/` 패키지를 만들면 그 모듈이
   **가려져** 아홉 개 시험이 수집에서 터졌다(`cannot import name 'Budget'`).
   → `app/deepseek.py` 로 둔다. ⚠️ 지시서의 **뜻**(독립 클라이언트 파일)은
   그대로이고, 경로만 이 저장소의 사실에 맞췄다.

부록 v5-A §2 원문:

> 호출 규칙 — OpenAI 호환 SDK, `base_url` 은 공식 문서 값. **JSON 출력 모드
> 강제.** 타임아웃 120초, 재시도 2회. 실패하면 DeepSeek 없이 v5 원래 경로
> (Solar 초안 + 코드 필수형 보강)로 판정하고 카드에 `deepseek_unavailable`.
> **DeepSeek 장애가 경기 분석을 막지 않는다.**
> 웹 차단 — DeepSeek 호출에는 **도구를 하나도 넘기지 않는다**(`tools` 비움).
> 함수 호출·검색 기능이 있어도 쓰지 않는다.

══════════════════════════════════════════════════════════════════
🔴 **M42 — 도구를 넘길 *길이* 없다**
══════════════════════════════════════════════════════════════════

⚠️ DeepSeek 공식 문서에 `Tool Calls ✓` 가 있다. 🔴 **있어도 쓰지 않는다** —
   검색·본문 읽기는 **Solar 자리**이고(v5-A §1), DeepSeek 가 웹에 닿으면 그
   출력이 **검증층을 안 지난 사실**을 들고 온다.
🔴 그래서 `ask()` 에 `tools` 인자를 **두지 않았다** — 없는 문은 안 열린다.

══════════════════════════════════════════════════════════════════
🔴 **M45 — 장애를 삼킨다**
══════════════════════════════════════════════════════════════════

⚠️ 예외를 위로 던지면 그 경기 분석이 **통째로 멈춘다.** 🔴 DeepSeek 는
   **거드는 단계**다 — 없으면 v5 원래 경로가 돈다.

🔴 **보내지 않는 것**(v5-A §2): 기사 원문 전체 · URL · 사용자 정보 · 배당.
   ⚠️ 보내는 것은 코드가 만든 JSON 하나다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.reasons import Reason

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """🔴 한 호출의 결과. ⚠️ **못 불렀어도 이 꼴로 온다**(예외가 아니다)."""

    ok: bool
    reason: Reason
    why: str
    text: str = ""
    usage: dict | None = None
    usd: float = 0.0

    def json(self) -> tuple[dict | None, str]:
        """🔴 JSON 으로. ⚠️ 못 읽으면 `(None, 사유)` — 지어내지 않는다."""
        if not self.ok:
            return None, self.why
        try:
            got = json.loads(self.text or "{}")
        except ValueError as exc:
            return None, f"🔴 DeepSeek 출력이 JSON 이 아니다: {exc}"
        return (got, "") if isinstance(got, dict) else (
            None, f"🔴 사전이 아니다: {type(got).__name__}")


def _off(why: str) -> Answer:
    return Answer(False, Reason.DEEPSEEK_UNAVAILABLE, why)


def stage_on(stage: str) -> tuple[bool, str]:
    """🔴 그 단계를 **켜도 되나**. `enabled` 는 네 값이다.

    ⚠️ `false` · `stage3` · `stage3+4` · `true`. 🔴 §5 측정 순서가 그 값들을
       쓴다(작업지시 §5-3·§5-4) — 단계 3만 켜고 재면 그 효과가 갈린다.
    """
    from app import rules
    said = rules.deepseek_cfg().get("enabled")
    if said is True:
        return True, ""
    if not said:
        return False, (f"🔴 `deepseek.enabled` 가 **꺼짐**이다 — `{stage}` 를 "
                       f"돌리지 않는다(작업지시 §4: 켜는 것은 사용자 승인)")
    got = str(said)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **글자 포함으로 보면 틀린다**(실측 2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `"stage4" in "stage3+4"` 는 **거짓**이다 — 그 값은 `stage3` 와 `4` 를
    #     `+` 로 이은 꼴이다. 🔴 그래서 `stage3+4` 를 켜 두고도 단계 4(반증)가
    #     **안 돌았다**(실측: `stage_on('stage4')` 가 False).
    #  🔴 **숫자로** 본다 — 값에서 숫자를 뽑아 그 안에 있나를 묻는다.
    import re as _re
    want = _re.findall(r"\d+", str(stage))
    have = _re.findall(r"\d+", got)
    if want and want[0] in have:
        return True, ""
    return False, (f"🔴 `deepseek.enabled: {got}` 에 `{stage}` 가 없다 — "
                   f"그 단계는 안 돈다(켜진 단계: {have or '없다'})")


def ask(messages: list[dict], *, match: str = "", stage: str = "stage3",
        now: datetime | None = None, _net=None,
        _ledger_root: Path | None = None, _force: bool = False) -> Answer:
    """🔴🔴 한 번 묻는다. **도구는 넘기지 않는다**(M42) · 장애를 삼킨다(M45).

    ⚠️ `_force` 는 **시험용**이다 — 스위치를 건너뛴다. 🔴 운영에서는 `False` 다.
    """
    from app import llmprice, rules, solar
    from app.config import get_settings
    s = get_settings()
    if not _force:
        ok, why = stage_on(stage)
        if not ok:
            return _off(why)
    if not s.deepseek_ready:
        return _off("🔴 `DEEPSEEK_API_KEY` 가 없다(v5-A §2)")
    cfg = rules.deepseek_cfg()
    m = dict(cfg.get("model") or {})
    # 🔴 **하루·월 가드는 Solar 와 합산**이다(v5-A §2) — 그쪽에 묻는다
    ok, why = solar.gate(now=now)
    if not ok:
        return _off(f"🔴 합산 예산 가드가 막았다: {why}")
    body = {
        "model": str(m.get("name") or "deepseek-flash"),
        "messages": list(messages),
        # 🔴 **JSON 출력 모드 강제**(v5-A §2)
        "response_format": {"type": "json_object"},
        "max_tokens": int((cfg.get("budget", {}).get("per_match") or {})
                          .get("output_tokens") or 15_000),
    }
    # ⚠️ `tools` 를 **넣지 않는다** — M42. 🔴 넣는 길도 만들지 않았다.
    if m.get("thinking"):
        body["thinking"] = {"type": "enabled"}
    try:
        got = (_net or _post)(str(m.get("base_url")), s.deepseek_api_key, body,
                              int(m.get("timeout_sec") or 120),
                              int(m.get("retries") or 2))
    except Exception as exc:                                # noqa: BLE001
        # 🔴🔴 **M45** — 삼킨다. 위로 던지면 경기 분석이 통째로 멈춘다.
        logger.warning("[deepseek] 못 불렀다: %r", exc)
        return _off(f"🔴 DeepSeek 호출 실패 — {exc}")
    usage = dict(got.get("usage") or {})
    usd = llmprice.deepseek_cost(usage, now=now)
    cached = int((usage.get("prompt_tokens_details") or {})
                 .get("cached_tokens") or 0)
    # 🔴 **M49 와 같은 칸**으로 같은 원장에 적는다(하루 가드가 합산한다)
    solar.write_ledger(
        {"match": match, "provider": "deepseek", "stage": stage,
         "model": got.get("model") or body["model"], "usd": usd,
         "in": max(0, int(usage.get("prompt_tokens") or 0) - cached),
         "cache": cached,
         "out": int(usage.get("completion_tokens") or 0),
         "band": llmprice.deepseek_band(now),
         "price_verified": bool(
             (cfg.get("price_usd_per_1m") or {}).get("verified_by_user"))},
        now=now, root=_ledger_root)
    text = ((got.get("choices") or [{}])[0].get("message") or {}).get("content")
    return Answer(True, Reason.OK, "DeepSeek 응답", str(text or ""), usage, usd)


def _post(base_url: str, key: str, body: dict, timeout: int,
          retries: int) -> dict:
    """🔴 v5-A §2 — 타임아웃 120초 · 재시도 2회(지수 대기).

    ⚠️ **OpenAI 호환**이다(`/chat/completions`) — 공식 문서의 `base_url` 그대로.

    🔴🔴 **녹화·재생을 지난다**(지시서 2026-10-06 §5) — Solar 와 **같은 길**이다
       (`solar._cassette_query` 가 열쇠 글자를 만든다 · 사본 금지).
    """
    from app import cassette
    from app.solar import _cassette_query
    url = base_url.rstrip("/") + "/chat/completions"
    qs = _cassette_query(body)
    if cassette.mode() == cassette.REPLAY:
        try:
            got = cassette.load("llm", url, qs)
        except cassette.CassetteMiss as exc:
            # 🔴 기본은 **실패**다(M134) — `fallthrough` 를 줄 때만 라이브로
            if not cassette.fallthrough():
                raise RuntimeError(str(exc)) from exc
            logger.info("[deepseek] %s — fallthrough 로 라이브로 간다",
                        cassette.REPLAY_MISS)
        else:
            return {k: v for k, v in got.items()
                    if k not in ("kind", "url", "query", "recorded_at")}
    got = _post_live(url, key, body, timeout, retries)
    if cassette.mode() in (cassette.RECORD, cassette.REPLAY):
        cassette.save("llm", url, qs, dict(got))
    return got


def _post_live(url: str, key: str, body: dict, timeout: int,
               retries: int) -> dict:
    """🔴 **실제로 망에 나가는 자리** — 재생이 이 함수를 건너뛴다."""
    import httpx
    last = ""
    for i in range(int(retries) + 1):
        try:
            r = httpx.post(url, json=body, timeout=timeout,
                           headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"})
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:                            # noqa: BLE001
            last = repr(exc)
        if i < int(retries):
            time.sleep(2 ** i)
    raise RuntimeError(last or "알 수 없는 실패")


def now_utc() -> datetime:
    """⚠️ 시험이 시각을 밀어 넣을 수 있게 한 자리."""
    return datetime.now(timezone.utc)
