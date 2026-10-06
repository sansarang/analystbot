"""eloratings.net — **국가대표 Elo 와 과거 경기 결과**(네 층 지시서 §3).

## 🔴 왜 이 출처인가

> 국가대표 경기에서 두 팀 Elo 차이는 결과 예측에 가장 유용한 변수 중 하나다
> (네 층 지시서 §3 근거).

실측 2026-10-06 — 이 사이트는 **TSV 를 그대로 준다**(자바스크립트 뒤에 숨지 않는다):

```
/World.tsv            31열 · 3열 ISO2 코드 · 4열 현재 등급     (KR 1722 · UZ 1653)
/en.teams.tsv         ISO2 → 이름(별칭 여러 개)
/{연}_results.tsv     16열 · 과거 경기 — **경기 전 등급**이 11·12열에 있다
```

🔴 `{연}_results.tsv` 가 이 파일의 진짜 값이다 — **적합 자료**다. 9열(개최국)이
   비면 홈 개최, 차면 그 나라에서 열렸다(중립). 8열이 `F`·`FFS` 면 친선이다.
⚠️ 홈 보정 값은 **이 출처가 말하지 않는다**(실측: `/about` 은 JS, `ratings.js` 에
   없다). 🔴 그래서 흔히 인용되는 100 점을 적지 않고 **적합으로 잰다**.

⚠️ `robots.txt` 는 404 다 → `allow`(§4-7). UA 는 봇이라고 밝힌다(절대규칙 3).
"""
from __future__ import annotations

import logging
from datetime import date

from app import rules

logger = logging.getLogger(__name__)

#: 🔴 출처 표가 원본이다 — 경로를 코드에 박지 않는다(#1)
SOURCE = "eloratings_net"

#: 🔴 친선 대회 코드(8열) — `F` 단판 친선 · `FFS` 친선 대회(실측 2026-10-06)
#   ⚠️ 과거 경기 줄(`{연}_results.tsv`)을 **읽는 코드는 여기 없다** —
#      `tools/fit_base_model.py` 안에 있다. 🔴 네 층 지시서 §3-2 가 *"실행 중 적합
#      금지"* 라서 봇 경로에 적합 재료를 두지 않는다(그 길 자체를 없앤다).
FRIENDLY_CODES = ("F", "FFS")


def base_url() -> str:
    """🔴 출처 표의 `base_url`. ⚠️ 표에서 금지면 **빈 문자열**이다."""
    row = rules.rating_source(SOURCE)
    return str(row.get("base_url") or "") if row.get("allowed") else ""


def file_of(name: str, *, year: int | None = None) -> str:
    """🔴 출처 표의 `files` 칸 → URL. `{year}` 는 여기서만 메운다."""
    row = rules.rating_source(SOURCE)
    rel = str((row.get("files") or {}).get(name) or "")
    base = base_url()
    if not rel or not base:
        return ""
    if year is not None:
        rel = rel.replace("{year}", str(year))
    return base.rstrip("/") + rel


def parse_ratings(text: str) -> dict[str, float]:
    """🔴 `World.tsv` → `{ISO2: 등급}`. ⚠️ 열 번호는 **출처 표**가 든다.

    실측 2026-10-06: `38 38 KR 1722 …` — 3열 코드, 4열 등급.
    """
    out: dict[str, float] = {}
    for line in text.splitlines():
        col = line.split("\t")
        if len(col) < 4:
            continue
        code, said = col[2].strip(), col[3].strip()
        if len(code) != 2 or not code.isalpha():
            continue
        try:
            out[code.upper()] = float(said)
        except ValueError:
            continue
    return out


async def ratings(net, *, when: date | None = None) -> tuple[dict[str, float], str]:
    """🔴 현재 등급표를 받는다. `(표, 사유)` — ⚠️ 못 받으면 **빈 표와 사유**다.

    🔴 하루 1회면 된다(§3 캐시) — 호출부가 날짜로 캐시한다.
    """
    url = file_of("ratings")
    if not url:
        return {}, f"출처 표가 `{SOURCE}` 를 막았거나 경로가 없다"
    ok, why = await net.allowed(url)
    if not ok:
        return {}, f"robots 가 막았다 — {why}"
    got = await net.get(url)
    body = getattr(got, "text", "") or ""
    if not body:
        return {}, f"본문이 비었다(HTTP {getattr(got, 'status', '?')})"
    table = parse_ratings(body)
    if not table:
        return {}, "TSV 를 읽었지만 등급 줄이 0건이다 — 형식이 바뀐 것 같다"
    logger.info("[elo] 등급 %d개 ← %s", len(table), url)
    return table, f"{len(table)}개 ← eloratings.net(받은 날 {when or date.today()})"
