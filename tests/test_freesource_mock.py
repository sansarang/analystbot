"""[P5-1] 무인증 수집기 목 스위치 — 켜지는 조건과 **켜지면 안 되는 조건**.

이 스위치의 위험은 두 방향이다:
  ① 테스트에서 안 켜지면 실트래픽이 나간다 (P5-2가 잡는다)
  ② 프로덕션에서 켜지면 봇이 가짜 데이터로 카드를 만든다 ← 이쪽이 훨씬 위험
아래 테스트는 ②를 막는 데 무게를 둔다.
"""

import pytest

from app.collectors.base import freesource_mocked
from app.config import Settings


def test_production_default_is_not_mocked():
    """선언된 기본값에서는 목이 꺼져 있다.

    켜지는 경로는 FORCE_MOCK=true 하나뿐이고, .env.example도 false다.
    이게 깨지면 운영 봇이 2026-08-22 픽스처로 오늘 경기를 판정한다.

    ⚠️ `Settings(_env_file=None).mock_freesource` 로는 이걸 볼 수 없다 —
       `_env_file=None` 은 .env만 끄고 **환경변수는 그대로 읽으며**,
       `tests/conftest.py` 가 FORCE_MOCK=true 를 프로세스 환경에 심는다.
       그래서 그 표현은 테스트 안에서 항상 True다(실측 2026-08-30).
       선언된 기본값과 매핑을 따로 본다.
    """
    assert Settings.model_fields["force_mock"].default is False
    assert Settings(_env_file=None, force_mock=False).mock_freesource is False


def test_force_mock_turns_it_on():
    assert Settings(_env_file=None, force_mock=True).mock_freesource is True


def test_injected_client_wins_over_mock(monkeypatch):
    """client를 주입하면 목으로 가로채지 않는다.

    호출자가 이미 경계를 통제하고 있다는 뜻이다. 가로채면 파싱·TTL을
    검사하는 테스트가 통째로 죽는다 (tests/test_naver_kbo.py가 실제로 그렇다).
    """
    import app.collectors.base as base

    monkeypatch.setattr(base, "get_settings",
                        lambda: Settings(_env_file=None, force_mock=True),
                        raising=False)
    assert freesource_mocked(client=object()) is False


@pytest.mark.parametrize("module_name", [
    "park", "naver_kbo", "kbo_stats", "kbo_usage", "kbo_roster", "kbo_park",
    "yahoo_npb", "npb_stats", "npb_form", "weather", "absences", "kbo",
    "kbo_news", "statcast",
])
def test_every_freesource_collector_has_a_guard(module_name):
    """무인증 수집기 14개 전부가 진입부에서 목을 확인한다.

    새 수집기를 붙이면서 가드를 빼먹으면 그 소스만 조용히 실트래픽을 낸다 —
    P5-2 차단이 잡아주긴 하지만, 그때는 이미 테스트가 깨진 뒤다.
    """
    from pathlib import Path

    src = Path(f"app/collectors/{module_name}.py").read_text(encoding="utf-8")
    assert "freesource_mocked(" in src or "mock_freesource" in src, \
        f"{module_name}에 무인증 목 가드가 없다"
