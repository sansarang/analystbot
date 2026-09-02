# 분석 과정 증명 — San Diego Padres @ Cincinnati Reds

생성 2026-09-02 · 표본 `game_id=824472` · 슬레이트 `2026-09-01`(미 동부) · 시작 09/02 07:40 KST

**이 문서는 주장이 아니라 산출물이다.** 각 단계가 실제로 만든 데이터를 원문 그대로 싣는다. 요약·의역하지 않는다.

## 왜 KBO가 아닌가

지시는 "가능하면 KBO"였다. **불가능했다** — 사유:

- 오늘(2026-09-02) KBO 경기가 네이버 스케줄 피드에 0건이다.
- 로컬 DB의 KBO 09-01 슬레이트 5경기는 `lineup_status=none`, 선발 `None`, `lineup_events` 0행이다 (개발 DB에 크롤러 데이터가 없다).
- 운영 DB·Redis 는 내부 호스트명이라 밖에서 못 읽는다. 공개 프록시를 여는 것은 DB를 인터넷에 노출하는 일이라 임의로 하지 않았다.

MLB를 쓴 이유는 편해서가 아니다. **7단계 전부를 실물로 보일 수 있는 유일한 종목**이다 — 특히 ④ 가치 게이트는 새 무료 배당(ESPN)이 붙는 MLB 에서만 지금 증명된다.

⚠️ 이 경기는 이미 끝났다. 시즌 라인에 그 경기가 포함돼 **누수가 있다.** 이 문서는 **기계가 도는지**를 증명하는 것이지 적중률을 주장하지 않는다.

---

## ① 수집 — 무엇이 실제로 적재됐나

### 확정 타순 (statsapi boxscore → `research.today_nine`)
```json
{
 "order": [
  {
   "slot": 1,
   "name": "Héctor Rodríguez",
   "pos": "RF"
  },
  {
   "slot": 2,
   "name": "Elly De La Cruz",
   "pos": "DH"
  },
  {
   "slot": 3,
   "name": "Sal Stewart",
   "pos": "1B"
  },
  {
   "slot": 4,
   "name": "JJ Bleday",
   "pos": "LF"
  },
  {
   "slot": 5,
   "name": "Matt McLain",
   "pos": "SS"
  },
  {
   "slot": 6,
   "name": "Jose Trevino",
   "pos": "C"
  },
  {
   "slot": 7,
   "name": "Juan Brito",
   "pos": "2B"
  },
  {
   "slot": 8,
   "name": "Dane Myers",
   "pos": "CF"
  },
  {
   "slot": 9,
   "name": "Edwin Arroyo",
   "pos": "3B"
  }
 ]
}
```

### 선발투수 · 최근 등판 (DB `pitcher_appearances`)
```json
{
 "선발": {
  "name": "Nick Lodolo"
 },
 "최근등판": [
  {
   "opponent": "San Francisco Giants",
   "innings": 4.0,
   "r": 4,
   "hits": 6,
   "k": 5,
   "bb": 2,
   "run_support": 10,
   "date": "2026-08-26"
  },
  {
   "opponent": "Arizona Diamondbacks",
   "innings": 3.3333333333333335,
   "r": 6,
   "hits": 10,
   "k": 2,
   "bb": 2,
   "run_support": 0,
   "date": "2026-08-22"
  },
  {
   "opponent": "Miami Marlins",
   "innings": 5.0,
   "r": 0,
   "hits": 3,
   "k": 2,
   "bb": 2,
   "run_support": 1,
   "date": "2026-08-16"
  },
  {
   "opponent": "Chicago White Sox",
   "innings": 4.0,
   "r": 4,
   "hits": 5,
   "k": 5,
   "bb": 0,
   "run_support": 5,
   "date": "2026-08-11"
  }
 ],
 "시즌라인_표본보정전용": {
  "선발": 17,
  "이닝": "85.0",
  "ERA": "5.08",
  "WHIP": "1.52",
  "K": 69,
  "BB": 35,
  "BB9": 3.71,
  "K9": 7.31
 }
}
```

### 최근 3경기 **원본 박스스코어** (`{side}_usage.games`)
```json
[
 {
  "date": "2026-08-31",
  "game_id": "824473",
  "opponent": "San Diego Padres",
  "home": true,
  "runs": 0,
  "opp_runs": 5,
  "result": "L",
  "one_run": false,
  "shutout_loss": true
 },
 {
  "date": "2026-08-30",
  "game_id": "824636",
  "opponent": "Chicago Cubs",
  "home": false,
  "runs": 7,
  "opp_runs": 5,
  "result": "W",
  "one_run": false,
  "shutout_loss": false
 },
 {
  "date": "2026-08-29",
  "game_id": "824637",
  "opponent": "Chicago Cubs",
  "home": false,
  "runs": 5,
  "opp_runs": 17,
  "result": "L",
  "one_run": false,
  "shutout_loss": false
 }
]
```

### 타순 9명 시즌 타격 — 2026-09-02 신설
```json
{
 "타자": [
  {
   "이름": "Héctor Rodríguez",
   "PA": 77,
   "AVG": ".243",
   "OBP": ".312",
   "SLG": ".457",
   "OPS": ".769",
   "HR": 4,
   "BB": 6,
   "SO": 19
  },
  {
   "이름": "Elly De La Cruz",
   "PA": 537,
   "AVG": ".271",
   "OBP": ".352",
   "SLG": ".476",
   "OPS": ".828",
   "HR": 21,
   "BB": 59,
   "SO": 146
  },
  {
   "이름": "Sal Stewart",
   "PA": 603,
   "AVG": ".268",
   "OBP": ".338",
   "SLG": ".489",
   "OPS": ".827",
   "HR": 31,
   "BB": 57,
   "SO": 130
  },
  {
   "이름": "JJ Bleday",
   "PA": 463,
   "AVG": ".217",
   "OBP": ".329",
   "SLG": ".423",
   "OPS": ".752",
   "HR": 21,
   "BB": 64,
   "SO": 99
  },
  {
   "이름": "Matt McLain",
   "PA": 431,
   "AVG": ".189",
   "OBP": ".287",
   "SLG": ".339",
   "OPS": ".626",
   "HR": 13,
   "BB": 46,
   "SO": 117
  },
  {
   "이름": "Jose Trevino",
   "PA": 130,
   "AVG": ".230",
   "OBP": ".234",
   "SLG": ".373",
   "OPS": ".607",
   "HR": 5,
   "BB": 1,
   "SO": 24
  },
  {
   "이름": "Juan Brito",
   "PA": 56,
   "AVG": ".176",
   "OBP": ".250",
   "SLG": ".255",
   "OPS": ".505",
   "HR": 0,
   "BB": 4,
   "SO": 17
  },
  {
   "이름": "Dane Myers",
   "PA": 277,
   "AVG": ".254",
   "OBP": ".347",
   "SLG": ".367",
   "OPS": ".714",
   "HR": 6,
   "BB": 32,
   "SO": 67
  },
  {
   "이름": "Edwin Arroyo",
   "PA": 154,
   "AVG": ".232",
   "OBP": ".276",
   "SLG": ".275",
   "OPS": ".551",
   "HR": 0,
   "BB": 6,
   "SO": 37
  }
 ],
 "팀": {
  "가중OPS": 0.737,
  "합계타석": 2728,
  "인원": 9
 }
}
```

### 뉴스 (Google News RSS · 무인증·무료)
```json
[
 {
  "title": "San Diego Padres promote highly-touted 20-year-old catcher Ethan Salas from Triple-A - Greenwich Time",
  "url": "https://news.google.com/rss/articles/CBMinAFBVV95cUxNaTlLZEg3R19IaF9xSU0wN0tmUm53R1hxajlxSkh3ZG5XTGlZRmNpZ0VCX01pdU9ZSlVFUTUtclhySV9YZW5yUC0zaV9jMm5TdmJ5VDhJdGM3MFgzY1VBXzRKR3l6dm9wV2dJTjdyU1JTeXQzcWJZNDVCOE14YlcyQXFRQ3FzT0lCRGZBNXJOc19HRGZlT05jNmVXbGw?oc=5",
  "source": "Greenwich Time",
  "published": "Wed, 02 Sep 2026 03:57:19 GMT",
  "age_h": 0.4,
  "team": "San Diego Padres"
 },
 {
  "title": "Cincinnati Reds sign veteran infielder Orlando Arcia to minor league deal - Yahoo Sports",
  "url": "https://news.google.com/rss/articles/CBMikAFBVV95cUxOYzN0aFd2ci1EWGgxTTl0NmwtLXZwd3JFU0J0TThNajJiRDh0MFJHT2FROENkZmtFMUdyai1XTnBBYzdnUkRyYWdRWkk0R0dOQVZwMGh6Z2lnd1VVUU4yRjBkVkppZ09xU2pFNTdBWndDSmh2QmNadG00WE1Td2p3b3czb0taNFZJWXdISGdaY3o?oc=5",
  "source": "Yahoo Sports",
  "published": "Wed, 02 Sep 2026 03:27:00 GMT",
  "age_h": 0.9,
  "team": "Cincinnati Reds"
 },
 {
  "title": "Terry Francona on Jose Trevino's clutch hit in win - MLB.com",
  "url": "https://news.google.com/rss/articles/CBMiiAFBVV95cUxOcl9HNS1CZkxCR3dPNlR6UWZpUXZnUHRrcXh5anFONUh3LVhINXVWaWl6eHlsR2hsd3UxT3FmaHk0bzJrOF9ydWRFZFFNeWhtWlIzNF9Ib2ViMDFRZDhLV2N2REpsVk9zQlJ2YjJ6M0dlOVl4eFFoRlJTMW0xTE9sMko3QS1RZGJn?oc=5",
  "source": "MLB.com",
  "published": "Wed, 02 Sep 2026 03:23:19 GMT",
  "age_h": 1.0,
  "team": "Cincinnati Reds"
 },
 {
  "title": "Craig Stammen on having chances early in tough loss - MLB.com",
  "url": "https://news.google.com/rss/articles/CBMijAFBVV95cUxQdWprdUZOb2ZjcW1QaGVJT0M0d0loSEpfUDRjbV91RFQzczBNMEpYUTYxRFZYMzJiSV92TTI2OHNpZy1DTGRrWlIwNXBmLWZhSkhtaWtPcnNMbnl4SFd3cFJDaU1yTlJkVzFfZE5uZXVTcjctS1RJSUpVY3hIWmltWEdUSmpMV1ltNkFWbQ?oc=5",
  "source": "MLB.com",
  "published": "Wed, 02 Sep 2026 03:21:21 GMT",
  "age_h": 1.0,
  "team": "San Diego Padres"
 }
]
```

### 배당 (무료 3원 체계 · ESPN)
수집 실행 결과:
```json
{
 "provider": null,
 "games": 0,
 "rows": 0,
 "matched": 0
}
```
> 09-01 슬레이트는 **이미 시작**해 적재 가드에 걸린다(0행). 아래 ④ 에서 쓰는 배당은 그 경기의 **경기 전 마감 라인을 사후 조회**한 것이며, 출처를 `espn/draftkings 경기 전 마감 라인(사후 조회)` 로 명시한다.

---

## ② 재료 조립 — 판정에 실제로 들어간 프롬프트

렌더 결과 **9,547자**. 자리표시자 잔여 `{{` : 0건 (0이어야 정상).

아래는 자른 요약이 아니라 **모델이 받은 전문**이다.

````text
당신은 야구 매치업 판정가다. 홈팀이 이길 확률을 산출한다.

[입력 자료]
1. 양팀 최근 3경기 **원본 박스스코어** (최신순): {"home": {"경기": [{"date": "2026-08-31", "game_id": "824473", "opponent": "San Diego Padres", "home": true, "runs": 0, "opp_runs": 5, "result": "L", "one_run": false, "shutout_loss": true}, {"date": "2026-08-30", "game_id": "824636", "opponent": "Chicago Cubs", "home": false, "runs": 7, "opp_runs": 5, "result": "W", "one_run": false, "shutout_loss": false}, {"date": "2026-08-29", "game_id": "824637", "opponent": "Chicago Cubs", "home": false, "runs": 5, "opp_runs": 17, "result": "L", "one_run": false, "shutout_loss": false}], "results_l3": "LWL", "runs_l3": 12, "runs_allowed_l3": 27, "runs_per_game_l3": 4.0}, "away": {"경기": [{"date": "2026-08-31", "game_id": "824473", "opponent": "Cincinnati Reds", "home": false, "runs": 5, "opp_runs": 0, "result": "W", "one_run": false, "shutout_loss": false}, {"date": "2026-08-30", "game_id": "822933", "opponent": "Tampa Bay Rays", "home": false, "runs": 4, "opp_runs": 5, "result": "L", "one_run": true, "shutout_loss": false}, {"date": "2026-08-29", "game_id": "822936", "opponent": "Tampa Bay Rays", "home": false, "runs": 6, "opp_runs": 7, "result": "L", "one_run": true, "shutout_loss": false}], "results_l3": "WLL", "runs_l3": 15, "runs_allowed_l3": 12, "runs_per_game_l3": 5.0}}
   경기마다 상대·상대순위·상대승률·득점·실점·승패, 그 경기 선발의
   이름·이닝·실점·투구수, 불펜 투입 인원, 안타·홈런·볼넷·삼진·실책이 들어 있다.
   `results_l3`·`runs_l3`·`runs_allowed_l3`·`runs_per_game_l3`는 그 3경기의 합계다.

2. 최근 72시간 뉴스 태그 (없으면 빈 객체): {}
   `tag`·`dir`(▲호재/▼악재)·`근거`. 사전에 걸러진 것만 온다.
3. 오늘 확정 라인업: {"home": {"선발투수": "Nick Lodolo", "타순": [{"타순": 1, "이름": "Héctor Rodríguez", "포지션": "RF"}, {"타순": 2, "이름": "Elly De La Cruz", "포지션": "DH"}, {"타순": 3, "이름": "Sal Stewart", "포지션": "1B"}, {"타순": 4, "이름": "JJ Bleday", "포지션": "LF"}, {"타순": 5, "이름": "Matt McLain", "포지션": "SS"}, {"타순": 6, "이름": "Jose Trevino", "포지션": "C"}, {"타순": 7, "이름": "Juan Brito", "포지션": "2B"}, {"타순": 8, "이름": "Dane Myers", "포지션": "CF"}, {"타순": 9, "이름": "Edwin Arroyo", "포지션": "3B"}]}, "away": {"선발투수": "Randy Vásquez", "타순": [{"타순": 1, "이름": "Fernando Tatis Jr.", "포지션": "2B"}, {"타순": 2, "이름": "Samad Taylor", "포지션": "LF"}, {"타순": 3, "이름": "Manny Machado", "포지션": "3B"}, {"타순": 4, "이름": "Ty France", "포지션": "1B"}, {"타순": 5, "이름": "Jackson Merrill", "포지션": "CF"}, {"타순": 6, "이름": "Xander Bogaerts", "포지션": "SS"}, {"타순": 7, "이름": "Luis Campusano", "포지션": "DH"}, {"타순": 8, "이름": "Sung-Mun Song", "포지션": "PH"}, {"타순": 9, "이름": "Jake Cronenworth", "포지션": "PH"}]}}
   `선발투수`와 `타순`(각 항목에 **타순 번호·이름·포지션**). 순서가 곧 정보다 —
   1번과 8번은 타석 수가 다르고 3~5번은 득점권 상황이 다르다.
4. 양팀 오늘 선발투수의 최근 등판 기록: {"home": {"선발등판": [{"opponent": "San Francisco Giants", "innings": 4.0, "r": 4, "hits": 6, "k": 5, "bb": 2, "run_support": 10, "date": "2026-08-26"}, {"opponent": "Arizona Diamondbacks", "innings": 3.3333333333333335, "r": 6, "hits": 10, "k": 2, "bb": 2, "run_support": 0, "date": "2026-08-22"}, {"opponent": "Miami Marlins", "innings": 5.0, "r": 0, "hits": 3, "k": 2, "bb": 2, "run_support": 1, "date": "2026-08-16"}, {"opponent": "Chicago White Sox", "innings": 4.0, "r": 4, "hits": 5, "k": 5, "bb": 0, "run_support": 5, "date": "2026-08-11"}]}, "away": {"선발등판": [{"opponent": "Pittsburgh Pirates", "innings": 5.0, "r": 0, "hits": 1, "k": 2, "bb": 2, "run_support": 3, "date": "2026-08-26"}, {"opponent": "Minnesota Twins", "innings": 7.0, "r": 2, "hits": 2, "k": 3, "bb": 0, "run_support": 6, "date": "2026-08-22"}, {"opponent": "Houston Astros", "innings": 5.0, "r": 2, "hits": 2, "k": 1, "bb": 0, "run_support": 7, "date": "2026-08-10"}]}}
   `선발등판`이 주 자료다. `구원등판`은 **선발 표본이 얇을 때만** 붙는다.
5. 직전 판정 (재판정일 때만. 최초 판정이면 null): null
6. 라인업 의도 — **사실이 아니라 해석이다** (없으면 빈 객체): {}
   평소 라인업 대비 무엇이 달라졌는지(사실)와, 감독이 왜 그렇게 짰는지를
   해석봇이 매긴 부호다. `부호` ▲유리/▼불리/=중립, `득점방향` 다득점/저득점/중립.

7. 양팀 선발의 **시즌 라인** — **표본 보정 전용** (없으면 빈 객체):
   {"home": {"시즌": {"선발": 17, "이닝": "85.0", "ERA": "5.08", "WHIP": "1.52", "K": 69, "BB": 35, "BB9": 3.71, "K9": 7.31}, "최근등판수": 4}, "away": {"시즌": {"선발": 22, "이닝": "127.2", "ERA": "4.02", "WHIP": "1.28", "K": 79, "BB": 35, "BB9": 2.48, "K9": 5.59}, "최근등판수": 3}}
   `선발`(등판 수)·`이닝`·`ERA`·`WHIP`·`BB9`·`K9`.

8. 오늘 타순 9명의 **시즌 타격 라인** (없으면 빈 객체): {"home": {"타자": [{"이름": "Héctor Rodríguez", "PA": 77, "AVG": ".243", "OBP": ".312", "SLG": ".457", "OPS": ".769", "HR": 4, "BB": 6, "SO": 19}, {"이름": "Elly De La Cruz", "PA": 537, "AVG": ".271", "OBP": ".352", "SLG": ".476", "OPS": ".828", "HR": 21, "BB": 59, "SO": 146}, {"이름": "Sal Stewart", "PA": 603, "AVG": ".268", "OBP": ".338", "SLG": ".489", "OPS": ".827", "HR": 31, "BB": 57, "SO": 130}, {"이름": "JJ Bleday", "PA": 463, "AVG": ".217", "OBP": ".329", "SLG": ".423", "OPS": ".752", "HR": 21, "BB": 64, "SO": 99}, {"이름": "Matt McLain", "PA": 431, "AVG": ".189", "OBP": ".287", "SLG": ".339", "OPS": ".626", "HR": 13, "BB": 46, "SO": 117}, {"이름": "Jose Trevino", "PA": 130, "AVG": ".230", "OBP": ".234", "SLG": ".373", "OPS": ".607", "HR": 5, "BB": 1, "SO": 24}, {"이름": "Juan Brito", "PA": 56, "AVG": ".176", "OBP": ".250", "SLG": ".255", "OPS": ".505", "HR": 0, "BB": 4, "SO": 17}, {"이름": "Dane Myers", "PA": 277, "AVG": ".254", "OBP": ".347", "SLG": ".367", "OPS": ".714", "HR": 6, "BB": 32, "SO": 67}, {"이름": "Edwin Arroyo", "PA": 154, "AVG": ".232", "OBP": ".276", "SLG": ".275", "OPS": ".551", "HR": 0, "BB": 6, "SO": 37}], "팀": {"가중OPS": 0.737, "합계타석": 2728, "인원": 9}}, "away": {"타자": [{"이름": "Fernando Tatis Jr.", "PA": 605, "AVG": ".282", "OBP": ".349", "SLG": ".449", "OPS": ".798", "HR": 19, "BB": 54, "SO": 112}, {"이름": "Samad Taylor", "PA": 109, "AVG": ".344", "OBP": ".425", "SLG": ".430", "OPS": ".855", "HR": 1, "BB": 12, "SO": 31}, {"이름": "Manny Machado", "PA": 582, "AVG": ".219", "OBP": ".306", "SLG": ".403", "OPS": ".709", "HR": 24, "BB": 66, "SO": 126}, {"이름": "Ty France", "PA": 414, "AVG": ".288", "OBP": ".356", "SLG": ".503", "OPS": ".859", "HR": 19, "BB": 30, "SO": 90}, {"이름": "Jackson Merrill", "PA": 572, "AVG": ".243", "OBP": ".295", "SLG": ".421", "OPS": ".716", "HR": 22, "BB": 37, "SO": 141}, {"이름": "Xander Bogaerts", "PA": 523, "AVG": ".216", "OBP": ".317", "SLG": ".321", "OPS": ".638", "HR": 11, "BB": 65, "SO": 93}, {"이름": "Luis Campusano", "PA": 177, "AVG": ".285", "OBP": ".390", "SLG": ".457", "OPS": ".847", "HR": 5, "BB": 24, "SO": 40}, {"이름": "Sung-Mun Song", "PA": 143, "AVG": ".190", "OBP": ".293", "SLG": ".248", "OPS": ".541", "HR": 1, "BB": 18, "SO": 26}, {"이름": "Jake Cronenworth", "PA": 337, "AVG": ".217", "OBP": ".301", "SLG": ".294", "OPS": ".595", "HR": 4, "BB": 31, "SO": 79}], "팀": {"가중OPS": 0.727, "합계타석": 3462, "인원": 9}}}
   `타자` 배열은 타순 순서다 — 각 타자의 `PA`·`AVG`·`OBP`·`SLG`·`OPS`·`HR`·`BB`·`SO`.
   `팀`은 타석 가중 합계 — `가중OPS`·`합계타석`·`인원`.
   (센트럴리그처럼 투수가 타순에 들면 그 자리는 빠져 인원이 8이다.)

9. 양팀 불펜 (없으면 빈 객체): {}
   `era`는 팀 불펜 방어율. `roster`의 괄호는 `시즌ERA·컨디션`이며
   컨디션(매우 좋음~매우 나쁨)은 **ERA와 별개 항목**이다. 선발이 일찍 내려가면
   여기서 경기가 갈린다 — 자료1의 `bullpen_count`(그 경기 투입 인원)와 함께 읽어라.

[판정 규칙]
- 근거는 위 자료 안에서만 찾는다. 배당, 팀 명성, 시즌 승률, 사전 지식은 쓰지 않는다.
- **모든 판단은 위 숫자에서 직접 낸다.** 자료에는 다른 모델이 매긴 등급
  ('상/중/하', '흐름 상승' 같은 것)이 들어 있지 않다. 그런 표현을 근거에
  쓰지 말고, 어느 숫자에서 그 결론이 나왔는지를 적어라.
  (예: "선발진이 좋다"가 아니라 "3경기 선발 평균 6.3이닝 0.67실점")
- 오늘 나온 9명이 기준이다. "빠진 선수가 누구인가"로 승부를 뒤집지 않는다.
- 오늘 선발의 최근 등판은 팀 3경기 평가서와 별개의 핵심 변수다. 반드시 독립적으로 비중 있게 반영한다.
- 선발의 승패(W-L)는 판정 근거로 쓰지 않는다. 이닝·실점·투구수와 run_support로 실질을 평가한다.
- `구원등판`은 **구위·제구의 참고**이지 **이닝 소화력의 근거가 아니다.** 1이닝
  구원과 6이닝 선발은 다른 일이다. 구원 기록만으로 그 투수가 오늘 6이닝을
  던진다고 보지 마라. 근거에 쓸 때는 "구원 기록:"으로 시작하라.
- 직전 판정이 있으면: 달라진 입력(선발 변경, 타순 변경, 새 경기 결과)을
  먼저 식별하고, 그것이 직전 근거 중 무엇을 무효화하는지 판정한 뒤 확률을
  조정한다. 바뀐 입력이 없으면 직전 판정을 유지한다.
- 자료만으로 확신도가 '하'가 되는 이유가 외부에서 확인 가능한 정보라면
  추가확인에 적어라.
- 자료1(3경기)은 **표본 3이다.** 상대가 누구였는지(`opponent_rank`·
  `opponent_win_pct`)를 반드시 감안하고, 단정하지 말고 경향으로 읽어라.
  · 투수의 승패(W-L)는 쓰지 않는다. `starter_ip`·`starter_r`·`starter_pitches`로
    실질을 본다.
  · `errors`·`bullpen_count`는 그 경기의 사정이다. 오늘 반복된다고 보지 마라.
- 자료2(뉴스태그)는 보조 신호다: 확률을 최대 ±3%p까지만 조정할 수 있고,
  실적 데이터가 가리키는 우세 방향을 뉴스만으로 뒤집을 수 없다.
- 라인업 의도(6번)도 **같은 보조 신호다.** 뉴스와 의도를 **합쳐서** ±3%p를
  넘지 않고, 실적 데이터가 가리키는 우세 방향을 이 둘만으로 뒤집을 수 없다.
- 의도의 `부호`·`득점방향`이 '보류'인 항목은 **근거로 쓰지 마라.** 해석봇이
  판단하지 못했다는 뜻이지 중립이라는 뜻이 아니다.
- 의도는 해석이므로 근거에 쓸 때 반드시 "해석:"으로 시작해 사실과 구분하라.
  변경점 자체(무엇이 바뀌었나)는 사실이므로 그대로 인용해도 된다.
- 자료7(시즌 라인)은 **표본을 얼마나 믿을지 판단하는 데만 쓴다.** 이것으로
  우세를 정하지 마라. 승부는 오늘 선발의 최근 등판과 오늘 9명이다.
  · 최근 등판이 **2경기 이하**면 그 표본은 그 투수를 대표하지 않는다.
    시즌 라인이 최근 등판과 크게 어긋나면 **최근 등판 쪽을 낮게 보고**
    확신도를 낮춰라. 표본이 적을수록 0.50 쪽으로 당긴다.
  · 최근 등판이 3경기 이상이면 시즌 라인은 배경일 뿐이다. 최근 폼이 우선이다.
  · 시즌 라인을 근거에 쓸 때는 "표본 보정:"으로 시작하라.
  · 이 칸은 선발투수다. 타선 시즌은 8번 자료를 쓴다.
- 자료8(타선 시즌)은 **정식 근거다.** 3경기 팀 득점(자료1·2)보다 표본이 크므로
  **타선 평가의 주 근거로 쓴다.** 3경기 득점은 그 위의 변동으로 읽어라 —
  "시즌 대비 지금 어떤가"이지, 그 3경기가 그 타선의 실력은 아니다.
  · 팀 `가중OPS`로 두 타선의 수준을 먼저 견주고, 그 다음 개별 타자를 본다.
  · `PA`가 작은 타자(대타·백업·신인)의 비율·slash 는 믿지 마라. 표본이다.
  · 타선 격차와 선발 격차가 반대를 가리키면 **선발 쪽을 무겁게 본다.**
    오늘 던지는 선발 하나가 9명 각각보다 경기에 크게 관여한다.
  · 근거에 쓸 때는 "타선 시즌:"으로 시작하라.
  · 자료8이 없거나 한쪽만 있으면 **없는 쪽을 나쁘다고 보지 마라.** 수집
    실패이지 타선이 약하다는 뜻이 아니다. 그때는 자료1·2로만 판단한다.
- 3경기 표본의 한계를 인정한다. p_home은 0.32~0.68 범위를 벗어나지 않는다.
  자료가 그 이상을 시사해도 0.32 또는 0.68에서 멈춘다.
- 양팀 자료가 팽팽하면 억지로 차이를 만들지 말고 0.50 부근으로 낸다.

[출력]
아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{
  "p_home": 0.00,
  "우세": "home|away|박빙",
  "근거": ["핵심 근거 정확히 3개, 각각 어느 자료에서 나왔는지 명시"],
  "변수": ["이 판정을 흔들 수 있는 요인 1~2개"],
  "직전대비": {"변경입력": ["달라진 입력. 최초 판정이면 빈 배열"],
             "무효화된근거": ["직전 근거 중 더 이상 성립하지 않는 것"],
             "이동": "+N.N%p|-N.N%p|0"},
  "추가확인": ["확신을 세우는 데 필요한 미확인 정보 0~2개"],
  "뉴스반영": {"적용": true|false, "조정폭": "+N.N%p|-N.N%p|0", "사유": "1문장"},
  "확신도": "상|중|하"
}

````

---

## ③ 판정 — 모델 응답 원문

`claude-sonnet-5` 가 위 프롬프트를 받고 낸 JSON 그대로:

```json
{
 "p_home": 0.37,
 "우세": "away",
 "근거": [
  "선발 최근 등판(자료4): 홈 Lodolo 최근 4경기 평균 4.08이닝 3.5실점(4,6,0,4R, ERA환산 약 7점대) vs 원정 Vásquez 최근 3경기 평균 5.67이닝 1.33실점(0,2,2R, ERA환산 약 2점대)로 선발 격차가 원정 쪽으로 뚜렷",
  "자료1 팀 3경기: 홈 runs_per_game_l3 4.0·실점 27(9.0/경기) vs 원정 runs_per_game_l3 5.0·실점 12(4.0/경기)로 최근 흐름도 원정이 우위",
  "타선 시즌(자료8): 팀 가중OPS 홈 0.737 vs 원정 0.727로 거의 대등하여 선발 격차를 뒤집을 만큼의 타선 우위가 어느 쪽에도 없음"
 ],
 "변수": [
  "Lodolo가 시즌 표본(17경기, ERA5.08)과 유사하게 나쁜 흐름을 오늘도 이어갈지 여부",
  "불펜 자료(9번)가 없어 선발 조기강판 시 양팀 불펜 격차를 판단할 수 없음"
 ],
 "직전대비": {
  "변경입력": [],
  "무효화된근거": [],
  "이동": "0"
 },
 "추가확인": [
  "양팀 불펜 ERA 및 컨디션 정보",
  "Lodolo의 최근 부진이 부상/구위 저하인지 상대 타선 문제인지"
 ],
 "뉴스반영": {
  "적용": false,
  "조정폭": "0",
  "사유": "뉴스 태그 없음"
 },
 "확신도": "중",
 "model": "claude-sonnet-5"
}
```

### 클립 적용 여부

```json
{
 "raw": 0.37,
 "clipped": 0.37,
 "applied": false
}
```
> 모델 원값 0.37 → 저장값 0.37. 클립(0.32~0.68) **미적용 — 범위 안**.

---

## ④ 게이트 — 계산값과 통과/탈락

```json
{
 "p_home": 0.37,
 "우세": "away",
 "p_우세측": 0.63,
 "확률게이트_하한": 0.63,
 "확률게이트_통과": true,
 "라인업확정": true,
 "확신도": "중",
 "배당": {
  "home": 2.13,
  "away": 1.73
 },
 "필요배당": 1.67,
 "가치통과": true,
 "시장분류": {
  "market_prob": 0.5518,
  "divergence_pp": 7.8,
  "classification": "neutral",
  "edge_status": "none",
  "note": null
 },
 "암시확률": {
  "home": 0.4482,
  "away": 0.5518
 },
 "실제배당": 1.73,
 "배당출처": "espn/draftkings 경기 전 마감 라인(사후 조회)"
}
```

### 확률 게이트

- 우세 `away` → 우세측 확률 **0.6300**
- 원정 하한 **0.63** (야구 원정은 0.63)
- 판정: **통과** (0.6300 ≥ 0.63)
- 라인업 확정: **True** · 확신도 **중** (‘하’면 거부권으로 탈락)

### 가치 게이트 — **새 무료 배당으로**

- 배당 출처: `espn/draftkings 경기 전 마감 라인(사후 조회)`
- 실제 배당(우세측 away): **1.73**
- 필요 배당(1/p): **1.67**
- 판정: **가치 통과** (1.73 > 1.67)

### 시장 괴리

```json
{
 "market_prob": 0.5518,
 "divergence_pp": 7.8,
 "classification": "neutral",
 "edge_status": "none",
 "note": null
}
```
> 우리 63.0% vs 시장 55.18% = 괴리 **7.8%p**. 엣지 임계 8%p 미만이라 분류는 `neutral` — 추천 자격은 유지되고 엣지 라벨은 붙지 않는다.

🔴 **이것이 완료 기준 1(e) 다.** 가치 게이트가 "배당 미수집"이 아니라 실제 숫자로 판정을 냈다. 야구 가치 게이트가 배당을 받은 것은 이번이 처음이다 — 종전 수집기는 `야구는 totals 만, 승부 배당 키는 넣지 않는다` 로 h2h 를 건너뛰고 있었다.

---

## ⑤ 트리거·딥서치 — 무과금 경로 실행 로그

NPB 한신@야쿠르트로 T5 를 강제 발동한 원문 (같은 코드 경로):

```text
INFO [news_rss] npb Tokyo Yakult Swallows — 72시간 내 기사 10건
INFO [news_rss] npb Hanshin Tigers — 72시간 내 기사 17건
INFO HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
대상: Hanshin Tigers @ Tokyo Yakult Swallows

=== 결과 ===
search_source = rss
유료 web_search = 0회
발견: [{"사실": "검색 결과 12건 중 홈 선발 吉村의 추가 등판 기록(이닝, 실점, 등판 간격 등)을 직접 언급한 기사는 없음", "소스유형": "뉴스", "url": "N/A"}, {"사실": "원정 선발 髙橋 관련 기사(5,8,10,12)는 9/1 경기 결과(7回途中2失点, 13勝, 자책 2점, 멀티히트)를 다루나 이는 吉村의 표본 확대 요청과 무관한 원정 선발 기사임", "소스유형": "뉴스", "url": "デイリースポーツ (제목: 阪神・高橋遥人あっぱれ二刀流で１３勝目)"}, {"사실": "항목 11은 '2025年8月3日' 등 연도가 뒤섞인 티켓 재판매 페이지로 날짜 신뢰 불가하여 근거에서 제외함", "소스유형": "뉴스", "url": "lesalonbeige.fr"}, {"사실": "야쿠르트 공식 페이지(9번, JERA セ・リーグ公式戦 vs 阪神(神宮)③)는 본문 스니펫이 없어 吉村 관련 세부 통계 확인 불가", "소스유형": "공식", "url": "yakult-swallows.co.jp"}]
조정: {"p_home": 0.42, "사유": "요청된 홈 선발 吉村의 추가 등판 기록을 확인할 수 있는 신뢰 가능한 자료를 찾지 못해 '미확인'으로 남기고, 새 사실이 없어 조정하지 않음", "단일기사여부": false}
요약: 吉村의 추가 등판 표본 확대 요청에 답할 자료를 찾지 못해 미확인으로 남기며, p_home은 0.42로 유지함.
```

- `search_source = rss` · **유료 web_search = 0회**
- RSS 27건(야쿠르트 10 + 한신 17) 수집 → 상위 4건 본문까지 주입
- 모델이 기사 신뢰도를 스스로 검증했다: *"항목 11은 '2025年8月3日' 등 연도가 뒤섞인 티켓 재판매 페이지로 날짜 신뢰 불가하여 근거에서 제외함"*
- 자료를 못 찾자 **조정하지 않고** p_home 0.42 유지 — 지어내지 않았다

---

## ⑥ 발송 — 카드 최종 텍스트

```text
⏰ MLB · 1차
MLB  샌디에이고 파드리스 @ 신시내티 레즈
09/02 07:40
우세 샌디에이고 파드리스 63.0%  ★★★★
신호등 🟢
가치 배당 미수집 — 필요배당 1.67
근거1 선발 최근 등판(자료4): 홈 Lodolo 최근 4경기 평균 4.08이닝 3.5실점(4,6,0,4R, ERA환산 약 7점대) vs 원정 Vásquez 최근 3경기 평균 5.67이닝 1.33실점(0,2,2R, ERA환산 약 2점대)로 선발 격차가 원정 쪽으로 뚜렷
근거2 자료1 팀 3경기: 홈 runs_per_game_l3 4.0·실점 27(9.0/경기) vs 원정 runs_per_game_l3 5.0·실점 12(4.0/경기)로 최근 흐름도 원정이 우위
근거3 타선 시즌(자료8): 팀 가중OPS 홈 0.737 vs 원정 0.727로 거의 대등하여 선발 격차를 뒤집을 만큼의 타선 우위가 어느 쪽에도 없음
변수 Lodolo가 시즌 표본(17경기, ERA5.08)과 유사하게 나쁜 흐름을 오늘도 이어갈지 여부
변수 불펜 자료(9번)가 없어 선발 조기강판 시 양팀 불펜 격차를 판단할 수 없음
추천
```

> `가치 배당 미수집` 줄은 이 카드를 **배당 수집 전에** 렌더했기 때문이다. ④ 에서 보인 대로 배당이 붙으면 이 줄이 실판정으로 바뀐다 (필요배당 1.67 < 실제 1.73 → 가치 통과).

---

## ⑦ 대조표 — "63%는 어느 입력에서 왔나"

근거 3줄의 **모든 숫자를 원본과 대조**했다. 지어낸 값이 있는지 보는 표다.

| 근거 | 판정이 말한 숫자 | 원본 위치 | 원본 값 | 일치 |
|---|---|---|---|---|
| 1 | 홈 선발 4경기 평균 **4.08이닝 3.5실점** (4,6,0,4) | `research.home_starter_recent` (자료4) | 이닝 [4.0, 3.33, 5.0, 4.0] 평균 4.08 · 실점 [4, 6, 0, 4] 평균 3.50 | ✅ |
| 1 | 원정 선발 3경기 평균 **5.67이닝 1.33실점** (0,2,2) | `research.away_starter_recent` (자료4) | 이닝 [5.0, 7.0, 5.0] 평균 5.67 · 실점 [0, 2, 2] 평균 1.33 | ✅ |
| 2 | 홈 **runs_per_game_l3 4.0** · 실점 **27**(9.0/경기) | `research.home_usage` (자료1) | `runs_per_game_l3=4.0` `runs_allowed_l3=27` (27/3=9.0) | ✅ |
| 2 | 원정 **runs_per_game_l3 5.0** · 실점 **12**(4.0/경기) | `research.away_usage` (자료1) | `runs_per_game_l3=5.0` `runs_allowed_l3=12` (12/3=4.0) | ✅ |
| 3 | 팀 가중OPS 홈 **0.737** vs 원정 **0.727** | `research.{side}_lineup_season.팀` (자료8) | 홈 0.737 (타석 2728) · 원정 0.727 (타석 3462) | ✅ |
| 변수 | Lodolo 시즌 **17경기 ERA 5.08** | `research.home_starter_season` (자료7) | `선발=17` `ERA=5.08` `WHIP=1.52` | ✅ |

**대조 결과: 6/6 일치. 원본에 없는 숫자를 만들어낸 근거가 0건이다.**

### 확률이 만들어진 경로

```
자료4 선발 격차 (4.08이닝 3.5실점  vs  5.67이닝 1.33실점)   → 원정 쪽 주된 근거
자료1 3경기 실점 (9.0/경기  vs  4.0/경기)                  → 같은 방향 보강
자료8 타선 가중OPS (0.737 vs 0.727, 거의 대등)             → 뒤집을 힘 없음 → 중립
자료7 시즌 라인 (ERA 5.08 · 17경기 = 표본 충분)            → 최근 4경기를 신뢰 가능
                                        ↓
                          p_home = 0.37  (클립 미적용, 범위 안)
                          우세 away · 우세측 0.6300
```

판정 규칙 *"타선 격차와 선발 격차가 반대를 가리키면 선발 쪽을 무겁게 본다"* 가 여기서는 **타선이 대등**해 발동하지 않았고, 근거3이 그 사실을 명시적으로 적었다 — 규칙이 서술로 확인된다.

---

## 제3자 검증 절차

이 문서만으로 다음을 다시 확인할 수 있다:

1. ①의 `home_usage.games` 숫자를 statsapi 박스스코어와 대조
2. ②의 프롬프트에 ①의 값이 그대로 박혀 있는지 문자열 검색
3. ③의 `근거` 문장에 나온 숫자를 ⑦ 표로 대조 (여기서는 6/6 일치)
4. ④의 계산을 손으로 재현: `필요배당 = 1/0.63 = 1.587…` → 반올림 1.67은 `value_gate.required_odds` 의 마진 규칙을 포함한 값이다
5. ⑤의 로그에서 `search_source=rss` 와 `유료 web_search = 0회` 확인

## 이 문서가 증명하지 않는 것

- **적중률.** 표본 1경기이고 시즌 라인 누수가 있다.
- **KBO·NPB 배당.** 배트맨 엔드포인트가 막혀 있다(`evidence/OPEN.md` 참조).
- **운영 DB 상태.** 여기 데이터는 statsapi·ESPN 실호출 + 로컬 DB 조합이다.
