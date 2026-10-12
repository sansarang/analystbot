"""🔴🔴 **§12 하위 그룹 보정표**(검증 전용) — 지시서 2026-10-12(둘째) §12.

> 그룹: `streak_len ≥ 5` · `post_break` · `load_14d ≥ 4` · 신규/승격 팀 ·
> 감독 교체 후 5경기.
> 그룹에서 **구간상 체계적 편향** → 그 변수를 §9 후보로 올려 **같은 판정**을
> 밟는다(직접 보정 금지). 편향 없음 → **아무것도 안 넣는다**.

🔴 왜 "직접 보정 금지" 인가 — 원장·백필로 **계수를 맞추는 것**은 금지다
   (CLAUDE.md: *"쌓인 것은 검증에만"*). 🔴 그래서 이 모듈은 **어디가 치우쳤나만**
   말하고, 고치는 길은 §9 전진 선택(같은 판정 규칙) 하나다.
🔴 **C12-1** — `streak_len` 은 λ 에 **직접** 들어가지 않는다(계약이 센다).
⚠️ 보정표를 세는 함수는 `app/core/metrics.calib` 하나다(사본 금지).
"""
from __future__ import annotations

#: 🔴🔴 §12 가 적은 **다섯 그룹** — 이름과 그 뜻
GROUPS: dict[str, str] = {
    "streak5": "연속 무승·연패 5경기 이상",
    "post_break": "휴식기 직후 첫 리그 경기",
    "load4": "14일 안에 4경기 이상",
    "new_team": "신규·승격 팀(등급표에 없던 팀)",
    "coach_new": "감독 교체 후 5경기 이내(날짜 있는 것만)",
}

#: 🔴 문턱 — 지시가 적은 수(두 곳에 적지 않는다)
STREAK_MIN = 5
LOAD_MIN = 4


def group_of(box: dict) -> list[str]:
    """🔴 그 경기가 **어느 그룹**인가. ⚠️ 못 잰 칸은 **그룹에 안 넣는다**(#3)."""
    said = dict(box or {})
    out: list[str] = []
    streak = said.get("streak_len")
    kind = str(said.get("streak_kind") or "")
    if streak is not None and int(streak) >= STREAK_MIN and kind in ("패", "무"):
        out.append("streak5")
    if said.get("pb_home"):
        out.append("post_break")
    load = said.get("load_14d")
    if load is not None and int(load) >= LOAD_MIN:
        out.append("load4")
    if said.get("new_team"):
        out.append("new_team")
    if said.get("coach_new"):
        out.append("coach_new")
    return out


def bias(rows: list[dict], *, side: int = 0) -> dict:
    """🔴🔴 §12 — 그룹별 **평균 예측 − 실제**와 구간. 🔴 세는 곳은 `metrics` 하나다.

    `rows` 한 줄: `{p: [홈,무,원정], hit: 0|1|2, tags: [그룹…]}`.
    ⚠️ 한 경기가 여러 그룹에 들 수 있다 — 그래서 **그룹마다 따로** 센다.
    """
    from app.core import metrics as _me
    out: dict = {}
    for name in GROUPS:
        said = [{"p": r["p"], "hit": r["hit"], "g": name}
                for r in (rows or []) if name in list(r.get("tags") or [])]
        if not said:
            continue
        got = _me.calib(said, group="g", side=side)
        out[name] = got[name]
    return out


def verdict_of(got: dict) -> str:
    """🔴 §12 조치 규칙(고정) — 구간이 0 을 품으면 **그냥 둔다**.

    - 구간이 **0 을 품지 않는다** → `후보로`(§9 전진 선택으로 올린다)
    - 그 밖 → `그냥 둔다`(아무것도 넣지 않는다)
    """
    lo, hi = float(got.get("lo", 0.0)), float(got.get("hi", 0.0))
    if lo > 0 or hi < 0:
        return "후보로"
    return "그냥 둔다"
