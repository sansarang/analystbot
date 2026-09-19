# NAR-2 영향 지도 — ⑫가 없는 함수를 부르고 있었다

## 1. 무엇이 틀렸나 (실측 원문)

운영 컨테이너에서 ⑫를 직접 돌렸다:

```
페이로드 키: ['adjustments','away','confidence','confirmed_vars','home',
             'kickoff_kst','p_code','pick_market','pick_side','pick_type']
[flow:n12] 서술 실패: cannot import name 'complete_text' from 'app.llm.provider'
[flow:n12] game=10098 규격 미달 (문장 0 · 지어낸 숫자 [])
[flow:n12] 서술 실패: cannot import name 'complete_text' from 'app.llm.provider'
시도 2 · 환각 True · 문장 0
```

두 번 다 같은 `ImportError` 로 죽고 `hallucination=True` 가 된다.
**⑫가 카드를 만들 수 있었던 적이 없다.**

드러나지 않은 이유: 흐름이 ⑥(`n06_unknown`)에서 멈춰 ⑫까지 간 적이 없다.
"배포했고 테스트가 통과한다"가 동작의 증거가 아니라는 예다(CLAUDE.md 규율).

⚠️ 페이로드 자체는 깨끗했다 — 배당·시즌 누적·H2H 가 없다. 그 부분은 결함이
   아니고, 회귀만 막으면 된다(같은 커밋의 `test_nar1_payload.py`).

## 2. 어디를 고치나

`app/flow/nodes/n12_text.py` `_ask` 한 곳.

## 3. 영향 지도 5문

**① 진짜 API 가 무엇인가.**
`provider.complete(role, messages, *, system, schema, max_tokens, ...) -> LLMResult`
다. `complete_text` 는 없다. `narrator` 는 이미 등록된 역할이다(`provider.ROLES`).

**② 왜 `narrator` 역할인가.**
판정 역할(`judge_*`)을 쓰면 서술이 **판정 예산을 먹는다.** provider 주석이
이미 "역할 넷(interpreter·narrator·intent·judge_a)의 운영 사슬" 을 구분하고
있다. 계약이 `"narrator"` 를 쓰는지 센다.

**③ 반환 모양이 다르다.**
`complete` 는 `LLMResult` 를 돌려준다(문자열이 아니다). 텍스트를 꺼내는
자리를 한 곳에 두고, 모양이 바뀌면 거기서만 고친다.

**④ 사슬이 죽으면.**
예외를 올리지 않는다. 지금도 `try/except` 가 감싸고 있고 빈 문자열을 돌려
`hallucination=True` 로 끝난다 — **흐름이 죽지 않는다.** 계약이 그것을 센다.
gemini 는 429, groq 은 200 이므로(Phase 0 E-1) 폴백 사슬이 groq 으로 간다.

**⑤ 무엇이 조용히 0이 되나.**
서술이 실패하면 ⑬이 카드를 못 만든다. 그 자체는 맞는 동작이지만,
**실패 이유가 로그에만 있으면 모른다.** 스냅샷에 `hallucination` 과
`attempt` 가 이미 남으므로 원장에서 셀 수 있다 — 새 칸을 만들지 않는다.

## 4. 안 하는 것

- 프롬프트를 바꾸지 않는다.
- 페이로드 항목을 늘리지 않는다.
- 발송을 켜지 않는다.
