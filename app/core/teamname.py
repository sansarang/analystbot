"""🔴🔴 **표시 판의 팀 이름 맞춤** — 판은 fotmob 약칭, 카드는 정식명이다.

⚠️ 실사고 2026-10-14 01:14(UCL 두 경기): 판 셋(`comp_record`·`comp_history`·
   `league_elo_auto`)을 그 자리에서 채웠는데 카드가 **셋 다 ⬜** 였다 —
   판에는 `Lens`·`Sporting CP`·`Slavia Prague` 로 적혔고 카드는
   `Racing Club de Lens`·`Sporting Clube de Portugal`·`SK Slavia Praha` 로
   물었다. 똑같은 팀인데 글자가 달라 못 찾았다.

🔴 **맞춤은 이 함수 하나다**(사본 금지) — 세 읽기가 같은 규칙을 쓴다.
🔴 규칙 — ① 글자 그대로(대소문자 무시) ② 흔한 꼬리말(fc·cp·sk·fk·clube…)을 뺀
   **속 낱말**이 반쪽이라도 겹치면 후보 ③ 후보가 **하나일 때만** 쓴다.
⚠️ 후보가 둘 이상이면 **고르지 않는다** — 이름으로 남긴다(지어내지 않는다 · #3).
⚠️ 이 통로는 **표시 전용 판**만 쓴다 — 확률 경로에 닿지 않는다.
"""
from __future__ import annotations

#: 🔴 팀 이름에서 **구단 형태**를 말하는 낱말 — 겹침을 셀 때 뺀다
NOISE = {"fc", "cf", "cp", "sc", "sk", "fk", "ac", "as", "rc", "club",
         "clube", "de", "da", "do", "of", "the", "futbol", "football",
         "calcio", "sport", "sportif", "team", "afc", "kf", "nk", "bk"}
# ⚠️ `racing`·`sporting`·`united`·`city` 는 **빼지 않는다** — 그것이 유일한 속
#    낱말인 이름이 있다(`Sporting CP` 의 속 낱말은 `sporting` 뿐이다).

#: 🔴🔴 **혼자서는 못 맞추는 낱말** — 수십 팀이 함께 쓴다.
#    ⚠️ 실사고 2026-10-14 01:19: `Buriram United` 가 `united` 하나로
#    `JEF United Chiba`(J1 판)에 붙었다 — 계약 SR2 가 잡았다(`ja` ≠ `th`).
WEAK = {"united", "city", "sporting", "racing", "athletic", "club", "al"}
# ⚠️ `al` — 아랍어 관사다. 안 빼면 `Al-Sadd`·`Al Hilal`·`Al Ahli` 가 서로
#    절반 겹친다(실측 2026-10-14: 외부 대조 표에 남의 경기가 섞여 들어왔다).
# ⚠️ `real`·`atletico` 는 **빼지 않는다** — 실측 2026-10-14: `real` 을 약한
#    낱말로 두자 `Real Madrid` 와 `Atlético Madrid` 의 겹침이 **1.00 으로 같아져**
#    외부 대조에서 짝을 못 골랐다(UCL 58경기가 그렇게 떨어졌다).

#: 🔴 겹침 문턱 — 속 낱말이 **반쪽**은 같아야 한다
CUT = 0.5


def _core(said: str) -> set[str]:
    """🔴 속 낱말 — 소문자·꼬리말 제거."""
    # ⚠️ 한 글자 토막은 버린다(`F.C.` → `f`·`c` 가 남아 겹침을 어지럽힌다)
    got = {w for w in str(said or "").lower().replace(".", " ")
           .replace("-", " ").split()
           if w and len(w) > 1 and w not in NOISE}
    return got or {w for w in str(said or "").lower().split() if w}


def share(a: str, b: str, *, weak: bool = True) -> float:
    """🔴 두 이름의 **속 낱말 겹침**(0~1) — `pick` 과 외부 대조가 같이 쓴다.

    🔴 `weak=False` 면 흔한 낱말을 **안 뺀다** — 외부 대조가 `Real Madrid` 와
       `Atlético Madrid` 를 가를 때 그 수를 잣대로 쓴다(짝 맞춤의 가름끈).
    """
    mine, yours = _core(a), _core(b)
    if not mine or not yours:
        return 0.0
    if weak:
        x, y = mine - WEAK, yours - WEAK
        if x and y:
            mine, yours = x, y
    return len(mine & yours) / max(1, min(len(mine), len(yours)))


def pick(name: str, keys) -> tuple[str, str]:
    """🔴 그 이름에 맞는 **판의 열쇠**. 못 고르면 `("", 사유)`.

    🔴 후보가 둘 이상이면 **고르지 않는다**(사유에 후보를 적는다).
    """
    rows = [str(k) for k in (keys or [])]
    said = str(name or "").strip()
    if not said or not rows:
        return "", "⬜ 판이 비었다"
    low = said.lower()
    hits: list[tuple[float, str]] = []
    for k in rows:
        if k.strip().lower() == low:
            return k, "글자 그대로"
    for k in rows:
        # 🔴 **흔한 낱말만 겹치는 것은 맞춤이 아니다**(`share` 가 그 규칙을 든다)
        got = share(said, k)
        if got >= CUT:
            hits.append((got, k))
    if not hits:
        return "", f"⬜ `{said}` 가 판에 없다(적힌 팀 {len(rows)}개)"
    top = max(h[0] for h in hits)
    best = [k for s, k in hits if s >= top]
    if len(best) > 1:
        return "", (f"⬜ `{said}` 는 후보가 둘 이상이다 — "
                    f"{' · '.join(sorted(best)[:4])}(고르지 않는다)")
    return best[0], f"이름 맞춤 `{best[0]}`(속 낱말 {top:.0%} 같다)"
