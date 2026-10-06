🏟 **South Korea vs Uzbekistan** · Friendlies · 10-06 20:00 KST
🌐 **오픈월드** — 리그: Friendlies · 팀 열쇠 임시 발급
💵 $0.0000 · 호출 0회 · 출력 0 (추론 0)

**1. 자료 한계 고백**
- 버린 것: `body_missing` 11건 · `conflict` 1건 · `duplicate` 6건 · `identity_mismatch` 65건 · `replay_miss` 2건 · `sport_mismatch` 5건 · `stale` 2건 · `type_off_catalog` 3건
- 문서 7건 · 변수 9개 · 시나리오 4개
- ⚠️ 순위표가 없다(친선·네이션스리그는 애초에 없다)

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

**3b. 경우의 수**
- ⬜ 경우의 수를 못 센다 — 순위표·잔여 경기가 없다(형식 `friendly`)

**4. 뒤집는 변수**
- `R1` [fatigue] Kim Min-jae is dealing with fatigue from his recent matches and is unlikely to play in the Uzbekistan friendly. — 승패 **away** · 득점 - · hard · 출처 3곳 · 대상 `Kim Min-jae`
- `R2` [individual_title] South Korea will play an October friendly against Uzbekistan. — 승패 **home** · 득점 ↑ · soft · 출처 1곳 · 대상 `Uzbekistan`
- `S01-home` [recent_pattern] 최근 5경기 L L W L D · 득점 평균 0.8(보정 0.25) — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S01-away` [recent_pattern] 최근 5경기 L L L W W · 득점 평균 1.8(보정 1.25) — 승패 **away** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S04` [match_type] 친선 — 실험 라인업·교체 다수 가능 — 승패 **both** · 득점 - · soft · 출처 구조 사실 · 대상 `match_type` · [규칙 S04]
- `IR04-home` [regression] South Korea 득점 평균 0.8 → 보정 0.25(이상치 한 경기를 뺐다) — 승패 **both** · 득점 - · soft · 출처 구조 사실 · 대상 `regression:IR04-home` · [규칙 IR04-home]
- `IR04-away` [regression] Uzbekistan 득점 평균 1.8 → 보정 1.25(이상치 한 경기를 뺐다) — 승패 **both** · 득점 - · soft · 출처 구조 사실 · 대상 `regression:IR04-away` · [규칙 IR04-away]

**(근거 불가)** — 맥락으로만 쓴다
- `S02` [h2h_pattern] 맞대결 9경기 6승 3무 0패 · 평균 3.0골 — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `h2h` · [규칙 S02]
- `S03` [home_field] South Korea 홈 경기 — 홈 이점 — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `home_field` · [규칙 S03]

**5. 팀별 가설 + 무너지는 조건**
- ⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가 0개다

**6. 시나리오**
- **A** (1-0) blowout · 무게 0.1 [보강] — 🔴 필수형(핸디 ±0.5 대응) — 그 줄의 반대는 상대가 **1점 차**로 이기는 것이다. 없으면 `+0.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음
- **B** (2-0) blowout · 무게 0.1 [보강] — 🔴 필수형(핸디 ±1.5 대응) — 그 줄의 반대는 상대가 **2점 차**로 이기는 것이다. 없으면 `+1.5` 가 죽을 자리가 없어 1.0 을 받는다 ← 근거 없음
- **C** (0-0 · 0-1) lock · 무게 0.1 [보강] — 🔴 축구 필수형(저득점) — IR04 발동 ← 근거 없음
- **D** (2-1) conceding · 무게 0.1 [보강] — 🔴 필수형(우세팀 실점 동반) — 우세팀이 이기면서 한 점을 준다. ⚠️ 이 갈래가 없으면 `언더`·`클린시트` 가 **공짜로** 1.0 을 받는다(표: 우세팀_실점_동반형) ← 근거 없음

**7. 보드 대입**
| 마켓 | A | B | C | D | 생존 | 상한 | 등급 |
|---|---|---|---|---|---|---|---|
| win home | ○ | ○ | ✗ | ○ | 0.75 | 0.8 | 자료부족 |
| draw  | ✗ | ✗ | △ | ✗ | 0.125 | 0.8 | 자료부족 |
| win away | ✗ | ✗ | △ | ✗ | 0.125 | 0.8 | 자료부족 |
| unbeaten home | ○ | ○ | △ | ○ | 0.875 | 0.8 | 자료부족 |
| unbeaten away | ✗ | ✗ | ○ | ✗ | 0.25 | 0.8 | 자료부족 |
| handicap South Korea -0.5 | ○ | ○ | ✗ | ○ | 0.75 | 0.8 | 자료부족 |
| handicap Uzbekistan 0.5 | ✗ | ✗ | ○ | ✗ | 0.25 | 0.8 | 자료부족 |
| handicap South Korea -1.5 | ✗ | ○ | ✗ | ✗ | 0.25 | 0.8 | 자료부족 |
| handicap Uzbekistan 1.5 | ○ | ✗ | ○ | ○ | 0.75 | 0.8 | 자료부족 |
| btts yes | ✗ | ✗ | ✗ | ○ | 0.25 | 0.8 | 자료부족 |
| btts no | ○ | ○ | ○ | ✗ | 0.75 | 0.8 | 자료부족 |
| total over 1.5 | ✗ | ○ | ✗ | ○ | 0.5 | 0.8 | 자료부족 |
| total under 1.5 | ○ | ✗ | ○ | ✗ | 0.5 | 0.8 | 자료부족 |
| total over 2.5 | ✗ | ✗ | ✗ | ○ | 0.25 | 0.8 | 자료부족 |
| total under 2.5 | ○ | ○ | ○ | ✗ | 0.75 | 0.8 | 자료부족 |
| total over 3.5 | ✗ | ✗ | ✗ | ✗ | 0.0 | 0.8 | 자료부족 |
| total under 3.5 | ○ | ○ | ○ | ○ | 1.0 | 0.8 | 자료부족 |

**8. 결론**
🔴 **등급 없음 — 자료 얇음**(시나리오 4개가 **전부 코드 보강**이다 — 분석이 그린 갈래가 0개다(가설 단계가 돌지 않았다))

**9. 방향 판정**
방향: South Korea — 홈승 0.75 · 원정승 0.12 · 무 0.12

**10. 방아쇠**
- ⬜ 방아쇠가 없다 — 조건 표에 걸린 변수 유형이 없었다