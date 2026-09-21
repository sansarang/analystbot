# [3-재] robots 전 도메인 재감사 — 교정 파서 기준

실행 2026-09-21 18:4x KST · **도메인당 robots.txt 1회** · 대상 페이지 요청 0건

## 0. 판정 기준

```
User-Agent:  AnalystBot/1.0 (+research; respects robots)
```
구글 규격: `*`=임의 문자열 · `$`=끝 · **최장 일치 우선** · 같은 길이면 Allow ·
**우리 UA 를 지목한 그룹이 `*` 그룹을 이긴다.**

⚠️ 파서는 `ROB-1`(커밋 `72bc171`) 계약 **23건**으로 잠겨 있다 — 실제 robots 10건 포함.
⚠️ 파이썬 표준 `urllib.robotparser` 는 `*`·`$` 를 해석하지 않는다. 그 버그로
   내가 FotMob 을 "robots 명시 허용"이라고 **오보**했다(DS-0). 그 자리를 계약으로 박아 뒀다.

## 1. 🔴 이전 판정과 달라진 행

**2행**. 🔴 **허용 → 거부로 바뀐 행은 0건이다.**

| 도메인 | 경로 | 이전 | 지금 | 뜻 |
|---|---|---|---|---|
| `www.oddsportal.com` | `/` | 파일없음(429) | **허용** | 전에는 robots.txt 자체를 못 받았다. 이번엔 받았고 허용이다 |
| `www.premierleague.com` | `/news` | 403(판단불가) | **허용** | 전에는 robots.txt 자체를 못 받았다. 이번엔 받았고 허용이다 |

⚠️ 둘 다 **확인불가 → 허용**이다. 끌 것이 늘지 않았다.

## 2. 판정 분포

총 **42행** — 허용 22 · 🔴 거부 6 · 확인불가 14

🔴 **`*` 그룹과 우리 UA 판정이 갈리는 행: 0건.**
   지금 감사 대상 중 우리를 **이름으로 지목**해 다르게 대하는 곳은 없다.
   (`news.google.com` 은 `ClaudeBot`·`anthropic-ai` 를 지목하지만 `*` 도 이미
    `/rss/search` 를 막으므로 결론이 같다.)

## 3. 🔴 거부 6곳

| 도메인 | 경로 | 코드 위치 | 채우는 칸 | 상태 |
|---|---|---|---|---|
| `www.koreabaseball.com` | `/ws/Schedule.asmx/GetScheduleList` | `kbo*.py` | KBO 전부 | **중단됨**(D33 · `source_gate`) |
| `m.sports.naver.com` | `/game/1` | `naver_kbo.py:31` | (Referer용) | 요청 0건 — Referer 헤더로만 쓴다 |
| `www.fotmob.com` | `/api/data/matches` | `fotmob.py:27` | 축구 전부 | **결정 1 진행 중** — 1a 로 호출 48% 감축(`2aae6ab`) · 전환은 b·c 뒤 |
| `news.google.com` | `/rss/search` | `news_rss.py:24` | 기사 검색 RSS | **끊었다**(DS-3 · `98921cd`) → Bing |
| `search.daum.net` | `/search` | `satellite.py:270` | KBO·축구 기사 검색 | 🔴 **아직 돈다** — D40 |
| `api.open-meteo.com` | `/v1/forecast` | `weather.py:107` | 날씨 | 🔴 **아직 돈다** — 결정 2 에서 `access_basis=api_terms` 로 이관 예정 |

## 4. ⚠️ 확인불가 14곳 — robots.txt 를 못 받았다

**"파일 없음"은 허용이 아니다.** 별도 열로 둔다.

| 도메인 | 응답 | 채우는 칸 | access_basis | 근거 URL |
|---|---|---|---|---|
| `statsapi.mlb.com` | 파일없음(404) | MLB 일정·예고선발·타순 | api_terms | **근거 없음** |
| `npb.jp` | 파일없음(404) | NPB 예고선발·등록말소 | 미분류 | **근거 없음** |
| `baseball.yahoo.co.jp` | 파일없음(404) | NPB 경기·순위·중지 | 미분류 | **근거 없음** |
| `api-gw.sports.naver.com` | 파일없음(404) | KBO 일정·프리뷰 | api_terms | **근거 없음** |
| `api.football-data.org` | 파일없음(404) | 축구 결과 | api_terms | **근거 없음** |
| `global.flashscore.ninja` | 파일없음(404) | 축구 피드 | 미분류 | **근거 없음** |
| `api.the-odds-api.com` | 파일없음(404) | 배당 | api_terms | **근거 없음** |
| `api.odds-api.net` | 파일없음(404) | 배당 | api_terms | **근거 없음** |
| `api.sharpapi.com` | ConnectError | 배당 | api_terms | **근거 없음** |
| `sports.core.api.espn.com` | 파일없음(403) | 배당 | 미분류 | **근거 없음** |
| `v3.football.api-sports.io` | 파일없음(403) | 축구 부상(호출 0) | 미분류 | **근거 없음** |
| `www.kleague.com` | 파일없음(404) | K1 순위 | 미분류 | **근거 없음** |
| `www.rakuteneagles.jp` | 파일없음(404) | NPB 중지공지 | 미분류 | **근거 없음** |
| `www.marines.co.jp` | 파일없음(404) | NPB 중지공지 | 미분류 | **근거 없음** |

🔴 **`access_basis` 근거 URL 이 하나도 없다.** 사용자 지시대로 표에 그대로 드러낸다.
   결정 1b 의 후보 표에서 이 칸을 채운다(약관 페이지를 후보당 1회 받아 캐시).

## 5. 허용 22곳

| 도메인 | 경로 | 채우는 칸 |
|---|---|---|
| `baseballsavant.mlb.com` | `/statcast_search` | MLB 구속 |
| `www.mlb.com` | `/news` | MLB 기사 |
| `news.yahoo.co.jp` | `/articles/` | NPB 기사 |
| `sports.chosun.com` | `/` | KBO 기사 |
| `sports.khan.co.kr` | `/` | KBO 기사 |
| `osen.mt.co.kr` | `/` | KBO 기사 |
| `www.spotvnews.co.kr` | `/` | KBO 기사 |
| `www.transfermarkt.com` | `/x/verletztespieler/verein/5` | 축구 부상표 |
| `www.football-data.co.uk` | `/mmz4281/` | 축구 elo CSV |
| `www.flashscore.com` | `/match/` | 축구 라인업 |
| `www.oddsportal.com` | `/` | 배당 시초·종가 |
| `lite.duckduckgo.com` | `/lite/` | 보강 검색 |
| `www.bing.com` | `/news/search` | **기사 검색(신규)** |
| `www.jleague.jp` | `/standings/j1/` | J1 순위·일정 |
| `www.premierleague.com` | `/news` | EPL 팀뉴스 |
| `www.msn.com` | `/ko-kr/news/` | 기사 본문(래핑) |
| `www.osen.co.kr` | `/article/` | KBO 기사 |
| `www.yna.co.kr` | `/view/` | KBO 기사 |
| `www.mt.co.kr` | `/sports/` | KBO 기사 |
| `www.fnnews.com` | `/news/` | KBO 기사 |
| `news.mynavi.jp` | `/article/` | NPB 기사 |
| `www.nikkansports.com` | `/baseball/` | NPB 기사 |

## 6. 이번 감사에서 새로 본 것

Bing 검색 결과가 물어오는 **매체 도메인 7곳**(msn·osen·yna·mt·fnnews·mynavi·
nikkansports)을 처음 감사에 넣었다. **전부 허용**이다 — DS-1W 에서 본문을 실제로
열어 본 결과(24주소·15도메인·**거부 0**)와 일치한다.

## 7. 예절

도메인당 robots.txt **1회**만 받았다. DS-1 런타임의 캐시는 24시간
(`config/deepsearch.yaml` · `robots.cache_ttl_sec: 86400`).

## 8. 1a 에 대한 확인 두 가지 (사용자 지시)

1. **호출 수 표는 "계산값"이라고 명시한 그대로 둔다.**
   실측은 FotMob 이 꺼지기 전 **런타임 집계가 붙는 시점**에 하루치만 받아 적는다.
   ⚠️ 그것 때문에 전환을 미루지 않는다.

2. **`bulk_allowed` 관문은 기본 `false`** 이고, `true` 로 바꾸는 것은 사용자
   지시가 있을 때만이다. 설정 변경 이력은 `docs/DEFECTS.md` 의
   "설정 변경 이력 — `fotmob.bulk_allowed`" 표에 남긴다.

