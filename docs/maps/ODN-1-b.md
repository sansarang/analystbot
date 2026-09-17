# ODN-1-b — **총점이 한 행도 안 들어온다.** 파서가 모양을 잘못 봤다

## 왜

배포 뒤 ⑨ 실측 2026-09-17:
```
CYCLE npb spreads 2532행 37북 · kbo spreads 1428행 39북
**totals 0행**
```

API 실제 모양(운영에서 직접 확인):
```
total       side=None · line="over 7.5" / "under 7.5" / "even" / "odd"
            → **방향이 `line` 안에 있다.** 나는 side 가 over/under 라고 봤다
team total  side=home/away(팀) · line="over 4.5"
            → **둘 다 있어야** 한 줄이 된다
handicap    side=home/away · line="-1.5"      ← 그래서 이것만 통과했다
```

🔴 **모양을 확인하지 않고 썼다.** 스모크에 내가 지어낸 `side="over"` 를 넣어
   통과시켰고, 그래서 계약도 초록이었다. ⑨ 가 다시 잡았다.

⚠️ `even`·`odd` 는 **홀짝**이다 — 총점과 다른 시장이고 라인이 없다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
oddsapinet.to_rows            ← 고치는 곳
oddsapinet.MARKET_MAP         ← 그대로
odds_free.store_rows          ← 적재. 그대로
structure.derived_probs       ← totals 를 먹는 쪽(Over/Under 두 쪽 필요)
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **핸디는 지금 잘 들어온다** — 건드리지 않는다. 계약이 잰다.
- 🔴 **홀짝은 버린다.** 라인이 없고 총점이 아니다.
- 🔴 **정규 이닝만**(종전 규칙 유지). 실측 period 분포: full time 271 ·
  1st inning 50 · 5 innings 41 · 3 innings 13.
- 🔴 **팀토탈은 팀 + 방향이 둘 다 필요**하다. `side` 를 `"{팀} Over"` 로 적는다.
  ⚠️ **읽는 쪽이 아직 없다**(`structure` 는 spreads·totals 만 본다). 그래서
     이건 **쌓아두는 값**이고, 소비자가 생길 때 그 형식을 쓰면 된다. 지금
     지어낸 형식이 나중에 걸림돌이 되지 않도록 계약에 적어 둔다.
- ⚠️ 같은 라인이 여러 북에서 온다 — 그게 정상이고 디빅이 북별로 이뤄진다.

## ③ 되돌리기

커밋 1개 revert (파서 한 덩어리).

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 운영에서 다시 돌려 `totals` 행이
실제로 쌓이는지 본다(⑨).

## ⑤ 계약

9건 — 총점 over/under 두 줄 · 라인을 문자열에서 뽑는다 · 홀짝 제외 ·
팀토탈이 팀+방향을 갖는다 · **핸디 불변** · 정규 이닝만 · 닫힌 배당 제외 ·
승패 제외 · 실측 모양 그대로 재현.
