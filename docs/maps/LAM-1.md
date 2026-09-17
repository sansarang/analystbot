# LAM-1 — 우리 총점 확률이 **원장까지 안 간다**

## 왜

STR-1 이 `structure.candidates` 에 `ours_totals` 자리를 냈고 pipeline 이
`jg["model_probs"]` 에 담기 시작했다. 그런데
- 원장에 **칸이 없고**
- `record_confirm_and_analysis` 가 `candidates` 를 부를 때 그 값을 **안 넘긴다**

→ 총점 후보는 여전히 **0 건**이다. STR-1 이 문을 열었는데 아무도 안 지나간다.

## ⚠️ 자리표 사고 주의

PA-23 에서 **칸만 늘리고 `$N` 을 안 늘려** 원장 저장이 통째로 터질 뻔했다.
현재 INSERT 는 `$29` 까지다 → `$30` 이 된다.
계약이 **가짜 커넥션으로 실제 저장을 돌려** 인자 수를 센다(글자를 세지 않는다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
db/schema.sql model_probs JSONB        ← 신규 칸
pick_ledger._row_from_game             ← row 에 싣는다
pick_ledger INSERT (:376)              ← 칸 + $30
pick_ledger.record_confirm_and_analysis ← 읽어서 candidates 에 넘긴다
structure.candidates(ours_totals=…)    ← STR-1 이 낸 자리
pipeline jg["model_probs"]             ← STR-1 이 담은 값
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **자리표 수를 맞춘다.** 계약이 실제 호출 인자 수를 센다.
- 🔴 **없으면 None 이다.** λ 가 안 나온 경기(`model_valid=False`)는 그대로
  총점 후보가 없다 — 지어내지 않는다.
- 🔴 **`structure_pick` 저장 경로는 그대로다.** 후보가 없으면 안 쓴다
  (PA-17 에서 잠근 성질).
- 🔴 **종목으로 안 가른다** — 축구·야구 같은 길이다.
- ⚠️ 라인 키가 JSON 을 거치면 **문자열**이 된다(`{"7.5": …}`). `candidates` 는
  `float(line)` 과 `line` 둘 다로 찾지만 문자열 키는 못 찾는다 —
  **읽을 때 숫자로 되돌린다.** 계약이 그 경로를 잰다.
- ⚠️ 지난 행은 백필할 수 없다.

## ③ 되돌리기

커밋 1개 revert. 칸 하나(`IF NOT EXISTS` 라 남아도 무해) · 자리표 하나 · 호출 인자.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 다음 판정 사이클 뒤 원장에
`model_probs` 가 차는지, 총점 후보가 나오는지 본다(⑨).

## ⑤ 계약

9건 — 칸이 스키마에 있다 · row 에 실린다 · **자리표 수(실측)** ·
candidates 에 넘어간다 · 문자열 라인 키를 숫자로 되돌린다 · 없으면 None ·
후보 없으면 안 쓴다 · 종목 안 가름 · structure_pick 경로 불변.
