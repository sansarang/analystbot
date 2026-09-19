"""[FIX-1 2026-09-20] 증거의 **방향** — 순수 함수. DB·HTTP·LLM 호출 0.

🔴 ⑦이 종전에 `sides` 의 **항목 수**만 보고 부호를 정했다. 그래서 상대 선발이
   6.0이닝 1자책인 경기와 4.0이닝 5자책인 경기에 같은 `+3.0` 이 붙었다
   (실측 2026-09-20, MLB 4경기 전부).
🔴 반환은 팀별 **호재 +1 / 악재 −1 / 모름 0** 이다. 그 팀에 대한 값이고,
   "우리 픽에 유리한가"는 ⑦이 픽 쪽을 보고 정한다.
🔴 문턱은 `config/rules.yaml` 의 `flow.direction.*` 이 원본이다. 여기 숫자를
   적지 않는다.
⚠️ 그 값들은 **미검증 사전값**이다. 채점 30건 전에는 고치지 않는다.
"""
from __future__ import annotations

from app.flow import rules as R


def _d(team: str, sign: int, dev: float | None, basis: str) -> dict:
    other = "away" if team == "home" else "home"
    return {team: sign, other: 0, "dev": dev, "basis": basis}


def era3_of(rows) -> tuple:
    """`(ERA3, 이닝합)`. 🔴 이닝이 0이면 `(None, 0.0)` — 0.00 은 완봉이다."""
    ip = sum(float(r.get("innings") or 0) for r in (rows or []))
    if ip <= 0:
        return None, 0.0
    er = sum(int(r.get("er") or 0) for r in (rows or []))
    return round(9.0 * er / ip, 3), round(ip, 2)


def starter_direction(rows, *, league_era: float | None, team: str) -> dict:
    """선발 최근 등판 → 그 **선발을 내는 팀**의 호재/악재.

    `dev = (ERA3 − 기준) / 기준`. 잘 던졌으면 dev 가 음수이고 그 팀 호재다.
    🔴 이닝합이 문턱 미만이면 표본 부족으로 **0** 이다 — 두 등판 8이닝으로
       "무너졌다"를 단정하지 않는다.
    ⚠️ 연속 짧은 등판은 방향과 별개의 사실이라 `basis` 에만 남긴다.
    """
    lo = float(R.get("direction.starter_dev_bad", 0.25))
    hi = float(R.get("direction.starter_dev_good", -0.25))
    min_ip = float(R.get("direction.starter_min_ip", 9.0))
    short_ip = float(R.get("direction.starter_short_ip", 5.0))

    era3, ip = era3_of(rows)
    flags = []
    if rows and all(float(r.get("innings") or 0) < short_ip for r in rows):
        flags.append("짧은 등판")
    if era3 is None or not league_era:
        return _d(team, 0, None, " · ".join(["재료 없음", *flags]))
    dev = round((era3 - float(league_era)) / float(league_era), 4)
    if ip < min_ip:
        return _d(team, 0, dev,
                  " · ".join([f"표본 부족(이닝합 {ip} < {min_ip})", *flags]))
    if dev >= lo:
        return _d(team, -1, dev, " · ".join([f"ERA3 {era3} (기준 {league_era})", *flags]))
    if dev <= hi:
        return _d(team, +1, dev, " · ".join([f"ERA3 {era3} (기준 {league_era})", *flags]))
    return _d(team, 0, dev, " · ".join([f"ERA3 {era3} — 기준 근처", *flags]))


def bullpen_direction(rows, *, team: str) -> dict:
    """최근 3일 구원 이닝합·2연투 수 → 그 팀의 악재 여부.

    🔴 호재(+1)는 내지 않는다 — "덜 썼다"가 곧 유리라는 근거가 우리에게 없다.
    """
    cap_ip = float(R.get("direction.bullpen_ip_heavy", 12.0))
    cap_b2b = int(R.get("direction.bullpen_b2b_heavy", 3))
    if not rows:
        return _d(team, 0, None, "재료 없음")
    ip = round(sum(float(r.get("innings") or 0) for r in rows), 2)
    days: dict = {}
    for r in rows:
        days.setdefault(r.get("pitcher"), set()).add(str(r.get("d")))
    b2b = sorted(k for k, v in days.items() if k and len(v) >= 2)
    dev = round(ip / cap_ip - 1.0, 4)
    if ip >= cap_ip or len(b2b) >= cap_b2b:
        return _d(team, -1, dev, f"3일 {ip}이닝 · 2연투 {len(b2b)}명")
    return _d(team, 0, dev, f"3일 {ip}이닝 · 2연투 {len(b2b)}명 — 문턱 미만")


def lineup_direction(*, excluded: int, confirmed: bool, team: str) -> dict:
    """평소 주전이 **오늘 확정 타순에서 빠진 수** → 그 팀의 악재 여부.

    🔴 IL 목록 길이가 아니다. `lineup_diff` 가 최근 10경기로 정한 '평소 주전'의
       오늘 제외분(`absences.classify == lineup_excluded`)을 센다.
    ⚠️ 확정 타순이 없으면 **0 + "미확정"** 이다 — 예상 타순으로 단정하지 않는다.
    """
    need = int(R.get("direction.lineup_out_heavy", 2))
    if not confirmed:
        return _d(team, 0, None, "미확정")
    dev = round(excluded / max(need, 1) - 1.0, 4)
    if excluded >= need:
        return _d(team, -1, dev, f"평소 주전 {excluded}명 제외")
    return _d(team, 0, dev, f"평소 주전 {excluded}명 제외 — 문턱 미만")


def merge(*dirs) -> dict:
    """여러 방향을 쪽별로 합친다. 🔴 같은 팀에 호재·악재가 겹치면 0(상쇄)."""
    out = {"home": 0, "away": 0, "dev": None, "basis": []}
    devs = []
    for d in dirs:
        if not d:
            continue
        for side in ("home", "away"):
            out[side] += int(d.get(side, 0) or 0)
        if d.get("dev") is not None:
            devs.append(abs(float(d["dev"])))
        if d.get("basis"):
            out["basis"].append(str(d["basis"]))
    for side in ("home", "away"):
        out[side] = max(-1, min(1, out[side]))
    out["dev"] = max(devs) if devs else None
    out["basis"] = " | ".join(out["basis"])
    return out
