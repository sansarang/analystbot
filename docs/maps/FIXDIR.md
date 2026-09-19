# FIXDIR 영향 지도 — 증거에 방향을 싣는다 (FIX-1~6)

## 1. 무엇이 틀렸나 (실측 원문)

```
WSH@STL  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 6.0이닝 1자책
NYY@ARI  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 6.7이닝 6자책
MIA@SD   starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 4.0이닝 5자책
MIN@LAA  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 4.0이닝 4자책
```

⑦은 `sides` 의 **항목 수**만 본다(`n07_adjust.py:32-39`). 내용을 안 읽는다.
`strength` 는 문자열에 숫자가 있으면 1.0 이다(`:21·58`).
증거 row 에 구조화된 편차가 **없다**(운영 g10938 원문: `sides={"away":2}`).

## 2. 어디를 고치나

| 파일 | 무엇 |
|---|---|
| `app/flow/direction.py` (신규) | 변수별 방향 판정 — 순수 함수, DB·LLM 0 |
| `config/rules.yaml` `flow.direction.*` | 문턱 (숫자는 여기에만) |
| `app/flow/nodes/n05_evidence.py` | row 에 `direction` 을 싣는다 |
| `app/flow/nodes/n07_adjust.py` | 부호·강도를 `direction` 에서 |
| `app/flow/nodes/n09_conf.py` | `struct_grade` 추가 |
| `app/flow/nodes/n11_value.py` | 가설 지정 마켓 1개 · 시장 동의 · edge 상한 · λ 절사 · 철회 |
| `app/flow/nodes/n13_send.py` | 등급 조건 |
| `app/engine/scoring.py` | `LambdaResult.clipped` 승격 |
| `app/models/lambda_model.py` | 투구수 피처·결측 처리 |

## 3. 영향 지도 5문

**① 문턱 숫자를 어디에 두나.**
`config/rules.yaml` 의 `flow.direction.*` 한 곳이다. 코드에 적지 않는다.
🔴 그 값들은 **미검증 사전값**이고 채점 30건 뒤 데이터로만 고친다 — yaml 주석에
그렇게 적는다. `league_era` 는 기존 settings 를 쓰고 새 상수를 만들지 않는다.

**② "모르면 −1" 을 버리면 무엇이 달라지나.**
종전에는 방향 미상이 곧 불리였다. 그러면 자료가 없을수록 확률이 내려간다 —
모름을 근거로 쓴 것이다. 이제 0 이고 조정 행 자체를 만들지 않는다.
⚠️ 상쇄 0 과 미상 0 을 `basis` 로 구분한다.

**③ ⑪의 max() 를 버리면 후보가 줄지 않나.**
줄어야 한다. 지금은 총점·팀토탈·핸디 전체에서 최대 edge 를 고른다 — 오늘
40여 후보 중 핸디 edge −46%p 가 best 로 뽑힌 경기도 있었다.
가설이 지정한 마켓만 본다. 지정이 없으면 보드다.

**④ λ 절사를 후보 0 으로 만들면.**
절사된 λ 는 모델이 범위 밖을 말했다는 뜻이고 그 위의 파생 확률은 믿을 수 없다.
지금은 `trace` 문자열로만 남아 읽는 쪽이 못 본다 — `LambdaResult.clipped` 로
**승격**한다(없던 것을 만드는 게 아니다).

**⑤ 무엇이 조용히 0이 되나.**
방향 미상이 늘면 조정이 0 이 되고 ⑨ A 가 안 난다. 그러면 ⑬이 안 보낸다.
그게 맞는 동작이다 — "자료가 없어서"와 "상쇄되어서"를 `basis` 로 구분해
원장에서 셀 수 있게 한다.

## 4. 안 하는 것

- λ 계수·① 사전값·③ 게이트 문턱·판정 입력 목록을 건드리지 않는다(동결).
- 발송 스위치를 켜지 않는다. LLM 호출을 늘리지 않는다.
- `lambda_model` 을 재학습하지 않는다.
- `lineup_out` 의 "직전 5경기 출장" 은 `lineup_history` 에 MLB 행이 0건이라
  만들 수 없다 → `lineup_diff` 가 최근 10경기로 이미 정한 **평소 주전**의
  오늘 제외 수(ABS-1 의 `lineup_excluded`)를 쓴다.
