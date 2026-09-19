# VEN-1 영향 지도 — 구장을 받아 놓고 버렸다

## 1. 무엇이 틀렸나 (실측 원문)

`mlb.py:227` 이 이미 받는다:

```python
"hydrate": "probablePitcher,venue(location)"
```

실측 응답:

```json
"venue": {"id": 4, "name": "Rate Field",
          "location": {"defaultCoordinates": {"latitude": 41.83, "longitude": -87.634167},
                       "elevation": 595, "city": "Chicago", ...}}
```

그런데 `_parse_games` 가 그 칸을 통째로 무시한다 — 주석이 "무시한다"고 스스로
적고 있었다. 그래서 내보내기가 이렇게 적는다:

```json
"venue": {"name": null, "roof": null, "park_factor_runs": null,
          "reason": "statsapi hydrate=venue(location) 를 받지만 _parse_games 가 무시한다 — 저장 테이블 없음"}
```

쿠어스 9·9점을 걸러내려면 파크팩터가 있어야 한다.

## 2. 어디를 고치나

| 파일 | 무엇 |
|---|---|
| `db/schema.sql` | `games.venue_id` · `venue_name` · `venue_lat` · `venue_lon` |
| `app/collectors/mlb.py` | `_parse_games` 에 네 칸 · upsert |
| `config/park_factors.yaml` | 29구장 3년 롤링 지수 + 지붕 (신규) |
| `app/engine/park.py` | yaml 로더 (신규) |
| `app/export/for_fable.py` | `venue` 블록 · `form.last5[].venue_pf` |

## 3. 영향 지도 5문

**① 파크팩터 값을 어디서 가져왔나 — 지어내지 않았다.**
MLB 자체 Baseball Savant 의 **3년 롤링 지수**를 2026-09-19 에 1회 받아 굳혔다.
지붕은 statsapi `/api/v1/venues?hydrate=fieldInfo` 의 `roofType` 이다.
출처 URL 과 받은 날짜를 파일 머리말에 적었고, 계약이 그것이 있는지 센다.
검증: 쿠어스 **125** 로 최고 — 딥서치가 말한 것과 같다("MLB 최고 득점 구장").

**② 키를 이름으로 하면 안 되나.**
안 된다. 구장명은 바뀐다 — Guaranteed Rate → **Rate Field**,
Minute Maid → **Daikin Park**(둘 다 이번 응답에서 실제로 확인됐다).
키는 **statsapi venue id** 다. 계약이 키가 정수인지 센다.

**③ 좌표는 왜 저장하나.**
2-8(날씨)이 open-meteo 에 lat/lon 을 넘겨야 한다. **같은 응답에 이미 있으므로**
지금 저장하면 그때 새 요청이 0이다. 한 번 받은 것을 두 번 받지 않는다.

**④ 판정에 새나.**
새면 안 된다. 파크팩터는 **표시·보정용**이고 v1.4 동결의 시즌 누적 금지 정신
밖이 아니다. 내보내기에만 싣고 판정 노드에 잇지 않는다.

**⑤ 모르는 구장은.**
29구장이다. 임시 구장이나 표본 없는 곳은 yaml 에 없고, 그때는
**`park_factor_runs=null` + 사유**다. 리그 평균 100 으로 메우지 않는다 —
채운 구장과 안 채운 구장이 같아 보이면 읽는 쪽이 오분류한다(U3 리즈 사례와 같다).

## 4. 안 하는 것

- 파크팩터를 매일 다시 받지 않는다(3년 롤링이라 하루에 안 바뀐다).
- KBO·NPB 파크팩터를 지어내지 않는다 — 그 리그 공개 지수를 아직 안 쟀다.
- 날씨를 이 단위에서 받지 않는다(2-8).
