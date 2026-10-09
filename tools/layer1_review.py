"""🔴🔴 **1겹 카드 검수** — 사용자 지시 2026-10-09(3차) §6.

> 녹화 재생으로 대전–전북, 미국–캐나다, 멕시코–칠레, 카자흐–페로의 **새 1겹 카드
> 전문**을 붙여라. 경기마다: 헤드라인, 이유 문단, 각 문장의 `fact_refs`,
> 검열 결과(i~l), 글자 수.

```
PYTHONPATH=. python tools/layer1_review.py                 # 표의 네 경기 전부
PYTHONPATH=. python tools/layer1_review.py dj_jb_1         # 하나만
```

🔴 **라이브에 안 간다** — 카세트 재생이고, 없는 요청은 `replay_miss` 로 실패한다
   (§5 *"라이브는 검수에만"* 과 같은 규율).
⚠️ 이 도구는 **보여 주기만** 한다 — 수를 고치지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

#: 🔴 검수할 경기 — `(실행 id, 질문)`. ⚠️ 질문은 **녹화 때 쓴 글자 그대로**여야
#   같은 카세트 열쇠가 나온다(열쇠에 질문이 들어간다).
RUNS: tuple[tuple[str, str], ...] = (
    ("dj_jb_1", "전북 현대 vs 대전 하나시티즌"),
    # 🔴 옛 녹화본은 `_1`(경기 찾기)·`_2`(나머지)로 **쪼개져 있다** — 합친 폴더를
    #    `CASSETTE_DIR` 로 가리켜 재생한다. ⚠️ 질문 글자는 **녹화 때 쓴 것**이어야
    #    한다(열쇠에 질의가 들어간다 · 실측: `us_ca_1` 에 `espn 미국 캐나다 match`
    #    질의가 있어 그때 한국어로 물었음을 안다).
    ("us_ca_m", "미국 vs 캐나다"),
    ("mx_cl_m", "멕시코 vs 칠레"),
    ("kz_fo_m", "카자흐스탄 vs 페로 제도"),
)


async def one(run_id: str, asked: str) -> int:
    """🔴 한 경기 — 재생으로 카드를 만들고 1겹과 검수 표를 찍는다."""
    from app import cassette
    os.environ[cassette.MODE_ENV] = cassette.REPLAY
    os.environ[cassette.RUN_ENV] = run_id
    os.environ.pop(cassette.FALLTHROUGH_ENV, None)
    os.environ.setdefault(cassette.MATCH_ENV, asked)

    from app import net as _net_mod
    from app import search as _search
    from app.config import get_settings
    from app.core import layer1, pipeline, render
    from app.core.schema import Ambiguous
    from app.core.stages import s9_audit
    from app.db import get_pool

    print("=" * 70)
    print(f"🔴 {run_id} — `{asked}`")
    print("=" * 70)
    pool = await get_pool(get_settings().database_url)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **녹화 시각으로 재생한다**(실사고 2026-10-09)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 그냥 재생하니 옛 카세트 셋이 `match_not_found` 로 떨어졌다 — 카세트가
    #     나쁜 것이 아니라 **경기가 지났다**(창 검사가 거부한다).
    #  🔴 그래서 `now` 를 **카세트가 적어 둔 `recorded_at`** 으로 준다. 시각을
    #     우리가 고르지 않는다 — 녹화본이 말하는 값이다.
    at = recorded_at(run_id)
    if at is not None:
        print(f"[검수] 재생 시각 — 녹화본의 `recorded_at` {at:%Y-%m-%d %H:%M}Z")
    got = await pipeline.analyze(asked, pool=pool, net=_net_mod.Net(),
                                 chain=_search.build_chain(), now=at)
    if isinstance(got, Ambiguous):
        print(f"🔴 경기를 확정하지 못했다 — {got.why}")
        return 1
    said = render.layer1_text(got)
    print(said)
    print("-" * 70)
    print(f"[검수] 헤드라인 — {layer1.headline(got)}")
    print(f"[검수] 방향 쪽 — {layer1.dir_side(got) or '반반'}")
    body = layer1.reason_text(got)
    print(f"[검수] 이유 문단 {len(body)}자 (상한 {layer1.CAP_REASON}) "
          f"{'✓' if len(body) <= layer1.CAP_REASON else '🔴 ✗'}")
    rows = list(getattr(got.reason, "sentences", None) or [])
    box = layer1.facts_catalog(got)
    for i, line in enumerate(rows, start=1):
        refs = [str(x) for x in (line.fact_refs or [])]
        unknown = [r for r in refs if r not in box]
        print(f"  {i}. {line.text}")
        print(f"     fact_refs: {refs or '**없다**'}"
              + (f" · 🔴 카드에 없는 id {unknown}" if unknown else ""))
    bad = s9_audit.reason_check(got.reason, card=got)
    print(f"[검수] 검열(i~l) — {'통과' if not bad else f'위반 {len(bad)}건'}")
    for x in bad:
        print(f"     🔴 {x}")
    print(f"[검수] 카드가 적은 검열 결과 — {got.reason_audit}"
          + (f" · 위반 {len(got.reason_violations)}건"
             if got.reason_violations else ""))
    # 🔴 **작성자가 왜 떨어졌나** — 수를 세는 것이 아니라 글자를 봐야 고친다
    for x in (got.reason_violations or []):
        print(f"     ↳ 작성/재작성 위반: {x}")
    print(f"[검수] 1겹 전체 {len(said)}자 (상한 {layer1.CAP_ALL}) "
          f"{'✓' if len(said) <= layer1.CAP_ALL else '🔴 ✗'}")
    print(f"[검수] 사실 목록 {len(box)}건 · 종류 "
          f"{sorted({v['kind'] for v in box.values()})}")
    return 0


def recorded_at(run_id: str):
    """🔴 그 녹화본이 적어 둔 **가장 이른 `recorded_at`**. 없으면 `None`.

    ⚠️ 시각을 **우리가 고르지 않는다** — 녹화본의 값이다(재계산은 재생이 아니다).
    """
    import json
    import pathlib as _pl
    from datetime import datetime

    from app import cassette
    root = cassette.root() / "nomatch" / run_id
    best = None
    for f in sorted(_pl.Path(root).glob("*.json")) if root.is_dir() else []:
        try:
            said = str(json.loads(f.read_text(encoding="utf-8"))
                       .get("recorded_at") or "")
        except (ValueError, OSError):
            continue
        if not said:
            continue
        try:
            when = datetime.fromisoformat(said.replace("Z", "+00:00"))
        except ValueError:
            continue
        if best is None or when < best:
            best = when
    return best


async def main(argv: list[str]) -> int:
    want = [x for x in argv[1:] if not x.startswith("-")]
    rows = [r for r in RUNS if not want or r[0] in want]
    if not rows:
        print(f"쓰는 법: tools/layer1_review.py [{' | '.join(r[0] for r in RUNS)}]")
        return 2
    rc = 0
    for run_id, asked in rows:
        try:
            rc |= await one(run_id, asked)
        except Exception as e:                               # noqa: BLE001
            print(f"🔴 {run_id} 터졌다 — {type(e).__name__}: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    raise SystemExit(asyncio.run(main(sys.argv)))
