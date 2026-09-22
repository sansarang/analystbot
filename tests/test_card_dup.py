"""[CARD-DUP] 판정된 경기가 "판정 못 받은" 목록에 또 나왔다.

🔴 실측 `card:kbo:2026-09-22` (운영 캐시 · 4,758자):

```
🏆 오늘의 예측 — 조사한 것만으로 고른 승자입니다
· Doosan Bears @ Kiwoom Heroes — 두산 베어스 (확신 하)
· NC Dinos @ Samsung Lions — 삼성 라이온즈 (확신 하)
· Lotte Giants @ Hanwha Eagles — 한화 이글스 (확신 하)
(5경기는 판정을 받지 못했습니다: Lotte Giants @ Hanwha Eagles,
 KT Wiz @ SSG Landers, KT Wiz @ SSG Landers, NC Dinos @ Samsung Lions,
 Doosan Bears @ Kiwoom Heroes)
```
승자를 낸 셋이 **바로 아래 미판정 목록에 그대로** 있고, `KT Wiz @ SSG Landers`
는 **두 번** 나온다. 머리글은 8경기라는데 그날 KBO 는 DB 상 4경기다.

원인: `missing = [g for g in scheduled if g not in judged]` 가 **dict 값 비교**다.
같은 경기가 두 벌 들어오면(칸이 조금 달라서) 값이 안 맞아 판정된 경기가
미판정 목록에도 실린다.

⚠️ **중복 자체는 여기서 고치지 않는다** — 표시를 고치는 것이고 상류의
   중복 유입은 별개 결함이다.
"""
from __future__ import annotations

import app.pipeline as P


def _card(scheduled):
    """⚠️ 반환값이 아니라 `lines` 에 쌓는 함수다 — 실제 시그니처를 쓴다."""
    lines, detail = [], []
    P._render_card_v3({}, scheduled, lines, detail)
    return "\n".join(lines) + "\n" + "\n".join(detail)


def _g(gid, away, home, *, winner=None, extra=None):
    g = {"game_id": gid, "away": away, "home": home,
         "starts_at_kst": "2026-09-22 18:30", "matchup": {}}
    if winner:
        g["winner"] = winner
        g["matchup"] = {"승자": winner, "확신": "하"}
    if extra:
        g.update(extra)
    return g


def test_판정된_경기가_미판정_목록에_안_나온다():
    """🔴 실측 재현 — 같은 경기가 칸이 다른 두 벌로 들어온다."""
    a = _g(1, "Doosan Bears", "Kiwoom Heroes", winner="Kiwoom Heroes")
    a2 = _g(1, "Doosan Bears", "Kiwoom Heroes", extra={"p_claude": 0.5})
    b = _g(2, "KT Wiz", "SSG Landers")
    out = _card([a, a2, b])

    assert "판정을 받지 못했습니다" in out
    head, tail = out.split("판정을 받지 못했습니다", 1)
    assert "Kiwoom Heroes" not in tail.split(")")[0], (
        f"판정된 경기가 미판정 목록에 있다: {tail[:120]}")
    assert "1경기는 판정을 받지" in out, out[out.index("("):][:80]


def test_같은_경기를_두_번_찍지_않는다():
    """⚠️ 실측에서 `KT Wiz @ SSG Landers` 가 미판정 목록에 두 번 나왔다."""
    ok = _g(1, "Doosan Bears", "Kiwoom Heroes", winner="Kiwoom Heroes")
    b = _g(2, "KT Wiz", "SSG Landers")
    b2 = _g(2, "KT Wiz", "SSG Landers", extra={"note": "다른 칸"})
    # ⚠️ 판정이 0건이면 카드가 "판정 실패" 분기로 빠져 미판정 목록을 안 찍는다
    #    (종전 규약). 그 분기를 피하려고 판정된 경기를 하나 넣는다.
    out = _card([ok, b, b2])
    seg = out[out.index("("):]
    assert seg.count("KT Wiz") == 1, f"두 번 나왔다: {seg[:150]}"
    assert "1경기는 판정을 받지" in out


def test_id_가_없어도_대진과_시각으로_센다():
    """⚠️ 더블헤더가 합쳐지면 안 되므로 시각까지 본다."""
    ok = _g(1, "Doosan Bears", "Kiwoom Heroes", winner="Kiwoom Heroes")
    x = {"away": "A", "home": "B", "starts_at_kst": "2026-09-22 14:00",
         "matchup": {}}
    y = {"away": "A", "home": "B", "starts_at_kst": "2026-09-22 18:30",
         "matchup": {}}
    out = _card([ok, x, y])
    assert "2경기는 판정을 받지" in out, out[out.index("("):][:80]


def test_무승부도_판정이다():
    """🔴 [SOC-2] 축구 3-way 에서 무는 `winner` 가 없다 — 그대로 두면
    "판정 실패"로 나간다. 종전 규약을 깨지 않았다."""
    from app.engine.verdict import DRAW

    d = {"game_id": 9, "away": "A", "home": "B", "starts_at_kst": "",
         "matchup": {"결과": DRAW}}
    out = _card([d])
    assert "판정을 받지 못했습니다" not in out, out[:200]


def test_판정이_하나도_없으면_실패로_말한다():
    """🔴 게이트를 넓히다 **진짜 실패**를 못 보면 그게 더 나쁘다."""
    out = _card([_g(1, "A", "B"), _g(2, "C", "D")])
    assert "판정 실패" in out or "판정을 받지 못" in out
