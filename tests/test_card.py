"""[§9] 상태 대조 카드 1단 — 사실 층.

이 층의 계약은 하나다: **사실만 넣는다.** 해석(▲▼)이 섞이면 3단 대조봇이
판단을 사실로 착각하고, 그 순간 정보 차단벽이 무너진다.
"""

from app.engine.card import CELL_KEYS, MAX_UNKNOWN, build_card, build_side

JG = {"game_id": 1, "home": "Kia Tigers", "away": "Lotte Giants"}

FULL = {
    "home_usage": {"last_game_date": "2026-08-25", "pitchers_used_last": 5,
                   "relief_ip_last": 4.33, "relief_batters_last": 16,
                   "relief_ip_l3": 9.0, "relief_batters_l3": 42, "window_games": 3,
                   "back_to_back": ["성영탁"], "back_to_back_count": 1,
                   "score_games": 3, "results_l3": "WLL", "runs_l3": 16,
                   "runs_allowed_l3": 16, "runs_per_game_l3": 5.33,
                   "comeback_wins_l3": 1, "blown_leads_l3": 1, "one_run_games_l3": 1},
    "home_pitcher": {"name": "황동하", "throws": "R", "era_season": 4.82,
                     "whip": 1.49, "ip_avg_recent": 3.82},
    "home_lineup": {"order": "이호연-박상준-김도영"},
    "lineup_announced_at": "17:43",
    "home_offense": {"ops": 0.788},
    "home_standing": {"rank": 4, "w": 61, "l": 50, "d": 2,
                      "games_behind": 5.5, "remaining": 31},
}


def test_all_five_cells_fill_from_real_shape():
    cells = build_side(FULL, "home")
    assert set(cells) == set(CELL_KEYS)
    assert all(c.known for c in cells.values()), \
        {k: c.facts for k, c in cells.items() if not c.known}
    assert "황동하" in cells["starter"].facts[0]
    assert "4위" in cells["weight"].facts[0]


def test_facts_carry_numbers_the_interpreter_can_cite():
    """2단은 사실의 숫자·이름을 인용해야 통과한다 — 인용할 것이 있어야 한다."""
    cells = build_side(FULL, "home")
    for key in ("bullpen", "starter", "recent3", "weight"):
        joined = " ".join(cells[key].facts)
        assert any(ch.isdigit() for ch in joined), f"{key} 칸에 숫자가 없다"


def test_facts_contain_no_interpretation():
    """🔴 사실 층에 판단이 섞이면 3단이 판단을 사실로 착각한다."""
    banned = ("▲", "▼", "우세", "열세", "얇", "좋다", "나쁘다", "유리", "불리")
    for c in build_side(FULL, "home").values():
        for f in c.facts:
            assert not any(b in f for b in banned), f"해석이 섞였다: {f}"


def test_missing_source_is_unknown_not_zero():
    """🔴 '소모 0'과 '모름'을 섞으면 수집 실패가 '충분함 ▲'으로 오독된다."""
    cells = build_side({}, "home")
    assert all(not c.known for c in cells.values())
    assert all(c.facts == [] for c in cells.values())


def test_zero_is_a_fact_not_a_gap():
    """반대 방향 — 실제로 0인 것은 사실이다. 빈칸으로 만들면 안 된다."""
    r = {"home_usage": {"last_game_date": "2026-08-25", "pitchers_used_last": 1,
                        "relief_ip_last": 0.0, "relief_batters_last": 0,
                        "relief_ip_l3": 0.0, "relief_batters_l3": 0,
                        "back_to_back": [], "back_to_back_count": 0}}
    cells = build_side(r, "home")
    assert cells["bullpen"].known
    assert any("연속 등판 없음" in f for f in cells["bullpen"].facts)


def test_unknown_cells_block_judgement():
    """모름이 셋 이상이면 판정하지 않는다 — 침묵이 추측보다 낫다."""
    partial = {k: v for k, v in FULL.items() if k in ("home_pitcher", "home_standing")}
    card = build_card(JG, partial)
    assert card["judgeable"] is False
    assert len(card["unknown"]) > MAX_UNKNOWN
    assert "판정하지 않는다" in card["reason"]


def test_a_cell_is_unknown_unless_both_teams_have_it():
    """한쪽만 아는 칸으로는 대조가 불가능하다 — 대조 카드의 단위는 '양 팀'이다."""
    card = build_card(JG, FULL)          # away 재료가 전혀 없다
    assert card["unknown"] == list(CELL_KEYS)
    assert card["judgeable"] is False


def test_both_sides_known_is_judgeable():
    both = dict(FULL)
    both.update({k.replace("home", "away"): v for k, v in FULL.items()
                 if k.startswith("home")})
    card = build_card(JG, both)
    assert card["unknown"] == []
    assert card["judgeable"] is True and card["reason"] == ""


def test_projected_starter_is_not_shown_as_confirmed():
    """예상을 확정으로 취급하면 안 된다 — 상태를 그대로 표기한다."""
    r = dict(FULL, starter_status="예상")
    facts = build_side(r, "home")["starter"].facts
    assert any("선발 발표: 예상" in f for f in facts)


def test_recent3_falls_back_to_form_string_only():
    """스코어보드가 없으면 승패 문자열만 낸다 — 없는 것을 만들지 않는다."""
    r = {"home_recent_form": {"form": "WLLWW"}}
    facts = build_side(r, "home")["recent3"].facts
    assert facts == ["최근 폼 WLLWW"]
