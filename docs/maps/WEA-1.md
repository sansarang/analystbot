# WEA-1 영향 지도 — 날씨를 이미 받아 놓고 안 읽었다

## 0. 🔴 내가 먼저 틀린 것 (기록으로 남긴다)

이 지도의 초판은 "`app/collectors/weather.py` **(신규)**" 라고 적고 open-meteo
수집기를 새로 짜려 했다. 그리고 실제로 **기존 파일을 덮어썼다.**
테스트가 즉시 잡았다:

```
AttributeError: module 'app.collectors.weather' has no attribute 'fetch_for_games'
  tests/conftest.py:301
```

`git checkout` 으로 복구했다. 그 파일은 **407줄짜리 완성된 모듈**이다 —
`DOMED` 구장 집합 · `PARK_COORDS`/`KBO_COORDS`/`NPB_COORDS` ·
`pick_hour` · `describe` · `wind_effect`(외야/홈/옆바람) · `merge_into_research`.

CLAUDE.md 는 "덮어쓰기 전에 대상을 본다"고 적고 있다. 나는 그걸 건너뛰었다.
**읽기를 먼저 했으면 250줄과 새 일일 잡 하나를 아꼈을 자리다.**

## 1. 진짜 결함 (실측 원문)

판정 캐시에는 이미 값이 있다:

```
10085 weather_card = {"dome": false, "temp_c": 27.6, "wind_ms": 4.0,
                      "precip_pct": 4, "wind_from_deg": 10}
      research.weather = "기온 28도, 풍속 4.0m/s"
```

그런데 내보내기는 이렇게 적었다:

```json
"weather": {"temp_c": null, "wind": null, "precip_pct": null,
            "reason": "아직 채우지 않음 (STEP 2)"}
```

**읽기만 안 이어져 있었다.**

## 2. 어디를 고치나

`app/export/for_fable.py` 한 곳 — `_weather_block` 과 그 배선.
⚠️ `app/collectors/weather.py` 는 **건드리지 않는다.**

## 3. 영향 지도 5문

**① 새 요청이 느나.** 0이다. 파이프라인이 이미 받아 캐시에 넣은 값을 읽는다.

**② 돔은.** 값이 아니라 **사유**다. `weather_card.dome` 이 참이면 날씨가 경기에
닿지 않으므로 숫자를 적지 않는다 — 적으면 읽는 쪽이 변수로 오해한다.

**③ 단위를 어떻게 하나.**
캐시는 `wind_ms`(m/s)다. `wind_kmh` 와 섞이면 8 과 29 가 같은 값이 된다.
키 이름에 단위를 남기고 `units` 를 함께 싣는다. 계약이 그것을 센다.

**④ 바람 방향의 뜻은.**
`wind_from_deg` 는 **불어오는 방향**이다. 외야/홈 판단(`wind_effect`)은 구장
방위각이 필요하고 그 값은 내보내기에 없다 — **각도를 그대로 싣고 해석하지
않는다.** 해석은 그 함수를 가진 쪽의 일이다.

**⑤ 캐시가 없으면.**
`null + 사유`다. "돔이라 없다"와 "아직 안 받았다"를 사유 문구로 가른다.

## 4. 안 하는 것

- 새 수집기·새 잡을 만들지 않는다(초판의 계획을 폐기했다).
- 판정에 잇지 않는다 — 표시용이다.
