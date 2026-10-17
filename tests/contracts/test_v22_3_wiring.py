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


def test_코드가_만드는_질의_다발이_사라졌다() -> None:
    """🔴🔴 **딥서치 삭제**(사용자 지시 2026-10-17) — 종전 이름은
    `test_new_queries_are_wired_into_s3` 였고 *"표 기반 질의가 ③ 에 들어간다"* 를
    지켰다. 그 배선이 **지금은 없어야 한다.**

    ⚠️ 실측이 지운 까닭이다: 코드 질의 24~30개가 결과 734건을 긁어 기사 변수
       **2개**였고 묵은 글 본문에 63초를 썼다.
    🔴 원천 표(`config/sources/*.yaml`)는 **살아 있다** — 이제 질의가 아니라
       **도메인 등급**(`search/sources.py`)과 **대체 경로**(`search/fetch.py`)로
       쓴다. 그 둘을 같이 지우지 않았음을 함께 지킨다.
    """
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    raw = (root / "app/core/stages/s3_docs.py").read_text(encoding="utf-8")
    # 🔴 **D46** — 독스트링·주석을 뺀 **코드만** 본다(지운 까닭을 글로 적어
    #    두는 것과 그것을 **부르는** 것은 다르다).
    tree = ast.parse(raw)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and ast.get_docstring(n):
            n.body = n.body[1:]
    said = ast.unparse(tree)
    for one in ("_table_queries", "queries_for", "search.query"):
        assert one not in said, f"🔴 `{one}`(코드 질의)가 되살아났다"
    # 🔴 원천 표는 등급·대체 경로로 남는다
    for f, mark in (("app/core/search/sources.py", "config/sources"),
                    ("app/core/search/fetch.py", "config/sources")):
        got = (root / f).read_text(encoding="utf-8")
        assert mark in got, f"🔴 `{f}` 가 원천 표를 안 본다"


def test_kind_of_passes_the_league_id() -> None:
    """🔴🔴 **번호가 글자를 이긴다** — 임시 `Facts` 에 `league_id` 를 넣는다.

    ⚠️ 실측 2026-10-13: 그 칸이 비어 J리그 컵 경기가 손 표(`league:JLC`)가 아니라
       자동 등록 `league:fotmob224` 로 떨어졌고, **그 리그의 원천 표·징계 공시가
       안 붙었다**(사다리 칸 3 이 "통로 없음"으로 적혔다).
    """
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/core/stages/s2_facts.py").read_text(encoding="utf-8")
    i = said.index("def _kind_of(")
    box = said[i:i + 1200]
    assert "league_id=" in box, box[:400]
    # 🔴 번호가 있으면 손 표가 먼저다(그 규칙은 `competition.key_of` 가 든다)
    from app.core import competition as cp
    assert cp.key_of(league_id=224)[0] == "league:JLC"
