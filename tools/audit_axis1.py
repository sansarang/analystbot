"""🔴🔴 **축1 감사** — 사용자 지시 2026-10-11 ②.

> LAFC·밴쿠버의 축1을 **경기별로** 찍어라 — 경기·상대·상대 전력·득점·실점·
> 운 요소 할인·r 가중·보정 후 값.

```
PYTHONPATH=. python tools/audit_axis1.py "Los Angeles FC" "Vancouver Whitecaps"
```

🔴 **봇의 그 함수들을 그대로 부른다**(사본 금지) — `s2e_matchup._history` 가 경기를
   모으고 `form.form_of` 가 보정한다. 여기서 수식을 다시 쓰지 않는다.
⚠️ 읽기만 한다 — 봇을 돌리지 않는다(#12).
"""
from __future__ import annotations

import asyncio
import sys


async def audit(home: str, away: str) -> None:
    """🔴 두 팀의 축1 을 **봇과 같은 길**로 찍는다(사본 금지)."""
    from app.core import form as _form
    from app.core.state import RunState
    from app.core.stages import s2e_matchup as _s2e
    from app.net import Net
    net, st = Net(cache=True), RunState()
    rows = {}
    for side, name in (("home", home), ("away", away)):
        got = await _s2e._history(net, name, state=st)
        if got is None:
            print(f"🔴 `{name}` 과거 경기를 못 받았다")
            return
        rows[side] = got

    class _Ref:
        home_name, away_name = home, away
        competition = ""
    elo = _s2e._elo_of(_Ref(), rows)
    for side, name in (("home", home), ("away", away)):
        said = _s2e._as_form(rows[side], name)
        got = _form.form_of(name, said, elo=elo, luck_goals=None)
        print(f"\n━━ {name} ━━ (Elo {'있다' if elo.get(name) else '🔴 **없다**'})")
        print(f"{'상대':<26}{'상대Elo':>8}{'득':>4}{'실':>4}"
              f"{'보정득':>9}{'보정실':>9}")
        for one in said[-5:]:
            opp = str(one.get("opp") or "")
            mine, their = elo.get(name), elo.get(opp)
            a, _w = _form.adjust_one(float(one["gf"]), mine_elo=mine,
                                     their_elo=their)
            b, _w2 = _form.adjust_one(float(one["ga"]), mine_elo=their,
                                      their_elo=mine)
            print(f"{opp[:24]:<26}{(f'{their:.0f}' if their else '—'):>8}"
                  f"{one['gf']:>4}{one['ga']:>4}{a:>9.2f}{b:>9.2f}")
        print(f"  합 — 득 {got.gf:.0f} · 실 {got.ga:.0f} · 보정 득 {got.adj_gf:.2f}"
              f" · 보정 실 {got.adj_ga:.2f}")
        print(f"  🔴 축1 지수 = (보정 득 − 보정 실) / {got.n} = **{got.index()}**")
        print(f"     원본 득실차/경기 = ({got.gf:.0f} − {got.ga:.0f}) / {got.n} = "
              f"{(got.gf - got.ga) / got.n:+.3f}")


if __name__ == "__main__":
    asyncio.run(audit(sys.argv[1], sys.argv[2]))
