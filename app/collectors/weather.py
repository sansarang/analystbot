"""[§2] 날씨 — Open-Meteo(무료·무인증)로 경기 시각 기온·풍속 조회.

그동안 날씨는 Perplexity 산문에서만 왔고, 리서치가 없으면 λ의 ④단계가
통째로 건너뛰어졌다(실측 2026-08-25: 15경기 전부 미반영).

Open-Meteo를 쓰는 이유: API 키가 없고, 시간 단위 예보를 좌표로 바로 준다.
파크팩터와 마찬가지로 **수치는 정식 API에서** 가져온다는 원칙의 적용이다.

돔구장은 조회하지 않는다 — 기온·바람이 타구 비거리에 영향을 주지 않으므로
보정을 걸면 안 된다. 조회를 아끼는 것이 아니라 **틀린 보정을 막는** 것이다.

⚠️ 풍향은 반영하지 않는다. 외야 방향인지는 구장 방위(홈플레이트→센터 각도)를
알아야 판정되는데, 그 표는 공개 출처가 제각각이라 검증 없이 넣으면 부호가
뒤집힐 수 있다(허용 xwOBA 오진 사례와 같은 종류의 위험). 기온·풍속만 쓴다.
"""

import logging

from app.collectors.base import BaseAPIClient

logger = logging.getLogger(__name__)

CACHE_KEY = "weather:mlb:{}"
CACHE_TTL = 3 * 3600          # 예보는 자주 바뀐다 — 3시간

# 돔·개폐식(닫고 하는 경우가 많은) 구장 — 날씨 보정 제외
DOMED = {
    "Tampa Bay Rays", "Toronto Blue Jays", "Milwaukee Brewers",
    "Arizona Diamondbacks", "Houston Astros", "Miami Marlins", "Texas Rangers",
    # [§8-26] KBO 돔구장 — 고척스카이돔이 유일하다. 날씨 조회 대상이 아니다.
    "Kiwoom Heroes",
    # [§8-26] NPB 돔구장 — 6곳. 나머지는 야외다.
    "Yomiuri Giants",              # 東京ドーム
    "Fukuoka SoftBank Hawks",      # みずほPayPayドーム
    "Saitama Seibu Lions",         # ベルーナドーム(준돔 — 지붕만 있고 측면 개방)
    "Chunichi Dragons",            # バンテリンドーム
    "Orix Buffaloes",              # 京セラドーム大阪
    "Hokkaido Nippon-Ham Fighters",  # エスコンフィールド(개폐식 — 통상 폐쇄)
}

# [§8-26] KBO 9구장 좌표 (위도, 경도). 고척은 돔이라 조회하지 않는다.
KBO_COORDS = {
    "LG Twins": (37.5122, 127.0719),        # 잠실
    "Doosan Bears": (37.5122, 127.0719),    # 잠실 (공용)
    "NC Dinos": (35.2225, 128.5822),        # 창원NC파크
    "Kia Tigers": (35.1682, 126.8891),      # 광주-기아 챔피언스필드
    "Lotte Giants": (35.1940, 129.0615),    # 사직
    "SSG Landers": (37.4370, 126.6932),     # 인천SSG랜더스필드(문학)
    "Hanwha Eagles": (36.3172, 127.4290),   # 대전 한화생명볼파크
    "KT Wiz": (37.2997, 127.0097),          # 수원KT위즈파크
    "Samsung Lions": (35.8411, 128.6819),   # 대구 삼성라이온즈파크
}

# [§8-26] NPB 야외 구장 좌표. 돔 6곳은 DOMED에 있어 조회 대상이 아니다.
NPB_COORDS = {
    "Hanshin Tigers": (34.7215, 135.3617),          # 甲子園
    "Hiroshima Toyo Carp": (34.3919, 132.4847),     # マツダスタジアム
    "Yokohama DeNA BayStars": (35.4433, 139.6400),  # 横浜スタジアム
    "Tokyo Yakult Swallows": (35.7014, 139.7172),   # 神宮
    "Chiba Lotte Marines": (35.6453, 140.0311),     # ZOZOマリン(해풍이 강하다)
    "Tohoku Rakuten Golden Eagles": (38.2564, 140.9022),  # 楽天モバイルパーク
}

# 홈 구장 좌표 (위도, 경도). MLB 30구장 + KBO 9 + NPB 6.
PARK_COORDS = {
    "Arizona Diamondbacks": (33.4455, -112.0667),
    "Atlanta Braves": (33.8907, -84.4677),
    "Baltimore Orioles": (39.2839, -76.6217),
    "Boston Red Sox": (42.3467, -71.0972),
    "Chicago Cubs": (41.9484, -87.6553),
    "Chicago White Sox": (41.8299, -87.6338),
    "Cincinnati Reds": (39.0975, -84.5069),
    "Cleveland Guardians": (41.4962, -81.6852),
    "Colorado Rockies": (39.7559, -104.9942),
    "Detroit Tigers": (42.3390, -83.0485),
    "Houston Astros": (29.7573, -95.3555),
    "Kansas City Royals": (39.0517, -94.4803),
    "Los Angeles Angels": (33.8003, -117.8827),
    "Los Angeles Dodgers": (34.0739, -118.2400),
    "Miami Marlins": (25.7781, -80.2197),
    "Milwaukee Brewers": (43.0280, -87.9712),
    "Minnesota Twins": (44.9817, -93.2777),
    "New York Mets": (40.7571, -73.8458),
    "New York Yankees": (40.8296, -73.9262),
    "Athletics": (39.5432, -119.7480),        # 새크라멘토 임시 홈(서터 헬스 파크)
    "Philadelphia Phillies": (39.9061, -75.1665),
    "Pittsburgh Pirates": (40.4469, -80.0057),
    "San Diego Padres": (32.7076, -117.1570),
    "San Francisco Giants": (37.7786, -122.3893),
    "Seattle Mariners": (47.5914, -122.3325),
    "St. Louis Cardinals": (38.6226, -90.1928),
    "Tampa Bay Rays": (27.7683, -82.6534),
    "Texas Rangers": (32.7473, -97.0847),
    "Toronto Blue Jays": (43.6414, -79.3894),
    "Washington Nationals": (38.8730, -77.0074),
}


PARK_COORDS.update(KBO_COORDS)
PARK_COORDS.update(NPB_COORDS)


class OpenMeteoClient(BaseAPIClient):
    """무료·무인증 기상 API. 키가 없어도 목 모드로 떨어지지 않는다."""

    name = "open_meteo"
    base_url = "https://api.open-meteo.com/v1"
    timeout = 10.0
    max_concurrency = 4
    min_interval = 0.2

    def __init__(self, mock: bool = False):
        super().__init__(mock=mock)

    async def hourly(self, lat: float, lon: float, day: str) -> dict:
        return await self._request(
            "GET", "/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m,wind_speed_10m",
                "start_date": day, "end_date": day,
                "timezone": "UTC",
            },
        )


def pick_hour(payload: dict, hour_utc: str) -> tuple[float | None, float | None]:
    """해당 UTC 시각의 (기온℃, 풍속 m/s). 정확히 없으면 가장 가까운 시각."""
    hourly = (payload or {}).get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    winds = hourly.get("wind_speed_10m") or []
    if not times:
        return None, None
    idx = None
    for i, t in enumerate(times):
        if str(t).startswith(hour_utc):
            idx = i
            break
    if idx is None:
        idx = min(range(len(times)), key=lambda i: abs(i - len(times) // 2))
    temp = temps[idx] if idx < len(temps) else None
    wind = winds[idx] if idx < len(winds) else None
    # Open-Meteo 기본 풍속 단위는 km/h — m/s로 환산한다
    return (float(temp) if temp is not None else None,
            round(float(wind) / 3.6, 1) if wind is not None else None)


def describe(temp_c: float | None, wind_ms: float | None) -> str | None:
    """`scoring._weather_factor`가 파싱하는 한국어 문장으로.

    그쪽은 정규식 `(-?\\d{1,2})\\s*(?:도|℃|C)`로 기온을 읽고 바람 방향 단어를 본다.
    방향을 모르므로 **바람 단어는 넣지 않는다** — 넣으면 없는 근거로 λ가 움직인다.
    """
    if temp_c is None:
        return None
    parts = [f"기온 {round(temp_c)}도"]
    if wind_ms is not None:
        parts.append(f"풍속 {wind_ms:.1f}m/s")
    return ", ".join(parts)


async def fetch_for_games(games: list[dict], client: OpenMeteoClient | None = None,
                          redis=None) -> dict[int, dict]:
    """경기별 날씨. 반환: {game_id: {"text", "dome", "temp_c", "wind_ms"}}.

    돔구장은 조회하지 않고 dome=True만 남긴다.
    """

    from app.collectors.base import freesource_mocked

    if freesource_mocked(client):        # [P5-1] 무인증 소스 — 목 모드
        return {}
    client = client or OpenMeteoClient()
    out: dict[int, dict] = {}
    for g in games:
        gid = g.get("game_id") or g.get("id")
        home = g.get("home")
        if gid is None or not home:
            continue
        if home in DOMED:
            out[gid] = {"text": None, "dome": True, "temp_c": None, "wind_ms": None}
            continue
        coords = PARK_COORDS.get(home)
        if coords is None:
            logger.warning("[weather] 좌표 없음: %s", home)
            continue
        starts = str(g.get("starts_at") or "")
        day, hour_utc = (starts[:10], starts[:13]) if len(starts) >= 13 else ("", "")
        if not day:
            continue
        try:
            payload = await client.hourly(coords[0], coords[1], day)
        except Exception as exc:      # 날씨 실패가 파이프라인을 막지 않는다
            logger.warning("[weather] 조회 실패 %s: %s", home, exc)
            continue
        temp, wind = pick_hour(payload, hour_utc)
        out[gid] = {"text": describe(temp, wind), "dome": False,
                    "temp_c": temp, "wind_ms": wind}
    return out


def merge_into_research(research: dict, jg: dict, weather: dict) -> str | None:
    """날씨 문장을 리서치에 얹는다.

    🔴 **[WX-1 2026-09-10] 실제 예보가 리서치 산문을 이긴다.**
       종전 첫 줄은 `if research.get("weather"): return None` — 리서치 LLM 이
       먼저 채워 놓으면 Open-Meteo 예보를 **통째로 버렸다.** 절대규칙 2
       ("LLM 출력의 수치는 API 숫자와 교차검증. 충돌 시 API가 이긴다") 위반이다.

       실측 2026-09-09 MLB 10경기: 자료11 날씨가 10/10 붙었는데 전부 LLM
       산문이었고, 그래서 `_weather_factor` 가 숫자를 못 뽑아 **계수 라벨이
       3/10** 밖에 안 붙었다. 필라델피아는 이렇게 왔다 —
       "구체적인 수치는 실시간 기상 데이터에 접근해야 하나, 일반적으로 초가을
        동부 지역 저녁 기온은 섭씨 20도 내외 … 경우가 많다."
       예보가 아니라 추측이고, 그것이 판정의 환경 자료였다.

    ⚠️ **리서치 문장을 지우지는 않는다.** 우천 지연 언급처럼 예보 수치에 없는
       현지 사실이 거기 있을 수 있어 `weather_research` 로 옮겨 보존한다.
    ⚠️ 예보가 없으면(수집 실패·키 없음) 기존 문장을 **그대로 둔다** — 빈 값으로
       덮으면 있던 정보까지 잃는다.
    """
    info = (weather or {}).get(jg.get("game_id"))
    if not info:
        return None
    prior = research.get("weather")
    if info.get("dome"):
        research["weather_note"] = "돔구장 — 날씨 보정 없음"
        return "날씨 돔구장(보정 제외)"
    if not info.get("text"):
        return None
    if prior and prior != info["text"]:
        research["weather_research"] = prior
    research["weather"] = info["text"]
    return f"날씨 {info['text']}" + (" (리서치 문장 대체)" if prior else "")


# ── [SAT-10] 위성 고급정보: 풍향→홈런 효과 ────────────────────────────────
#   🔴 이전 세션이 풍향을 뺀 이유(위 docstring)는 **구장 방위표가 출처마다
#      다르다**였다. statsapi venue 의 `azimuthAngle`(홈→중견)은 MLB 공식값이라
#      그 우려가 해소된다 — 그래서 MLB 에 한해 풍향을 쓴다(KBO/NPB 는 방위 없음).
#   ⚠️ 여기 함수는 **위성(딥서치 재료)** 전용이다. λ 경로(pick_hour/describe/
#      merge_into_research)는 손대지 않는다 — 풍속·기온만 쓰던 그 계약 그대로다.

import re as _re  # noqa: E402

OUT = "외야(홈런 촉진)"
IN = "홈(홈런 억제)"
CROSS = "옆바람"
CALM = "약함"

WIND_MIN_MPH = 8.0          # 이 미만은 무시(연구 5mph, 보수적으로 8)
RAIN_PCT = 50              # 순연·불펜 리스크로 보는 강수확률(%)
TEMP_HOT, TEMP_COLD = 30, 5


def _bearing_diff(a: float, b: float) -> float:
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def wind_effect(*, wind_from_deg: float, wind_mph: float,
                field_azimuth_deg: float) -> str:
    """풍향(불어오는 방향)·풍속·구장 방위 → 외야/홈/옆/약.

    기상 풍향은 **불어오는 방향**이라 실제로 부는 방향 = from+180. 구장 방위
    (홈→중견)와의 각도차가 작으면 외야로(홈런 촉진), 크면 홈으로(억제).
    """
    if wind_mph is None or wind_mph < WIND_MIN_MPH:
        return CALM
    blows_toward = (wind_from_deg + 180) % 360
    diff = _bearing_diff(blows_toward, field_azimuth_deg)
    if diff <= 45:
        return OUT
    if diff >= 135:
        return IN
    return CROSS


def _hkey(iso: str) -> int:
    s = _re.sub(r"[^0-9]", "", (iso or "")[:13])
    return int(s) if s else 0


def _at(hourly: dict, key: str, idx: int):
    arr = (hourly or {}).get(key) or []
    return arr[idx] if 0 <= idx < len(arr) else None


def forecast_at(hourly: dict, when_iso: str) -> dict | None:
    """시간별 예보에서 경기 시각에 가장 가까운 시간을 고른다.

    반환 {wind_mph, wind_from_deg, temp_c, precip_pct}. 못 고르면 None.
    ⚠️ 이 payload 의 풍속 단위는 **mph** 다(`hourly_rich` 가 mph 로 받아온다).
       λ 경로의 `pick_hour`(km/h→m/s)와 다른 계약이라 섞지 않는다.
    """
    times = (hourly or {}).get("time") or []
    if not times:
        return None
    tgt = _hkey(when_iso)
    idx = min(range(len(times)), key=lambda i: abs(_hkey(times[i]) - tgt))
    return {
        "wind_mph": _at(hourly, "wind_speed_10m", idx),
        "wind_from_deg": _at(hourly, "wind_direction_10m", idx),
        "temp_c": _at(hourly, "temperature_2m", idx),
        "precip_pct": _at(hourly, "precipitation_probability", idx),
    }


def weather_article(*, team: str, forecast: dict,
                    field_azimuth_deg: float | None) -> dict | None:
    """예보 → 위성 발견 기사(news_rss 모양). 센 바람·비·이상기온일 때만.

    평범하면 None — 소음을 만들지 않는다. `field_azimuth_deg` 가 없으면(KBO/NPB)
    풍향 효과는 빼고 풍속·기온·강수만 쓴다.
    """
    if not forecast:
        return None
    wind = forecast.get("wind_mph")
    precip = forecast.get("precip_pct")
    temp = forecast.get("temp_c")
    eff = CALM
    if field_azimuth_deg is not None and wind is not None:
        eff = wind_effect(wind_from_deg=forecast.get("wind_from_deg") or 0,
                          wind_mph=wind, field_azimuth_deg=field_azimuth_deg)
    notable = (eff in (OUT, IN)
               or (precip is not None and precip >= RAIN_PCT)
               or (temp is not None and (temp >= TEMP_HOT or temp <= TEMP_COLD)))
    if not notable:
        return None
    parts = []
    if wind is not None:
        parts.append(f"바람 {wind:.0f}mph" + (f" {eff}" if eff != CALM else ""))
    if temp is not None:
        parts.append(f"기온 {temp:.0f}℃")
    if precip is not None:
        parts.append(f"강수확률 {precip:.0f}%"
                     + (" (순연·불펜 리스크)" if precip >= RAIN_PCT else ""))
    body = f"{team} 홈구장 날씨 — " + " · ".join(parts) + "."
    return {"title": body, "url": "https://open-meteo.com", "source": "Open-Meteo",
            "team": team, "body": body, "age_h": None}


async def hourly_rich(lat: float, lon: float, *, client=None) -> dict | None:
    """위성용 시간별 예보(풍향+강수 포함, 풍속 **mph**). 실패는 None.

    ⚠️ λ 경로의 `OpenMeteoClient.hourly`(km/h·temp+wind만)와 별개다 — 그쪽 계약을
       바꾸지 않으려 풍향·강수를 여기서 따로 받는다.
    """
    if client is not None:
        return await client(lat, lon)
    import httpx

    try:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon,
                        "hourly": "wind_speed_10m,wind_direction_10m,"
                                  "temperature_2m,precipitation_probability",
                        "wind_speed_unit": "mph", "forecast_days": 2})
            r.raise_for_status()
            return r.json().get("hourly")
    except Exception as exc:
        logger.warning("[weather] rich 예보 실패 %s,%s: %s", lat, lon, exc)
        return None
