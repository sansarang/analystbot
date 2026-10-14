"""🔴🔴 **재생 덤프를 한 곳에서 읽는다** — 목록을 손으로 들지 않는다(#1).

```python
from replays import load
rows, why = load()                 # 전부(서로 다른 경기만)
rows, why = load(league="league:PD")
```

🔴 **왜** — 덤프 목록을 손으로 든 자리가 **셋**이었다(`build_grids.rows_of` ·
   `fit_offsets.DOMESTIC` · `comp_ready`). 새 리그를 받을 때마다 세 곳을 고쳐야
   했고, 한 곳만 고치면 그 리그가 **조용히 빠졌다**(실측: 준비 점검표가 챔피언십
   500경기를 *"재생 0"* 으로 적었다).
🔴 **같은 경기를 두 번 세지 않는다** — 덤프끼리 겹친다(`replay_444`·`replay_big`
   ·`replay_big2`·`replay_fix` 에 J1·K1 이 다 들어 있고, `replay_mls3` 는
   `replay_mls` 를 품는다). 열쇠는 `(리그, 날짜, 홈, 원정)` 이다.
⚠️ **큰 덤프가 이긴다** — 같은 경기가 두 덤프에 있으면 **줄이 더 많은 덤프**의
   줄을 남긴다(그쪽이 더 최근 재생이고 시즌 꼬리표·λ 가 채워져 있다).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "var/judge"


def files() -> list[Path]:
    """🔴 `var/judge/replay_*.json` — **줄이 많은 덤프가 먼저**(그쪽이 이긴다).

    🔴 **원본은 `app/core/domesticelo` 다**(수정 지시 2026-10-14 1번) — 적합과
       운영이 같은 함수를 써야 해서 `app/` 으로 옮겼다. 여기서 다시 짜지 않는다.
    """
    from app.core.domesticelo import files as _files
    return _files()


def load(*, league: str = "") -> tuple[list[dict], str]:
    """🔴 서로 다른 경기만 담은 재생 줄 + **어느 덤프가 몇 줄을 보탰나**.

    🔴 **원본은 `app/core/domesticelo.load` 다**(사본 금지 · 위 `files` 머리말).
    """
    from app.core.domesticelo import load as _load
    return _load(league=league)
