"""[6번 2026-09-04] 정찰 C1 이관 — 첫 소스(oddsportal).

🔴 `polite_client.py` 는 2026-09-04 오전에 만들어졌지만 **이관은 0건**이었다.
   공통 클라이언트를 만들어 두고 아무도 안 쓰면, 얻는 것은 없고 유지할 것만
   하나 늘어난다.

카나리아로 `oddsportal` 을 골랐다:
  · 판정 입력이 아니다(배당은 판정에 흐르지 않는다) — 틀려도 판정이 안 흔들린다.
  · 실패가 시끄럽다 — `W-ODDS-STALE` 이 60분이면 운다.
  · 손으로 적은 상수가 네 개(UA·TIMEOUT·MAX_ATTEMPTS·BACKOFF_SEC) 있었다.

실측 2026-09-04 이관 직후 라이브 호출: KBO 5경기 · NPB 5경기 정상 수집.

나머지 12개 소스는 이 카나리아를 한 사이클 관측한 뒤 옮긴다 —
"한 방향만 고치면 반대편에서 새 오류가 난다"(CLAUDE.md).
"""
from pathlib import Path

SRC = Path("app/collectors/oddsportal.py").read_text(encoding="utf-8")


def test_oddsportal_uses_the_shared_client():
    assert "from app.net.polite_client import PoliteClient" in SRC
    assert "PoliteClient(PROVIDER)" in SRC


def test_hand_copied_constants_are_gone():
    """🔴 사본 금지 — 네 상수의 원본은 polite_client + config 다."""
    import app.collectors.oddsportal as m

    for name in ("UA", "TIMEOUT", "MAX_ATTEMPTS", "BACKOFF_SEC"):
        assert not hasattr(m, name), f"{name} 사본이 남아 있다"
    # 종전 값을 주석으로 남겨 뒀는가 — 무엇이 바뀌었는지 추적 가능해야 한다.
    assert "종전 값" in SRC


def test_source_specific_politeness_stays_here():
    """소스 고유 예절(같은 리그 10분 내 재요청 금지)은 옮기지 않는다."""
    import app.collectors.oddsportal as m

    assert m.MIN_INTERVAL_SEC == 10 * 60


def test_conditional_request_is_off_with_the_reason():
    """🔴 304 를 그냥 켜면 W-ODDS-STALE 이 '안 바뀜'을 '고장'으로 읽는다."""
    assert "conditional=False" in SRC
    assert "304" in SRC and "W-ODDS-STALE" in SRC


def test_no_anti_bot_evasion():
    """차단 우회 금지 — 이관이 그 선을 넘지 않았는가."""
    lowered = SRC.lower()
    for banned in ("rotate", "user_agents", "random.choice", "proxy",
                   "cloudscraper", "undetected"):
        assert banned not in lowered, banned


def test_shared_client_pledges_no_evasion():
    src = Path("app/net/polite_client.py").read_text(encoding="utf-8")
    assert "우회 금지" in src
    assert "로테이션하지 않는다" in src
