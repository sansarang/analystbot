"""🔴🔴 **§3 S1 — 이번 시즌 우선 폼**(통합 지시서 2026-10-13 밤).

> `old_engine` 에 넘기는 폼용 경기 목록을 바꾼다(**코드 불변 · 입력만**):
> 이번 시즌 리그 경기가 `k_min` 이상이면 **이번 시즌 경기만** · 미만이면
> 이번 시즌 전부 + **지난 시즌 최근 경기로 채움**(채운 경기 **표시**).
> 계약 **S1-1**: `old_engine` 해시 불변(K0) · **S1-2**: 입력 목록에 `as_of`
> 이후 경기 **실패**.

🔴 **왜 입력만 바꾸나** — M1 은 **K0 고정**이다(§0 원칙). 폼은 `old_engine` 이
   받는 **경기 목록**에서 오므로, 목록을 바꾸면 코드를 안 고치고도 시험할 수 있다.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _rows(days: list[str]) -> list[dict]:
    return [{"utc": f"{d}T12:00:00Z", "league": "league:KL1",
             "gf": 1, "ga": 0} for d in days]


def test_this_season_only_when_enough() -> None:
    from app.core.legacy import form_input as fi
    rows = _rows(["2025-10-01", "2025-11-01",
                  "2026-03-01", "2026-03-08", "2026-03-15"])
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:KL1", k_min=3)
    assert len(got) == 3 and all(r["utc"].startswith("2026") for r in got)
    assert "이번 시즌만" in why


def test_fills_from_last_season_and_marks_it() -> None:
    """🔴 모자라면 지난 시즌으로 채우고 **채운 경기를 표시한다**."""
    from app.core.legacy import form_input as fi
    rows = _rows(["2025-10-01", "2025-11-01", "2026-03-01"])
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:KL1", k_min=5)
    assert len(got) == 3, got                 # 🔴 있는 것 전부(1 + 2)
    assert sum(1 for r in got if r.get("filled")) == 2, got
    assert "채웠다" in why and "2" in why


def test_weak_halves_the_fill() -> None:
    """🔴 가중 축소 판 — 보충분을 **절반만** 넣는다(가중 0.5 의 이산 근사)."""
    from app.core.legacy import form_input as fi
    rows = _rows(["2025-09-01", "2025-10-01", "2025-11-01", "2026-03-01"])
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:KL1", k_min=5, weak=True)
    # 🔴 모자란 수 4 의 **절반 = 2** 만 채운다(이번 시즌 1 + 보충 2)
    assert sum(1 for r in got if r.get("filled")) == 2, got
    assert "절반" in why or "축소" in why


def test_s1_2_no_future_match_can_enter() -> None:
    """🔴🔴 **S1-2** — `as_of` 이후 경기는 목록에 **없다**(문은 `before_as_of` 하나)."""
    from app.core.legacy import form_input as fi
    rows = _rows(["2026-03-01", "2026-03-08", "2026-09-01"])
    got, _why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                        league="league:KL1", k_min=2)
    assert all(r["utc"] < "2026-03-20" for r in got), got


def test_se1_guard_refuses_untagged_rows() -> None:
    """🔴 **SE1** — `season_id` 를 못 만든 경기가 있으면 **빈 목록 + 사유**다."""
    from app.core.legacy import form_input as fi
    rows = [{"utc": "2026-03-01T12:00:00Z", "league": "league:노리그"}]
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:노리그", k_min=3)
    assert got == [] and "🔴" in why


def test_s1_1_frozen_engine_hash_is_unchanged() -> None:
    """🔴🔴 **S1-1** — 얼린 `old_engine` 은 **안 바뀐다**(K0)."""
    import ast
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    got = hashlib.sha256(
        (root / "app/core/legacy/old_engine.py").read_bytes()).hexdigest()
    pin = (root / "tests/contracts/test_v16_0_legacy.py").read_text(
        encoding="utf-8")
    assert got in pin, "🔴 얼린 경로가 바뀌었다 — K0 계약을 먼저 본다"
    # 🔴 어댑터는 얼린 코드를 **부르지 않는다**(입력만 만든다)
    tree = ast.parse((root / "app/core/legacy/form_input.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    assert "old_engine" not in ast.unparse(tree)
