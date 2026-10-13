"""🔴🔴 **§2-3 감독 부임일**(통합 지시서 2026-10-13 밤 §2-3).

🔴🔴 **실측 2026-10-13 — fotmob 은 부임일을 주지 않는다.**
| 어디 | 무엇이 있나 |
|---|---|
| `/teams/<id>/overview` · `/squad` | `"coach":{"id","name","age","countryName"}` — **이름만** |
| `since`·`appointed`·`startDate` | 🔴 **0건**(두 쪽 다 세어 봤다) |

🔴 그래서 `since` 는 **기사 두 매체가 같은 날짜를 말할 때만** 선다(CO1). 못 찾으면
   **⬜** 이고, 그러면 `coach_games` 도 **못 센다**(0 으로 세지 않는다).
🔴 **L1** — `as_of` 이후 기사·경기는 안 본다. ⚠️ fotmob 의 감독은 **현재 값**이므로
   과거 재현에서는 *"그때 감독"* 이 아닐 수 있다 — 그 사실을 `why` 가 적는다(L2).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: 🔴 기사에서 날짜를 읽는 그물(`2026-07-01` · `2026년 7월 1일` · `2026/07/01`)
_DATE = re.compile(r"(20\d\d)[-/년.\s]{1,3}(\d{1,2})[-/월.\s]{1,3}(\d{1,2})")


@dataclass
class CoachRow:
    """🔴 감독 한 줄 — **수와 그 출처**를 함께 든다(지시 §2-3 꼴)."""

    team_id: str = ""
    coach: str = ""
    since: str | None = None
    source: str = ""
    why: str = ""


def _walk(box: object, key: str) -> object | None:
    """🔴 중첩된 payload 에서 그 열쇠를 **찾는다**(fotmob 이 자리를 바꾼다)."""
    if isinstance(box, dict):
        if key in box:
            return box[key]
        for v in box.values():
            got = _walk(v, key)
            if got is not None:
                return got
    elif isinstance(box, list):
        for v in box:
            got = _walk(v, key)
            if got is not None:
                return got
    return None


def row_of(*, team_id: str, payload: dict) -> CoachRow:
    """🔴 fotmob 팀 페이지 payload → `CoachRow`. **부임일은 없다**(실측)."""
    got = _walk(payload or {}, "coach")
    name = str(dict(got or {}).get("name") or "").strip() if got else ""
    if not name:
        return CoachRow(team_id=str(team_id),
                        why="🔴 fotmob 팀 페이지에서 **감독을 못 읽었다**")
    return CoachRow(
        team_id=str(team_id), coach=name, since=None, source="fotmob",
        why=(f"감독 **{name}**(fotmob) · 🔴 **부임일 없음** — fotmob 은 "
             f"`since`·`appointed`·`startDate` 를 **안 준다**(실측 2026-10-13) "
             f"→ ⬜ 기사 두 매체로만 선다 · ⚠️ 이 이름은 **현재 값**이다"
             f"(과거 재현에서는 그때 감독이 아닐 수 있다)"))


def since_of(hits: list[dict]) -> tuple[str | None, str]:
    """🔴🔴 **CO1** — 기사들의 날짜. **두 매체 이상이 같은 날**일 때만 선다.

    `hits` 한 줄: `{host, date}`(또는 `{host, text}` — 글에서 날짜를 읽는다).
    """
    by: dict[str, set[str]] = {}
    for one in list(hits or []):
        box = dict(one)
        host = str(box.get("host") or "").strip().lower()
        said = str(box.get("date") or "").strip()
        if not said:
            got = _DATE.search(str(box.get("text") or ""))
            said = (f"{got.group(1)}-{int(got.group(2)):02d}-"
                    f"{int(got.group(3)):02d}") if got else ""
        if host and said:
            by.setdefault(said, set()).add(host)
    agree = {d: hosts for d, hosts in by.items() if len(hosts) >= 2}
    if len(agree) == 1:
        day = next(iter(agree))
        return day, (f"부임일 **{day}** — 매체 {sorted(agree[day])} "
                     f"**둘 이상이 같은 날**을 말한다")
    if len(agree) > 1:
        return None, (f"⬜ **부임일 못 정했다** — 둘 이상이 말한 날짜가 **여럿**이다"
                      f"({sorted(agree)}) · 지어내지 않는다")
    return None, (f"⬜ **부임일 못 정했다** — 같은 날짜를 말한 **매체가 둘 미만**"
                  f"이다(날짜 후보 {sorted(by)}) · 추측 금지(CO1)")


def games_of(rows: list[dict], *, team: str, since: str | None, as_of
             ) -> tuple[int | None, str]:
    """🔴 `coach_games` — 부임 **뒤**, `as_of` **이전** 그 팀 리그 경기 수.

    ⚠️ 부임일이 없으면 **`None`** 이다(0 으로 세면 *"부임 첫 경기"* 라는 거짓이 된다).
    """
    if not since:
        return None, "⬜ **coach_games 못 셌다** — 부임일이 없다(CO1)"
    from app.collect import fotmob as fm
    said = fm.before_as_of(list(rows or []), as_of=as_of, key="utc")
    got = [r for r in said
           if str(r.get("utc") or "")[:10] >= str(since)[:10]
           and str(team) in (str(r.get("home") or ""), str(r.get("away") or ""))]
    return len(got), (f"부임 {since} 뒤 리그 **{len(got)}경기**(as-of 이전)")
