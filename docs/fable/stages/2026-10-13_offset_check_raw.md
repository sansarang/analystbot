# 🔴🔴 1번 오프셋 검증 — 외부 순위 상관 · K 비교 · 치우침

- 외부 순위 — 위키 `UEFA_coefficient` 협회 순위 56개 · 위키 `AFC_club_competitions_ranking` 협회 순위 80개

## UEFA — 판 `2026-10-13`(맞대결 210경기)

| 리그 | 나라 | 우리 오프셋 | 맞대결 | 외부 순위 |
|---|---|---|---|---|
| `league:PL` | England | **+81.4** | 88 | 1위 |
| `league:FL1` | France | **+9.8** | 60 | 5위 |
| `league:SA` | Italy | **+6.6** | 66 | 2위 |
| `league:PD` | Spain | **-10.2** | 72 | 3위 |
| `league:BL1` | Germany | **-24.4** | 67 | 4위 |
| `league:DED` | Netherlands | **-28.7** | 30 | 8위 |
| `league:PPL` | Portugal | **-34.5** | 37 | 6위 |

🔴 **스피어만 ρ = 0.750**(짝 7개) — ✅ **0.6 이상**(적합 방식을 의심하지 않는다)
🔴 판을 적었다 — `data/league_offsets/UEFA/verify.yaml`

### 원인 점검 (2) — 국내 리그 Elo 척도(평균 1500 고정)

| 리그 | 팀 | Elo 폭(표준편차) | 최고−최저 |
|---|---|---|---|
| `league:BL1` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:DED` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:FL1` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:PD` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:PL` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:PPL` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |
| `league:SA` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |

### K 비교(수축 벌) — 원인 점검 (1)

| K | 적합 손실 | 쓴 경기 | 보기: 가장 센 리그 · 가장 약한 리그 |
|---|---|---|---|
| 5 | 0.6554 | 210 | `league:PL` +118.0 · `league:PPL` -63.3 |
| 10 | 0.6628 | 210 | `league:PL` +100.4 · `league:PPL` -47.6 |
| 20 | 0.6702 | 210 | `league:PL` +81.4 · `league:PPL` -34.5 |

#### `league:PD`(Spain) — 상대 리그별

| 상대 리그 | 승 | 무 | 패 | 득 | 실 |
|---|---|---|---|---|---|
| `league:PL`(England) | 8 | 2 | 14 | 36 | 42 |
| `league:BL1`(Germany) | 9 | 0 | 7 | 37 | 34 |
| `league:FL1`(France) | 6 | 1 | 4 | 21 | 14 |
| `league:SA`(Italy) | 5 | 2 | 3 | 21 | 21 |
| `league:PPL`(Portugal) | 5 | 0 | 3 | 17 | 16 |
| `league:DED`(Netherlands) | 2 | 0 | 1 | 9 | 5 |

#### `league:BL1`(Germany) — 상대 리그별

| 상대 리그 | 승 | 무 | 패 | 득 | 실 |
|---|---|---|---|---|---|
| `league:SA`(Italy) | 7 | 3 | 8 | 28 | 30 |
| `league:PD`(Spain) | 7 | 0 | 9 | 34 | 37 |
| `league:PL`(England) | 1 | 2 | 11 | 11 | 33 |
| `league:FL1`(France) | 3 | 3 | 3 | 14 | 22 |
| `league:PPL`(Portugal) | 5 | 1 | 0 | 11 | 1 |
| `league:DED`(Netherlands) | 2 | 1 | 1 | 6 | 6 |

## AFC — 판 `2026-10-13`(맞대결 315경기)

| 리그 | 나라 | 우리 오프셋 | 맞대결 | 외부 순위 |
|---|---|---|---|---|
| `league:J1` | Japan | **+72.8** | 82 | 2위 |
| `league:fotmob536` | Saudi Arabia | **+23.6** | 48 | 1위 |
| `league:fotmob535` | Qatar | **+22.4** | 69 | 6위 |
| `league:fotmob113` | Australia | **+9.8** | 22 | 8위 |
| `league:KL1` | South Korea | **+3.7** | 64 | 3위 |
| `league:fotmob461` | Singapore | **-3.5** | 27 | 15위 |
| `league:fotmob538` | United Arab Emirates | **-5.2** | 56 | 4위 |
| `league:fotmob523` | Iran | **-6.0** | 37 | 5위 |
| `league:fotmob540` | Uzbekistan | **-10.9** | 23 | 9위 |
| `league:fotmob524` | Iraq | **-11.8** | 23 | 13위 |
| `league:fotmob8984` | Thailand | **-16.7** | 60 | 7위 |
| `league:fotmob8985` | Malaysia | **-20.0** | 28 | 10위 |
| `league:fotmob120` | China | **-38.5** | 52 | 11위 |
| `league:fotmob529` | Kuwait | ⬜ 미산출 | 4 | 20위 |
| `league:fotmob8983` | Indonesia | ⬜ 미산출 | 14 | 19위 |
| `league:fotmob9088` | Vietnam | ⬜ 미산출 | 10 | 14위 |
| `league:fotmob9478` | India | ⬜ 미산출 | 4 | 25위 |
| `league:fotmob9495` | Australia | ⬜ 미산출 | 7 | 8위 |

🔴 **스피어만 ρ = 0.654**(짝 13개) — ✅ **0.6 이상**(적합 방식을 의심하지 않는다)
🔴 판을 적었다 — `data/league_offsets/AFC/verify.yaml`

### 원인 점검 (2) — 국내 리그 Elo 척도(평균 1500 고정)

| 리그 | 팀 | Elo 폭(표준편차) | 최고−최저 |
|---|---|---|---|
| `league:J1` | 20 | 53 | 188 |
| `league:KL1` | 14 | 46 | 179 |
| `league:fotmob113` | 12 | 38 | 135 |
| `league:fotmob120` | 18 | 67 | 207 |
| `league:fotmob461` | 8 | 89 | 242 |
| `league:fotmob523` | 19 | 45 | 162 |
| `league:fotmob524` | 23 | 77 | 325 |
| `league:fotmob529` | 12 | 58 | 217 |
| `league:fotmob535` | 13 | 47 | 168 |
| `league:fotmob536` | 21 | 90 | 309 |
| `league:fotmob538` | 16 | 71 | 264 |
| `league:fotmob540` | 16 | 61 | 248 |
| `league:fotmob8983` | 21 | 72 | 283 |
| `league:fotmob8984` | 19 | 58 | 200 |
| `league:fotmob8985` | 14 | 85 | 306 |
| `league:fotmob9088` | 16 | 54 | 204 |
| `league:fotmob9478` | 15 | 39 | 136 |
| `league:fotmob9495` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |

### K 비교(수축 벌) — 원인 점검 (1)

| K | 적합 손실 | 쓴 경기 | 보기: 가장 센 리그 · 가장 약한 리그 |
|---|---|---|---|
| 5 | 0.6376 | 315 | `league:J1` +118.3 · `league:fotmob120` -70.2 |
| 10 | 0.6467 | 315 | `league:J1` +95.4 · `league:fotmob120` -53.2 |
| 20 | 0.6546 | 315 | `league:J1` +72.8 · `league:fotmob120` -38.5 |

#### `league:fotmob536`(Saudi Arabia) — 상대 리그별

| 상대 리그 | 승 | 무 | 패 | 득 | 실 |
|---|---|---|---|---|---|
| `league:fotmob535`(Qatar) | 9 | 4 | 2 | 35 | 21 |
| `league:fotmob538`(United Arab Emirates) | 9 | 1 | 2 | 26 | 13 |
| `league:fotmob523`(Iran) | 4 | 4 | 0 | 13 | 3 |
| `league:fotmob524`(Iraq) | 5 | 1 | 1 | 19 | 4 |
| `league:fotmob540`(Uzbekistan) | 3 | 1 | 1 | 11 | 5 |
| `league:J1`(Japan) | 1 | 0 | 2 | 6 | 5 |
| `league:fotmob9478`(India) | 2 | 0 | 0 | 6 | 1 |
| `league:KL1`(South Korea) | 1 | 0 | 0 | 7 | 0 |

#### `league:J1`(Japan) — 상대 리그별

| 상대 리그 | 승 | 무 | 패 | 득 | 실 |
|---|---|---|---|---|---|
| `league:KL1`(South Korea) | 16 | 4 | 8 | 45 | 30 |
| `league:fotmob120`(China) | 13 | 3 | 3 | 38 | 15 |
| `league:fotmob8984`(Thailand) | 8 | 2 | 1 | 21 | 4 |
| `league:fotmob113`(Australia) | 6 | 0 | 1 | 17 | 5 |
| `league:fotmob8985`(Malaysia) | 2 | 1 | 2 | 4 | 5 |
| `league:fotmob535`(Qatar) | 1 | 1 | 3 | 7 | 10 |
| `league:fotmob9088`(Vietnam) | 4 | 0 | 0 | 11 | 1 |
| `league:fotmob9495`(Australia) | 3 | 0 | 0 | 9 | 2 |
| `league:fotmob536`(Saudi Arabia) | 2 | 0 | 1 | 5 | 6 |
| `league:fotmob461`(Singapore) | 0 | 1 | 1 | 1 | 4 |
| `league:fotmob538`(United Arab Emirates) | 1 | 0 | 0 | 1 | 0 |
