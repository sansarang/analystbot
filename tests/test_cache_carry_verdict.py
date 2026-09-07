"""캐시 재생성이 판정을 지우지 않는다 — 2026-09-06 15:34 실사고.

15:32 에 Opus 최종 판정(p=0.37)이 붙어 카드까지 나갔는데, 15:34 의 캐시
재생성이 그 경기를 판정 없는 상태로 되돌렸다. 유료 호출 하나가 그냥
버려졌고, 최종 락은 잡힌 채라 다시 낼 수도 없었다.
(그 락 문제는 `4eb767b` 에서 따로 고쳤다 — 여기는 유실 자체를 막는다.)
"""
from __future__ import annotations

from app.pipeline import _VERDICT_FIELDS, _carry_verdicts


def _judged(gid=1, p=0.37, stage="final"):
    return {"game_id": gid, "p_claude": p, "judge_stage": stage,
            "final_verdict": stage == "final", "verdict": "홈 우세",
            "judge_confidence": "medium", "judge_pass": False,
            "matchup": {"model": "claude-opus-5", "p_home": p},
            "model": "claude-opus-5", "form_unavailable": False,
            "p_market_send": 0.64, "elo": {"home": {"레이팅": 1514.4}}}


def _empty(gid=1):
    return {"game_id": gid, "home": "H", "away": "A"}


def test_verdict_is_carried_when_the_rebuild_has_none():
    new = [_empty(1)]
    n = _carry_verdicts([_judged(1)], new)
    assert n == 1
    assert new[0]["p_claude"] == 0.37
    assert new[0]["judge_stage"] == "final"
    assert new[0]["matchup"]["model"] == "claude-opus-5"
    assert new[0]["p_market_send"] == 0.64


def test_a_fresh_verdict_is_never_overwritten():
    """🔴 재판정 결과를 옛 판정으로 되돌리면 안 된다."""
    new = [_judged(1, p=0.55, stage="prelim")]
    n = _carry_verdicts([_judged(1, p=0.37, stage="final")], new)
    assert n == 0
    assert new[0]["p_claude"] == 0.55 and new[0]["judge_stage"] == "prelim"


def test_nothing_to_carry_is_a_noop():
    new = [_empty(1)]
    assert _carry_verdicts([], new) == 0
    assert _carry_verdicts([_empty(1)], new) == 0
    assert new[0].get("p_claude") is None


def test_only_matching_game_ids_are_carried():
    new = [_empty(2)]
    assert _carry_verdicts([_judged(1)], new) == 0
    assert new[0].get("p_claude") is None


def test_field_list_covers_what_a_verdict_writes():
    """`apply_matchup` 이 새기는 필드가 원본이다 — 목록이 뒤처지면 유실된다."""
    import pathlib

    src = pathlib.Path("app/engine/matchup.py").read_text(encoding="utf-8")
    body = src[src.index("def apply_matchup"):]
    body = body[:body.index("\ndef ", 1)]
    import re
    written = set(re.findall(r'jg\["([^"]+)"\]\s*=', body))
    missing = written - set(_VERDICT_FIELDS)
    assert not missing, f"판정이 쓰는데 승계 목록에 없다: {sorted(missing)}"


def test_save_caches_reads_the_previous_cache_first():
    import pathlib

    src = pathlib.Path("app/pipeline.py").read_text(encoding="utf-8")
    body = src[src.index("async def _save_caches"):]
    body = body[:body.index("\nasync def ", 1)]
    assert "_carry_verdicts" in body
    assert body.index("_carry_verdicts") < body.index("redis.set")
