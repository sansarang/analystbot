# ODP-2 — 축구 배당 수집이 매 사이클 터진다 (`_match_soccer_ids` 의 `$1::date`)

## 왜

`ODP-1`(2026-09-13)로 축구 1X2 를 붙였는데 스케줄러가 **매 사이클 예외로
빠져나갔다.** 최근 12시간 축구 배당 스냅샷 **0건**이 그 결과다.

```
WARNING  [odds] 축구 수집 실패: invalid input     scheduler.py:1270
asyncpg.exceptions.DataError: invalid input for query argument $1:
  '2026-09-14' ('str' object has no attribute 'toordinal')
```

재현(로컬 DB, 읽기 전용 SELECT):
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_odp2.py   → exit 1 (같은 DataError)
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "collect_soccer|_match_soccer_ids|idx_names" app/ tests/ tools/
app/scheduler.py:1229            import
app/scheduler.py:1267            await collect_soccer(pool, redis, today_kst())   ← 유일한 호출부
app/collectors/odds_free.py:212  idx = await _match_soccer_ids(pool, date)        ← 유일한 호출부
app/collectors/odds_free.py:231  idx_names.get(...)
app/collectors/odds_free.py:249  idx_names 정의
app/collectors/odds_free.py:252  _match_soccer_ids 정의
app/collectors/oddsportal.py:304 주석 언급
tests/test_oddsportal_soccer.py:137-138  존재·배선 단언
```
`_match_soccer_ids` 는 **비공개**이고 호출부가 하나다. 시그니처(`date: str`)를
바꾸지 않으므로 호출부는 그대로다.

같은 파일의 **형제 쿼리 둘은 이미 옳다** — 손으로 규칙을 다시 정하지 않고
그 형태를 그대로 쓴다:
```
odds_free.py:41-42   (starts_at AT TIME ZONE '{tz}')::date = $2 … _d.fromisoformat(date)
odds_free.py:284-285 (g.starts_at AT TIME ZONE '{tz}')::date = $2 … _d.fromisoformat(date)
odds_free.py:259-260 BETWEEN $1::date - 1 AND $1::date + 1 … date   ← 여기만 문자열이다
```
`grep -n "::date" app/collectors/odds_free.py` 로 센 결과, 파라미터를 받는
`::date` 자리는 위 셋뿐이고 결함은 하나다.

## ② 만드는/바꾸는 상태 (DB 컬럼·Redis 키·env·캐시)

**없다.** 새 컬럼·새 키·새 env·새 상수가 없다. 바뀌는 것은 인자 한 개의
**파이썬 타입**(`str` → `datetime.date`)뿐이고, SQL 문자열·반환 형태
(`(정규화 홈키, 정규화 원정키) → games.id`)·`idx_names` 는 그대로다.

부수적으로 **채워지기 시작하는** 기존 상태: `odds_snapshots`
(provider=`oddsportal`, sport=soccer). 이 표를 다른 규칙으로 갱신하는 곳은
`store_rows` 하나뿐이고, 야구가 이미 같은 경로로 쓰고 있다.

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** 고치는 줄은 `sport = 'soccer'` 경로 안에만 있다.
- MLB(`collect`)·KBO·NPB(`collect_asia`)는 이 함수를 부르지 않는다 — 무영향.
- 축구 리그 분기는 `SOCCER_URL` 표가 이미 정하고 있고 이 수정은 손대지 않는다.
- 날짜 창(`$1::date - 1 … + 1`)도 그대로다 — KST 슬레이트가 UTC 저장과
  어긋나는 것을 흡수하려고 ODP-1 이 둔 것이다.

## ④ 실패하면 "시끄럽게" 실패하는가

**지금은 아니다 — 이 결함이 12시간 조용히 0건이었던 이유가 여기 있다.**
- 호출부는 `except Exception` 으로 삼키고 `WARNING` 한 줄만 남긴다
  (`scheduler.py:1266-1270`). 야구를 막지 않으려는 의도이므로 그대로 둔다.
- 워치독 `check_odds` 는 **provider 단위**로 센다
  (`watchdog.py:145-160`: `due = sum(due_by_sport[sp] for sp in prov.sports)`).
  `oddsportal` 은 MLB 도 담당하므로 MLB 적재가 최신이면 `age` 가 신선하고,
  **축구만 0건인 상태는 `W-ODDS-STALE` 로 울지 않는다.**

이 수정 자체는 조용히 실패하지 않는다 — 고치면 그 `WARNING` 이 사라지고
`[odds_free] SOCCER … 경기 N · 매칭 M · 행 R` 정보 로그가 대신 찍힌다.
첫 사이클 실측(⑨)이 그 줄과 `odds_snapshots` 행으로 확인한다.

⚠️ **남는 결함(이번 범위 밖 · 보고만 한다):** 종목별 배당 0건을 보는 눈이
없다. `check_odds` 를 provider×sport 로 세면 잡히지만, 그건 감시 규칙 변경이라
지시 없이 만들지 않는다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 날짜 변환 규칙을 새로 만들지 않는다 — 같은 파일 형제 쿼리의
  `_d.fromisoformat(date)` 를 **그대로** 쓴다.
- 리그 목록·활성 소스·스냅샷 상한을 문서나 상수로 베끼지 않는다
  (`SOCCER_URL`·`registry`·`ODDS_STALE_MIN` 이 원본).
- 새 테스트는 **호출 인자의 타입**을 단언한다. SQL 문자열을 grep 하는
  형태로 쓰지 않는다 — 그건 사본이고, 원본이 바뀌면 따라가지 않는다.
