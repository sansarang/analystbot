"""🔴🔴 **§6-1 원천 표** — 리그·대회마다 등급을 **표에서** 읽는다.

> S(공식) · A(통신·주요지) · B(데이터) · C(기타 · 단독 근거 불가).
> 계약 **SR1**: 표에 **없는 도메인은 C등급** · **SR2**: S·A 없이 C등급만으로
> **hard 사실**을 만들면 실패.

🔴 표는 `config/sources/<리그>.yaml` **하나**다 — 코드에 도메인을 적지 않는다
   (사본 금지 · #1). ⚠️ `robots_checked` 가 빈 칸이면 **확인하지 않은 것**이다.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3] / "config/sources"

#: 🔴 등급 순서 — 높은 쪽이 먼저다(질의·판정이 이 순서를 쓴다)
ORDER: tuple[str, ...] = ("S", "A", "B", "C")


@lru_cache(maxsize=32)
def table(league: str) -> dict:
    """🔴 그 리그의 원천 표. 없으면 **빈 표**(그러면 전부 C 다)."""
    import yaml
    path = ROOT / f"{str(league or '').replace(':', '_')}.yaml"
    if not path.exists():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _host(said: str) -> str:
    got = str(said or "").strip().lower()
    got = got.split("//")[-1].split("/")[0]
    return got[4:] if got.startswith("www.") else got


def rows_of(league: str, grade: str) -> list[dict]:
    """🔴 그 등급의 줄들(`domain`·`lang`·`what`·`robots_checked`)."""
    said = table(league).get(str(grade).upper())
    out: list[dict] = []
    for one in list(said or []):
        box = dict(one) if isinstance(one, dict) else {"domain": str(one)}
        if str(box.get("domain") or "").startswith("⬜"):
            continue                  # ⬜ 미조사 칸은 **질의에 쓰지 않는다**
        out.append(box)
    return out


def grade_of(url: str, *, league: str) -> tuple[str, str]:
    """🔴🔴 **SR1** — 그 도메인의 등급. 표에 없으면 **C** 와 그 사유."""
    host = _host(url)
    if not host:
        return "C", "🔴 도메인을 못 읽었다 — C등급으로 본다"
    for grade in ORDER[:-1]:
        for one in rows_of(league, grade):
            got = _host(str(one.get("domain") or ""))
            if got and (host == got or host.endswith("." + got)):
                return grade, (f"{grade}등급(`{got}` · robots 확인 "
                               f"{one.get('robots_checked') or '⬜'})")
    return "C", (f"🔴 `{host}` 는 **원천 표에 없다**(`config/sources/`) → "
                 f"**C등급**이고 단독 근거로 쓰지 않는다(SR1)")


def hard_ok(grades: list[str], *, league: str) -> tuple[bool, str]:
    """🔴🔴 **SR2** — `hard` 사실을 세울 수 있나(S·A 가 **하나라도** 있어야 한다)."""
    said = [str(g).upper() for g in (grades or [])]
    good = [g for g in said if g in ("S", "A")]
    if good:
        return True, f"등급 {sorted(set(good))} 가 있다 — hard 로 세울 수 있다"
    return False, (f"🔴 **C등급(또는 B)만이다**({sorted(set(said)) or '없다'}) — "
                   f"hard 사실로 만들지 않는다(SR2 · `{league}`)")
