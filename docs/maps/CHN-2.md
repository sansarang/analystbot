# CHN-2 — 400 강등이 **본문 글자**에 매여 있어 gemini 에서 안 걸렸다

## 왜

CHN-1 ⑨ 첫 사이클이 잡았다. 운영 실측 2026-09-15 (gemini-3.5-flash-lite,
OpenAI 호환 엔드포인트):
```
reasoning_effort=none      400  "Request contains an invalid argument."   ← 필드명이 없다
reasoning_effort=low       200
reasoning_effort=minimal   200
필드 없음                  200
```
강등 사다리는 이미 있다(`_next_reasoning`, 2026-09-04 groq 실측). 그런데 조건이
```python
if r.status_code == 400 and "reasoning_effort" in (r.text or ""):
```
라서 **응답이 필드명을 말해줄 때만** 걸린다. groq 는 말해주고 gemini 는 안 한다.

🔴 **이건 CHN-1 이 만든 회귀다.** `reasoning = role != "form"`(team_form.py:227)
   이므로 `reasoning=False` 를 쓰는 것은 **팀 폼 전건**이고, gemini 를 사슬 1순위로
   올린 순간 팀 폼이 매번 400 → groq(8,000 TPM) 로 떨어진다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
openai_compat.complete  400 분기 · _next_reasoning
  ← team_form._run_chain(reasoning=role != "form")
      ← _complete_free  ← deepsearch · triage · narrative_card · synthesis
                        ← satellite.py:1010 (chain("form") 추출)
```

## ② 깨뜨릴 수 있는 기존 동작

- **400 을 전부 강등으로 읽으면 안 된다.** 진짜 잘못된 요청(모델명 오타 등)까지
  세 번 더 때린다. 그래서 조건을 "우리가 `reasoning_effort` 를 **보냈고**
  400 이 왔다"로 좁힌다 — 안 보냈으면 종전대로 즉시 실패다.
- groq 경로는 바뀌지 않는다(본문에 필드명이 있든 없든 같은 사다리를 탄다).

## ③ 되돌리기

커밋 1개 revert. 설정·스키마 변경 없음.

## ④ 측정

`repro_chn2.py` 를 그대로 다시 돌린다 — gemini 의 **실제 400 본문**을 그대로
돌려주는 가짜 서버에서 `none → low` 로 강등해 200 이 나오는지.

## ⑤ 계약

```
test_400이_필드명을_말하지_않아도_강등한다
test_보내지_않은_필드로는_강등하지_않는다      ← 반대 위험
test_강등_사다리_순서는_그대로다
```
