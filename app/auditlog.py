"""🔴🔴 **총평 검열 기록**(사용자 지시 2026-10-07 §4-4).

> 검열 결과(통과/재작성 후 통과/템플릿)와 위반 종류를 **경기별로 저장**. 운영자
> `/상태` 에 최근 20경기 **검열 통과율**과 **위반 상위 3종**.

🔴 파일 하나다 — `var/audit/log.jsonl`(한 줄 한 경기). ⚠️ DB 를 쓰지 않는다: 이
   기록은 **운영자용 셈**이고 판정에 닿지 않는다(원장으로 규칙을 고치지 않는다와
   같은 선 — 이 줄들은 **읽어서 세는 것뿐**이다).
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "var/audit/log.jsonl"
#: 🔴 `/상태` 가 세는 경기 수(§4-4 원문)
RECENT = 20
#: 🔴 위반 종류를 **글자에서** 뽑는 꼴 — `(d)`·`(모델)` 처럼 앞머리에 붙는다
KIND = re.compile(r"\((?:[a-h]|모델)\)")


def kind_of(said: str) -> str:
    """🔴 위반 줄 → **종류**(`(d)`·`(모델)`·`기타`)."""
    got = KIND.search(str(said or ""))
    return got.group(0) if got else "기타"


def add(*, match: str, audit: str, violations: list[str], shape: str = "",
        when: datetime | None = None) -> None:
    """🔴 한 경기의 검열 결과를 남긴다. ⚠️ 실패해도 **카드를 막지 않는다**."""
    row = {"at": (when or datetime.now(timezone.utc)).isoformat(),
           "match": str(match), "audit": str(audit), "shape": str(shape),
           "kinds": sorted({kind_of(x) for x in violations}),
           "violations": [str(x)[:200] for x in violations[:12]]}
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        with PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:                                   # noqa: BLE001
        logger.warning("[audit] 기록 못 했다 — %r", exc)


def rows(limit: int = RECENT) -> list[dict]:
    """🔴 최근 줄들(새것부터). ⚠️ 파일이 없으면 **빈 목록**이다."""
    if not PATH.exists():
        return []
    out: list[dict] = []
    for line in PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[-limit:][::-1]


def stats(limit: int = RECENT) -> str:
    """🔴🔴 `/상태` 한 토막 — **통과율**과 **위반 상위 3종**(§4-4).

    ⚠️ 0건이면 *"기록이 없다"* 라고 적는다(빈 줄은 *"다 통과했다"* 로 읽힌다 · #3).
    """
    got = rows(limit)
    if not got:
        return "🧭 총평 검열 — **기록이 없다**(아직 검열한 경기가 없다)"
    ok = sum(1 for r in got if str(r.get("audit", "")).endswith("통과"))
    tally: dict[str, int] = {}
    for r in got:
        for k in (r.get("kinds") or []):
            tally[k] = tally.get(k, 0) + 1
    top = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    first = sum(1 for r in got if r.get("audit") == "통과")
    return (f"🧭 총평 검열 — 최근 {len(got)}경기 통과율 **{ok / len(got):.0%}**"
            f"(1회차 {first} · 재작성 후 {ok - first} · 템플릿 {len(got) - ok})\n"
            f"   위반 상위: "
            + (" · ".join(f"`{k}` {v}건" for k, v in top) or "없다"))
