"""🔴🔴 **§6-2 새 질의를 실제로 던져 본다**(지시서 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/query_probe.py --n 3
```

> 질의 로그(경기별 질의 목록·결과 수) — 계약 **QY2**.

🔴 **왜** — 기준선(§6-7)은 결장 재현율 **16.3%** 였고 손실 깔때기는 ④ 신원
   52.9%(그 중 **잘못 버림 1%**) · ② 질의·날짜 34% 였다. 즉 **맞는 기사를 애초에
   못 찾는다** → 새 질의(현지어·별칭·원천 지정)가 **더 찾아오나**를 센다.
🔴 검색은 **운영과 같은 사다리**(`search.build_chain`)로 던진다 — 별도 통로를
   만들지 않는다. ⚠️ 받은 결과 수만 센다(본문은 §6-3 의 일이다).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 리그 열쇠를 카드의 리그 글자에서 찾는 문은 `competition.key_of` 하나다
CARD_N = 3


async def main(argv: list[str]) -> int:
    from search_quality import cards

    from app import search as _se
    from app.core import competition as _cp
    from app.core.search import query as qy
    from app.core.search import sources as sr
    n = CARD_N
    for a in argv[1:]:
        if a.startswith("--n"):
            n = int(a.split("=", 1)[1] if "=" in a else argv[argv.index(a) + 1])
    # 🔴 원천 표가 **있는 리그**의 카드부터 본다(없는 리그는 QY1 이 막는다 —
    #    그 사실은 §5-1 점검표가 이미 적는다)
    from app.core import competition as _cp0
    from app.core.search import sources as _sr0
    said_all = [c for c in cards(0) if any(c["claims"].values())]
    box = [c for c in said_all
           if _sr0.table(_cp0.key_of(competition=c["league"])[0] or "")]
    print(f"🔴 카드 {len(said_all)}장 중 **원천 표가 있는 리그 {len(box)}장**"
          f"(없는 리그는 질의를 만들지 않는다 · QY1)")
    chain = _se.build_chain(operational=False)
    print("# 🔴🔴 §6-2 새 질의 — 실제로 던져 본 결과")
    print()
    print(f"검색 사다리 — {'쓸 수 있다' if chain.available else '🔴 **못 쓴다**'}")
    print()
    for one in box[:n]:
        key, why_key = _cp.key_of(competition=one["league"])
        print(f"## {one['home']} vs {one['away']} · `{one['league']}` → "
              f"`{key or '⬜'}`")
        print()
        if not key or not sr.table(key):
            print(f"- 🔴 **원천 표가 없다**(`{key or '?'}`) — 질의를 만들지 "
                  f"않는다(QY1) · {why_key[:50]}")
            print()
            continue
        log = qy.Log()
        got, why = qy.build(league=key, home=one["home"], away=one["away"],
                            players=[], coach="",
                            kinds=("absence", "expected_xi"), log=log)
        print(f"- {why}")
        hits_all = docs = 0
        for q in got:
            try:
                said = await chain.query(q["q"], lang=q["lang"])
            except Exception as exc:                        # noqa: BLE001
                log.note(q["q"], hits=0)
                print(f"    · 🔴 `{q['q'][:48]}` — 실패 {exc!r:.40}")
                continue
            log.note(q["q"], hits=len(said))
            hits_all += len(said)
            docs += sum(1 for h in said
                        if sr.grade_of(str(getattr(h, "url", "")),
                                       league=key)[0] in ("S", "A"))
        print(f"- **결과 {hits_all}건** · 그 중 **S·A 원천 {docs}건** · "
              f"{log.summary()}")
        zero = [r for r in log.rows() if not r["hits"]]
        print(f"- 0건 질의 {len(zero)}개" + (f" — 예: `{zero[0]['q'][:50]}`"
                                            if zero else ""))
        print()
    print("⚠️ 이 표는 **결과 수**다 — 그 문서가 쓸 만한지는 §6-3(본문)·§6-5(추출)"
          "가 센다. 🔴 재현율 재측정은 `tools/search_quality.py` 다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
