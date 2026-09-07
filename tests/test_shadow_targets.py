"""감시 L2·L3 대상 선정 — 캐시에 없는 키를 기다리지 않는다.

🔴 실측 2026-09-07: `judge_review` 0행 · `shadow_panel` 0행 (전 기간).
   `pick_targets` 가 `g["gate_result"]` 를 읽는데 **분석 캐시의 경기 dict 에는
   그 키가 없다** — `analysis:mlb:2026-09-06` 15경기 전부 None 이었다.
   게이트 등급은 `pick_ledger` 에만 기록되고 캐시에는 안 남는다.
   그래서 대상이 언제나 0건이었고 감시 3층 중 두 층이 한 번도 돌지 않았다.
"""

from app.engine.pick_ledger import (GATE_BOARD_ONLY, GATE_RECOMMENDED,
                                    gate_result_of)
from app.engine.shadow_panel import pick_targets


def _g(gid, p, *, recommended, veto=False, **kw):
    jg = {"game_id": gid, "sport": "kbo",
          "matchup": {"p_home": p},
          "judge_confidence": "low" if veto else "medium",
          "pick_summary": {"recommended": recommended, "p": p, "odds": None}}
    jg.update(kw)
    return jg


def test_캐시에_gate_result_키가_없어도_대상을_찾는다():
    """🔴 이 파일이 존재하는 이유. 등급을 다시 계산해서 판정한다."""
    games = [_g(1, 0.64, recommended=True), _g(2, 0.52, recommended=False)]
    for g in games:
        assert "gate_result" not in g, "테스트 전제: 캐시에는 그 키가 없다"
    got = pick_targets(games)
    assert [g["game_id"] for g in got] == [1], f"대상 선정 실패: {got}"


def test_등급_규칙을_베끼지_않는다():
    """⚠️ `gate_result_of` 가 원본이다 — 여기서 추천 조건을 다시 쓰지 않는다."""
    src = open("app/engine/shadow_panel.py", encoding="utf-8").read()
    i = src.index("def pick_targets")
    seg = src[i:src.index("\ndef ", i + 10)]
    assert "gate_result_of" in seg
    assert "recommended" not in seg, "추천 판별을 베꼈다"


def test_보드만은_대상이_아니다():
    games = [_g(1, 0.55, recommended=False)]
    assert gate_result_of(games[0], games[0]["pick_summary"]) == GATE_BOARD_ONLY
    assert pick_targets(games) == []


def test_거부권_탈락은_대상이_아니다():
    """확신도 '하'는 확률이 높아도 탈락이다."""
    games = [_g(1, 0.66, recommended=True, veto=True)]
    assert pick_targets(games) == []


def test_확신_높은_순으로_자른다():
    """상한이 있으므로 0.5 에서 먼 것부터 본다."""
    games = [_g(1, 0.60, recommended=True), _g(2, 0.66, recommended=True),
             _g(3, 0.62, recommended=True)]
    got = pick_targets(games, limit=2)
    assert [g["game_id"] for g in got] == [2, 3], f"{[g['game_id'] for g in got]}"


def test_p_home_이_없으면_대상이_아니다():
    """판정이 없으면 검사할 것도 없다."""
    g = _g(1, 0.64, recommended=True)
    g["matchup"] = {}
    assert pick_targets([g]) == []


def test_상한은_config_가_원본이다():
    src = open("app/engine/shadow_panel.py", encoding="utf-8").read()
    i = src.index("def pick_targets")
    seg = src[i:src.index("\ndef ", i + 10)]
    assert "shadow_max_per_slate" in seg
    assert "GATE_RECOMMENDED" in seg and GATE_RECOMMENDED == "추천"


def test_등급_계산이_실패해도_다른_경기를_막지_않는다():
    """한 경기의 등급을 못 내면 그 경기만 빠진다."""
    bad = {"game_id": 9, "matchup": {"p_home": 0.6}, "pick_summary": None}
    good = _g(1, 0.64, recommended=True)
    got = pick_targets([bad, good])
    assert [g["game_id"] for g in got] == [1]
