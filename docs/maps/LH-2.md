# LH-2 — 날짜 칸에 문자열을 넘겼다 (ODP-2 재발)

## 왜

역매핑을 돌리니 **18,507행 전부 갱신 실패**했다:
```
[fotmob] 메타 갱신 실패 game=… : invalid input for query argument $4:
  '2026-09-14' ('str' object has no attribute 'toordinal')
리그별 적재 → (미상) 527경기 · 18507행 · 리그 미상 18507행
```
🔴 **오늘 아침 `ODP-2` 에서 고친 것과 같은 결함이다.** asyncpg 는 `$n::date`
   에 `datetime.date` 를 요구하는데 문자열을 넘겼다. `kickoff_utc`
   (TIMESTAMPTZ)도 같은 문제다 — ISO 문자열을 그대로 넘겼다.

🔴 **계약 테스트가 못 잡은 이유**: 가짜 풀(`_Pool.execute`)이 인자를 받아
   적기만 하고 **타입을 검사하지 않는다.** 그래서 "값이 들어간다"는 통과했고
   "그 값이 DB가 받는 타입인가"는 아무도 안 봤다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_lh2.py   # 진짜 DB
  → 🔴 날짜 칸이 비거나 타입이 틀리다
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
app/collectors/fotmob.py   save_lineup_history · backfill · backfill_meta
tests/test_lineup_history.py
```

## ② 만드는/바꾸는 상태

**없다.** 넘기는 **값의 타입**만 바뀐다(str → `date`/`datetime`).

## ③ 리그·종목·경로 분기가 생기는가

생기지 않는다.

## ④ 실패하면 "시끄럽게" 실패하는가

이번에는 시끄러웠다 — 갱신 실패 로그가 행마다 찍혔고 리그별 표가
`(미상) 18507행` 으로 나왔다. **그 표가 아니었으면 "칸을 더했다"로 끝났을
자리다.**

🔴 그래서 계약을 **진짜 DB 로** 바꾼다. 가짜 풀은 타입을 못 잡는다 —
   같은 결함이 하루에 두 번 났다는 것이 그 증거다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 날짜 변환 규칙을 새로 만들지 않는다 — `date.fromisoformat` /
  `datetime.fromisoformat` 표준을 쓴다(`odds_free.coverage` 와 같은 형태).
