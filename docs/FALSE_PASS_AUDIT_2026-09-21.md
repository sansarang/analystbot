# 거짓 통과 점검 — 목이 검사 대상 앞에서 값을 돌려주는 자리 (보고만)

실행 2026-09-21 13:45~13:50 KST · **편집 0** · 고칠 범위는 사용자가 정한다.

## 0. 왜 이 점검인가

SRC-OFF 에서 내 테스트가 **거짓 통과**였다:

```python
# 테스트
got = await kbo.fetch_month(2026, 9)
assert got == []          # ← 게이트를 껐든 켰든 늘 참

# 대상 코드
async def fetch_month(...):
    if freesource_mocked(client):   ← 목 분기가 **게이트 앞에** 있다
        return []
    client = client or KBOClient()
    rows = await client.schedule_rows(...)   ← require() 는 여기 있다
```

테스트 환경은 키가 없어 목 모드다. 그래서 단언은 **대상 코드에 닿지도 않고**
통과했다. 같은 구조가 더 있는지 라인 커버리지로 쟀다.

## 1. 목 분기 뒤 코드에 실제로 도달하는가 (전체 스위트 커버리지)

`pytest tests --cov=app.collectors` (5346 passed · 2026-09-21 13:48)

| 파일:함수 | 목 분기 줄 | 분기 뒤 실행/전체 | 판정 |
|---|---|---|---|
| `kbo.py:fetch_month` | 216 | **8/9** | 도달 |
| `naver_kbo.py:refresh` | 363 | **11/14** | 도달 |
| `kbo_news.py:fetch_for_games` | 276 | 7/14 | 도달 |
| `npb_form.py:refresh` | 213 | 1/8 | 일부 도달 |
| `absences.py:fetch_for_games` | 180 | **0/12** | 🔴 **분기 뒤 미도달** |
| `kbo_park.py:refresh` | 99 | **0/12** | 🔴 **미도달** |
| `kbo_roster.py:refresh` | 145 | **0/11** | 🔴 **미도달** |
| `kbo_stats.py:refresh` | 187 | **0/9** | 🔴 **미도달** |
| `kbo_usage.py:refresh` | 410 | **0/11** | 🔴 **미도달** |
| `npb_stats.py:refresh` | 160 | **0/7** | 🔴 **미도달** |
| `park.py:refresh` | 75 | **0/13** | 🔴 **미도달** |
| `weather.py:fetch_for_games` | 202 | **0/15** | 🔴 **미도달** |
| `yahoo_npb.py:refresh` | 729 | **0/14** | 🔴 **미도달** |

`app/collectors` 전체 라인 커버리지 **6,300/8,681 = 73%**

🔴 **9개 함수는 목 분기 뒤 코드가 테스트에서 한 줄도 실행되지 않는다.**
그 함수들에 대한 단언은 전부 "목이 돌려준 값"을 보고 있다 — SRC-OFF 와 같은
구조다. 게이트·파서·에러 처리를 바꿔도 테스트는 통과한다.

⚠️ 이것이 곧 "그 함수가 틀렸다"는 뜻은 **아니다.** "그 함수의 테스트가
   그 함수를 시험하지 않는다"는 뜻이다.

## 2. "아무 일도 안 일어남" 단언 — **1,155건**

`assert ... == []` · `is None` · `== {}` · `== 0` · `not ... called` 형태.
전수 나열은 의미가 없어 **성격별로만** 적는다:

| 성격 | 예 | 위험 |
|---|---|---|
| **의도된 빈손**(규약 검사) | `_factor_state({})["news"] is None  # '안 봤다'가 0 이 됐다` | 낮다 — 빈손 자체가 계약이다 |
| **정상 자료 통과 확인** | `invalid_reason("…OPS .812…") is None  # 정상 데이터는 통과` | 낮다 |
| **목이 돌려준 빈손** | `fetch_month(...) == []` (위 §1) | 🔴 **높다** |
| **호출 안 됨 확인** | `assert called == []` | 중간 — 목 주입이 맞는지에 달림 |

구분은 **§1 의 커버리지로만** 갈린다. 그래서 §1 을 먼저 냈다.

## 3. 고치는 법 (범위는 사용자가 정한다)

- 목 분기를 **테스트가 우회**하게 한다: 실제 클라이언트 객체를 넘겨
  분기 뒤 코드를 치게 한다(SRC-OFF 에서 한 방식).
- 또는 목 분기에 **표지**를 남기고(`reason="mocked"`) 단언이 그것을 구분하게 한다.
- ⚠️ 목 분기 자체는 **없애지 않는다** — 키 없이 크래시하지 않는 것이
  절대 규칙 3 이다. 바꿀 것은 테스트다.

## 4. 이번에 고친 것 (참고)

`tests/deepsearch/test_src_off.py` — `fetch_month(...) == []` →
`KBOClient().schedule_rows(...)` 가 `SourceDisabled` 를 올리는지로 바꿨다.
예외 종류도 `Exception` → `SourceDisabled` 로 좁혔다(넓은 예외는 `AttributeError`
까지 통과시킨다 — 실제로 그래서 한 번 놓쳤다).
