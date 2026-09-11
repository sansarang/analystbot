"""BLD-1 배선 계약 — 원장 행이 **실제로** 섀도 값을 싣는가.

🔴 이 파일은 `shadow_blend` 를 **최상단에서 임포트하지 않는다.** 임포트하면
   수정 전 코드에서 파일이 통째로 ImportError 로 죽고, 그러면 "심볼이 없다"로
   실패해 **결함 자체를 겨눈 단언**(원장에 값이 안 실린다)에 닿지 못한다.

🔴 왜 배선을 따로 잠그나: 실사고 PGP-2 — "죽으면 알리게" 수정이 **5일 전에
   배선이 끊긴 함수** 안에 들어갔다. 모듈이 있는 것과 불리는 것은 다르다.
"""


def test_원장_행이_섀도_값을_싣는다():
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 7, "p_claude": 0.54, "matchup": {"p_home": 0.54},
          "elo": {"home": {"레이팅": 1520}, "away": {"레이팅": 1480}}}
    row = _row_from_game(jg, {"sport": "kbo", "date": "2026-09-11"}, {})
    assert row is not None
    blend = row.get("shadow_blend")
    assert blend is not None, "원장 행에 섀도 값이 없다 — 배선이 끊겼다"
    assert blend["p_elo"] is not None
    assert blend["w0.5"] is not None


def test_Elo_가_없는_경기도_행은_만들어진다():
    """🔴 반대 위험 — 섀도 때문에 원장 행이 빠지면 판정 기록이 사라진다."""
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 8, "p_claude": 0.61, "matchup": {"p_home": 0.61}}
    row = _row_from_game(jg, {"sport": "npb", "date": "2026-09-11"}, {})
    assert row is not None and row["p_home"] == 0.61
    assert row["shadow_blend"]["why"] == "elo 없음"
