# DS-0 — 실측과 소스 지도 (편집 금지 · 측정만)

지시문 `deepsearch_parallel_0921` DS-0 · 실행 2026-09-21 12:45~12:57 KST ·
운영 컨테이너 · **코드 변경 0**

선행 조건 확인:

| 선행 | 상태 | 증빙 |
|---|---|---|
| W1 selfcheck | **완료** | `5fbdf5c` 배포 · 첫 실행 위반 49건 · /health 노출 |
| W2 식별자 | **완료** | `3bc759a`·`bcf363b` 배포 · `abs_same_both_sides` 0 · `player_team_mismatch` 0 |

→ DS-0 뒤로 진행 가능하다.

---

## ① 현재 위성의 직렬 구간 (파일:행)

```
app/collectors/satellite.py
  run_satellite()
    :  for r in rows:                     ← ① **경기가 순차다**
         └ await gate_of(pool, ...)       ← ② 게이트 계산도 경기마다 순차
    :  for r in rows:  (수집 루프)
         └ await gather(jg, ...)          ← ③ 경기당 수집 전체가 순차

  gather_npb()  (:509)
    :  for side in ("home","away"):       ← ④ **팀별 순차**
         └ await _yahoo_fetch(...)
         └ for it in parse_yahoo_news(...)[:N]:
              └ await _fetch_article_body(u)   ← ⑤ **기사 본문 순차**
    :  out += await _tor_supplement(...)  ← ⑥ 토르 보강(질의 간격 18~26초 대기)

  _search()  (:646)
    :  for team, q in queries:            ← ⑦ **쿼리 순차**
         └ await rss_hits(q, ...)
         └ for h in picked: await _fetch_article_body(u)   ← ⑧ 순차
```

**병렬 구간은 0 이다.** `asyncio.gather` 는 이 경로 어디에도 없다.

## ② 실측 — NPB 3경기 직렬 1회 (12:45 KST)

```
[직렬 실행] 총 159.7s · 경기 3
game        초   HTTP  LLM  기사
14394     41.4     13    0    7
14392     58.4     15    0    9
14393     59.9     14    0    8

도메인별 요청: news.yahoo.co.jp 30 · check.torproject.org 6 · lite.duckduckgo.com 6
LLM 호출: **0** (URL 묶음 캐시 적중 — "캐시 적중, 묻지 않는다")
```

- 경기당 **평균 53.2초 · HTTP 14회**
- 🔴 **토르 보강이 시간을 먹는다**: `질의 간격 18~26s 대기` 가 4회, 그러고도
  `DDG 403 — 보강 없음`. 순수 대기가 80초 이상이고 **성과는 0건**이다.
- 30경기로 늘리면 **약 27분**이다. DS-1 의 슬레이트 마감 600초(10분)를
  **현재 구조로는 지킬 수 없다.**

## ③ 소스 지도 — `config/source_map.yaml` (실측값)

행마다 status·bytes·ms 를 실제 호출로 채웠다. 요약:

| 리그 | 사실 | robots | status | 쓸 수 있나 |
|---|---|---|---|---|
| NPB | 예고선발 | 404(판단불가) | **200** | ✅ 09-21 10명 전건 일치 |
| NPB | 등록말소 | 404(판단불가) | **200** | ✅ 11:06 공시 재현 가능 |
| NPB | 확정타순 | 404(판단불가) | 200 | ⚠️ **정적 HTML 에 값 없음**(js) |
| NPB | 중지공지(구단) | 404(판단불가) | **200** | ✅ 단 **날짜 검증 필수** |
| NPB | 순위 | — | 404 | ❌ 경로 재탐색 |
| **KBO** | 엔트리·일정·순위·타순 | **거부** | 미시도 | ❌ **robots 거부 4경로** |
| MLB | 예고선발+타순 | 404(판단불가) | **200** | ✅ `probablePitcher,lineups` |
| MLB | 등록말소 | 404(판단불가) | **200** | ✅ transactions |
| 축구 | 경기·XI·결장 | **허용** | **200** | ✅ 이미 배선됨 |
| J1 | 순위·일정 | **허용** | **200** | ✅ 1.1MB · 勝点 단서 |
| K1 | 순위 | 404(판단불가) | 404 | ❌ 경로 재탐색 |
| EPL | 팀뉴스 | 403 | 403 | ❌ 불가 |

### 🔴 가장 큰 발견 둘

**(a) KBO 공식·네이버가 전부 robots 거부다.**
`koreabaseball.com` 4경로와 `sports.news.naver.com` 이 모두 거부다. 우회하지
않는다(지시문 규율). 즉 **KBO 엔트리·확정 타순·순위를 공식에서 받을 길이
지금은 없다.** 대안은 구단 공식·보도뿐이고, 그것도 확인이 필요하다.

**(b) 스포츠나비 경기 id 가 우리 `ext_id` 와 그대로 맞는다.**
```
우리  games.ext_id = 'yahoo:2021039443'
그쪽  https://baseball.yahoo.co.jp/npb/game/2021039443/top
```
이름 대조가 필요 없다 — 매칭 비용 0. 다만 **타순 값이 정적 HTML 에 없다.**

## ④ JS 페이지 뒤의 JSON — 찾지 못했다 (DS-0 ③)

`baseball.yahoo.co.jp/npb/game/{id}/top` 실측:

```
__NEXT_DATA__            없음
window.__PRELOADED_STATE__ 없음
<script type="application/json">  없음
본문 내 yahoo API URL    0건

XHR 후보 6개 직접 호출:
  /score                       200 · 단서 0
  /text                        200 · 단서 0
  /start                       404
  /member                      404
  /api/npb/game/{id}           404
  sp.baseball.findfriends.jp   200 · 단서 0
```

→ **헤드리스가 필요할 수 있다**(DS-4 3단). 지시문대로 헤드리스는 기본 경로가
아니므로, DS-2 착수 전에 다른 정적 소스(구단 공식 스타멘 페이지 등)를 한 번
더 찾는 것이 먼저다.

## ⑤ 09-20~21 실패와 소스 지도의 대응

| 실패 | 원인 | 지도의 답 |
|---|---|---|
| 기사 14건에서 추출 0 | 검색이 관련 없는 기사를 물어옴(평야 레미·귀털) | DS-3 질문별 쿼리 + DS-6 검증 |
| 9/11 중지를 9/21 로 읽음 | **날짜를 본문에서 안 읽음** | DS-6 ① `date_unverified` |
| 중지 결정(08:30)을 12:05 에도 모름 | 구단 공지를 폴링하지 않음 | DS-2 아침 폴링 `07:30·09:00·11:30` |
| 확정 타순을 8경로에서 못 찾음 | 타순 소스가 js 이고 JSON 주소 미확인 | ④ 그대로 — **미해결** |
| 일본 매체 도메인 접근 거부 | 검색 도구 제약 | 직독기(L1)가 공식 페이지를 직접 읽는다 |

## ⑥ 다음 단계로 넘길 것

- **DS-1 골격**: 경기 병렬 + 도메인 세마포어. 토르 보강은 **성과 0·대기 80초**
  이므로 기본 경로에서 빼는 것을 검토한다(지시 필요 — 지금 끄지 않았다).
- **DS-2 착수 전 숙제 셋**: NPB 순위 경로 · K리그 순위 경로 · NPB 확정 타순의
  정적 대안. 셋 다 404/미확인이라 파서를 붙일 수 없다.
- **KBO 는 별도 결정이 필요하다** — 공식이 막혀 있다. 사용자 지시를 기다린다.

---

# [2] KBO robots 거부 — 후속 실측 (사용자 지시 2026-09-21 12:56)

## a. robots 원문 (EUC-KR · HTTP 200 · 실측 13:04 KST)

```
# 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.

User-agent: Googlebot   Disallow: /ws/
User-agent: Yeti        Disallow: /ws/
User-agent: Daumoa      Disallow: /ws/
User-agent: Bingbot     Disallow: /ws/
User-agent: *           Disallow: /

can_fetch(AnalystBot/1.0) → 전 경로 False
```

🔴 **명시적 전면 거부 + 한국어 고지**다. `source_map.yaml` 에 `robots: false` ·
`status: "불가(robots)"` 로 적었다. 수집기는 그 행을 요청하지 않는다.

네이버:
```
sports.news.naver.com/robots.txt   200
  User-agent: *   Disallow: /   Allow: /$   Allow: /index
  User-agent: Yeti  Allow: /  Disallow: /article/     ← 네이버 자체 봇만
api-gw.sports.naver.com/robots.txt 404 (JSON 에러) → **판단 불가**(별도 호스트)
```

## b. 🔴 기존 수집 경로 감사 — **우리는 이미 거부 경로를 치고 있다**

| 코드 위치 | 도메인 | 경로 | robots | 무엇 |
|---|---|---|---|---|
| `kbo.py:31` | koreabaseball.com | `/ws/Schedule.asmx/GetScheduleList` | 🔴 **거부** | 일정(JSON) |
| `kbo.py:89` | koreabaseball.com | `/Schedule/Schedule.aspx` | 🔴 **거부** | 일정(HTML) |
| `kbo_stats.py:26` | koreabaseball.com | `/Record/Team/Hitter/Basic1.aspx` | 🔴 **거부** | 팀 타격 |
| `kbo_stats.py:28` | koreabaseball.com | `/Record/Team/Pitcher/Basic1.aspx` | 🔴 **거부** | 팀 투수 |
| `kbo_stats.py:29` | koreabaseball.com | `/Record/Player/PitcherBasic/BasicOld.aspx` | 🔴 **거부** | 투수 개인 |
| `kbo_roster.py:25` | koreabaseball.com | `/Player/RegisterAll.aspx` | 🔴 **거부** | 엔트리 |
| `kbo_boxscore.py` | koreabaseball.com | `/ws/Schedule.asmx/GetBoxScoreScroll` | 🔴 **거부** | 박스스코어 |
| `naver_kbo.py:22` | api-gw.sports.naver.com | `/schedule/games` | 판단불가(404) | 일정·프리뷰 |
| `source.go:137` | api-gw.sports.naver.com | `/schedule/games?fields=…` | 판단불가(404) | 크롤러 일정 |
| `source.go:159` | api-gw.sports.naver.com | `/schedule/games/{id}/preview` | 판단불가(404) | 크롤러 프리뷰 |

**koreabaseball.com 7경로가 전부 robots 거부**이고, 우리는 지금도 그것을 친다.
지시문대로 **멈추지 않고 사실만 보고한다.** 어떻게 할지는 지시를 기다린다.

## b-2. 🔴 D09a(09-12 등판 중단)의 원인 — **차단이 아니다**

```
KBO pitcher_appearances  마지막 2026-09-12 (4경기 40행) · pitches 채움 0
KBO batter_appearances   마지막 2026-09-12 (117행)       ← **같은 날 함께 멈췄다**
두 표 모두 source = 'boxscore' 하나

그 뒤 KBO 경기: 09-13 4 · 09-15 4 · 09-16 4 · 09-17 2 · 09-18 4 · 09-19 4 · 09-20 5
                (전부 status='final' — 결과는 들어왔다)

같은 시각 일정 수집은 정상:
  [kbo] 2026-09 일정 108경기 (행 108 · 파싱실패 0)   ← 오늘 로그
```

→ **도메인이 막힌 것이 아니다.** 일정은 지금도 같은 도메인에서 들어온다.
타격·투구 적재만 09-12 에 **동시에** 끊겼고, 둘 다 `boxscore` 한 소스다.
원인 후보는 (i) 박스스코어 잡이 안 돌거나 (ii) `/ws/GetBoxScoreScroll` 응답
구조가 바뀌었거나 (iii) 그 잡이 예외로 죽는 것이다. **아직 안 가렸다** —
잡을 실제로 돌려 봐야 하는데, 그 경로가 robots 거부라 **지시 없이 치지 않는다.**

⚠️ `pitches` 는 09-12 이전에도 **전건 0** 이다(D09b). 중단과 별개의 결함이다.

## c·d. 대체 소스 — 아직 안 했다

`koreabaseball.com` 이 막혔으므로 구단 공식 10곳·허용 포털·영어권 기록 사이트를
실측해야 한다. **b 의 결과(이미 거부 경로를 치고 있음)를 먼저 보고하고 지시를
기다리는 것이 순서**라고 판단해 c 를 시작하지 않았다.

## e. 🔴 스포츠나비는 `js` 가 아니라 `static` 이었다 — 내 오분류

지시대로 정적 HTML 을 다시 읽었더니 **값이 그대로 있었다**:

```
予告先発  背番号19 右投 髙橋 宏斗 · 今季 2.87 / 17등판 3승7패 · 대상대 2.18
          最近の成績 9/13 vs.阪神 9이닝 142구 4피안타 12탈삼진 0실점
                    9/4  vs.ヤクルト 6이닝 125구 6피안타 4탈삼진 1실점
順位表    セ·パ 양 리그 승·패·무·게임차·매직넘버(M11) · 09-20 22:05 갱신
試合中止  "楽天 - 試合中止 ソフトバンク" · "試合中止 降雨のため"
```

- `fetch: js` → **`fetch: static`** 으로 정정했다.
- `スタメン`·`打順` 만 없는데, **js 라서가 아니라 발표 전**일 수 있다 —
  경기 전 몇 분에 나타나는지는 DS-2 폴링에서 실측한다.
- 🔴 **이 페이지가 중지 공지도 준다.** 09-21 라쿠텐-소프트뱅크(우천)·
  롯데-세이부(태풍) 두 경기 중지를 여기서 읽었다.
- 🔴 **npb.jp/bis 순위 404 의 대안이 여기 있다.**
