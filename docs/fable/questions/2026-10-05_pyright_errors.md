# 갈림길 — **pyright 에러를 언제 더 고치나** (2026-10-05)

## 사용자 지시 원문 (3번 · 타입 경계)

```
pyright 설치(dev 의존성). pyrightconfig.json: app/research/* strict, 나머지 basic.
pyright를 테스트 스위트의 계약 하나로 돈다(에러 0이어야 초록). 기존 코드 basic 에러는
**목록만 뽑아 questions/에 적고**, research/와 그것이 부르는 경계(lead.merge 입력·출력)만
지금 고친다.
```

🔴 그대로 했다 — `app/research/` 는 **에러 0**(strict)이고 나머지는 **여기 목록**이다.
⚠️ 계약(`tests/contracts/test_v5_3_types.py`)은 **`research/` 만** 0 을 요구한다 —
   나머지를 지금 요구하면 이 단계가 끝나지 않는다(v4 §13 범위 잠금).

## 수치 — 전체 **246건**

| 파일 | 건수 |
|---|---|
| `app/analyze.py` | 99 |
| `app/classify.py` | 32 |
| `app/cells.py` | 21 |
| `app/agentloop.py` | 19 |
| `app/collect/fotmob.py` | 15 |
| `app/survive.py` | 12 |
| `app/datehint.py` | 6 |
| `app/live.py` | 6 |
| `app/scenarios.py` | 5 |
| `app/searchcells.py` | 5 |
| `app/collect/mlb.py` | 4 |
| `app/r5gate.py` | 4 |
| `app/scheduler.py` | 3 |
| `app/verify.py` | 3 |
| `app/card.py` | 2 |
| `app/collect/ingest.py` | 2 |
| `app/main.py` | 2 |
| `app/bot/__main__.py` | 1 |
| `app/hypo.py` | 1 |
| `app/openworld.py` | 1 |
| `app/queries.py` | 1 |
| `app/solar.py` | 1 |
| `app/types.py` | 1 |

## 규칙별

| 규칙 | 건수 |
|---|---|
| `reportArgumentType` | 143 |
| `reportAttributeAccessIssue` | 59 |
| `reportOptionalMemberAccess` | 28 |
| `reportCallIssue` | 5 |
| `reportIndexIssue` | 5 |
| `reportOptionalSubscript` | 2 |
| `reportReturnType` | 1 |
| `reportGeneralTypeIssues` | 1 |
| `reportAssignmentType` | 1 |
| `reportOperatorIssue` | 1 |

## 🔴 왜 이것이 중요한가 — 두 크래시가 **꼴 불일치**였다

| 사고 | 무엇 | 타입이 잡았을까 |
|---|---|---|
| 2026-10-05 ① | `done.variables` 가 **문자열**로 와서 `row.get` 이 터졌다 — 변수 15,455자 소실 | ✅ `list[dict]` 로 선언했으면 잡는다 |
| 2026-10-05 ② | `lead.merge` 가 **`Classified`** 를 받아 `dict(v)` 가 터졌다 — **봇 사망** | ✅ 그래서 `SubtaskOut`·`VarLike` 를 넣었다 |

🔴 둘 다 *"받는 쪽이 꼴을 믿었다"* 다. 남은 에러 중 **같은 꼴**이 얼마인지는
   아직 세지 않았다 — 세는 것도 작업이므로 사용자 답을 기다린다.

## 묻는 것

| 선택 | 뜻 |
|---|---|
| **A** | `research/` 만 0 으로 두고 나머지는 안 고친다(**현 상태**) |
| **B** | 크래시가 났던 파일부터 — `analyze.py`·`classify.py`·`agentloop.py` |
| **C** | 전부 — ⚠️ 판정층 코드에 손이 간다 |

⚠️ **C 는 지시서와 충돌한다** — §0 이 *"검증층·판정층·DeepSeek 단계·보드 대입 코드
   변경(서치 층 밖은 전부)"* 을 금지했다. 그 금지가 걷히지 않으면 C 는 할 수 없다.
