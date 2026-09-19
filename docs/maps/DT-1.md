# DT-1 영향 지도 — 문자열 킥오프가 ⑤의 DB 조회를 통째로 죽였다

## 1. 무엇이 틀렸나 (실측 원문)

운영에서 g10932 로 `_bullpen3d` 를 직접 불렀다:

```
asyncpg.exceptions.DataError: invalid input for query argument $2:
  '2026-09-19T23:10:00Z' (expected a datetime.date or datetime.datetime
   instance, got 'str')
```

`::timestamptz` 캐스트가 SQL 안에 있어도 asyncpg 는 **바인딩 단계에서** 타입을
본다 — 캐스트가 구해 주지 않는다.

그런데 호출부가 조용히 삼킨다:

```python
except Exception as exc:
    logger.info("[flow:n05] 불펜 조회 실패 …")
    return []
```

그래서 `bullpen_3d`·`form_recent5` 가 **영원히 `unknown`** 이었고 ⑥이 늘
`모름과반`으로 끝났다. 오늘 7경기 전부 그 이유로 멈췄다.

**데이터는 있었다** — HOU 불펜 3일 10행 · STL 2행(실측).

⚠️ 이 저장소는 같은 함정을 이미 겪었다("'str' object has no attribute
   'toordinal'", 09-14 P0-2). **두 번째다.**

## 2. 어디를 고치나

`app/flow/nodes/n05_evidence.py` — 시각 변환 함수 1개 + 호출부 2곳.

## 3. 영향 지도 5문

**① 왜 로그가 있는데 몰랐나.**
`logger.info` 였고, 그 줄은 정상 로그에 묻힌다. 그리고 **반환값이 빈 목록이라
"자료가 없다"와 구분되지 않았다.** ⑥은 둘 다 `unknown` 으로 읽는다.
이번엔 실패를 `warning` 으로 올린다 — 조용한 0 을 만들지 않는다.

**② 변환에 실패하면 무엇을 넘기나.**
🔴 **None** 이다. `_LAST3_SQL` 은 `$3 IS NULL` 이면 "전체 기간"으로 동작한다 —
창이 0이 되는 것보다 낫다. `_BULLPEN_SQL` 은 시각이 필수이므로 None 이면
**조회하지 않고 빈 목록**을 돌려준다(지어내지 않는다).

**③ 다른 곳에도 같은 버그가 있나.**
`pick_ledger:1433` 은 `g["starts_at"]`(이미 datetime)을 넘긴다 — 멀쩡하다.
문자열을 넘기는 곳은 ⑤의 두 곳뿐이다(`rg` 로 확인).

**④ 계약은 무엇을 겨누나.**
"문자열을 넘기지 않는다"를 **풀에 들어간 인자로** 확인한다. 변환 함수만
테스트하면 호출부가 여전히 문자열을 넘겨도 통과한다.

**⑤ 이걸 고치면 ⑥이 풀리나.**
`bullpen_3d` 와 `form_recent5` 두 변수가 산다. 야구 핵심 변수는 셋
(`starter_recent3`·`bullpen_3d`·`lineup_out`)이라 미상비율이 2/3 → 1/3 로
내려간다. `starter_recent3` 는 별건이다(→ STR-2).

## 4. 안 하는 것

- SQL 을 바꾸지 않는다(캐스트는 그대로 둬도 무해하다).
- `except` 를 없애지 않는다 — 한 경기 실패가 슬레이트를 막으면 안 된다.
  올리는 것은 **로그 수준**뿐이다.
