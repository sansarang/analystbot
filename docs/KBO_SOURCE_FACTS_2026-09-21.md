# [2]b — KBO 칸별 사실표 · 기존 수집 경로 점검

실측 2026-09-21 13:44~13:52 KST · 운영 컨테이너 · **대상 페이지 요청 0건**
(게이트가 요청 전에 막았고, 막힌 경로는 치지 않았다)

## 1. 칸별 — 무엇이 어디서 왔고 지금 어떤가

| 칸 | 코드 경로 | 소스 | robots | 지금 | 마지막 실적 |
|---|---|---|---|---|---|
| 일정·결과 | `kbo.fetch_month` | koreabaseball `/ws/Schedule.asmx` · `/Schedule.aspx` | 🔴 거부 | **중단(D33)** | `games` 148행 `2026-08-22~09-30` · 최종 09-21 04:01 |
| 박스스코어(타자) | `kbo_boxscore.backfill` | koreabaseball `/ws/…GetBoxScoreScroll` | 🔴 거부 | **중단(D33)** | `batter_appearances` `source=boxscore` 2,144행 · **마지막 경기일 09-12** |
| 박스스코어(투수) | `kbo_boxscore.backfill` | 같음 | 🔴 거부 | **중단(D33)** | `pitcher_appearances` 781행 · **마지막 경기일 09-12** |
| 팀 타선·투수 기록 | `kbo_stats.refresh` | koreabaseball `/Record/Team/*` | 🔴 거부 | **중단(D33)** | 캐시 `load()` tuple n=2 (**낡은 값이 남아 있다**) |
| 엔트리(등록·말소) | `kbo_roster.refresh` | koreabaseball `/Player/RegisterAll.aspx` | 🔴 거부 | **중단(D33)** | 캐시 `load()` dict **n=0** |
| 구장 계수 | `kbo_park.refresh` | koreabaseball (일정 경유) | 🔴 거부 | **중단(D33)** | `refresh → {'stadiums':0,'games':0}` · 캐시 **n=0** |
| 확정 타순·예고선발 | `naver_kbo.refresh` | api-gw.sports.naver `/schedule/games/*/preview` | ⚠️ 404(판단불가) | **중단(D33)** | 캐시 **n=0** |
| 투수 소모(불펜) | `kbo_usage.refresh` | 같은 API `/record` | ⚠️ 404 | **중단(D33)** | `refresh → {'teams':0}` |
| 순위 | `naver_kbo.build_standings` | 같은 API | ⚠️ 404 | **중단(D33)** | 캐시 n=0 |
| **라인업(발표)** | **Go 크롤러** `source.go:137·159` | **같은 API** | ⚠️ 404 | 🔴 **계속 돈다** | `lineup_events` `source=crawler` **148행 · 마지막 경기일 09-20** |
| 기사 | `kbo_news.fetch_for_games` | 스포츠조선·경향·OSEN·SPOTV | 🟢 허용 | **정상** | Redis `crawl:kbo:2026-09-20:*` 156키 |
| 배당 | `odds.py` 등 | the-odds-api 외 | 확인불가(404) | **정상** | — |

## 2. 🔴 세 가지가 사실과 다르다

### (1) Go 크롤러는 게이트 밖이다
`crawler/internal/source/source.go:137·159` 가 `api-gw.sports.naver.com` 을
**10분마다** 친다. SRC-OFF 는 Python 진입점 5곳만 막았다. 크롤러는 별도 서비스라
`source_gate` 를 모른다.
⚠️ **끄지 않았다** — 지시가 "보고만"이고, 끄면 KBO 라인업이 **완전히** 0 이 된다
   (지금 KBO 라인업의 유일한 공급원이다).

### (2) `refresh` 가 조용한 0 을 돌려준다
```
kbo_park.refresh   → 정상반환 {'stadiums': 0, 'games': 0}
kbo_usage.refresh  → 정상반환 {'teams': 0}
naver_kbo.refresh  → SourceDisabled (예외가 올라온다)
```
`source_gate` 는 "조용히 빈손을 주지 않는다"고 약속했지만, 그 약속은 **게이트까지**다.
수집기가 `except Exception` 으로 잡아 0 을 돌려주면 약속이 끊긴다.
→ **SRCV-1 이 이것을 `/health`·export 에 보이게 했다**(수집기 `except` 는 안 고쳤다 —
  잡 하나가 스케줄러를 죽이면 그게 더 나쁘다).

### (3) 박스스코어는 **게이트 이전부터** 끊겨 있었다
`batter_appearances`·`pitcher_appearances` 의 마지막 경기일이 **09-12** 다.
게이트를 켠 것은 09-21 13:0x 다. 즉 **9일 전부터 안 들어오고 있었다.**
→ D09a 와 같은 자리로 보인다. [2]c 에서 **경로를 치지 않고** 확인한다.

## 3. 오늘(09-21) KBO 0행은 정상이다

`games(kbo, 2026-09-21) = 0행` 이지만 **9/21·9/28 은 월요일**이고 9/14·9/7 도
같다. KBO 정기 휴식일이다. 적재 단절이 아니다.
⚠️ 하마터면 결함으로 보고할 뻔했다 — 요일을 먼저 확인했다.

## 4. `leagues.py` 의 KBO judge·router 플래그 — **건드리지 않았다**

사용자 결정 사항이다. 지금 상태로 두면 KBO 는 **자료 0 → 미상 → 판정 보류**로
간다. 끄면 슬레이트에서 아예 빠진다. 어느 쪽인지 지시를 기다린다.

## 5. 함께 눈에 띈 것 (범위 밖 — 등록만)

⚠️ **UA 위장 20곳** — `Mozilla/5.0` 을 쓰는 수집기가 20개다
(`fotmob`·`flashscore`·`yahoo_npb`·`satellite`·`news_rss`·`oddsportal` 등).
지시문 규율은 "봇 크롤러는 **식별 가능한** User-Agent 를 쓴다"이다.
DS-0 프로브에서만 `AnalystBot/1.0 (+research; respects robots)` 를 썼고,
**운영 수집 경로는 전부 브라우저 위장**이다. → `docs/DEFECTS.md` 등록 대상.
