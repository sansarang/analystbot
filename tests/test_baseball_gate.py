"""야구 추천 게이트 — 2-소스 폐기, NPB last-3 검증 전 탈락. 축구 2-소스는 유지."""
from app.config import Settings
from app.pipeline import qualifies


def test_npb_rec_fails_until_last3_verified():
    s = Settings(_env_file=None)
    assert s.npb_last3_verified is False
    pick = {"p": 0.64, "sport": "npb", "pick_state": "final",
            "lineup_status": "confirmed", "two_source": True}
    assert not qualifies(pick, s)
    s.npb_last3_verified = True
    assert qualifies(pick, s)


def test_kbo_qualifies_without_two_source():
    """야구 2-소스 폐기 — 58% + 라인업이면 추천 게이트 통과."""
    s = Settings(_env_file=None)
    pick = {"p": 0.62, "sport": "kbo", "pick_state": "final",
            "lineup_status": "confirmed", "two_source": False}
    assert qualifies(pick, s)


def test_soccer_still_requires_two_source():
    s = Settings(_env_file=None)
    pick = {"p": 0.62, "sport": "soccer", "two_source": False}
    assert not qualifies(pick, s)
    pick["two_source"] = True
    assert qualifies(pick, s)


def test_form_unavailable_fails_baseball_rec():
    s = Settings(_env_file=None)
    pick = {"p": 0.64, "sport": "kbo", "pick_state": "final",
            "lineup_status": "confirmed", "form_unavailable": True}
    assert not qualifies(pick, s)
    pick["form_unavailable"] = False
    assert qualifies(pick, s)
