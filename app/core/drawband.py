"""🔴🔴 **무 구간 실측 표시**(수정 지시 2026-10-13 밤 2-④) — **표시 전용**.

> ④ 카드 표시 (측정 결과 나오는 즉시 · **확률 값은 안 바꾼다**)
>   - 무 % 옆에 "백필 실측: 이 구간 예측 x% → 실측 y% (n경기)".
>   - 편차 ≥ 3%p 이면 🟡 "무 과소/과대 구간" — 그 경기의 강팀 미승·±0.5 핸디·
>     오버 1.5 줄에도 같은 표시.

🔴🔴 **확률 경로에 닿지 않는다** — D1·D2 가 **둘 다 탈락**했으므로(2-③ 판정)
   경로는 그대로다. 이 모듈은 **글자만** 만든다(계약 DB1 이 확률 모듈에서
   호출 0건을 센다).
🔴 판은 `data/draw_bands/<as-of>.yaml` 이고 `tools/draw_audit.py` 가 적는다
   (`app/` 은 yaml 을 쓰지 않는다).
⚠️ **as-of 로 고르지 않는다** — 이 수는 그 경기의 정보가 아니라 **지난 백필의
   성적표**이고 확률에 닿지 않는다. L3(판 고르기)는 확률에 들어가는 계수를
   지키는 규율이므로 여기서는 **가장 최근 판**을 읽고 그 날짜를 글자에 적는다.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BOX = ROOT / "data/draw_bands"

#: 🔴 이보다 벌어지면 🟡 를 붙인다(지시의 3%p)
DEV_CUT = 0.03


def plate() -> tuple[dict, str]:
    """🔴 가장 최근 판. 없으면 `({}, 사유)`."""
    rows = sorted(BOX.glob("*.yaml")) if BOX.exists() else []
    if not rows:
        return {}, "⬜ **무 구간 판이 없다**(`tools/draw_audit.py` 가 아직 안 돌았다)"
    import yaml
    got = yaml.safe_load(rows[-1].read_text(encoding="utf-8")) or {}
    return dict(got), f"판 `{rows[-1].stem}`(백필 {got.get('n')}경기)"


def band_of(draw: float | None) -> str:
    """🔴 그 무 확률이 속한 구간 이름(판의 구간 목록을 쓴다 · 사본 금지)."""
    if draw is None:
        return ""
    box, _why = plate()
    for one in list(box.get("bands") or []):
        name = str(one.get("band") or "")
        lo, hi = _edges(name)
        if lo is not None and lo <= float(draw) < hi:
            return name
    return ""


def _edges(name: str) -> tuple[float | None, float]:
    """🔴 `20~25%`·`30%+` 같은 구간 이름 → 경계(판이 이름을 든다)."""
    said = str(name or "").replace("%", "").strip()
    if said.endswith("+"):
        try:
            return float(said[:-1]) / 100.0, 1.01
        except ValueError:
            return None, 0.0
    if "~" in said:
        lo, hi = said.split("~", 1)
        try:
            return float(lo) / 100.0, float(hi) / 100.0
        except ValueError:
            return None, 0.0
    return None, 0.0


def of(draw: float | None) -> tuple[dict, str]:
    """🔴🔴 그 무 확률의 **구간 실측**. `({band,pred,real,n,dev}, 사유)`."""
    box, why = plate()
    if not box:
        return {}, why
    if draw is None:
        # 🔴 **확률이 없으면 구간도 없다** — 빈 괄호로 말하지 않는다(#3)
        return {}, f"⬜ **확률이 없어 무 구간을 못 잰다**({why})"
    name = band_of(draw)
    for one in list(box.get("bands") or []):
        if str(one.get("band")) == name:
            said = dict(one)
            if not int(said.get("n") or 0):
                # 🔴 **그 구간은 표본이 0 이다** — 지어내지 않고 그 말을 한다
                return {}, (f"⬜ 그 구간(**{name}**)은 백필 표본이 **0경기**다"
                            f"({why})")
            said["dev"] = float(said.get("diff") or 0.0)
            return said, why
    return {}, (f"⬜ 그 무 확률({'' if draw is None else f'{draw:.1%}'})이 "
                f"**판의 어느 구간에도 안 든다**({why})")


def said_of(draw: float | None) -> str:
    """🔴 카드 한 줄 — 무 옆에 붙는 글자(확률은 **안 바뀐다**)."""
    got, why = of(draw)
    if not got:
        return f"⬜ **무 구간 실측 없음** — {why}"
    dev = float(got.get("dev") or 0.0)
    head = ""
    if abs(dev) >= DEV_CUT:
        head = ("🟡 **무 과소 구간** — " if dev < 0
                else "🟡 **무 과대 구간** — ")
    return (f"{head}백필 실측: 이 구간(**{got.get('band')}**) 예측 "
            f"{float(got.get('pred') or 0.0):.1%} → 실측 "
            f"{float(got.get('real') or 0.0):.1%} "
            f"({int(got.get('n') or 0)}경기 · 편차 {dev:+.1%}) · {why}")


def flag(draw: float | None) -> str:
    """🔴 편차 ≥ 3%p 면 그 **꼬리표**(무와 엮인 줄에 같이 붙인다). 아니면 빈 글자."""
    got, _why = of(draw)
    dev = float(dict(got).get("dev") or 0.0) if got else 0.0
    if abs(dev) < DEV_CUT:
        return ""
    return (f" 🟡 **무 {'과소' if dev < 0 else '과대'} 구간**"
            f"(편차 {dev:+.1%} · 무와 엮인 줄)")
