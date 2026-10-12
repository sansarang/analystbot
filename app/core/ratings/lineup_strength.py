"""🔴🔴 **§8 결장의 무게 · 벤치 강도** — 지시서 2026-10-12(둘째) §8.

> `usual_xi(team, as_of)` : 최근 리그 N경기 **출전 분 가중**(ξ) 상위 11명 id
> `absence_loss` : Σ(usual_xi 중 오늘 XI 에 없는 선수 점수) − Σ(대신 들어온 선수)
> `bench_mean` : 오늘 벤치 점수 상위 5명 평균

🔴 **원칙**(지시 §8) — *"결장은 **누가** 빠졌나의 질로 센다. 이름 수가 아니다."*
   그래서 계약 **C8-1** 이 *"사람 수로 확률이 움직이면 실패"* 를 센다.
🔴 선수 점수는 §5(`player_pm`)가 적합한 판이 준다 — 이 모듈은 **받아서 센다**.
⚠️ 점수가 없는 선수를 **0 으로 세지 않는다**(계약 PL2) — 같은 묶음의 평균으로
   메우고 🔴 를 사유에 남긴다. 0 으로 세면 *"그 선수가 평균 이하"* 라고 말하는
   것이 되고, 결장 손실이 **부풀어 오른다**.
🔴 벤치는 λ 식에 **없다** — 시뮬 60분 이후 배율이다(`sim.BENCH_FROM` · C8-2).
"""
from __future__ import annotations

import math

#: 🔴 평소 XI 를 세는 리그 경기 수(지시의 "최근 리그 N경기")
USUAL_N = 5

#: 🔴 벤치에서 세는 사람 수 — 지시의 "상위 5명"
BENCH_TOP = 5

#: 🔴 시간 감쇠 반감기(일) — §6 ξ 가 적합되면 **판**에서 온다(여기 손값은 기본값)
HALF_LIFE = 180.0


def usual_xi(past: list[dict], *, as_of, n: int = 11,
             games: int = USUAL_N, half_life: float = HALF_LIFE
             ) -> tuple[list[str], str]:
    """🔴🔴 평소 XI — **출전 분 가중**(시간 감쇠) 상위 `n` 명 id. `(목록, 사유)`.

    🔴 `as_of` 이후 경기는 **안 본다**(L1 · 문은 `fotmob.before_as_of` 하나).
    ⚠️ `past` 한 줄은 `{utc, comp, minutes:{선수 id: 분}}` 다 — 이름 문자열이
       아니라 **id** 다(§5 배선: 신원 검문을 지난 것만).
    """
    from datetime import datetime

    from app.collect import fotmob as fm
    from app.core import level as _lv
    said = fm.before_as_of(list(past or []), as_of=as_of, key="utc")
    rows = [r for r in said
            if not _lv.is_cup(str(r.get("comp") or ""))
            and str(r.get("comp") or "").strip().lower() != "cup"]
    rows = sorted(rows, key=lambda r: str(r["utc"]))[-int(games):]
    if not rows:
        return [], "⬜ **평소 XI 를 못 만들었다** — 지난 리그 경기가 없다"
    decay = math.log(2.0) / max(1.0, float(half_life))
    got: dict[str, float] = {}
    for r in rows:
        when = datetime.fromisoformat(str(r["utc"]).replace("Z", "+00:00"))
        if when.tzinfo is None:                 # 🔴 절대규칙 2
            continue
        w = math.exp(-decay * max(0, (as_of.date() - when.date()).days))
        for pid, mins in dict(r.get("minutes") or {}).items():
            got[str(pid)] = got.get(str(pid), 0.0) + w * float(mins or 0.0)
    order = sorted(got, key=lambda k: -got[k])[:int(n)]
    return order, (f"평소 XI — 최근 리그 **{len(rows)}경기** 출전 분 가중"
                   f"(반감기 {half_life:g}일) 상위 {len(order)}명")


def _value_of(pid: str, value: dict) -> tuple[float, bool]:
    """🔴 그 선수 점수. 없으면 **같은 묶음의 평균**과 `True`(메웠다)."""
    box = dict(value or {})
    if str(pid) in box:
        return float(box[str(pid)]), False
    said = [float(v) for v in box.values()]
    return ((sum(said) / len(said)) if said else 0.0), True


def absence_loss(*, usual: list[str], today: list[str], value: dict
                 ) -> tuple[float, str]:
    """🔴🔴 §8 — **빠진 점수 합 − 들어온 점수 합**. `(손실, 사유)`.

    🔴 음수면 *"오늘 XI 가 평소보다 약하다"* 가 아니라 **그 반대**다(들어온 쪽이
       더 세다). ⚠️ 부호를 사유가 말한다.
    🔴 **C8-1** — 사람 수는 안 센다. 같은 수가 빠져도 점수가 같으면 손실이 같다.
    """
    out_ids = [p for p in (usual or []) if p not in set(today or [])]
    in_ids = [p for p in (today or []) if p not in set(usual or [])]
    filled: list[str] = []
    gone = 0.0
    for pid in out_ids:
        got, miss = _value_of(pid, value)
        gone += got
        if miss:
            filled.append(str(pid))
    came = 0.0
    for pid in in_ids:
        got, miss = _value_of(pid, value)
        came += got
        if miss:
            filled.append(str(pid))
    loss = gone - came
    said = (f"빠짐 {len(out_ids)}명 합 {gone:+.3f} · 들어옴 {len(in_ids)}명 합 "
            f"{came:+.3f} → **{loss:+.3f}**")
    if filled:
        said += (f" · 🔴 점수 없는 선수 {len(filled)}명은 **같은 묶음 평균**으로 "
                 f"메웠다(0 으로 세지 않는다): {', '.join(filled[:3])}")
    return loss, said


def bench_mean(bench: list[str], *, value: dict, top: int = BENCH_TOP
               ) -> tuple[float | None, str]:
    """🔴 오늘 벤치 **상위 `top` 명 평균**. 없으면 `(None, ⬜ 사유)`(0 이 아니다)."""
    said = list(bench or [])
    if not said:
        return None, "⬜ **벤치 id 가 없다** — 벤치 항을 쓰지 않는다(0 이 아니다)"
    got = []
    filled = 0
    for pid in said:
        val, miss = _value_of(pid, value)
        got.append(val)
        filled += 1 if miss else 0
    got.sort(reverse=True)
    take = got[:int(top)]
    out = sum(take) / len(take)
    why = f"벤치 {len(said)}명 중 상위 {len(take)}명 평균 **{out:+.3f}**"
    if filled:
        why += f" · 🔴 점수 없는 선수 {filled}명은 평균으로 메웠다"
    return out, why
