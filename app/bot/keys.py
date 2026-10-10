"""🔴🔴 **텔레그램 버튼** — 사용자 지시 2026-10-10(재작성) §1-3·§2-3.

> 후보 2개 이상 → **텔레그램 버튼으로 고르게 한다**(리그·날짜·시각을 붙여서).
> 고르기 전에 분석하지 않는다.
> 카드에 버튼 `[🔔 라인업 나오면 다시 분석]` — **사용자가 누른 경기만** 돈다.

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나
══════════════════════════════════════════════════════════════════

⚠️ 실측 2026-10-10: 봇에 **인라인 키보드가 하나도 없었다**(`grep InlineKeyboard`
   → 0건). 카드 밑의 `[📖 자세히] [🧩 시나리오] …` 는 **글자**였고 누를 수 없었다.
   🔴 그래서 §2-3 의 *"사용자가 누른 경기만 돈다"* 를 지킬 방법 자체가 없었다.

🔴 `callback_data` 는 **64바이트**다(텔레그램 한계). 그래서 긴 열쇠는 **토큰**으로
   줄여 `app/bot/pending.py` 가 들고, 버튼은 그 토큰만 싣는다.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.layer1 import BUTTONS

#: 🔴 콜백 글자의 **판 번호** — 꼴을 바꿀 때 옛 버튼이 조용히 오동작하지 않게
VER = "1"
#: 🔴 텔레그램 상한. ⚠️ 넘으면 **버튼이 안 만들어진다**(조용히 사라진다)
CB_CAP = 64


def pack(action: str, arg: str = "") -> str:
    """🔴 `v1|<하는 일>|<인자>` — 상한을 넘으면 **자른다**(토큰은 짧게 쓴다)."""
    said = f"{VER}|{action}|{arg}"
    return said[:CB_CAP]


def unpack(said: object) -> tuple[str, str]:
    """🔴 `(하는 일, 인자)`. ⚠️ 판 번호가 다르면 `("", "")`(안 받는다)."""
    parts = str(said or "").split("|")
    if len(parts) < 2 or parts[0] != VER:
        return "", ""
    return parts[1], ("|".join(parts[2:]) if len(parts) > 2 else "")


def card_keys(*, token: str, deep: bool = False, watch: bool = False,
              watching: bool = False) -> InlineKeyboardMarkup:
    """🔴 카드 아래 버튼들 — `layer1.BUTTONS` 가 **이름의 원본**이다(사본 금지).

    🔴 §2-3 — 확정 XI 전이면 `[🔔 라인업 나오면 다시 분석]` 을 **더한다**.
       ⚠️ 이미 누른 경기면 그 사실을 보여 준다(두 번 걸지 않게).
    """
    rows = [[InlineKeyboardButton(text=lab, callback_data=pack(act, token))
             for lab, act in BUTTONS[i:i + 2]]
            for i in range(0, len(BUTTONS), 2)]
    if watch:
        said = ("🔔 라인업 감시 중 — 끄기" if watching
                else "🔔 라인업 나오면 다시 분석")
        rows.append([InlineKeyboardButton(
            text=said, callback_data=pack("unwatch" if watching else "watch",
                                          token))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pick_keys(token: str, picks: list[dict]) -> InlineKeyboardMarkup | None:
    """🔴🔴 §1-3 — 후보 버튼. **리그·날짜·시각을 붙인다**. 없으면 `None`.

    ⚠️ 버튼 글자가 길면 텔레그램이 줄여 보여 준다 — 그래도 **리그와 시각은 넣는다**
       (그 둘이 없으면 사용자가 무엇을 고르는지 모른다).
    """
    rows = []
    for i, p in enumerate(picks or []):
        box = dict(p)
        said = f"{box.get('home')} vs {box.get('away')}"
        tail = " · ".join(x for x in (str(box.get("league") or ""),
                                      str(box.get("kst") or "")) if x)
        rows.append([InlineKeyboardButton(
            text=(f"{said} · {tail}" if tail else said),
            callback_data=pack("pick", f"{token}:{i}"))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
