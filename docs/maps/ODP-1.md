# ODP-1 — oddsportal 에서 축구 1X2 배당을 긁는다

Phase 1 완료 조건 1-3 이 "없음"이라 별도 승인을 요청했고, 사용자가 **"나"**
(oddsportal 확장)를 골랐다. 그런데 **실측이 선택지를 바꿨고**, 사용자가 다시
**"A"**(축구 1X2 먼저)를 골랐다.

## 왜 (실측 2026-09-13)

리그 목록 페이지를 실제로 받아 `bettingTypeId` 를 전수로 세었다:
```
KBO     bettingTypeId {3: 24}  scopeId {1}   handicapValue 0건
EPL     bettingTypeId {1: 90}  scopeId {2}   handicapValue 0건
라리가   bettingTypeId {1: 87}  scopeId {2}   handicapValue 0건
```
🔴 **핸디캡·언더오버는 리그 페이지에 없다.** 경기별 상세 페이지에만 있고,
   그 링크조차 HTML 에 안 실린다(Next.js 청크만). "2줄 추가"로 끝나지 않는다.

🟢 대신 **축구 1X2 가 이미 그 페이지에 있었다.** 그런데 우리 DB 는
   최근 14일 축구 69경기 중 **배당 보유 0건**이다. 원인은 단순했다 —
   `LEAGUE_URL` 에 kbo·npb 만 있어 **축구를 아예 안 긁었다.**

   이것이 막고 있던 것: Phase 1 ①(시장 디빅)이 축구에서 서지 않고,
   Phase 3 괴리 게이트도 `p_market` 이 없으면 전부 "보드 고정"으로 빠진다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "oddsportal" app/ | grep -v collectors/oddsportal.py
app/registry.py:42        OddsProvider("oddsportal", ("kbo","npb"), ...)
app/collectors/odds_free.py:164  fetch_league (collect_asia 안)
app/scheduler.py:1257     collect_asia(pool, redis, sport, today_kst())
```
`parse_odds`·`to_rows` 를 읽는 곳은 `fetch_league` 하나다(+테스트).

빌려 쓰는 원본 — 새로 만들지 않는다:
| 무엇 | 원본 |
|---|---|
| 리그 목록 | `app/leagues.py` `LEAGUES` (계약이 키 전수 대조) |
| HTML 언이스케이프·요청·간격 | 기존 `_unescape`·`fetch_league` 구조 |
| 적재 | `odds_free.store_rows` |
| 디빅 | `pipeline._market_probs` — 3-way 를 이미 처리한다 |

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `SOCCER_URL` (7리그) · `BETTING_TYPE_1X2` | 새 표·상수 |
| `norm` · `team_key` · `SOCCER_ALIAS` | 새 순수 함수·표 |
| `parse_odds(html, three_way=False)` | **기본값이 종전 동작**이다 |
| `to_rows` 에 `Draw` | 무승부가 **있을 때만** 만든다 |
| `fetch_soccer_league` · `odds_free.collect_soccer` | 새 함수 |
| `registry` oddsportal sports += soccer | 표 한 줄 |

🔴 **야구 경로는 한 글자도 안 바뀐다.** `parse_odds` 기본값이 2-way 이고,
   `to_rows` 는 `draw` 키가 없으면 무승부 행을 만들지 않는다. 계약이 둘 다 단언.
🔴 **무승부 칸을 야구에 만들면 디빅이 3-way 로 잘못 돌아** 승/패 확률이
   부풀고 전 경기 +EV 착시가 난다(`_market_probs` docstring 의 실사고 이력).

## ③ 리그·종목·경로 분기

분기가 아니라 **표 조회**다. 야구는 `LEAGUE_URL`, 축구는 `SOCCER_URL`.
축구는 종목 하나에 리그가 7개라 리그 단위로 요청한다(리그당 1요청·10분 간격).

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **다른 팀을 같은 팀으로 본다** ← 가장 큰 위험 | 퍼지 금지. 결정적 정규화 + 명시 별칭. 실측에서 실제로 충돌했던 짝(맨시티/맨유·레알/AtM·AC밀란/인테르·전북/울산)을 계약이 단언 |
| 정규화가 과해 구분 토큰을 지운다 | `united`·`city`·`real`·`atletico` 를 **지우지 않는다**. 지웠더니 위 충돌이 났다(실측) |
| 별칭이 순환한다 | 별칭 값이 다시 별칭 키가 아님을 단언 |
| 🔴 야구에 무승부가 생긴다 | `to_rows` 2-way 계약 + `parse_odds` 기본값 계약 |
| 리그를 빠뜨린다 | `leagues.LEAGUES` 전수 대조(손으로 적은 목록 금지) |
| 상대 서버를 두들긴다 | 기존 `MIN_INTERVAL_SEC` 10분·리그당 1요청 그대로 |
| 팀명이 안 붙어 조용히 0 | 미매칭을 로그·반환값에 남긴다(기존 `unmatched` 규약) |

⚠️ **아직 못 잰 것**: 실제 매칭률. 정규화만으로 66/122 였고 별칭 뒤 얼마가
   붙는지는 **배포 후 첫 사이클**에서 본다. J1 20팀은 우리 DB 에 경기가
   2팀분뿐이라 별칭 대상이 없다 — **추측해서 만들지 않는다.**
⚠️ `Gimcheon Sangmu` ↔ `Sangju Sangmu FC` 는 연고 이전(상주→김천)으로 같은
   팀이라고 **판단**한 것이다. 측정이 아니다. 첫 사이클에서 날짜·상대로 대조한다.

## ⑤ 사본

리그 목록·디빅·적재를 다시 만들지 않는다. 검색 간격·UA·타임아웃도 기존 상수 그대로.
