# wiring_0920 — 2026-09-20 실측 조각

🔴 **가짜 구조를 만들지 않는다.** 아래 파일은 전부 그날 운영에서 나온 출력·행을
잘라 온 것이다. 칸 이름·값 모양이 실제와 같아야 불변식이 진짜를 잡는다.

| 파일 | 무엇을 재현하나 | 출처 (그날 무엇을 돌렸나) |
|---|---|---|
| `abs_same_both_sides.json` | 결장 명단이 양 팀에 **똑같이** 복사됐다 | `soccer_export_0920` 위성 추출 (마치다@가시와 · AT마드리드@레알) |
| `abs_in_xi.json` | 결장자가 **선발 XI 에도** 있다 | 09-20 `scout:soccer:11338` 상자 (인천 무고사 · 대전 하창래) |
| `rest_hours_absurd.json` | 직전 경기가 **597~621시간 전**으로 나온다 | `soccer_export_0920` B 일정 블록 (포항) |
| `odds_move_exact_zero.json` | `open` 과 `now` 가 **같은 스냅샷 하나**다 | `odds_snapshots` 행 모양 (실측 컬럼 그대로) |
| `ingest_stale.json` | KBO 등판 적재가 **09-12 에 멈췄다** | `pitcher_appearances ⋈ games` 집계 (2026-09-21 실측) |
| `player_team_mismatch.json` | 타 팀 동명 선수가 결장 목록에 섞였다 | KBO 결장 추출 (롯데 목록에 박건우/NC) |

⚠️ 선수·팀 이름은 그날 값 그대로다. 숫자를 보기 좋게 고치지 않았다.
