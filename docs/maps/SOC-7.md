# SOC-7 — 본문 추출이 페이지 앞부분을 잘라 **메뉴만** 담았다

사용자 지적 2026-09-12: "선발 라인업 부상자 명단 배선해라... **인공위성이
그거를 가지고 있는데** 너가 똑같은 실수를 하고 있다."

## 왜

맞는 지적이다. 위성 캐시(첼시@헐시티, 24건)를 직접 열어 보니 **있었다**:

```
23. [DDG(토르)] Hull City Today Lineup — Football-Lineups
      "Predicted XI ... Phillips, Targett, Coyle, Herrington, Mendy,
       Crooks, Gourna-Douath, Dahl, Thomas, Cho, Vaz"        ← 선발 11명
24. [DDG(토르)] Hull City Injury Update and Team News Today
      "currently have 4 players sidelined"
14. [DDG(토르)] Chelsea XI vs Hull: Predicted lineup, confirmed team news, injury latest
```

그런데 판정은 매 경기 "확정 선발 라인업을 확인하지 못했다"고 썼고 선별은
**24건 중 3건만 채택**했다. 원인은 본문이다 — `_fetch_article_body` 가
`_strip_html(html)[:1200]`, 즉 **페이지 앞 1200자를 그냥 자른다.** 요즘
사이트는 그 자리가 내비게이션·광고·쿠키 배너다.

실측 2026-09-12 23:00 (캐시의 실제 라인업 기사 5개 URL, 같은 HTML 에 세 방식):

```
현재(앞 1200자)   0/5   전부 메뉴·광고·동의 배너
<p> 모음          3/5   SI 는 <p> 0개 · Standard 는 전부 쿠키 배너
최장 블록         4/5   Standard 에서 "Pedro Neto ... will celebrate his new
                        contract with a start at left wing-back" 을 건졌다
둘 중 나은 쪽     5/5
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "_fetch_article_body" app/
app/collectors/satellite.py        정의 · gather_mlb/kbo/npb · _tor_supplement
app/collectors/satellite_soccer.py gather_soccer
app/collectors/kbo_roster.py       (없음)
```

→ **야구도 같은 함수를 쓴다.** 이 수정은 야구 본문 품질도 함께 바꾼다.
   그래서 반대 위험(“종전에 오던 것이 안 온다”)을 계약으로 막는다.

빌려 쓰는 원본:
| 무엇 | 원본 |
|---|---|
| 태그 제거 | `satellite._strip_html` |
| 길이 상한 1200 | 딥서치 `_fetch_body` 와 같은 값 — 바꾸지 않는다 |

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `satellite.extract_body` | 새 순수 함수(시험 가능) | 아니다 |
| `_fetch_article_body` | 추출을 그 함수에 위임 | HTTP·실패 처리는 그대로 |

⚠️ 검색어·상한·모델·프롬프트를 건드리지 않는다. **추출만** 바꾼다.

## ③ 리그·종목·경로 분기

분기 없음. 순수 함수 하나이고 모든 종목이 같은 것을 쓴다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **새 규칙이 못 찾아 빈손을 준다** ← 가장 큰 반대 위험 | 후보가 없으면 **종전대로** 통째로 긁는다. 계약이 단언 |
| 🔴 야구 본문이 나빠진다 | 같은 계약이 야구 경로도 덮는다(같은 함수). 스크립트·스타일 제거 유지 |
| 쿠키 배너를 본문으로 고른다 | 동의 배너 문구를 가진 후보를 뺀다. 계약이 Standard 실측 사례로 단언 |
| 함수만 만들고 배선을 안 한다 | `_fetch_article_body` 소스에 호출이 있는지 단언 |
| 길이 상한이 흔들린다 | 1200 을 계약으로 고정 |

⚠️ **아직 못 잰 것**: 고친 뒤 선별 채택률이 3/24 에서 얼마로 가는가,
   판정 서술에서 "라인업을 확인하지 못했다"가 사라지는가. 재예측에서 잰다.

## ⑤ 이미 있는 사실을 다시 적는가

- 태그 제거를 새로 쓰지 않는다 — `_strip_html`.
- 상한 1200 을 새로 정하지 않는다 — 딥서치와 같은 값 그대로.
