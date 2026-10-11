"""🔴🔴 **사람이 준 라인업을 봇의 XI 로** — 사용자 지시 2026-10-10(김천 경기).

> 데스크탑 라인업 캡쳐 확인해라.. 네이버 스포츠에는 이미 떴다..

🔴 **왜 이 통로가 필요한가**(실측 2026-10-10 · 김천–안양 T-50분):
   네이버 스포츠에는 확정 라인업이 떴는데 **fotmob 은 아직 안 받았다**
   (`lineupType: None` · 선발 0). 사다리 다섯 칸이 전부 그 상태였고, K리그 공식
   XHR 은 **경기 전 선발을 주지 않는다**(오늘 실측). 그래서 사람이 준 글이
   **유일한 통로**였다.

🔴🔴 **이름이 아니라 등번호로 잇는다.** 캡처는 한글(`41 박만호`)이고 우리 명단은
   로마자(`Man-Ho Park`)다. ⚠️ 음차를 글자로 이으면 틀린다 — 등번호는 언어가 없다.
🔴 번호를 못 맞춘 선수는 **캡처의 이름을 그대로 둔다**(버리지 않는다) 그리고 그
   수를 사유에 적는다(#3 조용한 0 금지).
⚠️ 상태는 **`사람이 준 것`** 으로 남긴다 — 카드가 그 사실을 적는다. 출처를
   `fotmob` 이라고 말하지 않는다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 🔴 `41 박만호` · `9 엘쿠라노` · `33 대니 바커` — 번호와 이름
#
#  🔴🔴 **번호 뒤 공백이 없을 수 있다** — ⚠️ 실사고 2026-10-11(스포팅 KC 캡처):
#     OCR 이 한 줄에 선수 **셋**을 담았고(`10 다비드 … 21차라 … 80 오르티스`)
#     `21차라` 가 번호+이름 사이에 공백이 없어 **그 줄 전체가 안 잡혔다**
#     (두 선수를 통째로 잃었다). 🔴 `\s*` 로 받고, 다음 선수의 시작도
#     `\d{1,2}\D`(번호 뒤가 글자여도 된다)로 본다.
_ROW = re.compile(r"(?<!\d)(\d{1,2})\s*([^\d\n][^\n]{0,24}?)\s*(?=$|\n|\d{1,2}\D)")
#: 🔴 포메이션 글자 — `4-4-2`·`4-2-3-1`
_FORM = re.compile(r"\b(\d(?:-\d){1,3})\b")


#: 🔴 선수 줄이 **아닌** 것을 가리키는 낱말(캡처 머리글)
NOT_PLAYER: tuple[str, ...] = ("감독", "코치", "선발", "교체", "벤치", "후보",
                               "경기", "포메이션", "lineup", "coach", "manager")
#: 🔴 이름에 **글자**가 이만큼은 있어야 한다(한글 음절 또는 로마자)
_LETTER = re.compile(r"[가-힣A-Za-z]")


def parse(said: str) -> list[dict]:
    """🔴 캡처 글 → `[{"number": "41", "name": "박만호"}]`. 순서는 글 그대로.

    ⚠️ 번호가 없는 줄은 **버린다** — 번호가 이 통로의 열쇠다.
    🔴🔴 **OCR 잡음을 거른다**(실사고 2026-10-11 · 스포팅 KC 캡처):
       `2 감독 위키` · `7 3) €` · `0 ()` · `0 a` 가 선수 줄로 섞여 **11/11 가름이
       밀렸다**(홈에 10명, 원정에 엉뚱한 줄). 거르는 기준은 셋이고 **이름을
       지어내지 않는다**:
         ① 등번호 `0` 은 버린다(OCR 이 동그라미를 0 으로 읽는다)
         ② 이름에 글자(한글·로마자)가 **2개 미만**이면 버린다
         ③ `감독`·`코치` 같은 **머리글 낱말**이 들어 있으면 버린다
    """
    out: list[dict] = []
    for num, nm in _ROW.findall(str(said or "")):
        one = " ".join(str(nm).split()).strip(" ·-")
        if not one or one.isdigit():
            continue
        if int(num) == 0:
            continue
        if len(_LETTER.findall(one)) < 2:
            continue
        low = one.lower()
        if any(w in low for w in NOT_PLAYER):
            continue
        out.append({"number": str(int(num)), "name": one})
    return out


def forms_of(said: str) -> list[str]:
    """🔴 캡처 글의 **포메이션 전부**(위→아래 차례). 없으면 빈 목록.

    ⚠️ 한 장에 두 팀이 있으면 포메이션도 둘이다 — `formation_of` 는 **첫 것**만
       주므로 원정 포메이션이 홈 것으로 붙을 자리였다(실측 2026-10-11).
    """
    return [m.group(1) for m in _FORM.finditer(str(said or ""))]


def formation_of(said: str) -> str:
    """🔴 캡처 글에서 **포메이션**. 없으면 빈 글자."""
    hit = _FORM.search(str(said or ""))
    return hit.group(1) if hit else ""


def to_xi(rows: list[dict], numbers: dict, *, team: str, formation: str = "",
          size: int = 11) -> tuple[object, str]:
    """🔴🔴 번호표로 이어 **`XI` 를 만든다**. `(XI, 사유)`.

    `numbers` 는 `fotmob.squad_numbers` 가 준 `{번호: 로마자 이름}` 이다.
    🔴 앞 `size` 명이 **선발**이고 나머지는 벤치다(캡처가 선발만 담았으면 11명이다).
    ⚠️ 번호를 못 맞춘 선수는 **캡처 이름 그대로** 넣고 그 수를 사유에 적는다.
    """
    from app.core.schema import Player, XI
    hit: list[str] = []
    miss: list[str] = []
    lineup: list = []
    for one in (rows or [])[:size]:
        box = dict(one)
        num = str(box.get("number") or "")
        got = str(dict(numbers or {}).get(num) or "")
        name = got or str(box.get("name") or "")
        if got:
            hit.append(f"{num}:{got}")
        else:
            miss.append(f"{num}:{box.get('name')}")
        lineup.append(Player(name=name, number=(int(num) if num.isdigit()
                                                else None)))
    said = XI(team=str(team), state="confirmed",
              formation=str(formation or ""),
              players=[p.name for p in lineup], lineup=lineup,
              source_url="user_capture")
    why = (f"사람이 준 라인업 — 번호로 이은 선수 **{len(hit)}명**"
           + (f" · ⚠️ 못 이은 {len(miss)}명은 캡처 이름 그대로({miss[:3]})"
              if miss else " · 전원 이었다"))
    return said, why
