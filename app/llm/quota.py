"""[U14 2026-09-15] 제공자 잔량 추적 — 라운드로빈 본 구현.

🔴 CHN-1(2026-09-15)은 **임시 규칙**이었다: 429·401 을 맞으면 즉시 다음
   제공자로 간다. 그런데 "어느 제공자에 얼마나 남았는지"를 아무도 몰라서,
   다음 호출에서 **방금 한도를 맞은 그 제공자를 또 먼저** 불렀다.
🔴 **모르는 것과 없는 것은 다르다.** 헤더를 안 주는 제공자(gemini)는
   잔량 미상이고, 미상이면 **순서를 바꾸지 않는다.** 0 으로 읽으면 멀쩡한
   제공자가 영원히 맨 뒤로 간다.
⚠️ **순서를 뒤집지 않는다.** 기본은 `chain()` 그대로다. 잔량은 *한도를 맞은
   제공자를 잠시 뒤로 미루는 데만* 쓴다 — 라우팅 재설계는 지시받지 않았다.
⚠️ 프로세스 안 메모리다. 재시작하면 잊는다 — 그게 맞다(한도는 분 단위로 찬다).
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

#: 헤더 이름. 🔴 제공자마다 다르다 — 표를 손으로 늘리지 말고 접두사로 찾는다.
_REMAIN_KEYS = ("x-ratelimit-remaining-tokens", "x-ratelimit-remaining-requests",
                "x-ratelimit-remaining")
_RESET_KEYS = ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests",
               "retry-after")

#: 한도를 맞았을 때 기본으로 미뤄두는 시간(초). `Retry-After` 가 있으면 그게 이긴다.
DEFAULT_COOLDOWN = 60.0

#: {provider: {"remaining": int|None, "until": float|None, "at": float}}
_STATE: dict[str, dict] = {}


def _now() -> float:
    return time.monotonic()


def _secs(raw) -> float | None:
    """`"12s"` · `"1m30s"` · `"7.5"` → 초. 못 읽으면 None(0 이 아니다)."""
    t = str(raw or "").strip().lower()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        pass
    total, num = 0.0, ""
    for ch in t:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in "hms" and num:
            total += float(num) * {"h": 3600, "m": 60, "s": 1}[ch]
            num = ""
        else:
            return None
    return total or None


def note_headers(provider: str, headers, *, status: int | None = None) -> dict:
    """응답 헤더에서 잔량·리셋을 읽어 기록한다. 읽은 것을 그대로 돌려준다."""
    p = str(provider or "").strip()
    if not p:
        return {}
    h = {str(k).lower(): v for k, v in dict(headers or {}).items()}

    rem = None
    for k in _REMAIN_KEYS:
        if k in h:
            try:
                rem = int(float(h[k]))
            except (TypeError, ValueError):
                rem = None
            break

    until = None
    if status in (429, 401):
        wait = None
        for k in _RESET_KEYS:
            if k in h:
                wait = _secs(h[k])
                if wait is not None:
                    break
        until = _now() + (wait if wait is not None else DEFAULT_COOLDOWN)
        rem = 0 if status == 429 else rem

    box = _STATE.setdefault(p, {"remaining": None, "until": None, "at": 0.0})
    if rem is not None:
        box["remaining"] = max(0, rem)     # 🔴 음수로 안 내려간다
    if until is not None:
        box["until"] = until
    box["at"] = _now()
    logger.info("[quota] %s 잔량=%s · 대기해제=%s · status=%s", p,
                box["remaining"],
                (None if box["until"] is None
                 else f"{max(0.0, box['until'] - _now()):.0f}초 뒤"), status)
    return dict(box)


def remaining(provider: str):
    """남은 양. **모르면 None** — 0 이 아니다."""
    return (_STATE.get(str(provider or "")) or {}).get("remaining")


def cooling(provider: str) -> float:
    """남은 대기 초. 0 이면 지금 쓸 수 있다."""
    until = (_STATE.get(str(provider or "")) or {}).get("until")
    return 0.0 if until is None else max(0.0, until - _now())


def order_by_remaining(chain: list | tuple) -> list:
    """사슬을 **재정렬**한다. 🔴 쉬는 중인 제공자만 뒤로 민다.

    사슬 원소는 `"provider/model"` 이다. 잔량이 미상이면 자리를 안 바꾼다.
    전부 쉬는 중이면 **원래 순서 그대로** 돌려준다 — 그때는 호출자가 기다린다.
    """
    items = list(chain or [])
    if not items:
        return []

    def _p(x) -> str:
        return str(x).split("/", 1)[0]

    live = [x for x in items if cooling(_p(x)) <= 0]
    cold = [x for x in items if cooling(_p(x)) > 0]
    if not live:
        return items
    # 쉬는 것들은 **해제가 이른 순서**로 뒤에 붙인다
    cold.sort(key=lambda x: cooling(_p(x)))
    return live + cold


def all_cooling(chain: list | tuple) -> bool:
    """전부 한도인가. 이때만 기다린다."""
    items = list(chain or [])
    return bool(items) and all(cooling(str(x).split("/", 1)[0]) > 0
                               for x in items)


def wait_secs(chain: list | tuple) -> float:
    """전부 한도일 때 **가장 빨리 풀리는** 시간."""
    items = list(chain or [])
    if not items:
        return 0.0
    return min(cooling(str(x).split("/", 1)[0]) for x in items)


def snapshot() -> dict:
    """진단용. 지금 아는 전부."""
    return {p: {"remaining": b.get("remaining"),
                "cooling": round(cooling(p), 1)} for p, b in _STATE.items()}


def reset() -> None:
    """테스트용. 운영 경로에서 부르지 않는다."""
    _STATE.clear()
