# ACL-1 — ACL 엘리트를 리그로 받는다. 경기는 FotMob, 배당은 오즈포털

## 왜

사용자 지시 2026-09-15. 오늘(09-15) ACLE 4경기를 판정 대상으로 삼으려는데
시스템에 **경기가 존재하지 않았다.** 재현:
```
지원 리그: ['bundesliga','denmark','epl','j1','kleague1','la_liga','serie_a']
오늘 축구 적재 0경기
team_key('Gamba Osaka (Jpn) ') = 'gamba osaka jpn'     ← 국가 접미사가 남는다
🔴 leagues.LEAGUES 에 acl 이 없다 · SOCCER_URL 에 acl 이 없다 · 경기 4건 없음
```

## 소스 실측 (2026-09-15 · 원문은 세션 로그)

| 소스 | 결과 |
|---|---|
| The Odds API 종목 **178개 전수** | **AFC 계열 키 0개.** UEFA CL 만 있다 → 우리 축구 적재 경로(`upsert_games_from_odds_events`)로는 **못 받는다** |
| football-data.org | ACL 미제공(우리 4개 유럽 리그 코드만) |
| **FotMob** `matches?date=20260915` | 168경기 중 `AFC Champions League Elite East` 에 **지정 4경기 전부** id 6049976·77·78·80 |
| **오즈포털** `/football/asia/afc-champions-league/` | 경기행 15 · 1X2 배당 16 — 4경기 전부 값 있음 |
| 오즈포털 **북별**(`positionsWithProviders`) | **0경기** — 이 대회 페이지엔 없다. 평균 배당만 된다 |

→ 경기는 **FotMob**, 배당은 **오즈포털 평균**. sharp/soft proxy 는 ACL 에서
  **불가**이고, 그 사실을 표에 "소스없음"으로 적는다(0으로 채우지 않는다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
leagues.LEAGUES              (새 항목 acl · odds_key=None)
  ← odds.py:23  SPORT_KEYS["soccer"]        = [cfg["odds_key"] …]   ← None 이 섞이면 터진다
  ← odds.py:44  SOCCER_LEAGUE_LABELS        = {odds_key: label}     ← None 키 충돌
  ← pipeline.py:1354 · 1535                 odds_key 로 필터
  ← scheduler.py:1390 label_to_key
  ← bot/main.py:413  cfg["odds_key"]
  ← oddsportal.SOCCER_URL                   (계약이 키 전수 대조)
oddsportal.team_key → norm                  ← odds_free.collect_soccer 가 경기와 맞출 때
fotmob.slate                                ← 새 적재 함수가 쓴다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **`odds_key=None` 이 기존 7리그 경로에 새면 배당 수집이 통째로 죽는다.**
  그래서 None 을 **읽는 쪽에서 거른다**(추가할 때마다 반복될 자리라 계약으로 잠근다).
- 🔴 **국가 접미사 제거가 다른 리그의 팀을 합치면 안 된다.** 패턴을
  `\s*\([A-Za-z]{3}\)\s*$`(끝의 3글자 괄호)로 좁힌다 — `Hull City AFC` 처럼
  괄호 없는 이름은 건드리지 않는다. 계약이 기존 122팀 대조를 유지한다.
- FotMob 적재는 **fotmob_id 가 키**(`ext_id='fotmob:{id}'`)다. 기존
  `odds:{id}` 경기와 충돌하지 않는다. 별칭으로 canonical 을 못 찾으면
  **로그 남기고 제외**한다(지어내지 않는다).

## ③ 되돌리기

커밋 1개 revert + `games` 에서 `ext_id LIKE 'fotmob:%'` 삭제. 스키마 변경 없음.

## ④ 측정

`repro_acl1.py` 를 운영 컨테이너에서 그대로 다시 — 리그 존재 · 4경기 적재 ·
`team_key` 에 국가코드 없음.

## ⑤ 계약

```
test_acl이_리그로_있다
test_odds_key_없는_리그가_기존_경로를_깨지_않는다     ← 반대 위험
test_국가접미사만_떼고_다른_이름은_그대로다           ← 반대 위험
test_fotmob_적재는_매핑_실패를_조용히_넘기지_않는다
test_SOCCER_URL_키가_LEAGUES_와_같다                 (기존 계약 유지)
```
