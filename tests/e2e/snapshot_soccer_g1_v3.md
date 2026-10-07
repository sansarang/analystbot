🏟 **South Korea vs Uzbekistan** · Friendlies · 10-06 20:00 KST
🌐 **오픈월드** — 리그: Friendlies · 팀 열쇠 임시 발급
💵 $0.0000 · 호출 0회 · 출력 0 (추론 0)
⏳ **확정 XI 전** — 10-06 19:00 KST 이후 `/재분석`(지금 XI 는 none)

**1. 자료 한계 고백**
- 버린 것: `body_missing` 6건 · `conflict` 1건 · `duplicate` 11건 · `identity_mismatch` 63건 · `quote_not_found` 2건 · `replay_miss` 3건 · `sport_mismatch` 5건 · `stakes_vague` 1건 · `stale` 2건 · `team_tier_mismatch` 4건 · `type_off_catalog` 3건
- 문서 8건 · 변수 8개 · 시나리오 4개
- 못 받은 칸 — 오늘 XI 없음(상태 none — IR02·IR03 이 안 돈다) · 감독 미확보 · 순위표 없음
- 🔴 충돌: **채택 구조 사실**(공식 어댑터 6승 3무 0패 · 표본 9경기) / **버림 기사**(11승 4무 1패) — 공식 > 출처 수 > 등급

**2. 기준 XI**
- **South Korea** 포메이션 미상 [없음]
    ⬜ 선발 명단 없음

**2b. 결장**
- **South Korea**
    Jens Castrop(?) — 부상 · 복귀 Mid October 2026 · www.fotmob.com

**3. 폼**
- **South Korea** — 최근5 **L L W L D** · 득점 평균 0.8 · 보정 평균 **0.25** · 휴식 4일 · 무패 1 · 무승 2
    2026-10-02 홈 Venezuela 0-0
    2026-09-28 홈 Uruguay 1-4
    2026-09-24 홈 Ecuador 3-0
    2026-06-25 원정 South Africa 0-1
    2026-06-19 원정 Mexico 0-1
- **Uzbekistan** — 최근5 **L L L W W** · 득점 평균 1.8 · 보정 평균 **1.25** · 휴식 5일 · 무패 2 · 연속 득점 3
    2026-10-01 홈 Syria 4-1
    2026-09-24 홈 Iran 3-1
    2026-06-27 원정 DR Congo 1-3
    2026-06-23 원정 Portugal 0-5
    2026-06-18 홈 Colombia 1-3
- 맞대결 — 6승 3무 0패 · 표본 9경기 · 평균 3.0골 · 표본 무게 0.7

**3c. 기준 전력 (데이터)**
- Elo: South Korea **1722** · Uzbekistan **1653** · 차 +69 → 승 54% · 무 29% · 패 17%
    출처 eloratings.net(2026-10-06) · 순서형 로짓 `national_friendly`(표본 3842경기 · 적합 2026-10-06 · logloss 0.883157)
- 라인업 보정: 평소 대비 team:000129 +0.0% → 홈 승 **+0.0%p**(환산 R² 0.6094 · 표본 33)
    보정 후 승 54% · 무 29% · 패 17%

**3b. 경우의 수**
- ⬜ 경우의 수를 못 센다 — **순위표가 없다**(`unknown`) · 형식 `friendly`

**4. 뒤집는 변수**
- `R1` [def_absence] Kim Min-jae is likely to sit out the Uzbekistan match. — 승패 **away** · 득점 ↑ · hard · 출처 3곳 · 대상 `Kim Min-jae`
- `R2` [individual_title] Son Heung-min scored his 58th international goal, drawing level with Cha Bum-kun on the all-time men's scoring chart, and a single goal in either upcoming match would give him the record outright. — 승패 **home** · 득점 ↑ · soft · 출처 1곳 · 대상 `Son Heung-min`
- `S01-home` [recent_pattern] 최근 5경기 L L W L D · 득점 평균 0.8(보정 0.25) — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S01-away` [recent_pattern] 최근 5경기 L L L W W · 득점 평균 1.8(보정 1.25) — 승패 **away** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S03` [home_field] South Korea 홈 경기 — 홈 이점 **수치 없음**(대회 유형 `national_friendly` 의 표가 없다 · 다른 대회 숫자를 빌리지 않는다) — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `home_field` · [규칙 S03]
- `S04` [match_type] 친선 — 실험 라인업·교체 다수 가능 — 승패 **both** · 득점 - · soft · 출처 구조 사실 · 대상 `match_type` · [규칙 S04]
- `IR11-home` [fatigue] South Korea 일정 과부하 — 8일 안에 이번이 3번째 경기(직전 [4, 8]일 전) — 승패 **away** · 득점 - · soft · 출처 구조 사실 · 대상 `fatigue:IR11-home` · [규칙 IR11-home]

**(근거 불가)** — 맥락으로만 쓴다
- `S02` [h2h_pattern] 맞대결 9경기 6승 3무 0패 · 평균 3.0골 — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `h2h` · [규칙 S02]

**5. 팀별 가설 + 무너지는 조건**
- ⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가 0개다

**6. 시나리오**
- **A** (1-0) blowout · 무게 0.1 [보강] — 🔴 필수형(핸디 ±0.5 대응) — 그 줄의 반대는 상대가 **1점 차**로 이기는 것이다. 없으면 `+0.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음
- **B** (2-0) blowout · 무게 0.1 [보강] — 🔴 필수형(핸디 ±1.5 대응) — 그 줄의 반대는 상대가 **2점 차**로 이기는 것이다. 없으면 `+1.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음
- **C** (1-1 · 0-0) lock · 무게 1.4 [보강] — 🔴 축구 필수형(무승부) — 무승부 갈래가 **하나도 없었다** · 근거 R1, S02, S04 ← R1, S04
- **D** (2-1) conceding · 무게 0.1 [보강] — 🔴 필수형(우세팀 실점 동반) — 우세팀이 이기면서 한 점을 준다. ⚠️ 이 갈래가 없으면 `언더`·`클린시트` 가 **공짜로** 1.0 을 받는다(표: 우세팀_실점_동반형) ← 근거 없음

**7b. 확률 세 열**
- 시장 = 사용자 보드 · 업체 몫 8.6%

| | 기준(②반영) | 우리 | 시장 |
|---|---|---|---|
| South Korea 승 | 54% | 53% | 55% (1.66) |
| 무 | 29% | 29% | 24% (3.79) |
| Uzbekistan 승 | 17% | 18% | 20% (4.55) |
- Shin 방식(괄호 비교용): 홈 57% · 무 24% · 원정 19%
- ③ 이 움직인 양(로그 오즈 합 0.270): `R2`(individual_title→home) +0.105 · `S04`(match_type→draw) +0.060 · `IR11-home`(fatigue→away) +0.105
- 판정: **기준과 맞는다**
    홈승 — 기준 54% · 우리 53% · 시장 55%
    무 — 기준 29% · 우리 29% · 시장 24%
    원정승 — 기준 17% · 우리 18% · 시장 20%
    시장 열 — 사용자 보드(피드 없음 — 시장 없음 — odds_api_io — 키가 없다(`ODDS_API_IO_KEY` 비었다) · oddspapi — 키가 없다(`ODDSPAPI_KEY` 비었다) · the_odds_api — `Friendlies` 에 맞는 종목 열쇠가 표에 없다 — 이 피드는 대표팀 친선·CONCACAF·AFC 를 다루지 않는다(실측 2026-10-06))
- → 시장은 **South Korea** 쪽을 앞세운다(55%) — 🔴 **참고용**(판정에 안 쓴다)
- → Elo 차 +69점(1722 vs 1653) — 우리 정보에: **없음**
- → 라인업 전력 team:000129 +0.0% — 우리 정보에: **있음**
- → 홈 — 우리 정보에: **무게 낮음**
- → 🔴 **우리 판단 유지** — 근거: `R1`(def_absence·hard·무게 1.0) — 시장이 다르게 보는 까닭(Elo 차)은 우리 정보에 없지만, 위 근거가 **인용까지 검증된 사실**이다

**7. 보드 대입**
출처: **사용자 보드**

| 마켓 | A | B | C | D | 생존 | 상한 | 등급 |
|---|---|---|---|---|---|---|---|
| win home | ○ | ○ | ✗ | ○ | 0.1765 | 0.8 | 자료부족 |
| draw  | ✗ | ✗ | ○ | ✗ | 0.8235 | 0.8 | 자료부족 |
| win away | ✗ | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| total over 2.5 | ✗ | ✗ | ✗ | ○ | 0.0588 | 0.8 | 자료부족 |
| total under 2.5 | ○ | ○ | ○ | ✗ | 0.9412 | 0.8 | 자료부족 |
| handicap home -0.5 | ○ | ○ | ✗ | ○ | 0.1765 | 0.8 | 자료부족 |
| handicap away 0.5 | ✗ | ✗ | ○ | ✗ | 0.8235 | 0.8 | 자료부족 |

**8. 결론**
🔴 **등급 없음 — 자료 얇음**(시나리오 4개가 **전부 코드 보강**이다 — 분석이 그린 갈래가 0개다(가설 단계가 돌지 않았다))

🧭 **종합 논평 — 없다**(양상을 못 쟀다 — 시나리오가 없다)

**9. 방향 판정**
방향: **South Korea** (세 열 중 3열이 0.15 이상 앞세운다) — 기준 홈 54%/원정 17% · 우리 홈 53%/원정 18% · 시장 홈 55%/원정 20%

**10. 방아쇠**
- ① 확정 XI 에 **Kim Min-jae** 가 있으면 `R1` 가 사라져 → 다시 센다 · 10-06 14:00 KST (`absence` 세포가 깨는 T-360분)