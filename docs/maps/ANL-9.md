# ANL-9 — **선발이 분석 입력에 안 들어간다**

## 왜

사용자가 준 목표 분석(2026-09-17):
> "**선발 축이 이 경기의 전부입니다.** 톰슨은 … 이로운은 투구수 한도(70~80구선)로
> 짧은 이닝이 예정된 등판"
> "올러는 최근 매 등판 6~7이닝 안정 소화. 안우진은 직전 두 경기 10이닝 16피안타 9실점"

**재료는 이미 있다**(실측 2026-09-17 운영):
```
games.home_pitcher / away_pitcher       → '라일리' / '이로운'
pitcher_appearances                     → 8,203행
starter_recent.attach_starter_recent    → research.{side}_starter_recent 를 채운다
                                          (pipeline:2924 에서 판정 때 이미 부른다)
```
그런데 `record_confirm_and_analysis` 는 **원장 행**으로 `blk` 을 만들고 research 는
원장에 없다. `build_input` 에도 **선발 칸이 없다.**
→ 목표 분석이 "전부"라고 한 축을 **모델이 본 적이 없다.**

## ① 이 함수/상태를 읽는 곳 **전부**

```
pick_ledger.record_confirm_and_analysis ← 선발을 붙이는 곳
  └ games SELECT                        ← home_pitcher · away_pitcher 추가
starter_recent.attach_starter_recent    ← 재사용. **안 건드린다**(pipeline 도 쓴다)
starter_recent.slim_start               ← 등판 한 줄의 모양. **원본**
analyze.build_input                     ← 선발 줄을 만든다
analyze.fact_words (ANL-6)              ← 선발 이름·상대를 사실 낱말에 넣는다
analyze.l1 숫자 검사                     ← 입력에 숫자가 늘어 **인용 허용 범위가 는다**
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **`attach_starter_recent` 를 다시 만들지 않는다.** pipeline 이 쓰는 그
  함수를 그대로 부른다(사본 금지). `conn` 은 `.fetch` 가 있어 pool 자리에 맞는다.
- 🔴 **ERA 를 만들지 않는다.** `slim_start` 머리말이 "ERA 키는 만들지 않는다"고
  못 박았다 — 이닝·실점·피안타·득점지원만 싣는다. 계약이 잰다.
- 🔴 **없으면 줄을 안 쓴다.** 예고 선발이 없거나(축구) 등판 기록이 0건이면
  줄을 늘리지 않는다 — "없음"을 쓰면 없는 사실이 있어 보인다.
- 🔴 **최근 N건만.** 전부 실으면 프롬프트가 길어지고 잡음이 는다. 상한은
  `starter_recent.RECENT_STARTS` 가 이미 정한다 — 여기서 새 숫자를 안 만든다.
- 🔴 **실패해도 분석을 막지 않는다** — 선발 조회가 터지면 선발 줄만 없다.
- ⚠️ `l1` 의 숫자 검사 기준이 **넓어진다.** 입력에 이닝·실점 숫자가 들어가므로
  모델이 그 숫자를 인용해도 통과한다 — **그게 맞다**(규칙은 LLM 이 숫자를
  **만드는** 것을 막는 것이다). ANL-5 와 같은 판단이다.
- ⚠️ 축구는 예고 선발 칸이 없다 — 줄이 안 생기고 종전 그대로다.

## ③ 되돌리기

커밋 1개 revert. SELECT 칸 둘 · 붙이는 블록 · 렌더 줄.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 오늘 밤 게이트 경기에 다시 돌려
선발 줄이 들어가는지, 분석이 그걸 인용하는지 본다(⑨).

## ⑤ 계약

10건 — 이름이 들어간다 · 최근 등판이 들어간다 · 없으면 줄이 안 는다 ·
**ERA 를 안 만든다** · 상한을 손으로 안 적는다 · 조회 실패해도 분석이 산다 ·
SELECT 에 칸이 있다 · fact_words 가 선발 이름을 안다 · 종전 줄 불변 ·
attach_starter_recent 를 재사용한다.
