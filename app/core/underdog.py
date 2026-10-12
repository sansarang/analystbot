"""🔴🔴 **§11 역배 확률 · 보호 줄** — 지시서 2026-10-12(둘째) §11(**즉시 적용**).

> 강팀 = 승 확률 높은 쪽(차 **3%p 미만 → "강팀 없음"**). 같은 격자에서 약팀 승·
> 강팀 미승·약팀 +0.5/+1.5/+2.5·더블찬스·DNB.

🔴 왜 — 실사고 둘(광주 4-3 울산 · 가와사키 1-2 나고야)에서 **시장도 봇도 강팀을
   봤다**. 카드가 *"강팀 41%"* 만 적으면 읽는 사람은 그 41% 를 **확신**으로 읽는다.
   🔴 같은 격자에서 나온 **약팀 쪽 줄**을 나란히 적으면, 그 41% 가 *"강팀이 안
   이길 확률 59%"* 와 같은 수임이 보인다.
🔴 **수를 새로 만들지 않는다** — 전부 `probfloor.markets_of` 가 센 그 격자다
   (계약 U1). 확률·등급을 **바꾸지 않는다**(표시 전용).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴 강팀을 가르는 문턱 — 승 확률 차가 이보다 작으면 **강팀 없음**(지시 §11)
EDGE = 0.03

#: 🔴 약팀 보호 줄(핸디) — 지시가 적은 셋
AH_LINES: tuple[float, ...] = (0.5, 1.5, 2.5)


@dataclass
class Read:
    """🔴 역배·보호 줄 한 묶음(표시 전용)."""

    fav: str = ""
    dog: str = ""
    fav_name: str = ""
    dog_name: str = ""
    fav_win: float = 0.0
    dog_win: float = 0.0
    draw: float = 0.0
    fav_nowin: float = 0.0
    dog_dc: float = 0.0
    dog_dnb: float = 0.0
    dog_ah: dict = field(default_factory=dict)
    why: str = ""


def read(grid: dict, *, home_name: str, away_name: str) -> Read:
    """🔴🔴 그 격자에서 **약팀 쪽 줄**을 읽는다. 🔴 수는 격자 하나에서만 온다."""
    from app.core import probfloor as _pf
    mk = _pf.markets_of(dict(grid or {}))
    home, draw, away = (float(mk["home"]), float(mk["draw"]), float(mk["away"]))
    got = Read(draw=draw)
    if abs(home - away) < EDGE:
        got.why = (f"⬜ **강팀 없음** — 승 확률 차 {abs(home - away):.1%} 가 "
                   f"{EDGE:.0%} 미만이다(홈 {home:.1%} · 원정 {away:.1%})")
        return got
    if home > away:
        got.fav, got.dog = "home", "away"
        got.fav_name, got.dog_name = str(home_name), str(away_name)
        got.fav_win, got.dog_win = home, away
        got.dog_ah = {line: float(mk["ah"][f"away+{line:.1f}"])
                      for line in AH_LINES}
    else:
        got.fav, got.dog = "away", "home"
        got.fav_name, got.dog_name = str(away_name), str(home_name)
        got.fav_win, got.dog_win = away, home
        got.dog_ah = {line: float(mk["ah"][f"home+{line:.1f}"])
                      for line in AH_LINES}
    got.fav_nowin = 1.0 - got.fav_win
    got.dog_dc = got.dog_win + draw
    tot = got.dog_win + got.fav_win
    got.dog_dnb = (got.dog_win / tot) if tot else 0.0
    got.why = (f"강팀 {got.fav_name} {got.fav_win:.1%}(차 "
               f"{abs(home - away):.1%}) · 수는 **그 격자 하나**에서 왔다")
    return got


def line(got: Read) -> str:
    """🔴 카드 1겹 맨 위 한 줄 — 지시가 적은 꼴 그대로."""
    if not got.fav:
        return f"⬜ **강팀 없음** — 역배 줄을 적지 않는다({got.why})"
    return (f"강팀 {got.fav_name} {got.fav_win:.0%} · 🔁 **{got.dog_name} 승 "
            f"{got.dog_win:.0%}** · {got.fav_name} 미승 {got.fav_nowin:.0%} · "
            f"{got.dog_name} +1.5 {got.dog_ah[1.5]:.0%} · "
            f"{got.dog_name} 더블찬스 {got.dog_dc:.0%} · "
            f"{got.dog_name} DNB {got.dog_dnb:.0%}")
