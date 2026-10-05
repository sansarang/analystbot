"""🔴🔴 **결정 ④ — 어댑터 고유 모양은 어댑터 안에서 끝낸다**(v5 §8-3).

사용자 결정 2026-10-04:

> v5 §8-3대로 **어댑터 고유 모양(dict)은 어댑터 안에서 list로 바꾸고 밖으로
> 내지 않는다.** `roster_of` 입력은 **`list[str]` 만 받는다**는 계약을 걸고,
> **NPB 경기만** 다시 돌린다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (게이트2 2판 · NPB 가 **크래시**했다)
══════════════════════════════════════════════════════════════════

```
File "app/analyze.py", line 856, in roster_of
    for nm in (val.get("squad") or []) + (val.get("players") or []):
TypeError: can only concatenate list (not "dict") to list
```

NPB 어댑터가 `players` 를 **dict**(이름 → 선수 페이지 URL)로 냈다:

```
players={'デュプランティエ': 'https://npb.jp/bis/players/13715150.html', …}
```

⚠️ fotmob 의 `squad` 는 **목록**이다. 🔴 두 어댑터가 **다른 모양**을 같은 칸에
넣었고 `roster_of` 는 목록만 가정했다 — `gather` 입구라 **경기 전체가 죽었다.**

🔴 막는 것은 증상(*"NPB 가 터진다"*)이 아니라 **모양**이다(§11-1):
   *"어댑터가 넣는 모양을 판정층이 모른다."*
"""
from __future__ import annotations

import pytest


def test_dec4_npb_가_players_를_목록으로_낸다():
    """🔴 어댑터 **안에서** 바꾼다 — dict 를 밖으로 내지 않는다(§8-3)."""
    from app.cells import Question
    from app.collect import npb
    from app.net import Fetched

    # 🔴 실측한 그 모양이다 — npb.jp 명단 표의 선수 링크(2026-10-04).
    #    ⚠️ `parse_roster_ids` 가 그 dict 를 만든 함수다(`/teams/rst_` 페이지).
    html = ('<table><tr><td><a href="/bis/players/13715150.html">'
            'デュプランティエ</a></td></tr>'
            '<tr><td><a href="/bis/players/5115513.html">東克樹</a></td></tr>'
            '</table>')
    got = Fetched(url="https://npb.jp/bis/teams/rst_db.html", ok=True,
                  status=200, text=html, reason="ok")
    q = Question(type="roster_ids", subject="横浜DeNAベイスターズ",
                 team="横浜DeNAベイスターズ")
    rows = npb.parse_roster_ids(got, q)
    assert rows, "🔴 고정물에서 명단을 못 뽑았다 — 계약을 먼저 고쳐라"
    for row in rows:
        val = row.value if hasattr(row, "value") else row
        assert "players" in (val or {}), (
            f"🔴 공유 칸 `players` 가 **없다** — 다른 어댑터는 다 넣는다: "
            f"{sorted(val or {})}")
        said = val["players"]
        assert isinstance(said, list), (
            f"🔴 `players` 가 **{type(said).__name__}** 다 — 어댑터 고유 모양을 "
            f"밖으로 냈다(§8-3). 어댑터 안에서 `list[str]` 로 바꿔라")
        for nm in said:
            assert isinstance(nm, str), (
                f"🔴 `players` 안에 **{type(nm).__name__}** 가 있다 — "
                f"`list[str]` 이어야 한다")


def test_dec4_roster_of_는_list_만_받는다():
    """🔴🔴 **계약으로 잠근다** — dict 가 들어오면 **사유와 함께 거부**한다.

    ⚠️ 조용히 통과시키면(키만 꺼내 쓰면) 어댑터가 모양을 흘린 사실이 **아무
       데도 안 남는다**(#3). 🔴 터지지도, 조용하지도 않아야 한다.
    """
    from app.analyze import roster_of

    class _F:
        team = "T"

        def __init__(self, value):
            self.value = value

    # ✅ 목록은 지난다
    got = roster_of([_F({"squad": ["A", "B"], "players": ["C"]})], "T")
    assert set(got) == {"A", "B", "C"}, got

    # 🔴 dict 가 오면 **터지지 않는다** — 거부하고 사유를 남긴다
    bad = _F({"players": {"デュプランティエ": "https://x/1.html"}})
    out = roster_of([bad], "T")
    assert isinstance(out, tuple), out
    # ⚠️ 이름을 **주워 쓰지 않는다** — 그 칸은 계약 위반이므로 버린다
    assert "デュプランティエ" not in out, (
        "🔴 dict 에서 이름을 **주워 썼다** — 그러면 어댑터가 모양을 흘린 사실이 "
        "아무 데도 안 남는다(#3). 버리고 사유를 남겨라")


def test_dec4_흘린_모양이_사유로_남는다():
    """🔴 **조용한 0 금지**(#3) — 거부한 칸을 셀 수 있어야 한다."""
    from app import analyze
    from tests._helpers import strip_docs
    import inspect
    body = strip_docs(inspect.getsource(analyze.roster_of))
    assert "SHAPE" in body or "list" in body, body[:200]
    # 🔴 그 사실을 **세는 자리**가 있어야 한다
    assert hasattr(analyze, "ROSTER_SHAPE_DROPPED"), (
        "🔴 어댑터가 흘린 모양을 **세지 않는다** — `analyze.ROSTER_SHAPE_DROPPED` "
        "같은 자리에 쌓고 사유로 내라(#3)")


@pytest.mark.parametrize("val", [
    {"squad": ["A"], "players": ["B"]},         # ✅ 둘 다 목록
    {"squad": ["A"]},                            # ✅ 하나만
    {"players": []},                             # ✅ 빈 목록
    {},                                          # ✅ 아무것도 없다
])
def test_dec4_정상_모양은_그대로_돈다(val):
    """⚠️ 고치면서 **멀쩡한 길을 막지 않는다**."""
    from app.analyze import roster_of

    class _F:
        team = "T"
        value = val
    assert isinstance(roster_of([_F()], "T"), tuple)
