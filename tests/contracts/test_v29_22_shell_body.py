"""🔴🔴 **알맹이 문턱** — 사용자 지시 2026-10-15 *"(가) 수정"*.

⚠️ 실사고 2026-10-15(BG Pathum): BeSoccer 부상·징계 명단이 `200 · 756자` 로
   와서 **"받았다"로 셌다**. 그 756자는 연령 확인·광고·로그인·남의 리그 선수
   이름뿐이고 부상자는 **0줄**이었다(실측). 🔴 그래서 사다리(AMP·RSS·대체 경로)가
   **한 번도 안 불렸다**.

지키는 것:
  FT5 껍데기 본문을 **성공으로 세지 않는다**
  FT6 긴 본문(ESPN 스쿼드 2,976자)은 **그대로 통과**한다
  FT7 껍데기면 사다리가 **내려간다**(칸 기록이 둘 이상)
"""
from __future__ import annotations

import asyncio

from app.core.search import fetch as ft

#: 🔴 실측한 그 756자의 **모양**(글자를 줄여 옮겼다 — 판정 재료는 같다)
SHELL = ("Are you of legal age?\nConfirm if you are 18 years old\n"
         "Champions League\nRound 2\nLaLiga\nRound 9\n"
         "Loading ad...\nBG Pathum United\nLogin\n"
         "Username must have between 4 and 16 characters\n") * 3
#: 🔴 알맹이 있는 본문(ESPN 스쿼드 꼴)
REAL = ("Adelaide United Squad\n"
        + "Craig Goodwin 11 F 34 5' 11\" 161 lbs Australia\n" * 40)


def test_ft5_shell_is_not_success() -> None:
    """FT5 🔴 껍데기 판정 — 짧고 껍데기 문구 둘 이상이면 참."""
    got, why = ft.shell_like(SHELL)
    assert got, f"FT5 🔴 껍데기를 못 잡았다 — {len(SHELL)}자"
    assert "껍데기 문구" in why, why


def test_ft6_real_body_passes() -> None:
    """FT6 🔴 알맹이 있는 본문은 **안 걸린다**(실측 2,976자)."""
    assert not ft.shell_like(REAL)[0]
    assert len(REAL) > ft.SHELL_MAX
    # 🔴 짧아도 껍데기 문구가 없으면 통과한다
    assert not ft.shell_like("부상자 명단 — 김민재(햄스트링) 결장")[0]


def test_ft7_ladder_descends_on_shell() -> None:
    """FT7 🔴🔴 껍데기면 **사다리를 내려간다** — 칸 기록이 둘 이상이고
    원문 칸이 `ok=False` 로 남는다."""

    class _Res:
        ok, status, text = True, 200, f"<html>{SHELL}</html>"

    class _Net:
        async def get(self, url):                           # noqa: ANN001
            return _Res()

    body, _when, rows = asyncio.run(ft.body_of(
        _Net(), "https://x.test/injuries", extract=lambda h, url="": (SHELL, None)))
    assert not str(body or "").strip(), f"FT7 🔴 껍데기를 본문으로 돌려줬다 — {body[:60]!r}"
    got_first = rows[0]
    assert got_first.get("rung") == "원문" and not got_first.get("ok")
    assert "껍데기" in str(got_first.get("why")), got_first
    assert len(rows) >= 2, f"FT7 🔴 사다리가 안 내려갔다 — {rows}"
