# WIR-2 영향 지도 — ⑤가 빈손으로 돌아오던 이유

## 1. 무엇이 틀렸나 (실측 원문)

게이트를 통과한 7경기 전부:

```
09-19 05:44 g10091  n05_evidence = []
09-19 05:19 g10090  n05_evidence = []

n06_verdict = {"per_var": {"weather":"unknown","bullpen_3d":"unknown",
  "lineup_out":"unknown","park_factor":"unknown","starter_recent3":"unknown",
  "travel_backtoback":"unknown"}, "verdict":"모름과반", "unknown_ratio":1.0}
```

자료가 DB 에 **없어서가 아니다.** 같은 DB 로 만든 오늘 내보내기는 적었다:

```
- 선발 홈 Paul Skenes (시즌 6선발 ERA 3.06) — 2026-09-13 7.0이닝 2자책
- 불펜 3일 홈 18.0이닝 / 원정 9.0이닝
- 결장 홈 4명(confirmed) / 원정 1명(confirmed)
```

원인은 한 줄이다:

```python
# app/flow/nodes/n05_evidence.py:153
absences = (ctx.inject or {}).get("absences") or []
```

그리고 주입하는 쪽은 하나만 준다:

```python
# app/flow/bridge.py:117
ctx.inject = {"model_probs": model_by_game.get(...)}
```

운영에서 `absences`·`starter_notes` 는 **영원히 빈 목록**이었다.

⚠️ 나머지 둘은 이미 DB 를 읽는다 — `bullpen_3d`(`_BULLPEN_SQL`) ·
   `form_recent5`/`last3`(`_LAST3_SQL`). 고칠 곳은 결장·선발 둘뿐이다.

## 2. 어디를 고치나

`app/flow/nodes/n05_evidence.py` — 캐시 읽기 1개 + 두 변수의 소스 연결.

## 3. 영향 지도 5문

**① 새 수집기를 만드나.**
아니다. 파이프라인이 이미 만들어 둔 판정 캐시(`analysis:{sport}:{date}`)를
읽는다 — 내보내기가 읽는 **바로 그 자리**다. HTTP 0, 새 표 0.
캐시 내용 실측: `research.absences` 에 문장 목록이 있고 `starter_changed` ·
`lineup_notes` 가 최상위에 있다.

**② MLB 날짜가 어긋나지 않나.**
어긋난다. 실측: `analysis:mlb:2026-09-19` 는 **없고** `analysis:mlb:2026-09-18`
이 있다(캐시 키가 미 동부 날짜다). KST 날짜로만 찾으면 MLB 는 언제나 빈손이다.
**양쪽 날짜를 다 본다** — 규칙의 원본은 `pipeline.mlb_slate_date` 이고 여기서
달력을 새로 만들지 않는다.

**③ 주입과 캐시 중 무엇이 먼저인가.**
주입이 먼저다. 픽스처·드라이런이 캐시에 덮이면 테스트가 못 믿을 것이 된다.
계약이 "주입이 있으면 캐시를 읽지 않는다"를 확인한다.

**④ 기사가 증거로 섞이나.**
안 섞인다. `run()` 은 `for var in wanted` 로 **가설이 요구한 변수만** 돈다.
트랜잭션 기사가 채점 분모에 섞이면 `모름과반` 이 아니라 **틀린 확인**이 되므로
계약으로 잠근다.

**⑤ 무엇이 조용히 0이 되나.**
캐시가 없는 날(파이프라인이 안 돈 날)은 여전히 빈손이다. 그때는 **지어내지
않는다** — `unknown` 이 맞다. 다만 "캐시가 없었다"와 "캐시에 결장이 0명이었다"가
구분되도록 로그를 남긴다.

## 4. 안 하는 것

- ⑥ 채점 규칙을 바꾸지 않는다. ⑥은 ⑤가 준 것만 보고, 그것이 맞다.
- `weather`·`park_factor`·`travel_backtoback` 은 그대로 `unknown` 이다 —
  소스가 없다(2-7·2-8·2-10 의 몫).
- 새 LLM 콜 0.
