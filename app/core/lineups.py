"""🔴🔴 **라인업 사다리** — 사용자 지시 2026-10-10 A.

> 라인업과 *"새로 나온 사실"* 이 승패를 가른다. … 라인업은 **출처가 없어서 못 받고**.
> 목표: **확정 라인업으로 판정한다.**

사다리 표는 `config/lineup_sources.yaml` 의 `ladder` 다(A-1) — 거기에 출처마다
`robots`·`약관`·확인일·**실측 결과**가 적혀 있다. 🔴 이 파일에 주소를 적지 않는다.

🔴 **망에 나가지 않는다** — `app/core/` 는 망 금지(§7 계약)이고 수집은
   `app/collect/` 다. ⚠️ 처음에 여기에 `urllib` 를 썼다가 그 계약이 빨개졌다.
🔴 **관찰하지 않은 엔드포인트를 쓰지 않는다**(금지 조항) — 표의 `use: false` 는
   건너뛰고, 그 까닭이 `why` 에 있다.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

CONF = "config/lineup_sources.yaml"


def table() -> dict:
    """🔴 사다리 표 — `config/lineup_sources.yaml` 의 `ladder` 하나다."""
    from app import rules
    return dict((rules._load(CONF) or {}).get("ladder") or {})


def ladder(comp_key: str = "") -> list[dict]:
    """🔴 그 리그의 사다리 — `리그별 + 기본` 순서. `use: false` 는 **뺀다**.

    ⚠️ 표에 없는 리그는 기본 사다리만 쓴다 — 그 사실이 `none_line` 에 남는다.
    """
    from app.core import competition as comp
    box = table()
    short = comp.short_key(comp_key) if comp_key else ""
    mine = list((box.get("leagues") or {}).get(short) or [])
    return [dict(x) for x in [*mine, *list(box.get("default") or [])]
            if dict(x).get("use")]


def skipped(comp_key: str = "") -> list[tuple[str, str]]:
    """🔴 **쓰지 않는 출처와 까닭**(`use: false`) — 카드·보고가 이것을 적는다.

    ⚠️ 막힌 출처를 조용히 빼면 *"출처가 원래 없다"* 로 읽힌다(#3).
    """
    from app.core import competition as comp
    box = table()
    short = comp.short_key(comp_key) if comp_key else ""
    rows = [*list((box.get("leagues") or {}).get(short) or []),
            *list(box.get("default") or [])]
    return [(str(x.get("id")), str(x.get("why") or x.get("measured") or ""))
            for x in map(dict, rows) if not x.get("use")]


def checked_at() -> str:
    """🔴 사다리를 **언제 확인했나**(A-1 마지막 줄 — 표가 든다)."""
    return str(table().get("checked_at") or "")


def status_line(*, state: str, source: str, when: datetime | None = None) -> str:
    """🔴🔴 A-3 — `📋 라인업 {확정|예상|없음} · 출처 {이름} · {HH:MM}`."""
    from app import timefmt
    at = f" · {timefmt.kst(when):%H:%M}" if when is not None else ""
    return f"📋 라인업 {state} · 출처 {source or '없음'}{at}"


def none_line(comp_key: str = "") -> str:
    """🔴 A-3 둘째 줄 — 선발을 하나도 못 받았을 때 **무엇을 돌았는지** 적는다."""
    from app.core import competition as comp
    rows = ladder(comp_key)
    short = comp.short_key(comp_key) or "그 리그"
    if not rows:
        return (f"🔴🔴 **XI 출처 없음** — `{short}` 에 **등록된 출처 0** "
                f"(`{CONF}` 의 `ladder` 에 넣어야 한다)")
    said = " → ".join(str(x.get("id")) for x in rows)
    out = (f"🔴🔴 **XI 출처 없음** — `{short}` 사다리 {len(rows)}칸({said})을 "
           f"다 돌았는데 선발을 못 받았다 · 확인일 {checked_at()}")
    off = skipped(comp_key)
    if off:
        out += (" · ⚠️ **막혀서 쓰지 않는 출처**: "
                + " · ".join(f"`{i}`" for i, _w in off))
    return out


def grade_word(confirmed: bool, grade: str) -> str:
    """🔴🔴 A-4 — **확정 XI 전 등급은 `잠정`** 이다.

    > 확정 XI 전 등급은 *"잠정"* 으로만 보이고 … 등급 확정은 확정 XI 뒤
    > 재분석에서만. (사용자 원칙: **라인업 없는 경기의 등급은 의미가 없다**.)
    """
    said = str(grade or "")
    if confirmed or said in ("없음", "보류", "자료부족"):
        return said
    return f"잠정 {said}"


def conclusion_prefix(confirmed: bool) -> str:
    """🔴 A-4 — 확정 XI 전 **결론 줄 머리말**."""
    return "" if confirmed else "⏳ **라인업 전 — 잠정 판단** · "
