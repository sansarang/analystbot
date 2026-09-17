# ANL-4 — L1·L2·금지어 판정이 **원장에 안 남는다**

## 왜

`analyze.run` 은 셋을 다 잰다(`l1`·`l2`·`banned_words`) 그리고 `out["analyze"]`
로 호출부에 **돌려준다.** 그런데 `_ANALYZE_SAVE` 는 main_axis·counter_axis·
market_view·swap_agree·structure_candidates·analyze_model·gate_vs_llm·
analyze_failed **만** 적는다. `skipped`(왜 못 했나)도 안 적는다.

🔴 실측 2026-09-17: 배포 직후 분석이 살아났는데 그 값이
```
L1=(False, '결정축_근거 에 확률·배당 숫자가 있다')
```
원장에는 `main_axis='주전 결장'` 만 남는다 — **반려당한 값인지 아닌지를
원장만 보면 알 수 없다.**

🔴 로그에만 있고, **로그는 재배포하면 날아간다** — 오늘 실제로 겪었다(분석
   실패 원인을 찾으려는데 이전 배포 로그가 이미 지워져 있었다).

`llm_winner`(MDL-1) · `model`(MDL-1) · `analyze_model`(ANL-3) 에 이어
**네 번째로 "잰 것을 안 남기는" 자리**다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
analyze.run                 ← led 에 analyze_check 를 싣는다
analyze.l1 / l2 / banned_words ← 재는 쪽. **안 건드린다**
pick_ledger._ANALYZE_SAVE   ← 칸 하나 + 자리표 하나
pick_ledger.record_confirm_and_analysis ← 그 값을 넘긴다
db/schema.sql analyze_check JSONB ← 신규 칸
out["analyze"] (호출부 반환) ← 그대로 둔다. 읽는 곳이 없어도 규약이다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **칸 하나만 늘린다.** 다섯 칸으로 쪼개면 원장이 넓어지고, 쪼갤 근거는
  아직 없다(무엇을 자주 조회할지 모른다). 한 JSONB 에 모은다.
- 🔴 **자리표 수를 맞춘다.** PA-23 에서 칸만 늘리고 `$N` 을 안 늘려 원장 저장이
  통째로 터질 뻔했다. 계약이 `$` 최대값을 잰다.
- 🔴 **실패 가지도 남긴다.** 호출 실패·JSON 아님일 때 `skipped` 가 들어간다 —
  "안 했다"와 "했는데 반려"를 갈라야 한다.
- 🔴 **검사 자체를 안 바꾼다.** `l1`·`l2`·`banned_words` 의 판정은 종전 그대로다.
  계약이 그 함수들이 안 바뀌었는지 잰다.
- 🔴 **반려가 원장을 막지 않는다**(ANL-2 에서 잠근 성질). 이번에도 그대로다 —
  반려해도 main_axis 는 남고, **반려당했다는 사실이 옆에 남을 뿐**이다.
- ⚠️ 지난 행은 백필할 수 없다.

## ③ 되돌리기

커밋 1개 revert. 칸 하나(`IF NOT EXISTS` 라 남아도 무해)와 자리표 하나.

## ④ 측정

①과 **같은 명령**이 통과한다. 배포 뒤 컨테이너에서 분석을 한 번 돌려
`analyze_check` 가 채워지는지 본다(⑨).

## ⑤ 계약

10건 — 통과/반려 둘 다 남는다 · 반려 사유가 남는다 · 금지어가 남는다 ·
skipped 가 남는다 · 반려해도 main_axis 는 남는다 · **자리표 수** ·
스키마 칸 · 검사 함수 불변 · JSON 직렬화 가능 · 실패 가지도 남는다.
