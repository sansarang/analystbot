# [3] 전 리그 도메인 × robots 감사 — 편집 금지 · 보고만

실행 2026-09-21 13:35~13:42 KST · 운영 컨테이너 · **코드 변경 0**
UA: `AnalystBot/1.0 (+research; respects robots)` · **robots.txt 만 받았다**
(대상 페이지 본문 요청 0건)

---

## 🔴 가장 먼저 읽을 것 — 내 앞선 판정이 틀렸다

Python 표준 `urllib.robotparser` 는 **`*`·`$` 와일드카드를 해석하지 않는다.**
그래서 `Disallow: /api/*` 를 **문자 그대로** 읽고 `/api/data/...` 를 "허용"으로
답한다. DS-0 에서 FotMob 을 "robots **명시 허용** — 유일하다"고 적은 것은
**이 버그로 인한 오판**이다.

널리 쓰이는 해석(구글 규격: `*`=임의 문자열, `$`=끝, 최장일치 우선)으로 다시
계산했다:

```
www.fotmob.com  robots.txt (200)
  User-agent: *
    Allow: /
    Disallow: /api/*        ← 우리가 치는 경로가 전부 여기 들어간다
    Disallow: /auth/*
    Disallow: /info
    Disallow: /health
    Disallow: /contact_us

  stdlib robotparser      → /api/data/matches  **허용**(틀림)
  와일드카드 해석          → /api/data/matches  🔴 **거부**
                           /api/matchDetails   🔴 **거부**
```

🔴 **영향이 가장 크다.** FotMob 은 우리 축구의 기반이다 — 경기·확정 XI·결장·
경기장·결과·소급 적재(오늘 1,299건)가 전부 이 경로에서 온다.

⚠️ **끄지 않았다**(지시대로 보고 먼저). 영향표는 아래 §3.

---

## 1. 전체 표

| 도메인 | 경로 | 코드 위치 | 잡·주기 | robots | 판정(와일드카드 해석) | `*` 블록 해당 줄 | 채우는 칸 |
|---|---|---|---|---|---|---|---|
| `statsapi.mlb.com` | `/api/v1/schedule` | `mlb.py:213`·`lineups.py:31`·`starter_season.py:51` | prefetch·mlb_pregame_5m | **파일없음(404)** | 확인불가 | — | MLB 일정·예고선발·타순 |
| `baseballsavant.mlb.com` | `/statcast_search` | `statcast_velo.py:24` | statcast_daily 03:30 | 200 | 허용 | `Disallow:`(빈 값) | MLB 구속 |
| `www.mlb.com` | `/news` | `satellite.py:102-103` | satellite_15m | 200 | 허용 | `Disallow: /test/ /api/ /app/ …` | MLB 기사 |
| `npb.jp` | `/announcement/starter/`·`/roster/` | `npb_stats.py:27`·`starter_season.py:340` | prefetch_asia | **파일없음(404)** | 확인불가 | — | NPB 예고선발·등록말소 |
| `baseball.yahoo.co.jp` | `/npb/game/{id}/top` | `yahoo_npb.py:22`·`source.go:219` | crawler·npb_pregame_2m | **파일없음(404)** | 확인불가 | — | NPB 경기·예고선발·순위·중지 |
| `news.yahoo.co.jp` | `/articles/` | `satellite.py:484` | satellite_15m | 200 | 허용 | `Disallow: /comment/plugin/ …` | NPB 기사 |
| `www.koreabaseball.com` | 7경로 | `kbo*.py` | **중단됨(D33)** | 200 | 🔴 **거부** | `Disallow: /` + 자동수집 금지 고지 | KBO 전부 |
| `api-gw.sports.naver.com` | `/schedule/games` | `naver_kbo.py:22`·`source.go:137` | **중단됨(D33)** | **파일없음(404)** | 확인불가 | — | KBO 일정·프리뷰 |
| `m.sports.naver.com` | `/game/{id}` | `naver_kbo.py:31`·`source.go:139` | (Referer 헤더용) | 200 | 🔴 **거부** | `Disallow: / / Allow: /$ / Allow: /index` | — (요청 아님) |
| `sports.chosun.com` | `/` | `kbo_news.py:44` | satellite_15m | 200 | 허용 | `Allow: /` | KBO 기사 |
| `sports.khan.co.kr` | `/` | `kbo_news.py:46` | satellite_15m | 200 | 허용 | `Disallow: /login …` | KBO 기사 |
| `osen.mt.co.kr` | `/` | `kbo_news.py:48-49` | satellite_15m | 200 | 허용 | `Disallow:`(빈 값) | KBO 기사 |
| `www.spotvnews.co.kr` | `/` | `kbo_news.py:51` | satellite_15m | 200 | 허용 | `Disallow:`(빈 값) | KBO 기사 |
| **`www.fotmob.com`** | **`/api/data/*`** | `fotmob.py:27`·`soccer_trial.py:34` | finals·prefetch·satellite | 200 | 🔴 **거부** | **`Disallow: /api/*`** | **축구 전부** |
| `www.transfermarkt.com` | `/x/verletztespieler/` | `satellite_soccer.py:159` | satellite_15m | 200 | 허용 | `Allow: /` | 축구 부상표 |
| `api.football-data.org` | `/v4/matches` | `football.py:66` | finals·prefetch | **파일없음(404)** | 확인불가 | — | 축구 결과 |
| `www.football-data.co.uk` | `/mmz4281/` | `soccer_elo.py:44` | elo_refresh_weekly | 200 | 허용 | `Disallow:`(빈 값) | 축구 elo CSV |
| `www.flashscore.com` | `/match/` | `flashscore.py:35` | satellite_15m | 200 | 허용 | `Disallow: /standings/ /draw/ /newsfeed/` | 축구 라인업 |
| `global.flashscore.ninja` | `/x/feed/` | `flashscore.py:29` | satellite_15m | **파일없음(404)** | 확인불가 | — | 축구 피드 |
| `www.oddsportal.com` | `/` | `oddsportal.py:53-81` | odds_snapshot_30m | **파일없음(429)** | 확인불가 | — | **배당 시초·종가** |
| `api.the-odds-api.com` | `/v4/sports` | `odds.py:74` | odds_snapshot_30m | **파일없음(404)** | 확인불가 | — | 배당 |
| `api.odds-api.net` | `/` | `oddsapinet.py:30` | oddsapinet_2x | **파일없음(404)** | 확인불가 | — | 배당 |
| `api.sharpapi.com` | `/` | `sharp_odds.py:20` | — | **ConnectError** | 확인불가 | — | 배당 |
| `sports.core.api.espn.com` | `/v2/sports` | `espn_odds.py:33` | odds | **파일없음(403)** | 확인불가 | — | 배당 |
| `v3.football.api-sports.io` | `/` | `football.py:191` | (호출 0건) | **파일없음(403)** | 확인불가 | — | 축구 부상 |
| **`news.google.com`** | **`/rss/search`** | `news_rss.py:24` | satellite_15m | 200 | 🔴 **거부** | `Disallow: / / Allow: /$ /? /home$ /topics/ …` | **기사 검색 RSS** |
| **`search.daum.net`** | **`/search`** | `satellite.py:270` | satellite_15m | 200 | 🔴 **거부** | `Disallow: /` | KBO·축구 기사 검색 |
| `lite.duckduckgo.com` | `/lite/` | `tor_search.py:169` | satellite_15m | 200 | 허용 | `Allow: /` | 보강 검색(성과 0) |
| **`api.open-meteo.com`** | **`/v1/forecast`** | `weather.py:107` | 날씨 | 200 | 🔴 **거부** | `Disallow: /` | 날씨 |

⚠️ **"파일 없음(404)"은 허용이 아니다.** 별도 열로 두었다. 약관의 자동 수집
조항은 **아직 확인하지 않았다**(§4).

## 2. 🔴 새로 나온 거부 4곳 (D33 의 KBO·네이버 외)

| 도메인 | 경로 | 무엇이 끊기나 | 대안 |
|---|---|---|---|
| **`www.fotmob.com`** | `/api/*` | **축구 전부** — 경기·확정 XI·결장·경기장·결과·소급 | football-data(4리그만)·Flashscore(라인업) — **J1·K1·ACL·덴마크·UEFA 는 대안 없음** |
| **`news.google.com`** | `/rss/search` | 축구·야구 **기사 검색의 기본 경로** | 리그·구단 사이트 내 목록 · 매체 자체 RSS |
| **`search.daum.net`** | `/search` | KBO·축구 기사 검색(층1) | 위와 같음 |
| **`api.open-meteo.com`** | `/v1/forecast` | 날씨(구장 조건) | 다른 무료 기상 API 확인 필요 |

`m.sports.naver.com` 도 `Disallow: /` 지만 우리는 **Referer 헤더로만** 쓰고
요청은 보내지 않는다(`naver_kbo.py:31`·`source.go:139`). 요청 0건이므로
거부 대상 행위가 아니다 — 다만 그 Referer 가 가리키는 API 는 이미 껐다.

## 3. 🔴 FotMob 을 끄면 무엇이 비나 (영향표 · 끄기 전 보고)

| 칸 | 지금 소스 | FotMob 없이 |
|---|---|---|
| 축구 결과 적재 | FotMob(J1·K1·ACL·덴마크·UEFA) + football-data(EPL·라리가·세리에A·분데스·리그앙·에레디비시) | **6리그만 남는다.** J1·K1·ACL·덴마크·UCL·UEL **0** |
| 확정 XI·결장 | FotMob `matchDetails` | Transfermarkt(부상표만·허용) · Flashscore(허용, 그러나 js) |
| 경기장 | FotMob `infoBox.Stadium` | **없다**(`venue_name` 축구 0/241) |
| 최근 5경기 폼 | FotMob `last5` + `games(final)` | `games(final)` 만 — 소급도 FotMob 이었다 |
| 오늘 소급 1,299건 | FotMob | 이미 DB 에 들어왔다(되돌릴 필요 없음) |

⚠️ **배당은 이번 감사에서 거부가 나오지 않았다** — oddsportal 은 robots.txt
자체가 **429**라 확인 불가이고, 나머지 배당 API 는 404/403 이다. 시초가·종가
기록은 지금 끊기지 않는다.

## 4. 약관(자동 수집 조항) — **아직 확인하지 않았다**

robots 만 읽었다. 약관 페이지는 도메인마다 위치가 다르고 본문을 받아야 하므로,
**확인할 URL 목록만** 남긴다(지시받으면 읽는다):

```
fotmob.com/terms · transfermarkt.com/intern/anb · flashscore.com/terms-of-use/
oddsportal.com/terms-and-conditions/ · the-odds-api.com/liveapi/guides/v4/
football-data.org/terms · mlb.com/official-information/terms-of-use
npb.jp (약관 페이지 위치 미확인) · yahoo.co.jp/docs/info/terms/
```

## 5. 하루 요청 수 — **정확히는 못 쟀다**

Railway 로그 보존 창 밖의 집계를 낼 수단이 없다. 대신 **직접 계측한 값**만 적는다:

```
NPB 3경기 직렬 1회(12:45): news.yahoo.co.jp 30 · check.torproject.org 6 ·
                           lite.duckduckgo.com 6   (경기당 HTTP 14회)
소급 적재 1회(11:20·12:00): fotmob.com 45일치 × 2회 = 90요청
```

잡 주기로 **추정**하면 satellite_15m(96회/일) × 경기 수 × 14 가 지배적이지만,
**추정값이므로 표에 넣지 않는다.** 정확한 집계는 DS-1 의 구조화 로그가 들어온
뒤에 낼 수 있다.

## 6. 판단이 필요한 것 (끄지 않고 기다린다)

1. **FotMob `/api/*`** — 축구 전체가 걸린다. 끄면 J1·K1·ACL·덴마크·UEFA 가
   통째로 빈다. 정식 접근 문의 대상이기도 하다.
2. **news.google.com·search.daum.net** — 기사 검색의 기본 경로 둘.
3. **api.open-meteo.com** — 날씨. 대체가 비교적 쉬울 수 있다.
4. **404·403·429(확인 불가) 12곳** — 약관을 읽어야 판단이 선다.
