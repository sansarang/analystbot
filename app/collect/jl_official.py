"""🔴🔴 **§6-6 전용 통로 — J리그 공식 공시**(지시서 2026-10-13 밤 셋째).

> 징계: 리그·대회 징계 공시(경고 누적·퇴장) → **결장 hard**.

🔴 받아서 확인했다(2026-10-13):
| 주소 | 무엇 |
|---|---|
| `data.j-league.or.jp/SFIN03/` | **출장정지 선수 공지** — `選手 \\| チーム \\| 前回の停止 \\| 今回の停止 \\| 出場停止試合`(`<tr>` 20줄) |
| `data.j-league.or.jp/SFPR02/` | 경고·퇴장·출장정지(누적) |
| `data.j-league.or.jp/SFIX02/` | 등록 선수 명단 |
| `data.j-league.or.jp/SFIX05/` | 임원·스태프(감독 **이름** · 부임일은 없다) |

🔴🔴 **L2 — 이 공시는 "현재 값"이다.** 오늘의 정지 목록이므로 **운영 전용**이고
   백필·as-of 재현에는 **쓰지 않는다**(계약이 백필 도구의 import 를 센다).
🔴 왜 이 통로인가 — 검색 기준선(2026-10-13)에서 J1 결장 **재현율 10.7%** 였고,
   K리그는 공식 통로가 **빈 응답**이라 기사에 의존한다. 🔴 공시는 **S등급**이므로
   `sources.hard_ok` 를 바로 지난다(SR2).
⚠️ 이름은 **일본어 표기**다(`高 宇洋`) — 신원표(`playerid`)를 지나야 id 가 된다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 🔴 공시 주소(받아서 확인한 것만)
SUSPEND = "https://data.j-league.or.jp/SFIN03/"
CARDS = "https://data.j-league.or.jp/SFPR02/"
SQUAD = "https://data.j-league.or.jp/SFIX02/"
STAFF = "https://data.j-league.or.jp/SFIX05/"

#: 🔴 `…第９節第２日(10/10)` 의 날짜
_DAY = re.compile(r"\((\d{1,2}/\d{1,2})\)")


def suspensions(html: str) -> tuple[list[dict], str]:
    """🔴🔴 출장정지 공지 → `[{player, team, kind, day, match}]` 와 사유.

    ⚠️ 선수 칸이 **빈 줄**은 라운드 머리글이다(선수가 아니다 · 실측).
    """
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", str(html or ""), re.S)
    out: list[dict] = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        if len(cells) < 5 or cells[0] in ("選手", ""):
            continue
        got = _DAY.search(cells[4])
        out.append({"player": cells[0], "team": cells[1],
                    "prev": cells[2], "kind": cells[3],
                    "match": cells[4], "day": (got.group(1) if got else "")})
    return out, (f"출장정지 공시 — 표 {len(rows)}줄에서 선수 **{len(out)}명**"
                 + (" · 🔴 한 명도 못 읽었다" if rows and not out else ""))


def for_match(rows: list[dict], *, team_names: list[str], day: str
              ) -> tuple[list[dict], str]:
    """🔴 그 경기의 결장만 — **팀 별칭**과 **날짜**로 가린다. `(줄, 사유)`."""
    said = [str(x).strip() for x in (team_names or []) if str(x or "").strip()]
    out = [r for r in (rows or [])
           if str(r.get("day") or "") == str(day)
           and any(nm and (nm in str(r.get("team") or "")
                           or str(r.get("team") or "") in nm) for nm in said)]
    return out, (f"그 경기({day}) 출장정지 **{len(out)}명**"
                 + (f" — {', '.join(r['player'] for r in out[:5])}" if out
                    else f" · 팀 별칭 {said[:3]} 로 못 찾았다(0명)"))


async def fetch_suspensions(net) -> tuple[list[dict], str]:
    """🔴 공시를 **받아서** 읽는다(한 번에 하나의 문). `(줄, 사유)`.

    🔴 **L2** — 현재 값이다. 부르는 쪽이 **재생이 아닐 때만** 부른다.
    """
    try:
        page = await net.get(SUSPEND)
    except Exception as exc:                                # noqa: BLE001
        return [], f"🔴 출장정지 공시를 **못 받았다**: {exc!r:.60}"
    return suspensions(getattr(page, "text", "") or "")
