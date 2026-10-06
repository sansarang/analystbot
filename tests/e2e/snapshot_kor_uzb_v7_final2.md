🏟 **South Korea vs Uzbekistan** · Friendlies · 10-06 20:00 KST
🌐 **오픈월드** — 리그: Friendlies · 팀 열쇠 임시 발급
💵 $0.0000 · 호출 0회 · 출력 0 (추론 0)

**1. 자료 한계 고백**
- 버린 것: `body_missing` 11건 · `conflict` 1건 · `duplicate` 7건 · `identity_mismatch` 65건 · `replay_miss` 2건 · `sport_mismatch` 5건 · `stakes_vague` 1건 · `stale` 2건 · `type_off_catalog` 3건
- 문서 7건 · 변수 6개 · 시나리오 3개
- ⚠️ **확정 XI 를 못 잡았다** — 상한이 그만큼 내려간다
- ⚠️ 순위표가 없다(친선·네이션스리그는 애초에 없다)

**2. 기준 XI**
- ⬜ 없다 — 어느 쪽 XI 도 못 받았다(사유는 블록 1)

**3. 폼**
- **South Korea** — 최근5 **L L W L D** · 득점 평균 0.8 · 보정 평균 **0.25** · 휴식 4일 · 무패 1 · 무승 2
    2026-10-02 홈 Venezuela 0-0 / 2026-09-28 홈 Uruguay 1-4 / 2026-09-24 홈 Ecuador 3-0 / 2026-06-25 원정 South Africa 0-1 / 2026-06-19 원정 Mexico 0-1
- **Uzbekistan** — 최근5 **L L L W W** · 득점 평균 1.8 · 보정 평균 **1.25** · 휴식 5일 · 무패 2 · 연속 득점 3
    2026-10-01 홈 Syria 4-1 / 2026-09-24 홈 Iran 3-1 / 2026-06-27 원정 DR Congo 1-3 / 2026-06-23 원정 Portugal 0-5 / 2026-06-18 홈 Colombia 1-3
- 맞대결 — 6승 3무 0패 · 표본 9경기 · 평균 3.0골 · 표본 무게 0.7

**4. 뒤집는 변수**
- `R1` [absence] Kim Min-jae is dealing with fatigue from his recent matches and is unlikely to play in the Uzbekistan friendly. — 승패 **away** · 대상 `Kim Min-jae` · hard(1.0) · 출처 A-home-D1, A-home-D2, A-away-D1
- `R2` [individual_title] Son Heung-min은 58골로 차범근과 함께 남자 국제 득점 공동 1위에 올라 있으며, 다가오는 두 경기 중 한 골만 넣으면 단독 기록을 세운다. — 승패 **home** · 득점↑ · 대상 `Son Heung-min` · soft(0.7) · 출처 C-away-D1
- `R4` [regression] 한국은 9월 두 경기에서 1-1의 결과를 냈으며, 에콰도르에 3-0으로 이겼으나 우루과이에 1-4로 크게 졌다. — 승패 **both** · 대상 `1-4` · soft(0.7) · 출처 C-away-D1
- `S02` [h2h_pattern] 맞대결 9경기 6승 3무 0패 · 평균 3.0골 — 승패 **home** · 대상 `h2h` · soft(0.7) · 출처  · S02 · ⚠️ **근거로는 못 쓴다**(맥락 전용)
- `S03` [home_field] South Korea 홈 경기 — 홈 이점 — 승패 **home** · 대상 `home_field` · soft(0.4) · 출처  · S03 · ⚠️ **근거로는 못 쓴다**(맥락 전용)
- `S04` [match_type] 친선 — 실험 라인업·교체 다수 가능 — 승패 **both** · 대상 `match_type` · soft(0.4) · 출처  · S04

**5. 팀별 가설 + 무너지는 조건**
- ⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가 0개다

**6. 시나리오**
- **A** (1-0) [blowout · code · strength 0.1] 🔴 필수형(핸디 ±0.5 대응) — 그 줄의 반대는 상대가 **1점 차**로 이기는 것이다. 없으면 `+0.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음(코드 보강)
- **B** (2-0) [blowout · code · strength 0.1] 🔴 필수형(핸디 ±1.5 대응) — 그 줄의 반대는 상대가 **2점 차**로 이기는 것이다. 없으면 `+1.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음(코드 보강)
- **C** (2-1) [conceding · code · strength 0.1] 🔴 필수형(우세팀 실점 동반) — 우세팀이 이기면서 한 점을 준다. ⚠️ 이 갈래가 없으면 `언더`·`클린시트` 가 **공짜로** 1.0 을 받는다(표: 우세팀_실점_동반형) ← 근거 없음(코드 보강)

**7. 보드 대입**
| 마켓 | A | B | C | 생존 | 상한 | 등급 |
|---|---|---|---|---|---|---|
| win home | ○ | ○ | ○ | 1.0 | 0.8 | 자료부족 |
| draw  | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| win away | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| unbeaten home | ○ | ○ | ○ | 1.0 | 0.8 | 자료부족 |
| unbeaten away | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| handicap South Korea -0.5 | ○ | ○ | ○ | 1.0 | 0.8 | 자료부족 |
| handicap Uzbekistan 0.5 | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| handicap South Korea -1.5 | ✗ | ○ | ✗ | 0.3333 | 0.8 | 자료부족 |
| handicap Uzbekistan 1.5 | ○ | ✗ | ○ | 0.6667 | 0.8 | 자료부족 |
| btts yes | ✗ | ✗ | ○ | 0.3333 | 0.8 | 자료부족 |
| btts no | ○ | ○ | ✗ | 0.6667 | 0.8 | 자료부족 |
| total over 1.5 | ✗ | ○ | ○ | 0.6667 | 0.8 | 자료부족 |
| total under 1.5 | ○ | ✗ | ✗ | 0.3333 | 0.8 | 자료부족 |
| total over 2.5 | ✗ | ✗ | ○ | 0.3333 | 0.8 | 자료부족 |
| total under 2.5 | ○ | ○ | ✗ | 0.6667 | 0.8 | 자료부족 |
| total over 3.5 | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| total under 3.5 | ○ | ○ | ○ | 1.0 | 0.8 | 자료부족 |

**8. 결론**
🔴 **등급 없음 — 자료 얇음**(시나리오 3개가 **전부 코드 보강**이다 — 분석이 그린 갈래가 0개다(가설 단계가 돌지 않았다))

**9. 방향 판정**
방향: South Korea — 홈승 1.00 · 원정승 0.00 · 무 0.00

**10. 방아쇠**
- ① player:{star} in XI → `R1`(absence · Kim Min-jae is dealing with fatigue from) 가 바뀌면 다시 센다 · 10-06 14:00 KST (`absence` 세포가 깨는 T-360분)