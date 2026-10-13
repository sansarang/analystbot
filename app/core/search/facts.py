"""🔴🔴 **§6-5 사실 추출 — 스키마·병합·EX1/EX2**(지시서 2026-10-13 밤 셋째).

> 스키마: {종류, 대상 선수 id·팀, **상태**(결장/의심/복귀/선발 예상), 사유,
> 기간, 출처 URL, **원천 등급**, 문서 시각, 근거 문장(짧게)}.
> 같은 사실 여러 원천 → 하나로 합치고 **원천 등급 최고값·원천 수 기록**.
> 서로 다르면 **충돌 표시**(카드에 둘 다).
> 계약 **EX1**: 근거 문장·출처 없는 사실은 버린다.
> **EX2**: 근거 문장에 **경기 결과**가 있으면 버린다(premature_result).

🔴 **묶는 일은 이미 `s5_verify._merge` 가 한다**(열쇠 = subject·종류·대상) —
   여기서 다시 묶지 않는다(사본 금지). 이 모듈이 더하는 것은 **네 가지**다:
   ① 상태(결장/의심/복귀/선발 예상) ② 원천 **등급 최고값**·원천 수
   ③ **충돌**(한 사실에 상태가 둘 이상) ④ EX1·EX2 걸러내기.
⚠️ 등급 글자는 `search.sources.grade_of` 가 준다(여기 베끼지 않는다).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 🔴 상태 넷 — 지시서의 그 글자(카드가 이 말을 적는다)
STATES: tuple[str, ...] = ("결장", "의심", "복귀", "선발 예상")

#: 🔴 상태를 가리는 낱말(현지어 포함 · 표가 아니라 **글자 규칙**이다)
_WORDS: dict[str, tuple[str, ...]] = {
    # ⚠️ 영어 꼴은 **실측 문장에서** 왔다(e2e 재생 R1: *"is unlikely to play in
    #    Tuesday's friendly"*) — 지어낸 목록이 아니다.
    "의심": ("doubtful", "doubt", "unlikely to play", "unlikely to feature",
             "race to be fit", "의심", "불투명", "불확실", "출전 미지수",
             "a race against time", "50-50", "微妙"),
    "복귀": ("return", "returns", "back in training", "복귀", "돌아온다",
             "fit again", "회복", "復帰"),
    "선발 예상": ("expected to start", "likely to start", "선발 예상",
                  "선발로 나선다", "출전할 전망", "스타팅", "先発"),
    "결장": ("will miss", "set to miss", "ruled out", "sidelined",
             "out injured", "out of", "suspended", "결장",
             "빠진다", "제외", "출전하지 못", "欠場", "出場停止"),
}

#: 🔴 **EX2** — 근거 문장에 **경기 결과**가 있으면 버린다
#   ⚠️ `2-1` 같은 스코어 꼴 + 결과 낱말이 **함께** 있을 때만 센다(선수 등번호·
#      시간은 스코어가 아니다 · 거짓 탈락을 막는다).
_SCORE = re.compile(r"\b([0-9])\s*[-–:]\s*([0-9])\b")
_RESULT = ("won", "win over", "beat", "defeated", "draw", "drew", "lost to",
           "승리", "이겼", "무승부", "패했", "완승", "역전승", "승부",
           "勝利", "敗れ", "引き分け")


def state_of(text: str) -> tuple[str, str]:
    """🔴 그 문장의 **상태**와 사유. 못 가리면 `("", 🔴 사유)`.

    🔴 순서가 있다 — *"의심"* 이 *"결장"* 보다 **앞**이다(`doubtful to miss`
       같은 문장은 **의심**이다). ⚠️ 그 순서를 코드가 정하고 카드가 그 말을 적는다.
    """
    low = str(text or "").lower()
    if not low.strip():
        return "", "🔴 **근거 문장이 비었다** — 상태를 못 가린다(EX1)"
    for name in ("의심", "복귀", "선발 예상", "결장"):
        for word in _WORDS[name]:
            if word.lower() in low:
                return name, f"`{word}` 가 있다 → **{name}**"
    return "", "🔴 **상태 낱말이 없다** — 결장/의심/복귀/선발 예상 중 어느 것도 아니다"


def has_result(text: str) -> tuple[bool, str]:
    """🔴🔴 **EX2** — 그 문장이 **경기 결과**를 말하나(스코어 + 결과 낱말)."""
    said = str(text or "")
    got = _SCORE.search(said)
    if not got:
        return False, "스코어 꼴이 없다"
    low = said.lower()
    for word in _RESULT:
        if word.lower() in low:
            return True, (f"🔴 **경기 결과** — `{got.group(0)}` 와 `{word}` 가 "
                          f"함께 있다(premature_result · EX2)")
    return False, f"스코어 꼴 `{got.group(0)}` 은 있지만 결과 낱말이 없다"


def keep(*, quote: str, urls: list[str]) -> tuple[bool, str]:
    """🔴🔴 **EX1·EX2** — 이 사실을 남기나. `(남긴다, 사유)`."""
    said = str(quote or "").strip()
    rows = [str(x) for x in (urls or []) if str(x or "").strip()]
    if not said:
        return False, "🔴 **EX1** — 근거 문장이 없다(버린다)"
    if not rows:
        return False, "🔴 **EX1** — 출처 URL 이 없다(버린다)"
    bad, why = has_result(said)
    if bad:
        return False, f"🔴 **EX2** — {why}"
    return True, f"근거 문장 {len(said)}자 · 출처 {len(rows)}곳"


def grades_of(urls: list[str], *, league: str = "") -> tuple[str, int, str]:
    """🔴 **원천 등급 최고값**·원천 수·사유. 표는 `search.sources` 가 든다."""
    from app.core.search import sources as _sr
    rows = [str(x) for x in (urls or []) if str(x or "").strip()]
    if not rows:
        return "", 0, "🔴 출처가 없다 — 등급을 못 센다(EX1)"
    said = [_sr.grade_of(u, league=str(league or ""))[0] for u in rows]
    order = list(_sr.ORDER)
    best = sorted(said, key=lambda g: order.index(g)
                  if g in order else 9)[0]
    box: dict[str, int] = {}
    for g in said:
        box[g] = box.get(g, 0) + 1
    return best, len(rows), (f"등급 최고 **{best}** · 원천 {len(rows)}곳("
                             + " · ".join(f"{k} {v}" for k, v
                                          in sorted(box.items())) + ")")


def conflict_of(quotes: list[str]) -> tuple[bool, str, list[str]]:
    """🔴🔴 한 사실에 상태가 **둘 이상**이면 충돌이다(카드에 둘 다 적는다)."""
    said = [state_of(q)[0] for q in (quotes or [])]
    rows = sorted({x for x in said if x})
    if len(rows) <= 1:
        return False, (f"상태 **{rows[0]}**" if rows
                       else "🔴 상태를 가린 문장이 없다"), rows
    return True, (f"🔴 **충돌** — 원천이 서로 다른 상태를 말한다({' vs '.join(rows)})"
                  f" · 카드에 **둘 다** 적는다"), rows
