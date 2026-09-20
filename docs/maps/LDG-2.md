# LDG-2 영향 지도 — 사람 판정 행에 저장 전용 기록이 안 붙었다

## 0. 재현 (실측 원문 · 2026-09-20 운영)

```
원장 1,393행 중  odds_at_verdict 298 · odds_closing 107 · clv 97
오늘 58경기 중 원장 행 있음 7   (전부 ledger_add 로 넣은 페이블 판정)

── 원장 행 생성 추이
     2026-09-20  행 7     market_flow 0     odds_open 0
     2026-09-19  행 4     market_flow 0     odds_open 0
     2026-09-18  행 4     market_flow 1     odds_open 1
     2026-09-17  행 55    market_flow 32    odds_open 32
```

`tools/ledger_add.py` 가 `_INSERT` 만 하고 `_record_side_effects` 를 부르지
않는다. `grade_pending` 이 `odds_closing` 은 채우지만 `clv` 는
`odds_at_verdict` 가 있어야 계산되므로(`_CLV_SAVE["closing"]` 의 CASE),
**사람 판정 행의 CLV 는 영원히 NULL** 이다.

⚠️ 09-17 이후 원장 행이 급감한 것은 별개다 — `PIPELINE_V14=true` 로 구경로
판정이 멈췄고 v1.4 는 **섀도라 설계상 원장에 쓰지 않는다**(`bridge` 는
`pick_ledger` 를 읽기만 한다). 그것은 이 수정의 대상이 아니다(**4-10-b**).

## 1. 머리말과 충돌하지 않는가

`ledger_add` 머리말: *"채점·CLV 는 여기서 채우지 않는다 — 결과 적재 잡의
몫이다"*.

🔴 그 문장이 말하는 것은 **채점**(`hit`·`graded_at`)과 **마감 배당**이다.
`odds_at_verdict` 는 채점이 아니라 **판정 시각의 배당**이고, 그 시각을 아는
것은 이 도구뿐이다 — 결과 잡은 나중에 복원할 수 없다. `record_clv` 가
`now=` 로 시점을 받게 이미 만들어져 있다는 것이 그 증거다.

## 2. 영향 지도 5문

**① 어디를 고치나.** `tools/ledger_add.py` 한 파일. 삽입 뒤
`pick_ledger._record_side_effects(conn, game_id, clv_at="verdict")` 를 부른다.
**새 함수를 만들지 않는다** — 구경로 판정이 쓰는 바로 그 함수다.

**② 무엇이 채워지나.**
`odds_at_verdict`(→ `clv`) · `market_flow`/`flow_class`/`odds_open`(이동 분류)
· 북 간 괴리 · `p_prior`/`gate_label`/`gap_pp`(사전값).
🔴 **판정은 안 건드린다** — `predicted_side`·`p_code` 를 쓰는 경로가 없다.

**③ 승패가 아닌 행은 어떻게 되나.**
`record_clv` 가 고른 쪽을 모르면(`predicted_side` None) **아무것도 쓰지
않는다**. 총점·팀토탈 행이 그렇고, 반대쪽 배당으로 채우면 CLV 가 통째로
무의미해지므로 그게 맞다. 로그만 남는다.

**④ 무엇이 깨질 수 있나.**
`ledger_add` 가 느려진다(스냅샷 조회 3~4회). 도구는 수동 실행이라 문제가
아니다. 🔴 진짜 위험은 **되돌릴 수 없는 쓰기**다 — 다만 대상 칸이 전부
현재 NULL 이고, `record_*` 들은 값이 없으면 아무것도 쓰지 않는다(0 으로
채우지 않는다). 실패해도 각각 감싸여 있어 행 삽입은 이미 끝나 있다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/test_ldg2_ledger_side_effects.py` 3건 — 저장 전용 기록을 부르는가,
판정 시각으로 찍는가, 승패가 아니면 `predicted_side` 가 None 인가.

## 3. 하지 않은 것 (등록만)

- **4-10-b** v1.4 흐름이 원장에 쓰지 않는다(섀도라 설계대로). 봇 판정을
  원장에 남길지는 **경로 전환 결정**이고 별건이다.
- **4-14-b** `source_score` 는 대조 자료를 남기는 자리가 없어 미구축이다.
