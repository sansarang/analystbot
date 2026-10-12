"""🔴🔴 **"현재 상태" 입구 표** — 사용자 지시 2026-10-12(2번 · 계약 L2).

> 각각: 경기 단위 자료에서 as_of까지 **재합산 가능 → 재합산으로 바꾼다** /
> 불가 → 재현 모드에서 **"현재 값 — 재현 불가" 표시**하고 **확률 경로에서 뺀다**.

🔴 왜 이 표가 필요한가 — ⓐ(누설)는 *"과거 경기 목록"* 을 막았다. 그런데 **지금
   상태를 그대로 주는 입구**(순위표·선수단 누계·명부)는 목록이 아니라 **값**이라
   as-of 로 자를 수가 없다. 그것이 확률에 닿으면 재현은 **미래를 본 카드**가 된다.
⚠️ 이 파일은 **판정만** 한다 — 값을 만들지 않는다.
"""
from __future__ import annotations

#: 🔴 재현 모드에서 확률 경로에 **못 들어가는** 값에 붙는 글자
MARK = "현재 값 — 재현 불가"

#: 🔴🔴 **입구 표**(2026-10-12 실측) — 열쇠는 `Facts` 의 칸 이름이다.
#
#  ⚠️ 새 입구가 생기면 **여기 더한다** — 빠지면 그 길로 미래가 들어온다(계약이 센다).
NOW_ONLY: dict[str, str] = {
    # ── 🔴 재현 불가(as-of 시점 값을 주는 통로가 없다)
    "player_stats": (
        f"{MARK} — 선수단 페이지의 **시즌 누계**다(득점·도움·레이팅). "
        "🔴 경기별 `fotmob.player_adv`(선수 xG/xA)·골 목록으로 **재합산 가능** → "
        "공격 기여표는 그 길로 바꾼다(`s2e_matchup.adv_players`)."),
    "standings": (
        f"{MARK} — 순위표는 **지금 순위**다. 과거 라운드 순위를 주는 통로가 없다 → "
        "확률 경로에서 뺀다(경우의 수·표시로만)."),
    # 🔴 순위표가 **확률에 닿는 두 자리**(실측 2026-10-12)
    "standings.match_total_baseline": (
        f"{MARK} — 리그 경기당 총골이 **지금 누계**다(λ 기준에 닿는다). "
        "🔴 as-of 창의 경기 목록으로 **재합산 가능**하지만 아직 안 바꿨다 → "
        "재현에서는 **뺀다**."),
    "standings.key_players": (
        f"{MARK} — 팀당 상위 2명 득점+도움이 **지금 누계**다(축0·꺼진 무기). "
        "🔴 경기별 `player_adv` 로 **재합산 가능**(그 길이 이미 1순위다) → "
        "재현에서는 이 **대체 경로를 막는다**."),
    "squad_names": (
        f"{MARK} — 선수단 명부·등번호는 **지금 명부**다 → 신원 대조(표시)로만 쓴다."),
    # ── ✅ as-of 정합(그 경기 페이지에서 온다 · 재합산 필요 없음)
    "player_value": (
        "✅ as-of 정합 — **그 경기 페이지**의 `marketValue` 다(현재 값이 아니다). "
        "재합산 불필요."),
    "missing": (
        "✅ as-of 정합 — 결장 명단은 **그 경기 페이지**의 `unavailable` 칸이다. "
        "재합산 불필요. ⚠️ 경기 뒤 그 페이지가 갱신되면 값이 달라질 수 있다."),
    "usual_starts": (
        "✅ as-of 정합 — 선발 비율(30% 규칙)은 **경기 목록**에서 센다(ⓐ 가 잘랐다). "
        "재합산 완료."),
}

#: 🔴 확률 경로에 못 가는 열쇠들(위 표에서 자란다 — 손으로 두 번 적지 않는다)
#  🔴 규칙: `MARK` 로 시작하는 칸은 막는다. ⚠️ *"재합산 가능"* 이라고 적혀 있어도
#     **그 길로 실제로 바꾼 뒤**에 이 표에서 `✅` 로 고쳐야 풀린다(글자가 약속이다).
BLOCKED: tuple[str, ...] = tuple(
    k for k, v in NOW_ONLY.items() if v.startswith(MARK))


def may_use(key: str, *, replay: bool) -> tuple[bool, str]:
    """🔴🔴 L2 — 그 값을 **확률 경로에 써도 되나**. `(된다, 사유)`.

    🔴 운영(`replay=False`)은 그대로 쓴다 — *"지금"* 이 as-of 이기 때문이다.
    🔴 재현(`replay=True`)에서는 `BLOCKED` 열쇠를 **막고 사유를 돌려준다**.
    ⚠️ 표에 없는 열쇠는 **통과**다(모르는 것으로 막지 않는다 · #4) — 대신 새
       입구를 표에 더하는 것이 규율이다(계약이 목록을 센다).
    """
    said = str(NOW_ONLY.get(str(key)) or "")
    if not replay or str(key) not in BLOCKED:
        return True, (said or "표에 없다 — 통과")
    return False, said


def said_of(keys: list[str] | None = None, *, replay: bool) -> str:
    """🔴 카드가 적을 한 줄 — 재현에서 **무엇을 뺐나**."""
    want = [str(k) for k in (keys or BLOCKED)]
    if not replay:
        return ""
    bad = [k for k in want if k in BLOCKED]
    if not bad:
        return ""
    return ("🔴 재현 모드 — " + ", ".join(f"`{k}`" for k in bad)
            + f" 는 {MARK} → **확률 경로에서 뺐다**")
