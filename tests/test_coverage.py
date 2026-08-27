"""[A-4·5단계] 미수집 정직 표기 · 리그별 딥서치 스위치.

없는 것을 억지로 만드는 것보다 없다고 말하는 것이 낫다.
"""

from app.config import Settings
from app.engine.coverage import (
    ALL_AXES,
    available_axes,
    coverage_note,
    qualifies_axes,
    uncollected,
)


def test_kbo_npb_have_no_expert_axis():
    """실측(2026-08-27): KBO expert_picks 0/5 · NPB 1/6 vs MLB 10/15 · 축구 3/3."""
    for sport in ("kbo", "npb"):
        assert "expert_picks" in uncollected(sport)
        assert available_axes(sport) == ("data", "model")
    for sport in ("mlb", "soccer"):
        assert uncollected(sport) == ()
        assert available_axes(sport) == ALL_AXES


def test_reduced_axes_raise_the_bar_explicitly():
    """🔴 축이 3개에서 2개로 줄었으면 문턱이 높아져야 한다.

    종전 `axes_n >= 2`는 KBO에서 **우연히** data+model을 요구했다. 우연에 기대면
    나중에 전문가 축이 살아났을 때 조용히 느슨해진다.
    """
    assert qualifies_axes("kbo", {"data": True, "model": True}) is True
    assert qualifies_axes("kbo", {"data": True, "model": False}) is False
    assert qualifies_axes("kbo", {"data": False, "model": True}) is False
    assert qualifies_axes("kbo", {}) is False


def test_full_axis_sports_keep_the_two_of_three_rule():
    assert qualifies_axes("mlb", {"expert": True, "model": True}) is True
    assert qualifies_axes("mlb", {"data": True, "model": True}) is True
    assert qualifies_axes("mlb", {"model": True}) is False
    # 전문가 다수 지지는 2축으로 센다 (종전 규율 유지)
    assert qualifies_axes("mlb", {"expert": True, "expert_strong": True}) is True


def test_note_tells_the_user_what_the_pick_rests_on():
    """사용자가 이 픽이 어떤 근거 위에 있는지 알아야 한다."""
    note = coverage_note("kbo")
    assert "전문가 픽" in note and "미수집" in note and "2축" in note
    assert coverage_note("mlb") == ""


# ---------------------------------------------------------------- [A-5] 스위치

def _st(**kw):
    return Settings(anthropic_api_key="k", **kw)


def test_deepsearch_switch_defaults_to_crawl_only_for_kbo_npb():
    s = _st()
    assert s.deepsearch_enabled("mlb") is True
    assert s.deepsearch_enabled("soccer") is True
    assert s.deepsearch_enabled("kbo") is False, "KBO는 크롤링으로 완전 대체됐다"
    assert s.deepsearch_enabled("npb") is False


def test_switch_is_env_controlled():
    """코드 수정 없이 .env만으로 켜고 끌 수 있어야 한다."""
    assert _st(deepsearch_sports="mlb,soccer,kbo").deepsearch_enabled("kbo") is True
    assert _st(deepsearch_sports="").deepsearch_enabled("mlb") is False
    assert _st(deepsearch_sports=" KBO , MLB ").deepsearch_enabled("kbo") is True


def test_off_is_not_a_failure_state():
    """🔴 '끈 것'과 '못 받은 것'을 섞으면 거짓 경보가 난다.

    "리서치 0/5 실패"라고 알리면서 실제로는 의도대로 크롤링만 쓰는 상황.
    """
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert '_OK_STATES = ("refreshed", "cached", "off", "stale_fallback")' in src
    assert "딥서치 비활성 — 크롤링 전용" in src


def test_uncollected_fields_are_not_fetched_behind_the_scenes():
    """카드가 '미수집'이라 말하면서 뒤에서 호출하면 표기가 거짓이 된다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index("_use_deep = get_settings().deepsearch_enabled(sport)")
    block = src[i:i + 1200]
    assert "if _use_deep:" in block
    assert block.index("if _use_deep:") < block.index("live_briefing"), \
        "여론 호출이 스위치 밖에 있다"
    assert block.index("if _use_deep:") < block.index("_grok.sentiment"), \
        "여론 호출이 스위치 밖에 있다"
