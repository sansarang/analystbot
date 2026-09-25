---
description: 그 날 전 경기의 ①~⑬ 노드 출력을 exports/ 로 덤프하고 분포를 요약한다
argument-hint: <날짜>
---

인자: `$ARGUMENTS` (날짜 · 예 `2026-09-25`)

`analysis_runs` 에서 그 날 **전 경기**의 ①~⑬ 노드 출력을
`docs/fable/exports/pipeline_trace_<날짜>.json` 으로,
요약을 같은 이름 `.md` 로 낸다.

## json

경기마다: `{game_id, sport, league, home, away, starts_at, status, score,
run_id, trace, stopped_at, stop_reason, nodes: [...]}`.
노드마다: `{node, at_utc, elapsed_ms_derived, input_keys, output(원문),
hyp_side, pick_side, stopped_at, stop_reason}`.

🔴 **경기마다 최신 run 하나**만 쓴다 — 하루에 수십 run 이 쌓인다.
⚠️ `elapsed_ms` 는 **저장되는 칸이 아니다.** 연속 노드 `created_at_utc` 차이로
   유도하고 이름에 `_derived` 를 붙여 그 사실을 남긴다.

## md 요약

종목별로: 멈춤 노드 분포 · 게이트 분포 · ⑥ 상태(확인/반박/모름/미실행) ·
⑨ 등급 분포 · PICK 분포(승패/구조/보드) · stance 분포.

## 규율

- 🔴 **읽기 전용.** 흐름을 다시 돌리지 않는다 — 돌리면 그 날의 기록이 바뀐다.
- 종목이 비면 "0건"이 아니라 **왜 0인지** 적는다(슬레이트 미적재·추적 없음 등).
- 운영 DB 조회는 `railway ssh` 읽기 프로브로 한다(`railway run` 은 훅이 막는다).
