# RPT-1 — 원장에서 **표를 뽑을 방법이 없다**

## 왜

`report.py` 의 다섯 함수는 전부 **순수 함수**다 — 행 목록을 받아 표를
돌려준다. 그게 이 파일의 규약이고(테스트가 DB 없이 돈다), 그래서 **행을
넣어주는 쪽이 따로 필요하다.** 그 쪽이 없다.

실측 ①: `report` 를 import 하는 **운영·도구 파일 0건**(tests 뿐). U13 부터
그랬고, 오늘 PA-28 로 `by_variable` 을 더해도 **볼 방법이 없다.**

딥서치(→ `docs/FORKS.md` F-5): "대시보드 피로는 실재하고 BI 를 실제로 쓰는
직원은 **약 30%** 뿐 — 대시보드는 **누가 열어주기를 기다린다**"(LogRocket).
열어줄 사람이 없는 표는 없는 표다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
tools/report_vars.py      ← 새 도구 (얇은 어댑터. **계산은 안 한다**)
app/engine/report.py      ← 계산 본체. **안 건드린다**
app/db.get_pool/close_pool ← 기존 규약 (tools/calibration.py 와 같다)
app/engine/gate.BOARD      ← 보드 라벨의 **원본**. 손으로 안 적는다
pick_ledger 칼럼           ← 읽기만: adj_pp · adj_evidence · predicted_side ·
                             clv · clv_line_shift · hit · p_home · p_code ·
                             p_market · hypothesis · confirmed · analyze_failed ·
                             watch_state · gate_label · gate_vs_llm ·
                             main_axis · flow_class · cancel_virtual_clv
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **읽기 전용이다.** INSERT·UPDATE 를 하지 않는다. 계약이 잰다.
- 🔴 **도구가 계산을 다시 하지 않는다.** `tools/calibration.py` 의 규약을
  그대로 따른다 — "도구와 운영이 다른 계산을 하면 **표를 믿을 수 없다**".
  평균·브라이어·판정은 전부 `report.py` 가 한다. 계약이 잰다.
- 🔴 **`p` 는 고른 쪽 확률이다.** `p_home` 은 홈 기준이고 `hit` 은 **우리 픽**
  기준이다(원장 주석: "▲를 준 쪽이 이겼으면 hit"). 원정을 골랐으면
  `1 − p_home` 을 넣어야 한다 — 안 돌리면 브라이어가 통째로 뒤집힌다.
  PA-28 의 부호 문제와 **같은 종류**다.
- 🔴 **보드 라벨을 손으로 안 적는다.** `gate.BOARD` 가 원본이다.
- 🔴 **`source_score` 는 안 부른다.** 그 함수는 `{source, claimed, actual}`
  모양을 받는데 원장에 그 대조 자료가 없다. 없는 것을 억지로 채우지 않고
  **왜 비었는지 찍는다.**
- 🔴 **스케줄러에 걸지 않는다.** 체크포인트 발송(B안)은 이 도구가 쓸 만한
  표를 내는 것을 본 뒤다 — 지시받은 것은 A 뿐이다.
- ⚠️ 로컬에서 `python tools/report_vars.py` 를 돌리면 **로컬 DB** 를 본다.
  운영 원장은 `railway ssh` 로 봐야 한다(`railway run` 은 안 닿는다).

## ③ 되돌리기

파일 하나 삭제. 기존 코드를 안 건드렸으므로 그것으로 끝난다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 실제 원장으로 한 번 돌려 표를 찍는다
(⑨ 첫 사이클).

## ⑤ 계약

12건 — report 함수를 부른다 · 계산을 직접 안 한다 · 쓰기 없음 · `p` 가 픽
기준(홈/원정) · 보드 라벨 사본 금지 · source_score 를 안 부르고 사유를 찍음 ·
행 변환이 빈 원장에서도 안 터짐 · 값 없는 칸이 0 으로 안 바뀜 · --json ·
--days/--sport 필터 · 스케줄러에 안 걸림.
