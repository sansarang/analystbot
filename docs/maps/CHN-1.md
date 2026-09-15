# CHN-1 — 무료 사슬이 사실상 groq 하나였고, 429 에서 453초를 기다렸다

## 왜

2026-09-15 사용자 지시("새 무료 키 2개 … 429·401은 즉시 다음 제공자로").
재현(`repro_chn1.py`)이 넷을 집었다:
```
사슬 = [('gemini','gemini-3.5-flash-lite'), ('groq','openai/gpt-oss-120b')]
🔴 gemini/gemini-3.5-flash-lite 이 유료로 분류돼 PAID_LLM_ALLOWED=0 에서 사슬에 못 든다
🔴 matchup_max_tokens=12000  · deepsearch_max_tokens=16000 — 1콜이 무료 분당 한도를 넘는다
🔴 429 에서 453초를 기다린다 (retries=4)
```
groq 무료 티어 실측: `x-ratelimit-limit-tokens = 8000`(분당). 판정 1콜이
이 한도를 통째로 넘으니 슬레이트가 통째로 막힌다 — 어젯밤 P0-1 실측이
다섯 번 연속 여기서 죽었다(`[triage] 실패` · `[v3] 탈락 — 판정 실패`).

## 실측한 제공자 (2026-09-15 12:4x KST)

| 후보 | 결과 |
|---|---|
| cerebras `llama-3.3-70b` | 404 — 계정 모델 목록에 없다 |
| cerebras `gpt-oss-120b`·`qwen-3.8-27b` | **402 Payment required** — 무료 아님 |
| gemini `gemini-2.5-flash-lite` | 404 **은퇴** (Google 안내: `gemini-3.5-flash-lite`) |
| gemini `gemini-3.5-flash-lite` | **200 · 0.9s** ✅ |
| gemini `gemini-3.6-flash` | 200 · 6,013토큰 프롬프트 6연속 무 429 ✅ |
| groq `openai/gpt-oss-120b` | 200 · 그러나 8,000 TPM |
| openrouter `nex-n2.5-pro:free` | **401 User not found** |

→ 사슬은 **gemini → groq** 둘. cerebras 는 결제를 켜면 1줄로 붙는다(지금은 안 붙인다 —
   못 쓰는 코드를 미리 넣지 않는다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
judge_route.FREE_PROVIDERS / is_free   → chain() 이 후보를 거를 때
openai_compat.complete  429/401 분기    → team_form._run_chain · provider.call_with_role
settings.matchup_max_tokens            → verdict.decide · dbref.recheck
settings.deepsearch_max_tokens         → triage
```

## ② 깨뜨릴 수 있는 기존 동작

- **gemini 를 무료로 분류**한다. AI Studio 무료 티어 키 기준이다. 결제를 켜면
  이 분류가 거짓이 된다 — `DISABLED_PROVIDERS` 가 여전히 안전판이다.
- **429 를 기다리지 않는다.** 종전 주석("우회하지 않는다. 기다린다")의 전제는
  제공자가 하나뿐일 때다. 둘이 되었으므로 기다림은 손해다. 후보가 전부 429 면
  종전보다 **빨리 실패**한다 — 그건 조용한 지연보다 낫다(원장에 사유가 남는다).
- **max_tokens 1500.** ⚠️ `config.py:317` 이 "1000 이면 사고에 토큰을 다 쓰고
  본문 JSON 이 잘린다"고 적고 있다. 1500 은 그 경계에 가깝다 — 첫 사이클에서
  `파싱=실패` 가 늘면 되돌린다.

## ③ 되돌리기

커밋 1개 revert + 환경변수 3개 복구. 스키마 변경 없음.

## ④ 측정

`repro_chn1.py` 를 그대로 다시 돌린다(같은 명령). 429 대기가 <5초,
제공자 2개, max_tokens 1500, gemini 무료 분류.

## ⑤ 계약

```
test_gemini는_무료_사슬에_든다
test_429는_기다리지_않는다        · 401도 같다
test_판정_토큰이_무료한도_안이다
test_openrouter는_사슬에_없다
```
