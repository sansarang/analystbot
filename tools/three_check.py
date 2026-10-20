"""🔴🔴 **세 경기를 한 코드로 — 다 맞히나**(사용자 지시 2026-10-20).

> 우선 **셋 다 맞추기**식으로 한다 .. 테스트코드로 만들어라 ..
> 하지만 **셋 다 코드는 같아야 한다**

```
PYTHONPATH=. python tools/three_check.py
```

## 무엇을 재나

어제(2026-10-19) 밤 봇이 돌린 **세 판**이다. 셋 다 **틀렸거나 1위가 없었다**:

| 경기 | 실제 | 그때 봇 | |
|---|---|---|---|
| Monza vs Cagliari | **4-0 홈** | 홈 31.3 · 무 29.0 · **원정 39.7** | 🔴 |
| U. Cluj vs FC Argeș | **2-2 무** | 홈 32.9 · 무 32.2 · **원정 34.9** | 🔴 |
| FC Kharkiv vs Liviy Bereh | **2-1 홈** | 홈 32.9 · 무 32.2 · **원정 34.9** | 🔴 |

🔴 **셋에 같은 코드가 돈다** — 경기마다 다른 처리를 두지 않는다. 이 파일은
   확률을 **계산하지 않는다**: 되감기 측정 도구의 `draw_lean._one` 하나를
   부른다(#1 사본 금지). 그래서 운영 확률이 바뀌면 이 표도 따라 바뀐다.

## 🔴 지금은 **실패하는 것이 맞다**

이것은 *"통과해야 하는 시험"* 이 아니라 **목표**다. 지금 0/3 이고, 무엇을
고치든 이 수가 올라가야 고친 값어치가 있다.

⚠️ **표본 셋이다.** 셋을 맞히려고 수를 손으로 맞추면 그건 적합이 아니라
   **외우기**다(CLAUDE.md: 원장으로 규칙을 고치지 않는다). 이 표는 *"고친 것이
   이 셋을 깨지는 않나"* 를 보는 자이지, 셋에 맞춰 깎는 자가 아니다.

## ⚠️ 재료가 날마다 바뀐다(실측 2026-10-20)

같은 코드로 열두 판을 다시 돌려 **다섯이 달라졌다** — fotmob 의 **결장 명단**과
선수 백분위가 갱신되기 때문이다(우디네세: 결장 2명 → 1명 · 민 변수 5 → 4 ·
쏠림 1단계 → 0단계). 🔴 그러니 이 표가 어제와 달라도 **코드 탓이 아닐 수
있다** — 재료 수(능력치·민 변수)를 함께 적는 까닭이다.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: 🔴 **셋** — `(경기 번호, 보기 이름, 실제 결과)`. 결과는 `home`·`draw`·`away`.
#  ⚠️ 결과를 손으로 적는 까닭 — 경기 페이지의 스코어로도 알 수 있지만, 이
#     파일이 **무엇을 목표로 하는지** 사람이 읽어야 한다(#3).
GAMES: tuple[tuple[str, str, str], ...] = (
    ("5749706", "Monza vs Cagliari", "home"),          # 4-0
    ("5853525", "U. Cluj vs FC Argeș", "draw"),        # 2-2
    ("5909177", "FC Kharkiv vs Liviy Bereh", "home"),  # 2-1
)

_KO = {"home": "홈", "draw": "무", "away": "원정", "tie": "동률"}


async def main() -> int:
    # 🔴 확률은 **되감기 도구가** 센다 — 여기서 다시 짜지 않는다(#1)
    from app.collect import fotmob as fm
    from app.core.state import RunState
    from app.net import Net

    import draw_lean as dl                               # noqa: E402

    net = Net(cache=True, day_cache=True)
    rows: list[dict] = []
    print("# 🔴 세 경기 — 한 코드로 다 맞히나\n", flush=True)
    for i, (mid, name, truth) in enumerate(GAMES, 1):
        page = await net.get(fm.match_url(mid))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            print(f"  {i}/3 `{mid}` 🔴 경기 페이지를 못 읽었다", flush=True)
            rows.append({"name": name, "why": "경기 페이지를 못 읽었다"})
            continue
        gen = (((j.get("props") or {}).get("pageProps") or {})
               .get("general") or {})
        kick = fm.kickoff(j)
        comp = str(gen.get("leagueName") or "") or "?"
        seed = {"id": mid,
                "home": str((gen.get("homeTeam") or {}).get("name") or ""),
                "away": str((gen.get("awayTeam") or {}).get("name") or ""),
                "utc": kick.isoformat() if kick else "", "finished": True}
        try:
            got = await dl._one(mid, net=net, league=comp, short=comp[:8],
                                state_cls=RunState, row=seed)
        except Exception as exc:                          # noqa: BLE001
            print(f"  {i}/3 {name} 🔴 터졌다 — {exc!r:.80}", flush=True)
            rows.append({"name": name, "why": f"터졌다 {exc!r:.60}"})
            continue
        if got is None or got.get("why"):
            why = (got or {}).get("why") or "사유 없음"
            print(f"  {i}/3 {name} 🔴 못 쟀다 — {why}", flush=True)
            rows.append({"name": name, "why": why})
            continue
        p, top = got["p"], got["top"]
        hit = top == truth
        rows.append({"name": name, "p": p, "top": top, "truth": truth,
                     "hit": hit, "lean": got["lean"],
                     "n_push": got["n_push"], "ability_n": got["ability_n"]})
        print(f"  {i}/3 {name} — 홈 {p['home']:.1%} · 무 {p['draw']:.1%} · "
              f"원정 {p['away']:.1%} · 1위 **{_KO.get(top, top)}** ↔ 실제 "
              f"**{_KO[truth]}** {'✅' if hit else '🔴'} "
              f"(쏠림 {got['lean']}단계 · 민 변수 {got['n_push']} · "
              f"능력치 {got['ability_n']}명)", flush=True)

    ok = [r for r in rows if r.get("hit")]
    bad = [r for r in rows if r.get("why")]
    print(f"\n## 🔴 **{len(ok)}/{len(GAMES)}**"
          + (f" · 못 쟨 경기 {len(bad)}건" if bad else ""), flush=True)
    for r in rows:
        if r.get("why"):
            print(f"  ⬜ {r['name']} — {r['why']}", flush=True)
            continue
        print(f"  {'✅' if r['hit'] else '🔴'} {r['name']:28} "
              f"1위 {_KO.get(r['top'], r['top']):4} ↔ 실제 {_KO[r['truth']]}",
              flush=True)
    # 🔴 셋을 다 맞히기 전에는 **0 이 아닌 값**으로 끝낸다 — 목표가 남았다는 표시
    return 0 if len(ok) == len(GAMES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
