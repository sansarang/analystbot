"""[SAT-10] 경기장 날씨 — 바람·기온·강수. 고급정보(박스스코어에 없다).

바람이 외야로 불면 홈런성 타구를 밀어 득점 환경이 오르고(맞바람이면 반대),
강수확률이 높으면 순연·불펜 경기 리스크다. 구장 방위(statsapi azimuthAngle)로
풍향을 홈런 촉진/억제로 환산한다.
"""
from __future__ import annotations

from app.collectors import weather as wx


def test_wind_out_helps_home_runs():
    """구장 방위 0°(홈→중견 정북)에서 남풍(from 180°)은 중견 쪽(북)으로 불어 외야."""
    assert wx.wind_effect(wind_from_deg=180, wind_mph=12, field_azimuth_deg=0) == wx.OUT


def test_wind_in_suppresses():
    """북풍(from 0°)은 홈 쪽(남)으로 불어 홈런 억제."""
    assert wx.wind_effect(wind_from_deg=0, wind_mph=12, field_azimuth_deg=0) == wx.IN


def test_crosswind():
    assert wx.wind_effect(wind_from_deg=90, wind_mph=12, field_azimuth_deg=0) == wx.CROSS


def test_light_wind_is_negligible():
    """약한 바람은 신호 아님."""
    assert wx.wind_effect(wind_from_deg=180, wind_mph=3, field_azimuth_deg=0) == wx.CALM


def test_weather_article_emitted_on_strong_wind():
    """센 외야 바람이면 발견 기사가 나온다(경기 고유 숫자 포함)."""
    art = wx.weather_article(
        team="Colorado Rockies",
        forecast={"wind_mph": 15, "wind_from_deg": 180, "temp_c": 24,
                  "precip_pct": 10},
        field_azimuth_deg=0)
    assert art is not None
    assert "15" in art["body"] and "mph" in art["body"]
    assert art["team"] == "Colorado Rockies"
    assert art["source"] == "Open-Meteo"


def test_weather_article_emitted_on_rain_risk():
    """강수확률이 높으면(순연·불펜 리스크) 약한 바람이어도 기사가 나온다."""
    art = wx.weather_article(
        team="A",
        forecast={"wind_mph": 3, "wind_from_deg": 0, "temp_c": 20, "precip_pct": 70},
        field_azimuth_deg=0)
    assert art is not None
    assert "70" in art["body"]


def test_weather_article_none_when_bland():
    """약풍·무비·평범한 기온이면 신호 없음(None) — 소음을 만들지 않는다."""
    art = wx.weather_article(
        team="A",
        forecast={"wind_mph": 4, "wind_from_deg": 0, "temp_c": 21, "precip_pct": 5},
        field_azimuth_deg=0)
    assert art is None


def test_pick_hour_matches_game_time():
    """예보 시계열에서 경기 시각에 가장 가까운 시간을 고른다."""
    hourly = {
        "time": ["2026-09-10T17:00", "2026-09-10T18:00", "2026-09-10T19:00"],
        "wind_speed_10m": [5, 10, 15],
        "wind_direction_10m": [90, 180, 200],
        "temperature_2m": [20, 21, 22],
        "precipitation_probability": [0, 10, 20],
    }
    f = wx.forecast_at(hourly, "2026-09-10T18:30")
    assert f["wind_mph"] == 10          # 18:00 이 18:30 에 가장 가깝다
    assert f["wind_from_deg"] == 180
    assert f["precip_pct"] == 10
