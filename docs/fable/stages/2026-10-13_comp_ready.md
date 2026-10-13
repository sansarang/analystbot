# 🔴🔴 §5-1 대회별 준비 점검

| 대회 | 유형 | 등록 | 재생(0-0 포함) | 홈 이점 판 | 레이팅 | 신원표 | 라인업 원천 | 결장 원천 | 검색 원천 표 |
|---|---|---|---|---|---|---|---|---|---|
| `league:ELC` | domestic_league | ✅ id 48 | 🔴 **재생 0** — 미산출 | ✅ 홈 몫 1.431 | ✅ football_data·적합 `league:ELC` | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | 🔴 **검색 원천 표 없다**(§6-1) |
| `league:UCL` | club_continental | ✅ id 42 | 🔴 **재생 0** — 미산출 | 🔴 **홈 이점 판 없다** | 🔴 적합 `없다` — 레이팅 미산출 | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | 🔴 **검색 원천 표 없다**(§6-1) |
| `league:ACLE` | club_continental | ✅ id 525 | 🔴 **재생 0** — 미산출 | 🔴 **홈 이점 판 없다** | 🔴 적합 `없다` — 레이팅 미산출 | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | 🔴 **검색 원천 표 없다**(§6-1) |
| `league:ACL2` | club_continental | ✅ id 9469 | 🔴 **재생 0** — 미산출 | 🔴 **홈 이점 판 없다** | 🔴 적합 `없다` — 레이팅 미산출 | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | 🔴 **검색 원천 표 없다**(§6-1) |
| `national_friendly` | national_friendly | ⬜ id 없다(친선은 id 로 안 가린다) | 🔴 **재생 0** — 미산출 | ✅ 홈 몫 1.618 | ✅ eloratings·적합 `national_friendly` | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | 🔴 **검색 원천 표 없다**(§6-1) |
| `league:J1` | domestic_league | ✅ id 223 | ✅ 290경기 | ✅ 홈 몫 1.332 | ✅ fotmob·적합 `league:J1` | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | ✅ S 2 · A 5 · B 1 |
| `league:KL1` | domestic_league | ✅ id 9080 | ✅ 414경기 | ✅ 홈 몫 1.270 | ✅ fotmob·적합 `league:KL1` | ⬜ 리그별로 안 갈린다(팀 별칭 29개 · 공통 표) | ⬜ 공통 규칙만(금지 호스트 3개 · 리그별 목록 없다) | 🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 `leagues` 가 비었다 | ✅ S 1 · A 5 · B 1 |

🔴 **빠진 칸은 그 칸 미산출**이다 — 손값으로 메우지 않는다. 대회 백필이 끝나기 전에는 카드가 *"대회 백필 미완 — 참고용"* 을 적고 등급 상한은 **조건부**다(§5-6).

- `league:UCL` 단계 `League phase` → 중립 아니오 · 중립 아님(단계 `League phase` · 표의 중립 목록에 없다)
- `league:UCL` 단계 `Final` → 중립 **예** · 중립 경기(`final` · 표 `config/competitions.yaml`)
- `league:ACLE` 단계 `League phase` → 중립 아니오 · 중립 아님(단계 `League phase` · 표의 중립 목록에 없다)
- `league:ACLE` 단계 `Final` → 중립 **예** · 중립 경기(`final` · 표 `config/competitions.yaml`)
- `league:ACL2` 단계 `League phase` → 중립 아니오 · 중립 아님(단계 `League phase` · 표의 중립 목록에 없다)
- `league:ACL2` 단계 `Final` → 중립 아니오 · 중립 아님(단계 `Final` · 표의 중립 목록에 없다)
