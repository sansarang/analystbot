# ODN-1 — KBO·NPB **총점 배당 소스가 없다**

## 왜

실측 2026-09-17 (odds-api.net 실호출):
```
/leagues?sport=baseball → ["CPBL","Japan NPB","Korean KBO","MLB", …]
/events 야구 6일 창 20건 — KBO 2 · NPB 5 · CPBL 4 · MLB 9
   09-17 09:30Z  Kiwoom Heroes @ Kia Tigers  · 북 44
   09-17 09:30Z  SSG Landers @ NC Dinos      · 북 44
/events/{id}/odds/snapshot → 1,405행
   total/over 7.5 33북 · total/under 7.5 33북 · handicap/home -1.5 39북
   bet_type: total 432 · handicap 428 · team total 272 · moneyline 116
```
→ 사용자 목표 분석의 **"총점 언더 7.5"·"핸디 −1.5"·"NC 팀토탈 오버 4.5"** 가
   전부 있는 소스다. 지금 KBO·NPB 는 **oddsportal 1북 h2h** 뿐이다.

앞서 막힌 셋: 배트맨(엔드포인트 폐기) · oddsportal(총점은 JS 뒤) ·
betexplorer(경기 페이지 data-odd 는 **과거 상대전적**이었다).

## 🔴 예산이 설계를 정한다

```
plan sandbox · api_credits_limit **1,000 / 월**
기존 30분 주기로 붙이면  8콜 × 48회 × 30일 = 11,520콜  → 이틀이면 끝
하루 2회                8콜 × 2 × 30 = 480콜          → 여유 2배
```
🔴 **기존 30분 잡은 안 건드린다.** ESPN·oddsportal 은 무료·무제한이고, 거기서
   CLV(판정시각·마감)와 라인 이동 스냅샷이 나온다. 늦추면 그게 깨진다.
   **새 소스만 별도 잡으로 하루 2회** 돈다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
app/collectors/oddsapinet.py     ← 신규 수집기 (KBO·NPB 전용)
  fetch_events / fetch_odds      ← API 두 경로
  to_rows                        ← odds_snapshots 모양으로
  budget_ok                      ← /usage 를 읽어 80% 넘으면 멈춘다
config.oddsapinet_key            ← **.env 에만**. 코드·커밋·로그에 안 남긴다
odds_free.store_rows             ← 적재는 기존 통로 그대로(사본 금지)
scheduler 새 잡(하루 2회)         ← 기존 odds_snapshot_30m 은 **그대로**
structure.candidates / LAM-1     ← 오늘 깔아둔 총점 배선이 받는다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **기존 배당 수집을 안 건드린다.** 계약이 `odds_snapshot_30m` 과
  `IntervalTrigger(minutes=30)` 이 그대로인지 잰다.
- 🔴 **키가 없으면 조용히 비활성**이다(`sharp_odds` 와 같은 규약). 키 부재로
  크래시하지 않는다(절대 규칙 3).
- 🔴 **예산 가드가 먼저다.** `/usage` 를 읽어 80% 를 넘으면 **수집을 멈추고
  로그를 남긴다.** 조용히 초과하면 다음 달까지 죽는다.
- 🔴 **KBO·NPB 만.** MLB·축구는 ESPN 무료로 이미 된다 — 크레딧을 아낀다.
- 🔴 **적재는 `store_rows` 를 쓴다.** INSERT 를 다시 쓰지 않는다.
- 🔴 **`is_available` 이 거짓인 행은 버린다.** 닫힌 배당을 시장으로 읽으면 안 된다.
- 🔴 **period 를 가린다.** `full time` 만 쓴다 — `5 innings` 는 다른 시장이다.
  실측에서 첫 행이 `5 innings` 였다. 섞으면 라인이 통째로 어긋난다.
- ⚠️ 팀 이름이 우리 DB 와 다르다(`Yokohama Dena Baystars`). 매칭은 기존
  `_match_game_ids` 규약을 따른다 — 새 별칭표를 만들지 않는다.
- ⚠️ 라인이 문자열로 온다(`"+0.5"`, `"7.5"`) — 숫자로 바꾼다.

## ③ 되돌리기

커밋 1개 revert + `.env` 키 삭제. 새 파일 하나와 잡 하나가 빠진다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 배포 뒤 첫 사이클에서 KBO·NPB
`totals` 행이 원장에 생기는지 본다(⑨).

## ⑤ 계약

12건 — 총점·핸디·팀토탈이 행으로 나온다 · 라인이 숫자다 · full time 만 ·
닫힌 배당 제외 · 키 없으면 비활성 · 예산 80% 가드 · KBO·NPB 만 ·
store_rows 재사용 · **기존 30분 잡 불변** · 키가 코드에 없다 ·
provider 이름 · 실측 모양 재현.
