# 무료 LLM 오디션 — 2026-09-04

Anthropic 크레딧 소진 후 **전량 무료 전환**(사용자 지시: "난 완전 돈이 안들어갔으면 해").
이 문서는 **실호출 측정치만** 담는다. 추정은 담지 않는다.

## 1. 선발 결과 (현재 운영 사슬)

| 역할 | 1순위 | 2순위 | 3순위 | 비상 |
|---|---|---|---|---|
| 판정 `matchup` | nvidia / nemotron-3-ultra-550b-a55b | openrouter / minimax-m3:free | — | anthropic (일일 캡 10) |
| 팀 폼 `form` | nvidia / nemotron-3-ultra-550b-a55b | groq / qwen3.8-27b | openrouter / gemma-4-31b-it:free | anthropic (캡) |
| 해석 `interpreter` | groq | gemini | — | — |
| 서술 `narrator` | groq | gemini | — | — |
| 의도 `intent` | groq | gemini | — | — |
| 감시 L2·L3 | gemini | — | — | — |

## 2. 후보 실측

### 2-1. 판정·폼 후보

| 후보 | 결과 | 비고 |
|---|---|---|
| nvidia / nemotron-3-ultra-550b-a55b | **채택** | KBO 판정 5/5 성공. 응답 15~87초 |
| openrouter / minimax-m3:free | **채택(2순위)** | 3.7초, JSON 정상, ctx 1M |
| openrouter / gemma-4-31b-it:free | **채택(3순위)** | 1.3초, JSON 정상, ctx 262k |
| openrouter / deepseek-r1 | **탈락 — 유료** | `:free` 아님. 키 사용액 $0.0002594 발생 |
| openrouter / nemotron-3-ultra:free | **탈락** | 업스트림이 NVIDIA — 주전과 같이 죽는다 (502 "Upstream error from Nvidia") |
| openrouter / nemotron-3-super-120b:free | 탈락 | 사고문이 `content` 로 샌다 |
| openrouter / dots-3-note-preview:free | 탈락 | 빈 응답 |
| openrouter / inkling:free | 호출 불가 | "only available on agentic harnesses" |
| mistral / mistral-medium-latest | 탈락 | 429 지속 (재시도 4회·95초 후에도) |

### 2-2. 무료 한도 (실측 헤더·공식 문서)

| 제공자 | 한도 | 출처 |
|---|---|---|
| **Groq** | `x-ratelimit-limit-requests: 1000` · **`x-ratelimit-limit-tokens: 8000`(분당)** | 응답 헤더 |
| **NVIDIA NIM** | 한도 헤더 없음 — **공개된 수치 없다.** 대신 **간헐 503** | 실측: 8회 중 3회 503 |
| **OpenRouter `:free`** | **20 req/분 · 50 req/일** (누적 결제 $10 미만) → $10 결제 시 1000/일 | 공식 문서 + 키 조회 `is_free_tier: true` |
| **Gemini** | 무료 20 RPD | 감시 3층 전용. 하루 수요 ≈122콜 — **부족하다** |
| **Mistral** | 실측 불가 (429) | — |

🔴 **Groq 분당 8000토큰**은 판정 프롬프트 1건에 빠듯하다. 그래서 Groq 는
   **폼 사슬에만** 두고 판정 사슬에는 넣지 않았다.
🔴 **OpenRouter 무료는 하루 50건**이다. 폴백으로만 쓰는 현재 구성에서는
   충분하지만, 주전이 되면 하루치가 안 된다.

## 3. Nemotron 의 사고 토큰 — 폼 파싱 실패의 원인

Nemotron 3 Ultra 는 사고를 `reasoning_content` 로 따로 주기도 하고
`content` 안에 쏟기도 한다(**비결정적**). 후자일 때 `team_form_max_tokens=1500`
이 전부 사고로 소진돼 JSON 이 나오지 않는다.

측정 (같은 프롬프트, `max_tokens=1200`):

```
content 423자 | reasoning_content 1814자 | completion_tokens 676 | finish stop
```

운영 로그 (프리페치 15:13):

```
1회차 resp_chars=599  앞='{\n  "team": "Samsung Lions", "타선": …'   ← 잘린 JSON
2회차 resp_chars=3881 앞="The user wants me to analyze Samsung Lions'" ← 영어 사고문
```

### 해법 — 사고를 끈다 (예산을 올리지 않는다)

| 방법 | 결과 |
|---|---|
| `reasoning_effort: "none"` | **reasoning 222자 → 0자** · completion 112→58토큰 |
| `chat_template_kwargs: {"thinking": false}` | reasoning 0자 (NIM 전용 필드) |
| system `/no_think` | 효과 없음 (reasoning 263자) |

세 제공자 모두 `reasoning_effort` 를 400 없이 받는다(nvidia·groq·openrouter 실호출 확인).
**폼만** 끄고 판정은 켠 채로 둔다 — 폼은 구조화 출력이고 판정은 사고가 품질이다.
`team_form_max_tokens` 는 1500 그대로다.

## 4. 미완

- Mistral·OpenRouter 후보를 **동일 프롬프트로 나란히 채점**하는 오디션 하네스
  (`tools/llm_audition.py`)는 만들어 뒀으나 전 후보 완주 기록이 없다.
  Nemotron 만 실슬레이트로 검증됐다.
- Gemini 20 RPD 대 수요 122콜 — 감시 3층이 하루치를 못 채운다. 아직 미해결.
