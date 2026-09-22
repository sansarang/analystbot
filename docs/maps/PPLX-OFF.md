# PPLX-OFF — 퍼플렉시티를 검색에 쓰지 않는다 (영향 지도 5문)

사용자 지시 2026-09-22: **"퍼플릭스는 서치에 사용하지 않는다"**

## ① 지금 상태 — **이미 꺼져 있었다** (실측 2026-09-22 · 운영)

```
DISABLED_PROVIDERS        'anthropic,perplexity,xai,nvidia'
is_disabled(perplexity)   True
DEEPSEARCH_PPLX_ENABLED   '0'
research_calls:2026-09-22 없음 → **오늘 0콜** (상한 60)
research_crosscheck 09-15·09-18·09-21  checked 0
PPLX_API_KEY              꽂혀 있다 (mock_perplexity=False)
```

## ② 🔴 내 첫 전제가 틀렸다 — 목은 막혀 있다

처음에 "`PerplexityClient.chat` 이 `self.mock` 만 보므로 게이트가 호출부에만
있고, 그 앞을 안 거치는 경로가 생기면 유료 요청이 나간다"고 적었다.
**한 단계 아래를 안 봤다:**

```
PerplexityClient.chat → BaseAPIClient._post → _request
  → api_guard.raise_if_unusable(name)
       if is_disabled(name): raise ProviderDisabledError   ← 여기서 끊긴다
  → _send  (실제 HTTP)                                      ← 도달하지 않는다
```

계약을 쓰고 돌리자 `ProviderDisabledError` 가 났고, 그게 내 전제를 뒤집었다.
**그래서 코드를 한 줄도 고치지 않았다.** 게이트를 더 놓으면 두 벌이 된다.

막는 곳은 셋이고 **층이 다르다**(중복이 아니다):

| 어디 | 무엇을 막나 | 왜 필요한가 |
|---|---|---|
| `api_guard.raise_if_unusable` | **모든 `BaseAPIClient` 요청** | 목. 여기 하나로 전 경로가 닫힌다 |
| `ask_json` | 자기 요청 | httpx 직호출이라 목을 안 지난다 |
| `deep.py:593`·`494` | 호출 전 조기 반환 | 콜 수 집계·캐시 반환 때문 |

## ③ 무엇을 했나

| 파일 | 무엇 | 코드? |
|---|---|---|
| `tests/test_pplx_off.py` | 계약 7건 — 지시를 **기계가 지킨다** | 테스트 |
| `CLAUDE.md` | 머리말 "의견은 딥서치로(Perplexity, Grok)" → **Bing 체인·Grok** · 마이그레이션 기한 무효 처리 · 규칙 절 신설 | 문서 |
| `app/engine/council.py` | 주석 "주전 — 퍼플렉시티" 정정 (실제 주전은 무료 사슬) | 주석 |

🔴 **운영 동작은 바뀌지 않는다.** 이미 0콜이었다. 바뀌는 것은 **다음 세션이
   퍼플렉시티를 주전 검색 통로로 읽지 않는다**는 것이고, 그게 이 지시의 내용이다.

## ④ 무엇이 깨질 수 있나

⚠️ **되돌릴 길을 막지 않았다.** `test_켜면_나간다` 가 그것을 잠근다 —
   `DISABLED_PROVIDERS` 를 비우면 요청이 다시 나가야 한다. 막기만 하는
   수정이면 정식 승인을 받아도 못 켠다.
⚠️ `PPLX_API_KEY` 는 **안 건드렸다.** 키 삭제는 사용자 몫이다(가입·결제·키는
   사용자가 한다). 키가 있어도 스위치 때문에 나가지 않는다.
⚠️ 계약이 예외 **이름을 베끼지 않는다** — `api_guard` 가 올리는 것을 그대로
   기대한다. 이름을 적으면 원본이 바뀔 때 계약이 안 따라간다(사본 금지).

## ⑤ 되돌릴 수 있나

`DISABLED_PROVIDERS` 에서 `perplexity` 를 빼면 된다. 코드 기본값에도 들어
있으므로 환경변수를 비우는 것만으로는 안 켜진다 — **의도적으로 켜야 켜진다.**

## ⑥ 첫 판에 계약이 두 번 거짓 실패했다 (기록)

1. `test_기본값이...` — `Settings()` 를 그냥 만들어 **개발자 `.env`** 를 쟀다.
   → `Settings.model_fields[...].default` (코드의 값)로 고쳤다.
2. `test_켜면_나간다` — 가짜 httpx 에 `.post`·`.get` 만 두고 `.request` 를
   빠뜨렸다. `BaseAPIClient._send` 는 `.request()` 를 쓴다 → 가짜가 안 잡혀
   "요청 0"으로 보였다. **거짓 통과의 전형**이라 주석으로 남겼다.
