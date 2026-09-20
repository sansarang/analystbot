# OBS-2 영향 지도 — 관측 상태기계가 한 번도 안 돌았다

## 0. 재현 (실측 원문)

```
── 4-11 watch_state
     칸: 있음
     (NULL)       1393          ← pick_ledger 전건
```

`app/engine/watch_state.py`(77줄 · U10 2026-09-15)와
`app/engine/observer.py`(110줄 · OBS-1 2026-09-19) **둘 다 app/ 안 호출부 0건**.

```
$ grep -rn "watch_state\." app/ | grep -v pycache      → 0건
$ grep -rn "observer"      app/ | grep -v pycache      → 0건 (자기 파일 제외)
```

## 1. 갈림길 — 둘 중 무엇이 원본인가

**같은 6개 상태를 각자 선언하고 있다(사본).** 나머지는 겹치지 않는다:

| | `watch_state.py` (U10) | `observer.py` (OBS-1) |
|---|---|---|
| `STATES` | 선언 | **또** 선언 |
| 전이 허용표 `ALLOWED` | **있다** | 없다 |
| `next_state` | 허용표 기반(전이 강제) | `contra` 면 취소, 그 외 그대로 |
| 조건 A | 4항목 | **6항목** |
| 조건 B | 없다 | **있다** |
| 발송 매핑 | 없다 | **있다** |
| 루프 주기 | 없다 | **있다** |

🔴 **고른 것**: 상태 목록·전이 허용표의 원본은 **`watch_state.py`** 다 —
전이를 강제하는 표가 거기 하나뿐이고, `db/schema.sql:566` 주석이
"코드만 전이한다"고 가리키는 성질이 그것이다. 정책(조건 A/B·발송·주기)은
`observer.py` 가 가진다. `observer` 가 `watch_state` 를 **읽는다**.

**안 고른 쪽**: observer 를 원본으로 삼으면 전이 허용표를 옮겨야 하는데,
그러면 U10 계약 테스트(`tests/test_u10_structure.py`)가 가리키는 자리가
사라진다. 새 모듈을 만드는 선택지는 **코드만 늘리므로 버렸다**.

## 2. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `app/engine/observer.py` | `STATES`·`TERMINAL` 을 `watch_state` 에서 **가져온다**(사본 제거) |
| `app/flow/watch.py` (신규 · 순수 함수) | 흐름이 아는 값 → 상태. DB·LLM 0 |
| `app/flow/bridge.py` | `run_slate` 가 경기마다 상태를 `games.watch_state` 에 쓴다 |

**② 흐름이 올릴 수 있는 상태는 어디까지인가.**
**관측 · 후보 · 추천 · 종료 넷뿐이다.** `추천대기` 로 올리려면 조건 A 가
`market_view`(분석 LLM 판단)와 `swap_agree` 를 요구하는데 **v1.4 경로에 그 값이
없다**. 🔴 없는 값을 지어내 상태를 올리지 않는다 — 그것이 이 배선의 유혹이다.

```
보드고정 → 관측      게이트 대상(동의·시장과대·가치의심) → 후보
⑬ 발송   → 추천      킥오프 지남                        → 종료
```

**③ 새 숫자를 만드나.**
만들지 않는다. 상태 이름은 `watch_state.STATES` 가 원본이고 게이트 라벨은
`flow.labels` 가 원본이다. 문턱 0개.

**④ 무엇이 깨질 수 있나.**
`games.watch_state` 에 UPDATE 가 는다(경기당 1행). 🔴 **역방향 전이**가 가장
큰 위험이다 — 재실행이 `추천` 을 `후보` 로 되돌리면 이미 나간 카드를 되돌려야
한다. `watch_state.next_state` 의 허용표를 반드시 통과시킨다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/pipeline/test_obs2_watch_state.py` 5건 — 상태 목록이 한 곳인가(사본),
게이트→상태 대응 3건, **역방향 전이 거부**, `run_slate` 가 실제로 기록하는가.

## 3. 하지 않은 것 (등록만)

- **4-11-b** 조건 A/B(`observer.cond_a`·`cond_b`)는 여전히 호출부 0건이다.
  `market_view`·`swap_agree`·`xi_status`·`diff_adverse` 를 v1.4 가 만들지 않는다.
  그 값들을 만드는 것은 **배선이 아니라 신규 기능**이라 범위 밖이다.
