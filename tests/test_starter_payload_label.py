"""PRM-1 — 선발 등판 칸이 홈/원정만 적어 원정이 눈에 안 띈다.

🔴 **실측 2026-09-13 (운영, Seattle Mariners @ Athletics, game 6003).**
   제미니가 "원정 선발 Bryan Woo의 최근 등판 기록이 확인되지 않았다"고 썼는데
   실제로는 **프롬프트에 있었다**:
     선발 최근 등판 원본 1331자 · ITEM_MAX 2600 · **잘림 없음**
     `"away"` 포함 True · 경기 10건(홈 5 + 원정 5)
     `DB본것` 에도 '선발 최근 등판' 을 적었다 — 보고도 홈만 읽었다.

   칸이 `{"home": {...}, "away": {...}}` 뿐이라 어느 팀·어느 투수인지 블록
   안에 없다. 이름을 넣어 원정이 건너뛰어지지 않게 한다.

⚠️ **기존 키(home·away)는 그대로 둔다** — 읽는 곳이 넷이다.
"""
from app.engine import matchup as M


def _jg():
    return {"home": "Athletics", "away": "Seattle Mariners",
            "home_pitcher": "Gage Jump", "away_pitcher": "Bryan Woo",
            "research": {
                "home_starter_recent": [{"innings": 4.0, "date": "2026-09-06"}],
                "away_starter_recent": [{"innings": 8.0, "date": "2026-09-06"}]}}


def test_블록에_팀과_선발_이름이_들어간다():
    """🔴 원정이 건너뛰어진 실측. 이름이 있으면 눈에 띈다."""
    out = M.starters_recent_payload(_jg())
    assert out["home"]["팀"] == "Athletics"
    assert out["home"]["선발"] == "Gage Jump"
    assert out["away"]["팀"] == "Seattle Mariners"
    assert out["away"]["선발"] == "Bryan Woo"


def test_기존_키는_그대로다():
    """⚠️ 반대 위험 — `home`·`away`·`선발등판` 을 읽는 곳이 넷이다."""
    out = M.starters_recent_payload(_jg())
    assert set(out) == {"home", "away"}
    assert out["away"]["선발등판"] == [{"innings": 8.0, "date": "2026-09-06"}]


def test_이름이_없어도_깨지지_않는다():
    jg = {"research": {"home_starter_recent": [], "away_starter_recent": []}}
    out = M.starters_recent_payload(jg)
    assert out["home"]["선발등판"] == []
    assert "팀" not in out["home"] or out["home"]["팀"] == ""
