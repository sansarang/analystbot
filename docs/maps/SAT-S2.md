# SAT-S2 — 축구 위성을 전 리그로. 그리고 고급 검색(토르 DDG)을 붙인다.

사용자 지시 2026-09-12:
- "인공위성을 j리그 k리그 국한하지 말고 내 프로그램에 있는 전 리그를 추가해라"
- "고급 파싱이 아니라 **고급 서치 기능**이 있다 … 우선 그것부터 살펴봐라"

## 왜

SAT-S1 은 K리그1·J1 둘만 붙였다. `app/leagues.py` 에는 **7리그**가 있고,
나머지 다섯(EPL·라리가·세리에A·분데스리가·덴마크)은 `gather_soccer` 가
빈손을 돌려준다.

그리고 위성에는 **고급 검색**이 이미 있다 — `tor_search`(SAT-7, 토르 경유
DDG). MLB·NPB 는 `_tor_supplement` 로 그것을 쓰는데 **축구는 안 쓴다**.

### 실측 ① 한국 언론이 유럽 축구를 두껍게 다룬다

다음 뉴스검색, 리그별 5팀 × 상위 8건 = 40건 만점 (2026-09-12):

```
K리그1            39/40  (98%)
EPL               33/40  (83%)   아스널 7 · 리버풀 6 · 맨시티 8 · 브렌트포드 6 · 입스위치 6
라리가             33/40  (83%)   레알 6 · 바르사 5 · 세비야 6 · 헤타페 8 · 엘체 8
분데스리가          32/40  (80%)
세리에A            30/40  (75%)
덴마크 수페르리가     27/40  (68%)   ← 의외로 된다
J1 (야후, 팀명만)    8/8
```

→ **다음 하나로 여섯 리그가 된다.** J1 만 야후(일본어가 정확).

### 실측 ② 영어 이름으로는 안 된다 — 별칭표가 필수

같은 팀을 영어/한국어로 각각 다음에 넣었을 때 축구 기사 수:

```
Arsenal FC        0/8   vs  아스널       7/8
SSC Napoli        0/8   vs  나폴리       7/8
Brondby IF        0/8   vs  브뢴뷔       6/8
Brighton…Albion   0/8   vs  브라이턴     3/8
US Sassuolo       0/8   vs  사수올로     5/8
RC Celta de Vigo  1/8   vs  셀타 비고    8/8
```

→ 폴백으로는 못 쓴다. **DB 실측 90팀 전부 별칭을 적는다.**

### 실측 ③ 토르 DDG — 질은 높고 속도 제한이 심하다

```
ensure_tor() = True  (운영 컨테이너에서 실제로 뜬다)

Arsenal injury news team news 2026            → 6건
  · Arsenal 2026-2027 Injury List & Player Status (OGscore)
Chelsea predicted lineup injury suspension     → 6건
  · Chelsea XI vs Hull: Predicted lineup, confirmed team news, injury… (Standard)
  · Team News: Chelsea vs Hull City injury, suspension list, predicted XIs (Sportsmole)

그 다음부터 전부 403:
  간격 0초  0/3 · 간격 5초 0/3 · 간격 15초 **1/3**
```

→ **예상 라인업·부상·출전정지가 한 기사에 다 있다** — 뉴스검색보다 질이 높다.
  그러나 연속 질의는 막힌다. `tor_search` 머리말이 이미 적어 둔 대로
  **"순수 보강이다"** — 주력은 뉴스검색이고 토르는 경기당 2질의로 묶는다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "SOCCER_ALIAS\|_SOCCER_SOURCE\|gather_soccer" app/
app/collectors/satellite.py   정의 · _ADAPTERS["soccer"]
   → 읽는 곳은 _ADAPTERS 하나 (SAT-S1 에서 확인)
$ grep -rn "_tor_supplement" app/collectors/satellite.py
   gather_mlb · gather_npb  ← 이미 쓴다. 축구를 그 옆에 나란히 둔다
```

빌려 쓰는 원본 — 새로 만들지 않는다:
| 무엇 | 원본 |
|---|---|
| 리그 라벨 | `app/leagues.py` 의 `LEAGUES[...]["label"]` (계약이 전수 대조) |
| 토르 검색·한국어 거부 | `tor_search.search` · `is_tor_safe_query` |
| 토르 보강 배선 | `satellite._tor_supplement` (MLB·NPB 와 같은 함수) |
| 검색·파싱·본문·기사 모양 | SAT-S1 과 같음 |

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `SOCCER_ALIAS` 12→90팀 | 표 확장 | 아니다. `QUERY_ALIAS`(야구)와 분리 유지 |
| `_SOCCER_SOURCE` 2→7리그 | 표 확장 | 아니다 |
| `_SOCCER_TOR_TAIL` | 새 상수 | 아니다 |
| `gather_soccer` 가 `_tor_supplement` 호출 | 호출 추가 | 🔴 아래 |

🔴 **토르를 켜면 경기당 외부 호출이 는다.** 지금 `satellite_tor_enabled` 는
   **기본 켜짐**(2026-09-09 사용자 지시)이라, 배선하는 순간 축구 경기마다
   DDG 질의 2회가 나간다. 무료지만 **시간이 든다**(질의당 3~6초) — 슬레이트가
   크면 위성 잡이 길어진다.
   → 경기당 **2질의로 묶는다**(팀당 1). 계약이 그 수를 단언한다.

## ③ 리그·종목·경로 분기

```
K리그1                                  → 다음(한국어) · 토르 X(한국어 거부)
EPL·라리가·세리에A·분데스리가·덴마크        → 다음(한국어) + 토르(영어 보강)
J1 리그                                 → 야후(일본어) + 토르(영어 보강)
```

⚠️ K리그1 도 팀명이 영어로 저장돼 있어 토르 질의는 영어가 된다
   (`Ulsan Hyundai FC team news…`). `is_tor_safe_query` 를 통과하므로 나간다.
   **한국 기사를 DDG 로 찾는 셈이라 수율이 낮을 것**이다 — 이번엔 막지 않고
   로그로 관찰한다. 막으려면 실측이 먼저다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **리그를 빠뜨린다** | `leagues.LEAGUES` 전수와 대조하는 계약. 손으로 적은 목록을 쓰지 않는다 |
| 🔴 **별칭이 없어 그 팀만 재료 0** | DB 실측 90팀을 넣고, 없으면 영어 폴백 + "별칭 없음" 로그(SAT-S1) |
| 별칭에 영어를 그대로 적어 폴백과 구분이 안 된다 | `alias != en` 전수 단언 |
| 토르 질의가 늘어 전부 403 | 경기당 2질의로 묶고, 그 수를 계약이 단언 |
| 토르가 안 뜨는데 조용히 0 | `_tor_supplement` 가 이미 로그를 남긴다(SAT-7) |
| 한국어가 토르로 나가 한국 사이트가 깨진다 | `is_tor_safe_query` 가 거부. 계약이 꼬리의 영어성을 단언 |

⚠️ **아직 못 잰 것**: 토르 보강이 실제 슬레이트에서 몇 건을 더하는가.
   403 때문에 경기 수가 늘면 뒤쪽 경기는 빈손일 가능성이 크다.
   이번 합격 기준은 "전 리그가 긁힌다 · 토르가 배선됐다"까지다.

## ⑤ 이미 있는 사실을 다시 적는가

- 리그 목록을 손으로 적지 않는다 — 계약이 `leagues.LEAGUES` 와 대조한다.
- 토르 검색·한국어 거부 규칙을 다시 만들지 않는다 — `tor_search` 를 부른다.
- 보강 배선을 새로 쓰지 않는다 — MLB·NPB 가 쓰는 `_tor_supplement` 그대로.
- 검색어 상수(`_SOCCER_TERMS = ""`)는 SAT-S1 의 실측 그대로 유지한다.
