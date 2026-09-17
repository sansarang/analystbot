# ANL-5 — 수집한 사실이 **분석에 안 닿는다**

## 왜

실측 2026-09-17 (오늘 밤 게이트 3건 · 운영 원장·추출 캐시):
```
원장:  p_prior 0.5487 / 0.68 / 0.574            ← blk 에 **하드코딩 None**
추출:  notes "고종욱 1군 말소."
       notes "서호철 1군 말소, 클레빈저 1군 등록."  ← build_input 이 **안 읽는다**
추출:  doubt (출전 의문)                          ← 스키마에 있는데 안 읽는다
```
그래서 모델이 본 입력이 **6줄**이었다:
```
[경기] Kia Tigers vs Kiwoom Heroes · KBO · KST
[숫자 — 변경 불가]
p_prior None · p_market(open) 0.6156 · gap 6.75 · 게이트 "가치 의심"
[홈 사실] 결장 고종욱 · XI predicted
[원정 사실] 결장 없음
[missing] 없음
```
L1 반려 2/3 의 사유가 **"결정축_근거가 입력 블록에 없는 사실이다"** 였다.

🔴 **재료가 없어서 지어낸 것이 아니라, 있는 재료를 안 줘서 되풀이한 것이다.**

## ① 이 함수/상태를 읽는 곳 **전부**

```
analyze.build_input            ← 사실 줄에 notes·doubt 를 더한다
pick_ledger.record_confirm_and_analysis ← p_prior 를 원장에서 읽어 blk 에 싣는다
  └ 그 안의 SELECT             ← p_prior 를 뽑는다
scout_config.EXTRACT_SCHEMA    ← notes·doubt 의 **원본**. 지어내지 않는다
analyze.l1                     ← build_input 을 검사 기준으로 쓴다 → **기준이 넓어진다**
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **`l1` 의 기준이 넓어지는 것은 이번에는 의도한 것이다.** `l1` 은 "근거가
  입력 블록에 있는 사실인가"를 본다 — 입력에 사실이 늘면 **인용할 수 있는
  사실이 느는 것**이지 검사가 약해지는 것이 아니다.
  ⚠️ 다만 `notes` 에 **숫자가 있으면** 숫자 인용 허용 범위가 넓어진다.
     그건 사실이니 허용이 맞다(규칙은 LLM 이 **만드는** 것을 막는 것이다).
- 🔴 **없으면 안 쓴다.** `notes`·`doubt` 가 비면 줄을 늘리지 않는다 —
  "없음"을 쓰면 없는 사실이 있는 것처럼 보인다.
- 🔴 **`p_prior` 가 없으면 종전대로 None 이다.** 0.5 로 채우지 않는다.
- 🔴 **칸 이름을 손으로 안 적는다.** `notes`·`doubt` 는 `EXTRACT_SCHEMA` 의 키다.
- 🔴 **`out`·`xi_status`·`last3`·`midweek` 줄은 안 바뀐다.** 계약이 잰다.
- ⚠️ `source`·`published`(URL·날짜)는 **안 넣는다** — 판단 재료가 아니라 잡음이다.
- ⚠️ `adj_pp`·`adj_evidence`·`market_flow`·`structure_pick` 은 **오늘 비어 있다**
  (실측). 없는 것을 넣을 수는 없다 — 그건 다른 단위의 일이다.

## ③ 되돌리기

커밋 1개 revert. 사실 줄 두 조각과 SELECT 칸 하나가 빠진다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 오늘 밤 게이트 경기에 다시 돌려
입력 블록이 늘고 L1 이 어떻게 되는지 본다(⑨).

## ⑤ 계약

10건 — notes 가 들어간다 · doubt 가 들어간다 · 없으면 줄이 안 는다 ·
p_prior 를 원장에서 읽는다 · 없으면 None · SELECT 에 칸이 있다 ·
종전 줄(out·xi_status·last3·midweek)이 안 바뀐다 · 칸 이름 사본 금지 ·
`with_schema=False` 기본 유지 · URL 을 안 넣는다.
