"""🔴🔴 **경기 열쇠** — v5 §8-1. `출처:경기ID`. [M30]

> 팀 열쇠는 봇이 한 번 발급하는 뜻 없는 번호(`team:000273`)… **경기 열쇠는
> `출처:경기ID`**(`fotmob:5181853`, `statsapi:…`).

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 의 열쇠들
══════════════════════════════════════════════════════════════════

```
nhl-2026020021   npb-…   fotmob-5181780   tsdb-…
849825           🔴 **MLB 는 접두가 아예 없다** — 이 열쇠는 출처를 말하지 못한다
```
⚠️ 그래서 `ingest.adapter_of(ext_id=…)` 가 MLB 행을 **라우팅하지 못했다**
   (실측: `_sport_from_ext('849825')` → `''`). 열쇠가 출처를 말해야 깊이 소스를
   고를 수 있다 — §8-1 이 그것을 못 박았다.

⚠️ **쌓인 행이 있다** — 읽기는 **두 꼴 다**, 쓰기는 **새 꼴만**. 이관이 끝났는지는
   `is_canonical` 로 **숫자로** 본다(#3 조용한 0 금지).
"""
from __future__ import annotations

import re

#: 🔴 §8-1 이 이름 댄 출처. ⚠️ 여기 없는 출처는 **거부한다** — 오타난 출처가
#   조용히 들어오면 라우팅이 그 행을 영영 못 찾는다.
SOURCES: tuple[str, ...] = ("fotmob", "statsapi", "nhl", "npb", "tsdb",
                            "fdorg", "espn", "kleague")

#: 🔴 새 꼴. ⚠️ 경기 ID 에 `:` 가 들어올 수 있으므로 **처음 하나**로만 가른다.
_CANON = re.compile(r"^([a-z][a-z0-9_]*):(.+)$")

#: ⚠️ 옛 꼴 — `fotmob-5181780`. 🔴 출처가 `SOURCES` 에 있을 때만 그렇게 읽는다
#   (팀 이름에 하이픈이 있는 열쇠를 잘못 쪼개지 않게).
_LEGACY = re.compile(r"^([a-z][a-z0-9_]*)-(.+)$")


def make(source: str, match_id: object) -> str:
    """🔴 `출처:경기ID`. ⚠️ 모르는 출처·빈 ID 는 **거부한다**."""
    src = str(source or "").strip().lower()
    mid = str(match_id if match_id is not None else "").strip()
    if src not in SOURCES:
        raise ValueError(
            f"🔴 모르는 **출처**다: {source!r} — §8-1 이 이름 댄 것은 "
            f"{list(SOURCES)}. 오타난 출처는 라우팅이 영영 못 찾는다")
    if not mid:
        raise ValueError(f"🔴 **경기 ID** 가 비었다(출처 {src!r})")
    return f"{src}:{mid}"


def parse(key: object) -> tuple[str, str]:
    """🔴 열쇠 → `(출처, 경기ID)`. ⚠️ 출처를 못 알면 `("", 그대로)`.

    🔴 **옛 꼴도 읽는다**(`fotmob-5181780`) — 쌓인 행을 깨뜨리지 않는다.
    ⚠️ 접두 없는 숫자(`849825` · MLB)는 출처가 **빈 문자열**이다. 그것이 사실이고,
       숨기지 않는다 — 그 행은 라우팅이 못 찾는다는 뜻이다.
    """
    raw = str(key or "").strip()
    if not raw:
        return "", ""
    m = _CANON.match(raw)
    if m and m.group(1) in SOURCES:
        return m.group(1), m.group(2)
    m = _LEGACY.match(raw)
    if m and m.group(1) in SOURCES:
        return m.group(1), m.group(2)
    return "", raw




def source_of(key: object) -> str:
    """⚠️ 출처만. 🔴 못 알면 빈 문자열(그 행은 라우팅이 못 찾는다)."""
    return parse(key)[0]




def mine(key: object, source: str, *, bare_ok: bool = False) -> str:
    r"""🔴🔴 **내 출처의 열쇠면 경기 ID, 아니면 빈 문자열.**

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 — **이관이 깊이를 통째로 끊었다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    어댑터마다 열쇠를 **자기 방식으로** 떼고 있었다:

    ```python
    mlb      if not pk.isdigit(): return []        # `statsapi:849825` 탈락
    espn     if not raw.startswith("espn-")        # `espn:401` 탈락
    fotmob   if not raw.startswith("fotmob-")      # `fotmob:5181` 탈락
    npb      re.match(r"npb-(\d{4})\d{4}-", …)     # `npb:2026…` 탈락
    nhl      raw.split("-")[-1]                   # `nhl:2026020021` 탈락
    ```

    🔴 `keymigrate` 가 45건을 `출처:ID` 로 옮긴 **직후** 깊이가 0 이 됐다:

        · 세포 Milwaukee Brewers:깊이: 공식 깊이 소스가 없다
          verified_vars: 6 → **0**

    ⚠️ 그리고 그 빈 목록이 **거짓 사유**까지 낳았다 — *"어댑터에
       `sources_context` 가 없다"*. **있다.** 빈 목록을 냈을 뿐이다(§8-6).

    🔴 §11-1 — **증상이 아니라 모양을 고친다.** 열쇠를 떼는 일은 **여기 한 곳**
       이고, 어댑터는 *"내 것이냐"* 만 묻는다.

    ══════════════════════════════════════════════════════════════════
    🔴 **맨숫자 열쇠는 기본이 거절이다** — `bare_ok` 로만 받는다
    ══════════════════════════════════════════════════════════════════

    ⚠️ 처음에 *"출처를 못 읽는 열쇠는 내 것으로 본다"* 로 짰다. 🔴 그러자
       `fotmob`·`espn` 이 **MLB 의 맨숫자 `849844`** 를 자기 것으로 집어
       야구 경기에 축구 페이지를 붙였다(계약 둘이 그 자리에서 터졌다 ·
       §17-g-3 *"남의 경기다"*).

    🔴 어댑터마다 **옛 꼴이 달랐다**:

        statsapi  `849825`         ← 맨숫자가 **그 어댑터의 옛 꼴**이다
        fotmob    `fotmob-5181853` ← 맨숫자는 **남의 것**이다
        espn      `espn-401`       ← 같다
        nhl       `nhl-2026020021` ← 같다
        npb       `npb-20261004-…` ← 같다

    ⚠️ 그래서 맨숫자를 받을지는 **어댑터가 정한다** — 그 어댑터의 옛 꼴이
       맨숫자였을 때만 `bare_ok=True`.
    """
    said, mid = parse(key)
    if said and said != str(source or ""):
        return ""
    if not said and not bare_ok:
        # 🔴 출처가 **안 적혀 있다** — 남의 열쇠일 수 있다. 거절한다.
        return ""
    return mid
