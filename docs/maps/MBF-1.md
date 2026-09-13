# MBF-1 — 모델 확률을 운영 `jg` 에 붙인다 (3차 결정 F(C) + G)

## 왜

3단계에서 만든 모델이 아직 운영에 닿지 않는다. 결정 F 는 접목 방식을 (C)로
정했다 — **모델 확률은 코드 쪽(`prob.py`)에만** 넣고 Gemini 프롬프트는
종전·v3 어느 쪽도 건드리지 않는다. (B)(종전 프롬프트에 블록 추가)는 사본
위험으로 금지다.

결정 G 는 관계를 이렇게 정했다:
```
p_code = p_market + Σadj + model_w · (p_model − p_market)
model_w = 0.0  (초기)   ← 기록만, 발송 숫자 영향 없음
```
300건 뒤 사용자가 `model_w` 상향을 판정한다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
pipeline._attach_market_spine  ← 여기에 호출 1줄 (두 러너가 이미 이 함수를 부른다)
prob.p_code                    ← 모델 축을 더한다
pick_ledger._row_from_game     ← 원장 기록
입력: jg["research"]["{side}_starter_recent"] · ["{side}_bullpen"]["최근3경기"]
      (MBL-1·2 가 아니라 **운영 부착 단계**가 채운 값이다)
```
빌려 쓰는 원본:
| 무엇 | 원본 |
|---|---|
| 모델 계산 | `model_baseball.model` (MBM-1·2) |
| 리그 득점 사전값 | `config.{league,kbo,npb}_runs_per_game` — **손으로 적지 않는다** |
| 승률 상하한 | `model.P_CAP`(= `config.max_win_prob_mlb`) |

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `model_baseball/forward.py` | 새 파일. **동기 순수 함수** — DB·HTTP 를 부르지 않는다 |
| `prob.MODEL_W` · `p_code(..., p_model, model_w)` | 모델 축 1개 |
| `pick_ledger` + `p_model·model_src·model_w·model_gap_pp` | 4칸 |

🔴 **새로 수집하지 않는다.** 이미 `jg` 에 붙은 재료만 쓰고, 없으면 사전값으로
   대체하고 `missing` 에 적는다(0 과 구분).
🔴 **Gemini 프롬프트에 모델 숫자가 가지 않는다.** 계약이 4개 파일을 전수 grep 한다.

⚠️ 허가 범위는 3칸(`p_model·model_src·model_w`)인데 결정 G 의 완료 조건이
   `model_gap_pp` 기록을 요구한다 — 두 결정의 합집합인 **4칸**을 넣고 여기 적는다.

## ③ 리그·종목·경로 분기

분기를 만들지 않는다. 리그 득점 사전값만 종목으로 조회한다(표 하나).
야구 3종목에서 같은 경로를 쓰고, 축구는 이 함수를 부르지 않는다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **모델이 발송 숫자를 움직인다** | `MODEL_W = 0.0` + 항등 계약(`p_code` 불변) |
| 🔴 Gemini 가 모델 숫자를 본다 | prompts·verdict·triage·dbref 전수 grep 계약 |
| 새로 수집해 느려진다 | 소스에 `pool.fetch`·`httpx`·`await` 부재 계약 |
| 재료 없는 축이 조용히 사전값 | `missing` 목록 + 계약 |
| 리그 득점을 베껴 적는다 | 숫자 리터럴 부재 계약 |
| 모델 실패가 판정을 막는다 | try/except — 실패는 `p_model=None` 이고 판정은 그대로 |

⚠️ **아직 못 잰 것**: `p_model` 이 `p_market` 과 얼마나 갈리는가.
   오늘 슬레이트 실행 표로 처음 본다. AUC 비교는 4단계다.

## ⑤ 사본

- 모델 식을 여기 다시 쓰지 않는다 — `model.predict` 를 부른다.
- 리그 평균·승률 상한을 새로 적지 않는다.
