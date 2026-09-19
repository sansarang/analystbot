"""[WEA-1] 날씨를 **이미 받아 놓고** 내보내기가 안 읽었다.

🔴 실측 2026-09-19 판정 캐시:
     10085 weather_card = {"dome": false, "temp_c": 27.6, "wind_ms": 4.0,
                           "precip_pct": 4, "wind_from_deg": 10}
     research.weather = "기온 28도, 풍속 4.0m/s"
   `app/collectors/weather.py` 는 **407줄짜리 완성된 모듈**이다 —
   `DOMED` 구장 집합 · `PARK_COORDS` · `wind_effect`(외야/홈/옆바람) 까지 있다.
   그런데 내보내기는 이렇게 적고 있었다:
     "weather": {"temp_c": null, ..., "reason": "아직 채우지 않음 (STEP 2)"}
🔴 그래서 이 단위는 **새 수집기도 새 잡도 만들지 않는다.** 읽기만 잇는다.
⚠️ 돔은 값이 아니라 **사유**를 적는다 — 날씨가 경기에 닿지 않는다.
"""
from __future__ import annotations


def test_새_수집기를_만들지_않았다():
    """🔴 이미 있는 모듈을 덮어쓰지 않았다는 계약이다."""
    from app.collectors import weather as W

    for fn in ("fetch_for_games", "pick_hour", "wind_effect", "merge_into_research"):
        assert hasattr(W, fn), fn
    assert hasattr(W, "DOMED") and hasattr(W, "PARK_COORDS")


def test_돔은_값이_아니라_사유다():
    from app.export.for_fable import _weather_block

    got = _weather_block({"dome": True})
    assert got["temp_c"] is None
    assert "돔" in got["reason"], got


def test_옥외는_캐시값을_그대로_싣는다():
    from app.export.for_fable import _weather_block

    got = _weather_block({"dome": False, "temp_c": 27.6, "wind_ms": 4.0,
                          "precip_pct": 4, "wind_from_deg": 10})
    assert got["temp_c"] == 27.6
    assert got["wind_ms"] == 4.0
    assert got["precip_pct"] == 4
    assert got["wind_from_deg"] == 10
    assert got["reason"] is None


def test_캐시가_없으면_지어내지_않는다():
    from app.export.for_fable import _weather_block

    got = _weather_block(None)
    assert got["temp_c"] is None and got["reason"], got
    assert "돔" not in got["reason"], got


def test_단위를_함께_적는다():
    """🔴 `wind_ms`(m/s)와 `wind_kmh` 를 섞으면 8 과 29 가 같은 값이 된다."""
    from app.export.for_fable import _weather_block

    got = _weather_block({"dome": False, "temp_c": 20.0, "wind_ms": 3.0})
    assert "m/s" in str(got.get("units") or ""), got
