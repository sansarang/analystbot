"""🔴🔴 **ⓒ 대회 수준** — 폼 창은 리그 경기만(사용자 지시 2026-10-12).

> 폼 창은 **리그 경기만**이 기본. 컵은 상대가 **같은 리그면 포함**, **하위 리그
> 상대면 제외**(또는 상대 Elo 보정 후 가중 0.5). 창에서 뺀 경기를 **사유에 적는다**.

🔴 왜 — 실측 2026-10-12(가와사키–나고야): 창 9경기 중 **3경기가 컵**이고 상대가
   하위 리그였다(`Tegevajaro Miyazaki`·`Roasso Kumamoto`·`Tochigi SC`). 그 득점이
   폼을 끌어올려 축1 이 +1.085(강)로 섰고, 그것이 종합의 59% 였다.
⚠️ **같은 리그인지 아는 방법은 하나다 — 그 리그 Elo 표에 그 팀이 있나**
   (`facts`/`leagueelo` 가 리그별로 만든 표다). 이름으로 추측하지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 컵 경기를 가리키는 **대회 이름 조각**(실측 2026-10-12 · fotmob 표기)
#  ⚠️ 목록을 늘릴 때는 **받아서 확인한 글자만** 넣는다(추측 금지).
CUP_WORDS: tuple[str, ...] = ("cup", "컵", "trophy", "shield", "copa",
                              "coppa", "coupe", "pokal", "taça", "beker")

#: 🔴🔴 다른 길 — *"상대 Elo 보정 후 가중 0.5"*. 🔴 **임시값**(백필 적합 전).
#  ⚠️ 지금은 쓰지 않는다(빼는 길을 기본으로 둔다) — 백필이 서면 그때 고른다.
CUP_WEIGHT = 0.5


def is_cup(league: str) -> bool:
    """🔴 그 대회가 컵인가 — 이름 조각으로 본다(원본은 `CUP_WORDS`)."""
    said = str(league or "").lower()
    return any(w in said for w in CUP_WORDS)


def keep(rows: list[dict], *, league: str, elo: dict | None = None
         ) -> tuple[list[dict], str]:
    """🔴🔴 ⓒ — 폼 창에서 **셀 경기만** 고른다. `(남긴 줄, 사유)`.

    🔴 차례:
      ① 그 경기의 리그와 **같은 대회**면 센다.
      ② 컵이면 **상대가 같은 리그에 있나**(리그 Elo 표)로 가른다 — 있으면 센다.
      ③ 없으면 **뺀다**(하위 리그 상대) — 그 경기 이름을 사유에 적는다.
    ⚠️ 그 경기의 리그를 **모르면 아무것도 빼지 않는다**(#4 추측 금지).
    """
    said_lg = str(league or "").strip()
    rows = [dict(x) for x in (rows or [])]
    if not said_lg:
        return rows, ("⚠️ 이 경기의 대회를 **모른다** — 폼 창에서 아무것도 "
                      "빼지 않았다")
    table = {str(k) for k in dict(elo or {})}
    out: list[dict] = []
    gone: list[str] = []
    same_cup: list[str] = []
    for one in rows:
        got_lg = str(one.get("league") or "")
        if got_lg == said_lg:
            out.append(one)
            continue
        if not is_cup(got_lg):
            # ⚠️ 다른 리그(2군·대륙 대회 등) — 그것도 뺀다(폼 창은 그 리그다)
            gone.append(f"{one.get('opp') or '?'}[{got_lg or '대회 미상'}]")
            continue
        opp = str(one.get("opp") or "")
        if opp and opp in table:
            out.append(one)
            same_cup.append(opp)
            continue
        gone.append(f"{opp or '?'}[{got_lg}]")
    bits: list[str] = []
    if gone:
        bits.append(f"🔴 폼 창에서 **{len(gone)}경기를 뺐다**(대회 수준) — "
                    + ", ".join(gone[:4]))
    if same_cup:
        bits.append(f"컵이지만 상대가 **같은 리그**라 셌다 — "
                    + ", ".join(same_cup[:3]))
    if not table and any(is_cup(str(x.get("league") or "")) for x in rows):
        bits.append("⚠️ 리그 Elo 표가 없어 컵 상대가 같은 리그인지 **못 가렸다**")
    return out, " · ".join(bits)
