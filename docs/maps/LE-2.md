# LE-2 — 누설 방지·시간순 검증 틀 (영향 지도 5문)

지시문 `learning_engine_0922` LE-2. **엔진보다 먼저** 온다.

> "§1 학습·검증은 시간순(walk-forward)만. 무작위 분할·미래 정보 누설(종가·결과·
>  경기 후 기사)이 학습 입력에 들어가면 **그 결과는 무효다.** 누설 방지는
>  계약 테스트로 잠근다."

🔴 **이 단계가 없으면 LE-4 의 숫자는 못 믿는다.** 그래서 모델보다 먼저 만든다.

## ① 파일

| 파일 | 무엇 | 신규 |
|---|---|---|
| `app/learning/split.py` | walk-forward 분할기 + **누설 검사** | 신규 |
| `app/learning/baselines.py` | 기준선 3개 — 시장·50%·Elo | 신규 |
| `app/learning/calibrate.py` | isotonic(기본)·platt | 신규 |
| `tools/baseline_report.py` | 리그별 기준선 Brier 표 | 신규 |
| `tests/learning/test_le2_split.py` | 누설·분할 계약 | 신규 |
| `config/learning.yaml` | `train_weeks`·`valid_weeks` 는 이미 있다 | 수정 0 |

🔴 **모델을 만들지 않는다.** LE-2 는 틀이다. `sklearn` 은 보정에만 쓴다.

## ② 테이블 / 잡

**없다.** 읽기만: `history_matches`·`history_prices`(LE-1b) · `decision_ledger`.
새 잡 없음(수동 도구).

## ③ 깨질 테스트

예상 없음(추가만). ⚠️ `test_random_split_forbidden` 이 `app/` 전체에서
`train_test_split`·`shuffle=True` 를 찾으므로, 기존 코드에 그런 호출이 있으면
**지금 드러난다.** 그건 결함이므로 드러나는 것이 맞다 — 나오면 보고한다.

## ④ 롤백

파일 5개 삭제. DB·기존 코드 변경 0.

## ⑤ 완료 조건 (지시문 원문)

> "역사 자료로 **기준선 3개의 리그별 Brier 표**."

1. 기준선 (i) 시장 디빅값 · (ii) 50% 고정 · (iii) 팀 Elo — 리그별 Brier·로그손실
2. 누설 계약 통과: `test_no_future_feature` · `test_random_split_forbidden`
3. walk-forward 분할이 **시간을 넘지 않는다**는 계약
4. 전체 스위트 통과 · 발송 0건

## 🔴 설계 결정 넷 — 근거를 미리 적는다

**① 누설을 "검사"가 아니라 "구조"로 막는다.**
   피처를 `(value, available_at)` 쌍으로만 받는다. `available_at` 이 없는 피처는
   **만들 수 없다**(생성자가 거부). 검사에 의존하면 검사를 안 부르는 경로가 생긴다.

**② 분할기 밖으로 나가는 길을 막는다.**
   `test_random_split_forbidden` 이 `app/learning/` 에서 `train_test_split` ·
   `shuffle=True` · `random_state` 호출을 금지한다. 지시문 원문의 요구다.

**③ 기준선 (iii) Elo 는 `soccer_elo` 를 재사용한다.**
   그 모듈이 이미 같은 CSV 로 Elo 를 피팅하고 walk-forward 백테스트까지 한다.
   여기서 Elo 를 다시 짜지 않는다(사본 금지). 아티팩트가 없으면 **"미가용"**
   으로 적는다 — 0 으로 채우지 않는다.

**④ 보정은 검증 창을 둘로 쪼갠다.**
   지시문: "보정은 검증 창의 **앞부분에서만** 맞추고 뒤에서 잰다."
   앞에서 맞추고 앞에서 재면 그건 학습 성적이다.

## ⚠️ 지금 없는 것

역사 적재가 **진행 중**이다(2026-09-22 15:30 기준 경기 7,228/19,289 · 가격
393,884행). 완료 조건 ①의 표는 적재가 끝난 뒤에 낸다 — **먼저 낸 표는
표본이 잘린 표다.**
