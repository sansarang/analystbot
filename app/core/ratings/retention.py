"""🔴🔴 **§2-4 선수단 잔류율**(통합 지시서 2026-10-13 밤).

> 지난 시즌 팀 리그 출전 분 중, `as_of` 시점 이번 시즌 그 팀 출전 기록에 있는
> 선수의 **분 비율** = `retention ∈ [0,1]`.

🔴 왜 — 코번트리(승격)·뉴캐슬(선수단 대폭 교체) 같은 팀은 **지난 시즌 자료가
   이번 시즌 팀을 잘못 말한다**. 잔류율은 *"지난 시즌 자료를 얼마나 믿을 수 있나"*
   를 **분으로** 센다.
🔴 **RT1** — 이번 시즌 출전은 `as_of` **이전**만 본다(문은 `before_as_of` 하나).
⚠️ 지난 시즌 자료가 없으면 **`None` + 사유**다(0 으로 적으면 *"전원 이탈"* 이라는
   거짓말이 된다 · #3). 승격·신생 팀은 그 사실을 사유가 **이름으로** 적는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _minutes(row: dict, team: str) -> dict:
    """🔴 그 경기에서 **그 팀 선수의 분**. 어느 쪽인지는 팀 이름이 가른다."""
    said = dict(row or {})
    if str(said.get("home") or "") == str(team):
        return dict(said.get("home_minutes") or {})
    if str(said.get("away") or "") == str(team):
        return dict(said.get("away_minutes") or {})
    return {}


def of(rows: list[dict], *, team: str, as_of, league: str
       ) -> tuple[float | None, str]:
    """🔴🔴 그 팀의 잔류율. `(값 또는 None, 사유)`.

    `rows` 한 줄: `{utc, league, home, away, home_minutes, away_minutes}`.
    """
    from app.collect import fotmob as fm
    from app.core import season as _se
    want, why_now = _se.id_of(league=league, when=as_of)
    if not want:
        return None, why_now
    said = _se.tag(fm.before_as_of(list(rows or []), as_of=as_of, key="utc"),
                   when_key="utc")
    mine = [r for r in said
            if str(team) in (str(r.get("home") or ""),
                             str(r.get("away") or ""))]
    now = [r for r in mine if str(r.get("season_id") or "") == want]
    past = [r for r in mine if str(r.get("season_id") or "") < want]
    if not past:
        return None, (f"⬜ **잔류율 못 쟀다** — `{team}` 의 **지난 시즌 자료가 "
                      f"없다**(이번 시즌 `{want}` {len(now)}경기) → **승격/신생 "
                      f"팀**이거나 받은 목록이 그 시즌을 안 덮는다")
    prev = sorted({str(r.get("season_id") or "") for r in past})[-1]
    old: dict[str, float] = {}
    for r in [x for x in past if str(x.get("season_id") or "") == prev]:
        for pid, mins in _minutes(r, team).items():
            old[str(pid)] = old.get(str(pid), 0.0) + float(mins or 0.0)
    if not old:
        return None, (f"⬜ **잔류율 못 쟀다** — 지난 시즌 `{prev}` 의 **출전 분이 "
                      f"없다**(경기 {len(past)}건은 있다)")
    stay: set[str] = set()
    for r in now:
        stay |= {str(p) for p, m in _minutes(r, team).items()
                 if float(m or 0.0) > 0}
    kept = sum(v for k, v in old.items() if k in stay)
    total = sum(old.values())
    got = max(0.0, min(1.0, kept / total)) if total > 0 else None
    if got is None:
        return None, f"⬜ **잔류율 못 쟀다** — 지난 시즌 `{prev}` 분 합이 0 이다"
    return got, (f"잔류율 **{got:.2f}** — 지난 시즌 `{prev}` 출전 분 {total:,.0f}분 중"
                 f" **{kept:,.0f}분**이 이번 시즌 `{want}`({len(now)}경기)에 남았다"
                 f"(선수 {len(stay)}명 확인)")
