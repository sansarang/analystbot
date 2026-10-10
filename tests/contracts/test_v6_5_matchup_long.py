"""🔴🔴 **긴 카드의 상성 네 덩이** — 사용자 지시 2026-10-10(셋째) §5.

> 긴 카드: **골 목록 표(분·유형·상태·xG), 시간대 분포, 리드 유지력·추격력,
> 발동 규칙과 적합 효과.**

🔴 이 계약이 막는 것: 그 넷 중 하나라도 **조용히 빠지는 것**(#3). 긴 카드는
   1겹에서 잘린 수를 드러내는 자리이고, 그 넷이 상성 판정의 **재료 전부**다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 두 경기의 **골 목록** — 분·유형·상태·xG 가 다 다르게 들어 있다
ROWS_HOME = [
    {"home_name": "A", "away_name": "B", "mine_home": True,
     "goals": [
         {"minute": 12, "home": True, "before": (0, 0), "after": (1, 0),
          "situation": "FromCorner", "xg": 0.09},
         {"minute": 77, "home": False, "before": (1, 0), "after": (1, 1),
          "situation": "RegularPlay", "xg": 0.31},
         {"minute": 88, "home": False, "before": (1, 1), "after": (1, 2),
          "desc": "Penalty", "xg": 0.76}]},
    {"home_name": "C", "away_name": "A", "mine_home": False,
     "goals": [
         {"minute": 30, "home": False, "before": (0, 0), "after": (0, 1),
          "situation": "FastBreak", "xg": 0.22},
         {"minute": 45, "home": True, "before": (0, 1), "after": (1, 1),
          "situation": "RegularPlay"}]},
]
ROWS_AWAY = [
    {"home_name": "B", "away_name": "D", "mine_home": True,
     "goals": [
         {"minute": 20, "home": False, "before": (0, 0), "after": (0, 1),
          "situation": "FromCorner", "xg": 0.14},
         {"minute": 65, "home": True, "before": (0, 1), "after": (1, 1),
          "situation": "SetPiece"},
         {"minute": 80, "home": True, "before": (1, 1), "after": (2, 1),
          "situation": "RegularPlay", "xg": 0.44},
         # 🔴 **앞선 상태**에서 넣은 골 — 상태 칸 세 값이 다 나와야 표다
         {"minute": 85, "home": True, "before": (2, 1), "after": (3, 1),
          "situation": "FastBreak", "xg": 0.51}]},
]


def _matchup():
    """🔴 `s2e` 가 담는 그 모양을 **그 함수들로** 만든다(손으로 짓지 않는다)."""
    from app.core import goals as _g
    prof = {"home": _g.profile_of("A", ROWS_HOME),
            "away": _g.profile_of("B", ROWS_AWAY)}
    return {"profile": prof,
            "table": {"home": _g.table_of(ROWS_HOME),
                      "away": _g.table_of(ROWS_AWAY)},
            "fired": _g.fire(prof["home"], prof["away"], rest={}),
            "fired2": [], "why": "시험"}


def _card():
    from datetime import datetime, timedelta, timezone

    from app.core.schema import Card, Facts, MatchRef
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000001", away="team:000002",
                   home_name="A", away_name="B",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    # 🔴 `Card` 는 얼었다 — `matchup` 은 **낳을 때** 넣는다(`pipeline` 과 같다)
    return Card(match=ref, facts=Facts(), matchup=_matchup())


def test_v6_긴카드가_골목록_표를_분유형상태xG_로_낸다():
    """🔴 §5 ① — 골 하나하나가 **분·유형·상태·xG** 네 칸으로 적힌다."""
    from app.core import render
    said = render.matchup_long(_card())
    # 🔴 분 — 네 골의 분이 다 나온다(하나라도 빠지면 표가 아니다)
    for minute in (12, 77, 88, 30):
        assert f"{minute}'" in said, f"🔴 {minute}분 골이 표에 없다"
    # 🔴 유형 — 세트피스·필드골·PK·역습이 **사람 말로** 적힌다
    for kind in ("세트피스", "필드골", "PK", "역습"):
        assert kind in said, f"🔴 유형 `{kind}` 이 표에 없다"
    # 🔴 상태 — 그 골 직전 상태
    for state in ("동점", "앞섬", "뒤짐"):
        assert state in said, f"🔴 상태 `{state}` 이 표에 없다"
    # 🔴 xG — 있는 골은 수로, **없는 골은 `xG 없음`**(0 으로 메우지 않는다 · #3)
    assert "xG 0.09" in said and "xG 없음" in said, "🔴 xG 칸이 비었다"
    # 🔴 득/실을 가른다 — 자책골 규칙과 같은 쪽으로 센다
    assert "득 12'" in said and "실 77'" in said, "🔴 득점·실점을 안 가렸다"


def test_v6_긴카드가_시간대_리드유지력_발동규칙을_낸다():
    """🔴 §5 ②③④ — 나머지 세 덩이. 🔴 표본·`관찰만` 표시가 함께 나온다."""
    from app.core import goals as _g
    from app.core import render
    said = render.matchup_long(_card())
    assert "시간대 분포" in said
    for bucket in ("0-30", "31-60", "61-90+"):
        assert bucket in said, f"🔴 시간대 `{bucket}` 칸이 없다"
    assert "리드 유지력" in said and "추격력" in said
    assert "발동 규칙과 적합 효과" in said
    # 🔴 표본 미달 규칙은 **확률을 안 움직인다** — 그 말이 카드에 적힌다(§3-4)
    rows = list(_matchup()["fired"])
    if any(f.watch_only for f in rows):
        assert _g.WATCH_ONLY in said and "확률 미반영" in said, (
            "🔴 `관찰만` 규칙을 움직이는 규칙처럼 적었다")
    # 🔴 적합 없는 계수는 **임시값 표시**를 달고 나온다(금지 조항)
    if any(_g.PROVISIONAL in (f.why or "") for f in rows):
        assert _g.PROVISIONAL in said, "🔴 임시값 표시가 카드에서 빠졌다"


def test_v6_축마다_0건을_따로_적는다():
    """🔴 #3 — 축3 이 발동했어도 **축2 0건**은 그대로 보인다.

    ⚠️ 돌연변이: 두 축을 한 목록으로 합쳐 세면(`if not rows`) 축3 발동 5건이
       축2 의 0건을 **조용히 가린다** — 그것이 실측 2026-10-10 의 모양이었다.
    """
    from app.core import render
    said = render.matchup_long(_card())            # 🔴 `fired2` 는 빈 목록이다
    assert "축2 T1~T6 발동 0건" in said, "🔴 축2 가 0건인 사실이 카드에서 사라졌다"
    assert "`T1" in said or "`T9" in said or "`T10" in said, (
        "🔴 축3 발동이 아예 안 적혔다 — 시험 재료가 틀렸다")


def test_v6_상성이_못돌면_사유를_적는다():
    """🔴 #3 — 세 축을 못 모았을 때 **그 사유**가 긴 카드에 남는다."""
    from app.core import render
    said = render.matchup_long(_card().model_copy(
        update={"matchup": {"why": "🔴 두 팀 과거 경기를 다 못 받았다"}}))
    assert "⬜" in said and "과거 경기" in said
    assert "안 돌렸다" in render.matchup_long(
        _card().model_copy(update={"matchup": {}}))


def test_v6_긴카드가_네_덩이를_부른다():
    """🔴 배선 — `card_text` 가 `matchup_long` 을 **실제로** 부른다(#2)."""
    import ast
    said = (ROOT / "app" / "core" / "render.py").read_text(encoding="utf-8")
    src = [n for n in ast.walk(ast.parse(said))
           if isinstance(n, ast.FunctionDef) and n.name == "card_text"]
    assert src and "matchup_long" in ast.unparse(src[0]), (
        "🔴 긴 카드가 상성 블록을 안 부른다")
