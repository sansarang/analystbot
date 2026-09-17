# ANL-3 — 원장의 `analyze_model` 이 **거짓말을 한다**

## 왜

실측 2026-09-17: 원장에 `analyze_model = 'claude-opus-5'` 로 찍혀 있는데
**Opus 는 불리지도 않았다.** 로그가 그대로 말한다:
```
[matchup_prelim] gemini/gemini-3.5-flash-lite 응답이 JSON 이 아니다 (1033자)
[matchup_prelim] 🔴 무료 사슬 전부 실패 — 유료로 내려가지 않는다
```
`analyze.run` 이 `to_ledger(model=s.matchup_model)` 로 **설정값**을 적는다.
무료 사슬은 폴백하므로 **설정값 ≠ 응답한 모델**이다.

🔴 오늘 MDL-1 에서 고친 것과 **똑같은 병이 두 번째 자리에 있다.**
`matchup.py:1621` 이 이미 적어 뒀다 — "폴백이 일어나면 어느 모델이 그 판정을
했는지가 사라지고, 그러면 **모델별 성적을 영영 못 가른다**".

⚠️ 이 칸이 거짓이면 ANL-2 로 분석이 살아난 뒤에도 **"어느 모델이 쓸 만한
   분석을 냈나"를 못 답한다.** docs/FORKS.md F-6 과 같은 자리다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
analyze.run (:339 :348)        ← 고치는 곳. to_ledger 에 넘기는 model
analyze.answered_model         ← **신규**. LAST_USAGE 에서 읽는다
analyze.to_ledger              ← 그대로. 받은 값을 적을 뿐이다
team_form.LAST_USAGE           ← 실제 응답 모델의 **원본**
matchup._real_model            ← 같은 일을 하는 v2 쪽 함수. **안 건드린다**
db: analyze_model              ← 원장 칸
report.by_variable 의 출처 집계 ← 나중에 이 값으로 가른다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **호출 실패 가지는 종전대로 None 이다.** 응답이 없으면 모델도 없다 —
  `''` 나 설정값으로 채우면 "안 불렸다"와 "불렸다"가 같아진다.
- 🔴 **판정 역할이 아닌 응답을 잡지 않는다.** `LAST_USAGE` 는 **직전 호출**이라
  폼 모델이 끼면 그것이 잡힌다 — 역할을 확인하고 아니면 설정값으로 떨어진다
  (`matchup._real_model` 과 같은 규약).
- 🔴 **`matchup._real_model` 을 안 건드린다.** v2 판정 경로가 그것을 쓴다.
  여기는 analyze 전용이고, **같은 규약을 따르되 각자 자기 역할을 본다** —
  analyze 는 `PRELIM_ROLE` 로 부르므로 `JUDGE_ROLES` 검사가 그대로 맞다.
- ⚠️ 두 함수가 거의 같은 일을 한다. 합치는 것이 옳아 보이지만 **그건 v2 판정
  경로를 건드리는 일**이라 여기서 하지 않는다. 계약이 `analyze` 쪽이
  `LAST_USAGE`·`JUDGE_ROLES` 라는 **같은 원본**을 보는지만 잰다.
- ⚠️ 지난 행은 **백필할 수 없다**(MDL-1 과 같다).

## ③ 되돌리기

커밋 1개 revert. 함수 하나와 인자 두 자리가 빠진다.

## ④ 측정

①과 **같은 명령**이 통과한다. 배포 뒤 오늘 밤 원장에서 `analyze_model` 이
실제 응답 모델(`gemini/…`)로 찍히는지 본다(⑨).

## ⑤ 계약

8건 — 실제 응답 모델을 적는다 · 설정값이 아니다 · 다른 역할이 끼면 설정값 ·
호출 실패면 None · to_ledger 는 안 바뀐다 · `matchup._real_model` 을 안 건드린다 ·
원본(LAST_USAGE·JUDGE_ROLES)을 본다 · 원장 칸까지 간다.
