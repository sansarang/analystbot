"""🔴🔴 **계수 판 관리(walk-forward)** — 사용자 지시 2026-10-12(3번 · 계약 L3).

> `state_rates`·`goal_baselines`·ρ·`league_elo`·(나중의) `matchup_model` 을
> **as-of 날짜별 판**으로 저장(`data/<표>/<as_of>.yaml`). 로더는 **as_of 이전
> 최신 판**만 고른다. 운영은 오늘 판, 재현·백필은 그 경기 날짜 **이전** 판.

🔴 **이 파일은 읽기만 한다** — 판을 적는 것은 도구다(`tools/versions_write.py`).
   ⚠️ 계약 `test_설정_yaml_을_코드가_쓰지_않는다` 가 앱의 yaml 쓰기를 막는다.

🔴 왜 판으로 두나 — 한 파일을 덮어쓰면 **어제 카드를 다시 돌릴 때 오늘 계수**가
   붙는다(미래를 본 값). 그러면 ⓑ·ⓒ 같은 고침이 좋아졌는지 **판단할 수가 없다**.
⚠️ **같은 날 판은 쓰지 않는다** — 그 판이 그날 경기를 먹었을 수 있다(엄격히 이전).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: 🔴 판이 사는 곳 — `data/<표>/<as_of>.yaml`
ROOT = Path(__file__).resolve().parents[2] / "data"


def path_of(table: str, key: str = "") -> Path:
    """🔴 그 표(와 열쇠)의 **판 디렉터리**. 열쇠의 `:`·`/` 는 `_` 로 바꾼다."""
    said = str(key or "").replace("/", "_").replace(":", "_")
    got = ROOT / str(table)
    return (got / said) if said else got


def _days(box: Path) -> list[str]:
    return sorted(p.stem for p in box.glob("*.yaml")) if box.exists() else []


def pick(box: Path, *, as_of) -> tuple[dict, str]:
    """🔴🔴 L3 — `as_of` **이전** 가장 최신 판. `(내용, 사유)`.

    ⚠️ `as_of` 가 없거나 tz 가 없으면 **예외**다(누설 금지와 같은 규율).
    ⚠️ 이전 판이 없으면 **빈 표 + 사유**다 — 가까운 미래 판으로 갈음하지 않는다.
    """
    if as_of is None:
        raise ValueError("🔴 `as_of` 가 없다 — 계수 판을 고를 수 없다(L3)")
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            raise ValueError("🔴 `as_of` 에 시간대가 없다 — naive 는 받지 않는다")
        want = as_of.date()
    elif isinstance(as_of, date):
        want = as_of
    else:
        raise ValueError(f"🔴 `as_of` 꼴을 모른다: {as_of!r}")
    rows = [d for d in _days(Path(box)) if d < want.isoformat()]
    if not rows:
        return {}, (f"🔴 `{Path(box).name}` 에 {want.isoformat()} **이전 판이 "
                    f"없다**(있는 판 {len(_days(Path(box)))}개) — 표 없이 간다")
    said = rows[-1]
    import yaml
    try:
        got = yaml.safe_load((Path(box) / f"{said}.yaml").read_text(
            encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return {}, f"🔴 판 `{said}` 을 못 읽었다: {exc}"
    return dict(got), f"판 `{said}`(as-of {want.isoformat()} 이전 최신)"
