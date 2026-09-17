# ODF-1 — ESPN 이 주는 **MLB 총점·핸디 가격을 버린다**

## 왜

사용자 지시 2026-09-17: **"Odds API 아니더라도 무료가 잇다"** — 맞았다.

실측(운영 컨테이너에서 ESPN Core API 직접 호출, 2026-09-17):
```
DraftKings 키 = [… 'overOdds', 'overUnder', 'spread', 'underOdds' …]
  overUnder 7.0 · overOdds 101.0 · underOdds -122.0
  spread -1.5 · homeTeamOdds.current.spread.value 2.42
```
**총점 라인·양쪽 가격·핸디 라인·핸디 가격이 전부 있다. 무인증·무료다.**

그런데 `espn_odds.parse_odds`(MLB)는:
```python
ou = item.get("overUnder")
# ESPN 은 O/U 가격을 따로 안 준다 — 라인만 있고 가격이 없으면 적재하지 않는다.
logger.debug("[espn_odds] O/U %s 라인만 있고 가격 없음 — 생략", line)
```
🔴 **그 판단이 지금은 틀렸다.** 그리고 같은 파일의 `parse_soccer_odds` 는
   **바로 그 필드를 이미 읽는다**(`overOdds`/`underOdds` → `from_american`).

결과 — 14일 실측: `mlb totals 0건` · `soccer totals 150건`.
목표 분석의 "총점 언더 7.5"·"팀토탈 오버" 판단이 **재료가 없어 불가능**했고
`structure.candidates`(S9)가 0/18 이었다.

⚠️ **KBO·NPB 는 여전히 h2h 뿐이다.** ESPN 이 그 리그를 커버하지 않는다.
   그쪽은 oddsportal 총점 페이지를 새로 긁어야 하고 **이 단위가 아니다.**

## ① 이 함수/상태를 읽는 곳 **전부**

```
espn_odds.parse_odds          ← 고치는 곳 (MLB)
espn_odds.parse_soccer_odds   ← **안 건드린다.** 이미 읽는다
espn_odds.from_american       ← 재사용. 머리말의 "축구에서만" 을 고친다
espn_odds._decimal            ← h2h 용. 그대로
odds_free.collect_mlb → store_rows → odds_snapshots(market)
structure.derived_probs / attach_derived ← totals·spreads 를 먹는 쪽(S9)
pick_ledger:구조 픽 · market_edge        ← 그 뒤
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **h2h 가 그대로 나와야 한다.** 승부 배당이 본선이다. 계약이 잰다.
- 🔴 **가격이 없으면 안 넣는다.** 종전 판단의 **원칙은 옳다** — 없는 값을
  −110 으로 지어내지 않는다. 필드가 있을 때만 넣는다. 계약이 잰다.
- 🔴 **라이브 북은 계속 버린다**(`is_live_book`). 안 건드린다.
- 🔴 **미국식 환산은 `from_american` 을 쓴다** — 항등식이라 추측이 아니다.
  ⚠️ 그 함수 머리말이 "축구에서만 쓴다(야구는 decimal 이 온다)"고 적었는데,
     **O/U·핸디 가격은 야구도 미국식**이다(실측 101.0 / −122.0). 머리말을 고친다.
- 🔴 **핸디 가격은 `current.spread.value`(소수)다** — 머니라인과 다른 자리다.
  `from_american` 을 쓰면 안 된다. 계약이 두 경로를 갈라 잰다.
- ⚠️ 콜 수가 **안 는다** — 같은 응답에서 더 읽을 뿐이다.
- ⚠️ 라인 부호: `spread` 는 **홈 기준**이다(홈 −1.5). 원정은 부호를 뒤집는다 —
  `parse_soccer_odds` 가 이미 그렇게 한다(사본 금지, 같은 방식).

## ③ 되돌리기

커밋 1개 revert. 파서 한 블록.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 다음 수집 사이클 뒤 원장에서
`mlb totals` 행이 생기는지 본다(⑨).

## ⑤ 계약

12건 — 총점 양쪽이 나온다 · 핸디 양쪽이 나온다 · h2h 불변 · 가격 없으면 안 넣음 ·
라인 부호(홈/원정) · 미국식 환산은 from_american · 핸디는 소수 그대로 ·
라이브 북 제외 · 축구 파서 불변 · 콜 수 불변 · 라인 값이 실린다 · 실측 숫자 재현.
