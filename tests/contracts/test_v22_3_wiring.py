"""🔴🔴 **3번 배선 — 새 질의 + J리그 출장정지 공시**(지시 2026-10-13 밤 넷째).

> 새 질의(다국어·`site:`) + J리그 출장정지 공시를 운영 ⑤⑦에 배선 →
> 같은 49장+신규 카드로 6-7 재측정(전후).

🔴 **공시는 결장 사다리 칸 3(연맹 징계)의 자리**다 — 그 칸은 2026-10-11 까지
   *"⬜ 통로 없음"* 이었다(주소를 받아 둔 리그가 없었다). 이제 J1·J2 에
   **받아서 확인한 주소**가 있다(`data.j-league.or.jp/SFIN03/`).
🔴 **L2** — 공시는 **현재 값**이다 → **재생(카세트)에서는 쓰지 않는다**.
"""
from __future__ import annotations


def test_discipline_table_has_the_measured_url() -> None:
    from app import rules
    for key in ("league:J1", "league:J2"):
        box = rules.discipline_of(key)
        assert box, f"🔴 `{key}` 징계 주소가 표에 없다"
        assert "data.j-league.or.jp" in str(box.get("url")), box
        assert str(box.get("checked_at") or ""), "🔴 확인한 날이 없다"


def test_rung_counts_the_notice_rows() -> None:
    """🔴 칸 3 이 **받은 줄 수**를 센다(부르는 쪽이 넘긴다)."""
    from app.core import absence as ab
    from app.core.schema import Facts
    got = ab.ladder(Facts(), keys=["t1"], league="league:J1",
                    discipline={"n": 2, "why": "출장정지 공시 2명",
                                "rows": []})
    rung = [r for r in got["rungs"] if r["rung"] == "연맹 징계"][0]
    assert rung["got"] == 2 and "2명" in rung["why"], rung


def test_rung_says_when_the_channel_is_not_called() -> None:
    """⚠️ 넘기지 않으면 **옛 사유**가 그대로다(조용히 0 이 아니다)."""
    from app.core import absence as ab
    from app.core.schema import Facts
    got = ab.ladder(Facts(), keys=["t1"], league="league:J1")
    rung = [r for r in got["rungs"] if r["rung"] == "연맹 징계"][0]
    assert rung["got"] == 0 and ("주소는 있다" in rung["why"]
                                 or "통로 없음" in rung["why"])


def test_l2_replay_does_not_use_the_notice() -> None:
    """🔴🔴 **L2** — 재생에서는 공시를 **안 받는다**(현재 값이다)."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    said = (root / "app/core/stages/s2_facts.py").read_text(encoding="utf-8")
    i = said.index("async def _discipline_rows")
    box = said[i:i + 2500]
    assert "cassette" in box or "REPLAY" in box, "🔴 재생 가드가 없다"
    tree = ast.parse(said)
    del tree


def test_new_queries_are_wired_into_s3() -> None:
    """🔴 새 질의(표 기반)가 ③ 문서 수집의 질의 목록에 **들어간다**."""
    said = __import__("pathlib").Path("app/core/stages/s3_docs.py").read_text(
        encoding="utf-8")
    assert "search.query" in said or "_table_queries" in said
    i = said.index("queries=[")
    assert "said_table" in said[i:i + 200], said[i:i + 160]
