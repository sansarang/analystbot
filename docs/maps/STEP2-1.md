# STEP2-1 — 축구가 통째로 막혀 있었다. 원인은 종목코드 한 줄

사용자 2026-09-23: "step 2로 가라..대신에 **모든 스포츠 적용**이라는 것을 명심해라"

## 실측 (운영 `n06_verdict`, 최근 3일)

```
종목     변수                확인  반증   미상
soccer  form_recent5          0    0   112   ← 전멸
soccer  xi_confirmed          0    0   305
soccer  rotation_risk         0    0   305
soccer  travel / motivation   0    0   112
mlb     lineup_out          976    0   137   ← 야구는 된다
mlb     bullpen_3d          732    0   381
```

**자료가 없어서가 아니었다.** 같은 시각 DB 에 축구 결과가 리그별로 다 있었다
(EPL 82 · 라리가 127 · 세리에A 97 · 분데스 55 · J1 80 · … 전부 09-20 까지).

## 원인

```python
def _sport_code(state) -> str:
    return (state.league or state.sport or "").lower()   # ← 리그가 먼저였다
```

이 값을 쓰는 **네 곳이 전부 `games.sport` 코드**를 원한다:

| 줄 | 쓰는 곳 | 필요한 값 |
|---|---|---|
| 125 | `redis f"analysis:{sport}:{day}"` | `analysis:kbo:…` (실물 확인) |
| 193 | `read_extract(redis, sport, game_id)` | 위성이 `jg["sport"]` 로 쓴다 |
| 312 | `{"kbo": …, "npb": …}[code]` | 키가 종목코드다 |
| 410 | `_LAST3_SQL WHERE sport = $1` | `games.sport` |

야구는 **리그명이 곧 종목코드**라(KBO→`kbo`) 우연히 맞았고 축구만 어긋났다.

```
_LAST3_SQL sport='epl'    team='Fulham FC' → 0행
_LAST3_SQL sport='soccer' team='Fulham FC' → 3행 ['09-20 무 1-1', …]
```

## 🔴 첫 수정이 틀렸다 — 측정이 바로잡았다

처음에는 "`state.sport` 를 먼저 보면 된다"고 고쳤다. 계약 하나
(`test_캐시에서_결장을_읽어_증거로_만든다`)가 즉시 걸렸고, 재보니:

```
운영 흐름 스냅샷의 sport   "baseball" 3,464건 · "soccer" 536건
구경로 캐시 키 실물        analysis:kbo:2026-09-22 · analysis:mlb:2026-09-22
```

`state.sport` 는 **정규화된 값**이라 야구에서 kbo/mlb/npb 를 못 가른다.
그래서 최종형은 **축구만 종목, 야구는 리그**다 — 특례가 아니라 `games.sport`
열의 실제 값이 그렇게 생겼다.

## 영향 지도 5문

① 파일 — `app/flow/nodes/n05_evidence.py` 함수 하나 + 계약 1.
② 테이블·잡 — 없음. 질의 인자만 바뀐다.
③ 깨질 테스트 — 첫 수정에서 1건 깨졌고 **테스트가 맞았다**(고친 것은 코드).
④ 되돌릴 길 — 함수 한 개 되돌리기.
⑤ 완료 조건 — 축구 `form_recent5` 가 미상에서 벗어난다 · 야구 수치 불변.

## 안 고친 것

- `travel` · `motivation` · `park_factor` · `weather` · `travel_backtoback`
  — **소스가 아예 없다.** 배선이 아니라 자료 문제다(다음 단위).
- `xi_confirmed` — `lineups` 테이블에 축구 라인업이 있는데(라리가·EPL 등)
  ⑤가 그 표를 **안 읽는다**. 별건이다.
- KBO `pitcher_appearances` 가 **09-12 에서 끊겼다**(10일). 이건 진짜 적재
  문제이고 STEP2-2 다.
