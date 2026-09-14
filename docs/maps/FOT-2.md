# FOT-2 — FotMob 호출부 배선 (수집 맨 앞 + T-60 재호출). 사용자 지시

## 왜

`FOT-1` 이 라인업·결장을 구조 JSON 으로 받는 길을 냈지만 **부르는 곳이 0**
이었다. 오늘 밤 완료 조건(Torino-Roma T-60 에서 디발라 선발 여부가 diff 로
잡히는가)은 두 시점 호출이 있어야 성립한다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_fot2.py
  → satellite.gather → fotmob.attach 0건 · _triggers_tick → 0건
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "fotmob" app/ tests/
app/collectors/fotmob.py     정의(FOT-1)
tests/test_fotmob.py         계약
   → app/ 안 호출부 **0**
```
붙이는 자리는 둘이다:
- `satellite.gather` — 축구 어댑터 **앞**. 층1(트랜스퍼마크트·플래시스코어)
  보다 먼저 붙어야 `gather_soccer` 가 그 값을 볼 수 있다.
  ⚠️ 어댑터 시그니처를 바꾸지 않으려고 `gather` 에서 부른다 — 그쪽이 `redis`
     를 이미 들고 있다(예상 XI 보관에 필요).
- `scheduler._triggers_tick` — `kind == "lineup"`(T-60)에서 **재호출**.
  트리거 모듈은 시각만 관리하고, 무엇을 할지는 이 호출부가 정한다(TRG-1 규약).

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `jg["fotmob"]` | 메모리(FOT-1 이 정한 모양) |
| Redis `fotmob:xi:{game_id}` | FOT-1 이 이미 쓰는 키 — 예상 XI 보관 |
| `game_trace` 행 | **두 시점 모두 원장에**(사용자 지시) — stage=수집, ref 에 XI·diff |

새 컬럼·새 테이블 없다. `game_trace.STAGES` 에 새 단계를 만들지 않고
`ref.event` 로 사건 이름을 남긴다(TOR-1 과 같은 규약).

## ③ 리그·종목·경로 분기가 생기는가

**축구만**이다. `gather` 에서 `sport == "soccer"` 일 때만 부르고, 트리거
쪽도 같은 조건이다. 야구는 FotMob 을 쓰지 않는다(라인업 경로가 다르다).

## ④ 실패하면 "시끄럽게" 실패하는가

- `attach` 는 실패를 결측으로 돌려준다(FOT-1). 호출부는 그 빈손을 그대로
  기록한다 — `predicted` 도 `confirmed` 도 못 받으면 원장에 그 사실이 남는다.
- T-60 에서 `confirmed` 가 아직 아니면 그것도 기록한다. "안 바뀌었다"와
  "못 받았다"를 원장에서 갈라야 내일 다시 재지 않는다.
- 트리거 tick 은 예외를 삼키고 로그를 남긴다 — 라인업 조회 실패가 스냅샷
  이름표(TRG-2)를 막으면 안 된다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 시점(T-60)을 코드에 적지 않는다 — `triggers.KINDS["lineup"]` 이 원본이고
  tick 은 그 이름(`kind`)만 본다.
- diff 규칙도 `fotmob.diff_xi` 가 원본이다(id 기준).
- 원장 쓰기는 `game_trace.note` 를 쓴다.
