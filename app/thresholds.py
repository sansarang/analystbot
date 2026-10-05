"""🔴🔴 **상수는 근거와 함께** — v5 §5-6. [#23]

> 상수가 필요한 자리는 `config/thresholds.yaml` 에 **근거(원장 통계)와 함께**
> 적고, **근거 없는 상수는 계약 실패.**

⚠️ 원본은 `config/thresholds.yaml` 이다 — 이 파일은 **읽고 검사만** 한다(사본 금지).
"""
from __future__ import annotations

THRESHOLDS = "config/thresholds.yaml"


def all_rows() -> dict[str, dict]:
    """🔴 선언 전부. 각 줄이 `value` 와 `basis` 를 든다."""
    from app import rules
    return dict((rules._load(THRESHOLDS).get("thresholds") or {}))


def check(row: dict, *, name: str) -> object:
    """🔴 그 줄의 값. ⚠️ **근거가 없으면 터진다**(§5-6).

    🔴 `value` 가 `null` 이면 **걷은 상수**다 — 부르는 쪽이 그것을 쓰면 안 된다.
    """
    why = str((row or {}).get("basis") or "").strip()
    if not why:
        raise ValueError(
            f"🔴 상수 `{name}` 에 **근거가 없다**(§5-6 [#23]) — "
            f"`config/thresholds.yaml` 에 `basis` 를 적어라. 근거 없는 상수로 "
            f"방향을 정하면 그 판정은 뜻이 없다(ERA 0.75 가 그랬다)")
    return (row or {}).get("value")


def value(name: str) -> object:
    """🔴 이름으로 꺼낸다. ⚠️ 없거나 걷힌 상수면 `None`."""
    rows = all_rows()
    if name not in rows:
        raise ValueError(f"🔴 선언에 없는 상수다: {name!r} — "
                         f"있는 것은 {sorted(rows)}")
    return check(rows[name], name=name)
