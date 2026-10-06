🏟 **South Korea vs Uzbekistan** · Friendlies · 10-06 20:00 KST
🌐 **오픈월드** — 리그: Friendlies · 팀 열쇠 임시 발급
💵 $0.0000 · 호출 0회 · 출력 0 (추론 0)

**1. 자료 한계 고백**
- 버린 것: `body_missing` 6건 · `conflict` 1건 · `duplicate` 5건 · `identity_mismatch` 63건 · `post_match` 2건 · `sport_mismatch` 5건 · `stale` 2건 · `type_off_catalog` 3건
- 문서 8건 · 변수 10개 · 시나리오 5개
- 못 받은 칸 — 확정 XI 아직 없음(예상만) · 감독 미확보 · 순위표 없음 · 선수 포지션 표 비었음(결장 유형은 다수결로 간다)
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

**3b. 경우의 수**
- ⬜ 경우의 수를 못 센다 — 순위표·잔여 경기가 없다(형식 `friendly`)

**4. 뒤집는 변수**
- `R1` [fatigue] Kim Min-jae is dealing with fatigue from his recent matches and is unlikely to play in the Uzbekistan friendly. — 승패 **away** · 득점 - · hard · 출처 3곳 · 대상 `Kim Min-jae`
- `R2` [team_stats] South Korea's men's football team claimed a fourth straight gold. — 승패 **home** · 득점 - · soft · 출처 1곳 · 대상 `gold`
- `R3` [regression] South Korea's gold count dropped sharply to 49 at the 2018 Jakarta-Palembang Games, slipping to third behind China and Japan, and the downward trend continued through the 2022 Hangzhou Games and into the current edition. — 승패 **both** · 득점 - · soft · 출처 1곳 · 대상 `gold count`
- `R4` [individual_title] Son Heung-min scored 58 international goals, drawing him level with Cha Bum-kun at the top of the all-time men's scoring chart, and a single goal in either upcoming match would give Son the record outright. — 승패 **home** · 득점 ↑ · soft · 출처 1곳 · 대상 `Son Heung-min`
- `S01-home` [recent_pattern] 최근 5경기 L L W L D · 득점 평균 0.8(보정 0.25) — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S01-away` [recent_pattern] 최근 5경기 L L L W W · 득점 평균 1.8(보정 1.25) — 승패 **away** · 득점 - · soft · 출처 구조 사실 · 대상 `recent` · [규칙 S01]
- `S03` [home_field] South Korea 홈 경기 — 홈 이점 **기본값** +16.8%p(MLS 실측(사용자 지시 2026-10-02 · app/classify.py:_dir_home_field 주석)) — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `home_field` · [규칙 S03]
- `S04` [match_type] 친선 — 실험 라인업·교체 다수 가능 — 승패 **both** · 득점 - · soft · 출처 구조 사실 · 대상 `match_type` · [규칙 S04]
- `IR02-home` [def_absence] South Korea 직전 선발 Bum-Keun Song, Young-Woo Seol, Han-Beom Lee 가 오늘 명단에 없다 — 승패 **away** · 득점 - · soft · 출처 구조 사실 · 대상 `def_absence:IR02-home` · [규칙 IR02-home]

**(근거 불가)** — 맥락으로만 쓴다
- `S02` [h2h_pattern] 맞대결 9경기 6승 3무 0패 · 평균 3.0골 — 승패 **home** · 득점 - · soft · 출처 구조 사실 · 대상 `h2h` · [규칙 S02]

**5. 팀별 가설 + 무너지는 조건**
- **South Korea**
  - 이긴다면: 손흥민이 차범근과 어깨를 나란히 한 58골 기록을 넘어설 수 있는 두 경기 중 하나라, 득점 동기가 최상이다. (R4)
  - 이긴다면: 남자 대표팀이 4연속 금메달을 따낸 전력이 있어 국제 무대에서 경기 주도권을 잡는 힘이 있다. (R2)
  - 이긴다면: 홈에서 열리는 경기라 홈 이점이 붙는다. (S03)
  - 이긴다면: 친선 경기라 실험 라인업이 가능하지만, 상대보다 두터운 자원으로 교체 카드를 활용할 수 있다. (S04)
  - 무너지는 조건: 김민재가 최근 경기 피로로 우즈베키스탄전에 나서기 어려워 중앙 수비가 약해진다. (R1)
  - 무너지는 조건: 직전 선발이었던 송범근·설영우·이한범이 오늘 명단에 없어 수비 조직이 재편된다. (IR02-home)
  - 무너지는 조건: 최근 5경기 L L W L D, 득점 평균 0.8(보정 0.25)로 득점 생산이 바닥에 가깝다. (S01-home)
  - 무너지는 조건: 친선 경기 특성상 실험 라인업과 잦은 교체로 조직력이 흐트러질 수 있다. (S04)
- **Uzbekistan**
  - 이긴다면: 최근 5경기 L L L W W, 득점 평균 1.8(보정 1.25)에 3경기 연속 득점으로 공격 흐름이 살아 있다. (S01-away)
  - 이긴다면: 상대 핵심 수비수 김민재가 피로로 결장할 가능성이 커 공격 부담이 줄어든다. (R1)
  - 이긴다면: 상대 직전 선발 3명이 명단에서 빠져 상대 수비 라인이 새로 짜인다. (IR02-home)
  - 이긴다면: 친선 경기라 상대가 실험 라인업을 돌리면 경기 흐름을 가져올 틈이 생긴다. (S04)
  - 무너지는 조건: 손흥민의 기록 도전 동기가 살아 있는 경기라 실점 위험이 커진다. (R4)
  - 무너지는 조건: 원정 경기라 상대의 홈 이점을 그대로 안고 시작한다. (S03)
  - 무너지는 조건: 상대는 국제 대회 4연속 금메달 전력이 있는 팀이라 경기 주도권을 내줄 수 있다. (R2)
  - 무너지는 조건: 최근 5경기에서 3연패가 섞여 있어 기복이 크다. (S01-away)

**6. 시나리오**
- **A** (3-1 · 4-1) home_win · 무게 1.8 — 홈팀이 홈 이점과 대회 전력으로 전반부터 상대 진영에 머물며, 손흥민의 기록 동기가 걸린 슈팅이 반복되어 다득점으로 이어진다. 상대는 한 골을 만회하지만 흐름을 되돌리지 못한다. ← R4, R2, S03
- **B** (2-1 · 3-2) home_win · 무게 2.1 — 홈팀이 득점은 만들어내지만 직전 선발 3명이 빠진 수비 재편과 김민재 공백으로 실점을 허용한다. 상대의 3경기 연속 득점 흐름이 살아 있어 한두 골을 따라붙는다. ← R4, S01-away, IR02-home
- **C** (1-1 · 0-1) open · 무게 2.1 — 홈팀의 중앙 수비 핵이 빠지고 친선 특성상 실험 라인업이 돌아가면서 최근 낮은 득점 흐름(평균 0.8)이 그대로 이어진다. 상대는 수비적으로 버티며 한 골 승부로 끌고 간다. ← R1, S04, S01-home
- **D** (0-2 · 1-2) away_win · 무게 1.4 — 홈팀의 최근 5경기 0.8득점이라는 낮은 수치가 반등 없이 이어지고, 3연패 뒤 2연승으로 올라온 상대의 득점 흐름이 원정에서도 유지된다. 홈 수비 라인 재편이 그 흐름을 받쳐준다. ← S01-home, S01-away, IR02-home
- **E** (2-0 · 1-0) home_win · 무게 1.5 — 친선 경기라 양 팀 모두 교체를 많이 쓰지만, 홈 이점과 두터운 자원을 가진 홈팀이 후반 교체 싸움에서 우위를 점한다. 상대는 실험 라인업 운영 속에 득점을 만들지 못한다. ← S03, S04, R2

**7. 보드 대입**
| 마켓 | A | B | C | D | E | 생존 | 상한 | 등급 |
|---|---|---|---|---|---|---|---|---|
| win home | ○ | ○ | ✗ | ✗ | ○ | 0.6067 | 0.8 | 없음 |
| draw  | ✗ | ✗ | △ | ✗ | ✗ | 0.118 | 0.8 | 없음 |
| win away | ✗ | ✗ | △ | ○ | ✗ | 0.2753 | 0.8 | 없음 |
| unbeaten home | ○ | ○ | △ | ✗ | ○ | 0.7247 | 0.8 | 없음 |
| unbeaten away | ✗ | ✗ | ○ | ○ | ✗ | 0.3933 | 0.8 | 없음 |
| handicap South Korea -0.5 | ○ | ○ | ✗ | ✗ | ○ | 0.6067 | 0.8 | 없음 |
| handicap Uzbekistan 0.5 | ✗ | ✗ | ○ | ○ | ✗ | 0.3933 | 0.8 | 없음 |
| handicap South Korea -1.5 | ○ | ✗ | ✗ | ✗ | △ | 0.2865 | 0.8 | 없음 |
| handicap Uzbekistan 1.5 | ✗ | ○ | ○ | ○ | △ | 0.7135 | 0.8 | 없음 |
| btts yes | ○ | ○ | △ | △ | ✗ | 0.6348 | 0.8 | 없음 |
| btts no | ✗ | ✗ | △ | △ | ○ | 0.3652 | 0.8 | 없음 |
| total over 1.5 | ○ | ○ | △ | ○ | △ | 0.7978 | 0.8 | 없음 |
| total under 1.5 | ✗ | ✗ | △ | ✗ | △ | 0.2022 | 0.8 | 없음 |
| total over 2.5 | ○ | ○ | ✗ | △ | ✗ | 0.5169 | 0.8 | 없음 |
| total under 2.5 | ✗ | ✗ | ○ | △ | ○ | 0.4831 | 0.8 | 없음 |
| total over 3.5 | ○ | △ | ✗ | ✗ | ✗ | 0.3202 | 0.8 | 없음 |
| total under 3.5 | ✗ | △ | ○ | ○ | ○ | 0.6798 | 0.8 | 없음 |

**8. 결론**
등급 없음 — 문턱을 넘은 줄이 없다(가장 높은 줄 생존 0.7978)

**9. 방향 판정**
방향: South Korea — 홈승 0.61 · 원정승 0.28 · 무 0.12

**10. 방아쇠**
- ① 확정 XI 에 **def_absence:IR02-home** 가 있으면 `IR02-home` 가 사라져 → 다시 센다 · 10-06 14:00 KST (`absence` 세포가 깨는 T-360분)