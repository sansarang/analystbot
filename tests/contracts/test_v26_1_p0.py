"""🔴🔴 **P0 — 시간**(수정 지시 2026-10-13 밤 P0).

> 사전 실행: T−24h 기본 → T−3h 갱신 → 확정 XI 뜨면 즉시 ⑲(T−60~45분).
> 캐시: 팀 과거 경기·대회 일정·순위표·신원표는 하루 1회 미리 받아 둔다.
> 시간 상한: 카드 1장 **15분**. 넘는 단계는 ⬜ + 사유로 넘기고 카드를 낸다.
> 슬레이트 스케줄러: 킥오프 순 큐 · 각 단계 시각을 **카드 머리에** 찍는다.

🔴 **SL1** 단계 시각은 `core/slate` 하나가 센다(사본 금지) · **SL2** 카드 머리가
   그 줄을 찍는다 · **SL3** 킥오프를 지나면 `사후`(사후 기록용) · **SL4** 상한은
   **15분**이고 넘는 단계는 **⬜ + 사유**로 건너뛴다(멈추지 않는다) · **SL5**
   무거운 단계가 그 시계를 **본다** · **SL6** 하루 캐시는 **느린 주소만** 담고
   XI·결장·뉴스는 **늘 새로 받는다** · **SL7** 상한·시각은 **확률에 닿지 않는다**.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KO = datetime(2026, 10, 13, 12, 15, tzinfo=timezone.utc)


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_sl1_stage_times() -> None:
    from app.core import slate
    box = slate.times_of(KO)
    assert box["기본"] == KO - timedelta(hours=24)
    assert box["갱신"] == KO - timedelta(hours=3)
    assert box["XI"] == KO - timedelta(hours=1)
    assert slate.STAGES == (("기본", 24.0), ("갱신", 3.0), ("XI", 1.0))


def test_sl2_card_head_stamps_it() -> None:
    said = _src("app/core/render.py")
    assert "slate" in said and "head_of(" in said
    i = said.index("def _head(")
    assert "_sl.head_of" in said[i:i + 3000]


def test_sl3_after_kickoff_is_post_hoc() -> None:
    from app.core import slate
    got, why = slate.stage_of(KO, KO + timedelta(minutes=30))
    assert got == "사후" and "사후 기록용" in why
    for left, want in ((30.0, "대기"), (20.0, "기본"), (2.0, "갱신"),
                       (0.5, "XI")):
        assert slate.stage_of(KO, KO - timedelta(hours=left))[0] == want


def test_sl4_cap_is_twenty_minutes_and_skips() -> None:
    """🔴 상한 15 → **20분**(사용자 결정 2026-10-15) — 수집이 17~18분이라
    마지막 단계 ⑯ 이 늘 굶었다. ⚠️ 상한만 올리면 재발하므로
    `deadline.RESERVE_SEC`(⑯ 몫)이 **함께** 있어야 한다."""
    from app.core import deadline, slate
    assert slate.CARD_CAP_MIN == 20.0
    assert deadline.RESERVE_SEC > 0, "🔴 ⑯ 몫 예약이 없다 — 같은 병이 재발한다"
    one = deadline.Deadline(20.0)
    assert not one.over() and one.left_min() > 19
    said = one.skip("시험 단계")
    assert "건너뛰었다" in said and one.skipped == ["시험 단계"]
    assert "건너뛴 단계" in one.said_of()
    # 🔴 상한이 없으면 안 넘긴다
    none = deadline.Deadline(None)
    assert none.left_min() == float("inf") and not none.over()


def test_sl5_heavy_stages_watch_the_clock() -> None:
    for rel in ("app/core/stages/s4b_gapsearch.py", "app/core/stages/s2_facts.py"):
        said = _src(rel)
        assert "clock" in said and ".over()" in said, rel
    assert "st.clock" in _src("app/core/pipeline.py")


def test_sl6_day_cache_only_slow_urls() -> None:
    """🔴🔴 **SL6** — XI·결장·뉴스 주소는 하루 캐시에 **안 담긴다**."""
    from app.net import Net
    net = Net(day_cache=True)
    for slow in ("https://www.fotmob.com/leagues/525/matches/x",
                 "https://www.fotmob.com/teams/4177/fixtures/x"):
        assert net._day_path(slow, "") is not None, slow
    for fast in ("https://www.fotmob.com/matches/a-vs-b/xyz#6049990",
                 "https://news.test/article/1"):
        assert net._day_path(fast, "") is None, fast
    # 🔴 끄면 늘 없다(기본 꺼짐)
    assert Net()._day_path("https://www.fotmob.com/leagues/1/x", "") is None
    assert Net.DAY_TTL_SEC == 24 * 3600.0


def test_sl7_never_touches_probability() -> None:
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/legacy/old_engine.py", "app/core/conclude.py"):
        said = _src(rel)
        assert "slate" not in said and "deadline" not in said, rel
