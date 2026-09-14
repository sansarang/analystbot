# TRG-2 — 시점 트리거를 아무도 쏘지 않는다 (1분 루프 배선)

## 왜

`TRG-1`(2026-09-13)이 시점표·계획·우선순위·SQL 셋을 만들었지만 **부르는 곳이
없다.** 그래서 `game_triggers` 는 비어 있고 `odds_snapshots.snap_tag` 는
스키마에만 있고 **아무도 쓰지 않는다**(grep: 쓰는 곳 0). Part 1-B(이동
분류)·Part 4(상태 기계)가 전부 이 태그를 기준선으로 쓰므로, 여기가 막히면
그 뒤가 전부 헛돈다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_trg2.py
  → ImportError: cannot import name '_triggers_tick' from 'app.scheduler'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "triggers\.\|snap_tag" app/ tests/
app/engine/triggers.py           KINDS · MAX_CONCURRENT · DUE_SQL · UPSERT_SQL · MARK_SQL · plan · prioritize
   → 호출부 **0** (이 배선이 최초)
app/engine/odds_move.py:67,78    baseline()·move_between() 이 snap_tag 로 스냅샷을 고른다
   → 그 두 함수의 호출부도 아직 0 (MOV-1 배선은 다음 단위)
tests/engine/test_odds_move.py   snap_tag 를 넣은 dict 로 단언
app/scheduler.py:_job_specs()    잡 표 — 여기에 한 줄이 는다
```
`snap_tag` 를 **쓰는** 곳은 지금 한 곳도 없다. 이 단위가 유일한 기록자다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `game_triggers` 행 | **데이터만** 는다. 테이블·컬럼은 이미 있다 |
| `odds_snapshots.snap_tag` | 기존 행에 이름표를 붙인다(UPDATE). 컬럼 이미 있음 |

🔴 **새 컬럼·새 테이블·새 소스 호출이 없다.** 배당을 새로 긁지 않고
`odds_snapshots` 에 **이미 있는** 가장 최근 행에 이름표만 붙인다
(`record_clv` 와 같은 원칙 — "새 소스를 부르지 않는다").
그 행을 다른 규칙으로 갱신하는 곳은 없다(①의 grep).

⚠️ 태그 대상은 **`snap_tag IS NULL` 이고 최근 70분 안에 잡힌 행**이다.
   70분은 수집 주기(`odds_snapshot_30m`)의 두 배 + 여유다 — 주기를 문서에
   베끼지 않고 상수 하나로 두고 그 근거를 주석에 남긴다.
   스냅샷이 없으면 **아무것도 태그하지 않는다**(0 으로 채우지 않는다).

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** `KINDS` 는 종목 무관이고 야구도 같은 5시점을 쓴다
(Part 4 7-6: "상태·조건은 같다. 라인업 확정 = 타순 발표"). 그래서 대상은
`starts_at` 이 있는 **예정 경기 전부**다. 축구만 걸면 야구 쪽에서 같은
배선을 또 만들게 되고, 그것이 이 저장소가 반복한 사본 결함이다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 잡 래퍼(`_job_specs` 경로)가 예외를 `job_failed` 로 올린다.
- 조용한 0 방지: tick 마다 **계획 n · 발사 n · 태그 n** 을 로그 한 줄로 남긴다.
  발사했는데 태그가 0이면 그 사유(최근 스냅샷 없음)를 경기별로 남긴다.
- 트리거는 스냅샷이 없어도 **fired 로 표시한다** — 안 그러면 같은 트리거가
  1분마다 영원히 재시도한다. 대신 `attempts` 가 남고 로그가 사유를 적는다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 시점 오프셋·동시 상한·SQL 셋을 **다시 적지 않는다.** `triggers.KINDS`·
  `MAX_CONCURRENT`·`DUE_SQL`·`UPSERT_SQL`·`MARK_SQL` 을 임포트해 그대로 쓴다.
- 우선순위도 `triggers.prioritize` 를 쓴다(|gap| 큰 순). 지금은 `gap_pp` 를
  넣어 주는 배선이 없어 전부 `None` → 사실상 `due_at` 순이다. **그 사실을
  로그에 적는다** — 나중에 GATE-1 이 붙으면 값이 생긴다.
