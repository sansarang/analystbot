"""🔴🔴 **s8 — 종합 논평**. 사용자 지시 2026-10-07 ③. DeepSeek **1회** · 구조화 출력.

```
Card.shape + 근거 변수 상위 4 + 시나리오 상위 3 + 보드 판정 + 방향 → Commentary
```

🔴 **먼저 숫자를 고치고, 그 숫자에서 논평을 만든다**(지시 머리글) — 그래서 이 단계는
   **아무 수도 바꾸지 않는다**. 입력은 이미 센 값이고, 출력은 글뿐이다.
🔴 **근거 불가·`context_only` 변수는 넣지 않는다**(§4-1 과 같은 규율).
🔴 **시장 확률은 입력에 없다** — 시장은 참고용이다(2026-10-06(8차) 원칙).
⚠️ 코드 검사에 어긋나면 그 칸을 버리고 **1회 재요청**, 또 어긋나면 **코드 템플릿**이다.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.core.schema import (CommentOut, Commentary, CommentLine, Facts,
                             HypoSet, Judgement, MatchRef, Variable)
from app.core.state import RunState

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **F7(2026-10-11) — 이 파일은 더 이상 글을 쓰지 않는다**
# ══════════════════════════════════════════════════════════════════
#
#  > 논평·이유 문단·전술 예측·최종 평 → **최종 평 한 번**(작성 1 + 검열 1).
#
#  🔴 그래서 `run`(LLM 작성 입구)을 **지웠다**. 남은 것은 검열·점수 **도우미**이고
#     `s9_say`·`layer1`·`render` 가 그것을 쓴다. 입구가 없으므로 아래에 적어 둔다.
STAGES = ("plain", "listy", "_sentence", "_basis")


# 🔴 F7 삭제에 함께 잘린 상수들(원본 그대로)
_JOIN = "이고 "


SENTENCE_FRAME: dict[str, str] = {
    "recent_pattern": "{who}의 최근 흐름은 {body}로 잡힌다.",
    "h2h_pattern": "두 팀 맞대결은 {body}다.",
    "home_field": "홈 이점은 {body}로 잡힌다.",
    "def_absence": "{who}는 {body}.",
    "absence": "{who}는 {body}.",
    "team_stats": "{who}는 {body}.",
    "fatigue": "{who}의 일정은 {body}.",
}



TOP_VARS = 4
TOP_SCEN = 3

def _basis(variables: list[Variable]) -> list[Variable]:
    """🔴 **근거 가능 변수 상위 4개**(무게 순) — 근거 불가는 **넣지 않는다**."""
    said = [v for v in variables if v.usable_as_basis]
    said.sort(key=lambda v: (-float(v.weight or 0.0), v.id))
    return said[:TOP_VARS]


def _scores_of(scen) -> list[str]:
    return [f"{h}-{a}" for s in scen for h, a in (s.outcomes or [])]





def _cut(said: str, n: int = 90) -> str:
    """🔴 글을 **낱말 경계에서** 자른다 — 가운데서 끊긴 글은 카드에 못 쓴다."""
    text = " ".join(str(said or "").split())
    if len(text) <= n:
        return text
    head = text[:n]
    if " " in head[n // 2:]:
        head = head[:head.rfind(" ")]
    return head.rstrip(" ,·") + "…"



def _sentence(v: Variable, ref: MatchRef) -> str:
    """🔴🔴 §4 — 변수 claim 하나 → **완결 문장 하나**.

    🔴 claim 의 나열(`A · B · C`)에서 **앞 두 토막만** 쓰고 문장으로 맺는다.
       ⚠️ 세 토막 이상을 그대로 이으면 그것이 바로 지시가 금지한 나열이다.
    """
    said = " ".join(str(v.claim or "").split())
    # 🔴 **말줄임표를 걷는다** — 잘린 글은 문장이 아니다
    said = said.replace("…", "").strip()
    bits = [x.strip(" ,") for x in said.split("·") if x.strip(" ,")]
    body = _JOIN.join(bits[:2]) if len(bits) > 1 else (bits[0] if bits else "")
    body = body.rstrip(" .")
    who = (ref.home_name if str(v.subject) == str(ref.home)
           else ref.away_name if str(v.subject) == str(ref.away) else "")
    frame = SENTENCE_FRAME.get(str(v.type), "{who} {body}.")
    out = frame.format(who=who or "이 경기", body=body or "수치를 못 쟀다")
    return " ".join(out.replace("  ", " ").split())


def listy(said: str) -> bool:
    """🔴🔴 §4 — **나열인가**(`·` 3개 이상 또는 말줄임표). 계약이 이것을 본다."""
    low = str(said or "")
    return low.count("·") >= 3 or "…" in low



def plain(said: Commentary) -> str:
    """🔴 카드에 들어가는 **사람 말 한 문단** — 변수 번호·코드를 **지운다**(지시 ④)."""
    body = " ".join(x.text.strip() for x in said.reasons)
    body = re.sub(r"`[^`]+`", "", body)
    # 🔴 `(IR11-home)` 같은 번호 괄호 — ⚠️ `IR01-away` 처럼 **꼬리가 붙은** 번호도
    #    같이 지운다(실측 2026-10-07 카자흐–페로: 본문에 그 글자가 그대로 나왔다).
    body = re.sub(r"\(\s*(?:var_ids?\s*[:：]\s*)?"
                  r"[A-Z]{1,3}\d{1,2}[A-Za-z0-9_\-]*"
                  r"(?:\s*[,·]\s*[A-Z]{1,3}\d{1,2}[A-Za-z0-9_\-]*)*\s*\)",
                  "", body)
    body = re.sub(r"\(\s*var_ids?\s*[:：][^)]*\)", "", body)
    return " ".join(body.split())
