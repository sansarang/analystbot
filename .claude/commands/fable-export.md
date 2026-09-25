---
description: 한 슬레이트의 경기별 자료를 exports/ 에 json+md 로 낸다 (판정·의견 금지)
argument-hint: <종목> <날짜>
---

인자: `$ARGUMENTS` (종목 날짜 · 예 `mlb 2026-09-25`)

그 슬레이트의 **경기별 자료**를
`docs/fable/exports/<날짜>_<종목>_fable_request.{json,md}` 로 만든다.

🔴 **판정·의견 금지.** 확률·픽·"유리하다"를 쓰지 않는다. 자료만 옮긴다.
🔴 **못 구한 칸은 `null` + 사유.** 비슷한 값으로 채우지 않는다.
⚠️ md 는 **경기당 10행 이내**. 상세는 json 에 둔다.

## 칸

| 칸 | 원본 |
|---|---|
| 예고/확정 선발 | statsapi `probablePitcher` · `games.home_pitcher` |
| 확정 타순 + status | statsapi `hydrate=lineups` · boxscore `battingOrder` (미발표면 null) |
| 선발 최근 3등판 | statsapi `stats=gameLog` (날짜·이닝·자책·피안타·볼넷·투구수) |
| 불펜 3일 | `pitcher_appearances` (이닝·투구수·연투) |
| IL | **활성 로스터 기준**으로만. 등재일은 마지막 `placed` 트랜잭션 |
| 순위 산술 | statsapi standings 원값 (magic·elimination) — 외부 매체와 어긋나면 statsapi 가 정본 |
| 배당 open→now | `odds_snapshots` 첫/마지막 배치 · 디빅 · 이동 %p (스냅샷 1개면 null) |
| 구장 | `config/park_factors.yaml` — 없으면 null + D47 등록 |
| 날씨 | open-meteo (`access_basis: api_terms`) |
| selfcheck | `app.ops.selfcheck` 최근치 |

## 규율

- `export-builder` 에이전트로 돈다 — 판정 코드를 부르지 않는다.
- 라인이 바뀌었으면 **바뀐 사실**을 적는다. "올랐다/내렸다"를 추측하지 않고 스냅샷으로 센다.
- 사용자 메모와 statsapi 가 어긋나면 **둘 다 적고** statsapi 를 정본으로 표시한다.
