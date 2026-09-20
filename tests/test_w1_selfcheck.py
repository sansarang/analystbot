"""[W1] 자가 점검 — 09-20 의 사고 여섯 가지를 **기계가 잡는가.**

🔴 이 단계는 판정에 쓰지 않는다(표시 전용). 이후 단계의 효과를 눈으로 보려면
   기준선이 먼저 있어야 한다 — 나아졌는지 말하려면 재는 자가 있어야 한다.

🔴 픽스처는 전부 `tests/fixtures/wiring_0920/` 의 **그날 실측 조각**이다.
   가짜 구조로 만든 불변식은 진짜 자료를 못 잡는다.

⚠️ **점검이 파이프라인을 죽이면 안 된다.** 자료가 비거나 모양이 달라도
   예외를 올리지 않는다 — 못 재면 "못 쟀다"고 적는다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

FX = pathlib.Path(__file__).parent / "fixtures" / "wiring_0920"


def _fx(name: str) -> dict:
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


def _codes(rows) -> set:
    return {r["code"] for r in (rows or [])}


# ── 09-20 사고 여섯 가지 ────────────────────────────────────────────
def test_결장이_양_팀에_똑같이_복사된_것을_잡는다():
    from app.ops import selfcheck as SC

    doc = _fx("abs_same_both_sides")
    hits = []
    for g in doc["games"]:
        hits += SC.check_absences(g["teams"], game_id=g["game_id"])
    assert "abs_same_both_sides" in _codes(hits), hits
    # 🔴 두 경기 **모두** 잡아야 한다 — 하나만 잡으면 규칙이 우연히 맞은 것이다.
    got = {h["key"] for h in hits if h["code"] == "abs_same_both_sides"}
    assert got == {"11201", "11244"}, got


def test_결장자가_선발_XI_에도_있는_것을_잡는다():
    from app.ops import selfcheck as SC

    doc = _fx("abs_in_xi")
    hits = SC.check_absences(doc["teams"], game_id=doc["game_id"])
    assert "abs_in_xi" in _codes(hits), hits
    # 무고사(Mugosa/Mugoša)는 발음부호가 달라도 같은 사람이다.
    detail = " ".join(h["detail"] for h in hits if h["code"] == "abs_in_xi")
    assert "Mugo" in detail or "Ha" in detail, detail


def test_오늘_XI_가_아닌_것을_잡는다():
    from app.ops import selfcheck as SC

    doc = _fx("abs_in_xi")
    hits = SC.check_xi(doc["teams"], game_id=doc["game_id"])
    assert "xi_not_today" in _codes(hits), hits


def test_휴식_시간이_말이_안_되는_것을_잡는다():
    from app.ops import selfcheck as SC

    rows = _fx("rest_hours_absurd")["rows"]
    hits = SC.check_rest(rows)
    assert "rest_hours_absurd" in _codes(hits), hits
    # 🔴 192h(8일)는 정상이다 — 문턱을 넘은 둘만 잡아야 한다(반대 위험).
    keys = {h["key"] for h in hits if h["code"] == "rest_hours_absurd"}
    assert keys == {"Pohang Steelers", "FC Seoul"}, keys


def test_스냅샷이_하나면_이동을_0_으로_적지_않는다():
    from app.ops import selfcheck as SC

    rows = _fx("odds_move_exact_zero")["rows"]
    hits = SC.check_odds_move(rows)
    assert "odds_move_exact_zero" in _codes(hits), hits


def test_적재가_멈춘_리그를_잡는다():
    from app.ops import selfcheck as SC

    doc = _fx("ingest_stale")
    hits = SC.check_ingest(doc["rows"], as_of=doc["as_of_kst"])
    assert "ingest_stale" in _codes(hits), hits
    keys = {h["key"] for h in hits if h["code"] == "ingest_stale"}
    assert keys == {"KBO"}, f"MLB·NPB 는 정상인데 잡혔다: {keys}"


def test_타_팀_선수가_섞인_것을_잡는다():
    from app.ops import selfcheck as SC

    doc = _fx("player_team_mismatch")
    hits = SC.check_absences(doc["teams"], game_id=doc["game_id"])
    assert "player_team_mismatch" in _codes(hits), hits


# ── 불변식 (T2) ─────────────────────────────────────────────────────
def test_selfcheck_never_raises():
    """🔴 점검이 파이프라인을 죽이면 안 된다 — 빈손·이상 모양에도 예외 없음."""
    from app.ops import selfcheck as SC

    junk = [None, {}, [], "", 0, {"home": None}, {"home": {"out": "문자열"}},
            [{"rest_hours": "없음"}], [{"odds": None}]]
    for fn in (SC.check_absences, SC.check_xi, SC.check_rest,
               SC.check_odds_move, SC.check_ingest):
        for j in junk:
            got = fn(j) if fn is not SC.check_absences else fn(j, game_id="x")
            assert isinstance(got, list), (fn.__name__, j, got)


def test_문턱은_config_한_곳에서_온다():
    """🔴 사본 금지 — 숫자를 코드에 박지 않는다."""
    import inspect

    from app.ops import selfcheck as SC

    src = inspect.getsource(SC)
    assert "ops.selfcheck" in src, "문턱 원본이 config 가 아니다"
    # ⚠️ `app.flow.rules` 는 경로에 `flow.` 접두사를 붙인다 — `ops:` 는
    #    최상위 블록이므로 `app.engine.rules` 가 맞다(실측으로 확인).
    from app.engine import rules as R

    assert R.get("ops.selfcheck.rest_hours_max") is not None
    assert R.get("ops.selfcheck.ingest_stale_hours") is not None


def test_코드_목록이_한_곳에_있다():
    """보고·집계가 이 이름으로 센다 — 이름표를 두 곳에 만들지 않는다."""
    from app.ops import selfcheck as SC

    assert set(SC.CODES) >= {
        "abs_same_both_sides", "abs_in_xi", "xi_not_today",
        "rest_hours_absurd", "odds_move_exact_zero", "source_blank_ratio",
        "ingest_stale", "player_team_mismatch", "match_unmapped",
        "derivatives_empty", "results_pending", "starter_unknown",
        "lineup_missing"}


@pytest.mark.asyncio
async def test_health_has_selfcheck_line():
    """/health 에 요약 한 줄이 실제로 나간다."""
    import app.health as H

    class _R:
        async def get(self, k):
            if k.startswith("selfcheck:"):
                return json.dumps([{"code": "ingest_stale", "key": "KBO",
                                    "detail": "마지막 적재 2026-09-12"}])
            return None

        async def hgetall(self, k):
            return {}

    line = await H.selfcheck_line(_R())
    assert "ingest_stale" in line or "점검" in line, line
    assert isinstance(line, str) and line.strip()
