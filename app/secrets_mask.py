"""API 키가 저장·로그·알림에 **평문으로 남지 않게** 가린다.

🔴 실사고 2026-09-07: 오염된 `GROQ_API_KEY` 값 하나에 NVIDIA·OPENROUTER 키가
   함께 들어 있었고, 그 문자열이 운영 로그에 평문으로 찍혔다. 더 나쁜 것은
   `llm/ledger.record_outage` 가 그것을 Redis 에 그대로 넣은 것이다 —
   로그는 회전되지만 그 키들은 **TTL 14일** 동안 조회 가능한 상태로 남았다
   (실측 2026-09-08: `llm_outage:*` 211행).

**설계 원칙 — 가리되 진단은 남긴다.**
가리는 것은 "키처럼 생긴 값"뿐이다. 상태 코드·오류 종류·모델명·provider 이름은
그대로 둔다. 마스킹이 넓으면 "무엇이 실패했는지"가 사라지고, 그러면 다음 사람이
이 기록을 안 보게 된다. `tests/test_secrets_mask.py` 가 양쪽을 함께 검사한다.

⚠️ 접두사 목록은 **provider 표의 사본이 아니다.** 여기 있는 것은 키 값의
   *형태*이고, provider 목록·모델명·활성 여부는 `app/config.py` 가 원본이다.
"""
from __future__ import annotations

import logging
import re

#: 키 값의 접두사. **긴 것을 앞에** 둔다 — `sk-or-v1-` 가 `sk-` 로 잡히면
#: 접두사가 잘려 어느 키였는지 알 수 없게 된다.
_PREFIXES = (
    "github_pat_", "sk-or-v1-", "sk-ant-", "nvapi-", "pplx-",
    "gsk_", "xai-", "AIza", "ghp_", "hf_", "sk-",
)
_PREFIX_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in _PREFIXES) + r")([A-Za-z0-9_\-]{12,})")

#: `Authorization: Bearer <token>`
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9_\-\.=]{16,})")

#: URL 쿼리 `?key=…` · `&api_key=…` — 다음에 올 것이 헤더가 아니라 링크일 수 있다
_QUERY_RE = re.compile(r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|key)=)([^&\s\"']{8,})")

#: `GROQ_API_KEY=…` 형태. 접두사를 모르는 키(예: Mistral)도 이걸로 잡힌다.
_ASSIGN_RE = re.compile(r"([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*)([^\s\"',;]{12,})")


def _hide(m: re.Match) -> str:
    """접두사·파라미터 이름은 남기고 값만 길이로 바꾼다."""
    return f"{m.group(1)}…{len(m.group(2))}자 가림"


def mask_secrets(text):
    """문자열에서 키처럼 생긴 값을 가린다. 문자열이 아니면 그대로 돌려준다."""
    if not isinstance(text, str) or not text:
        return text
    out = _PREFIX_RE.sub(_hide, text)
    out = _BEARER_RE.sub(_hide, out)
    out = _QUERY_RE.sub(_hide, out)
    out = _ASSIGN_RE.sub(_hide, out)
    return out


class MaskingFilter(logging.Filter):
    """로그 레코드의 메시지·인자에서 키를 가린다.

    ⚠️ 포맷 **전에** 건다 — `logger.warning("%s 실패", exc)` 처럼 인자로 들어온
       예외 문자열이 가장 흔한 유출 경로다.
    """

    def filter(self, record: logging.LogRecord) -> bool:   # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = mask_secrets(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: mask_secrets(v) if isinstance(v, str) else v
                                   for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        mask_secrets(a) if isinstance(a, str)
                        else (mask_secrets(str(a)) if isinstance(a, Exception) else a)
                        for a in record.args)
        except Exception:       # 로깅이 예외를 던지면 안 된다 — 가리기 실패가
            pass                # 프로그램을 멈추는 것보다 낫다
        return True


def install_log_filter(logger: logging.Logger | None = None) -> MaskingFilter | None:
    """필터를 건다. `logger` 를 주지 않으면 루트 로거와 그 핸들러 전부에 건다.

    🔴 **핸들러에도 건다.** 하위 로거가 전파(propagate)한 레코드는 상위 *로거* 의
       필터를 다시 타지 않는다 — 핸들러 필터만이 그것을 본다. 루트에만 걸고
       "전역에 걸었다"고 믿으면 `app.llm.provider` 의 로그는 그대로 샌다.
    """
    targets: list[logging.Logger | logging.Handler]
    if logger is not None:
        targets = [logger]
    else:
        root = logging.getLogger()
        targets = [root, *root.handlers]
    filt: MaskingFilter | None = None
    for t in targets:
        if any(isinstance(f, MaskingFilter) for f in t.filters):
            continue
        filt = filt or MaskingFilter()
        t.addFilter(filt)
    return filt


# ── [SEC-2 2026-09-09] 설정 객체 마스킹 ────────────────────────────────
#
# 🔴 실사고: `getattr(settings, "deepsearch_enabled")` 가 **메서드**여서
#    바운드 메서드 repr 에 `Settings(...)` 전체가 딸려 나왔고, 키 11종이
#    평문으로 노출됐다(2026-09-09). 가리는 장치는 여기 있었는데 **설정 객체
#    자신에는 물려 있지 않았다.**

#: 이름이 이러면 비밀이다. 값이 아니라 **필드 이름**으로 가른다 —
#  값 모양으로만 가르면 접두사 없는 키(Mistral·Odds 등)를 놓친다.
_SECRET_SUFFIX = ("_key", "_token", "_secret", "_password")


def is_secret_field(name: str, value=None) -> bool:
    """이 설정 필드가 비밀인가.

    ⚠️ `*_url` 을 통째로 가리지 않는다 — `pplx_base_url` 같은 진단값이 사라진다.
       **자격증명이 들어 있는 URL**(`scheme://user:pass@host`)만 가린다.
    """
    n = (name or "").lower()
    if n.endswith(_SECRET_SUFFIX):
        return True
    if isinstance(value, str) and "://" in value:
        head = value.split("://", 1)[1]
        return "@" in head.split("/", 1)[0] and ":" in head.split("@", 1)[0]
    return False


def mask_field(name: str, value):
    """비밀이면 길이만 남긴 표기로, 아니면 값 그대로.

    ⚠️ **필드 이름은 지우지 않는다.** 무엇이 있었는지가 남아야 진단이 된다.
    """
    if value is None or value == "":
        return value
    if not is_secret_field(name, value):
        return value
    return f"…{len(str(value))}자 가림"
