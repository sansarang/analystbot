# ODN-2 영향 지도 — MLB 팀토탈·F5 를 버리지 않는다

## 1. 무엇이 틀렸나 (실측 원문)

ESPN core API (오늘 MLB 15경기, 컨테이너에서 1회 호출):

```
odds items 1건 · provider DraftKings
최상위 키: ['awayTeamOdds','current','details','homeTeamOdds','initialOverUnder',
           'initialSpread','links','moneylineWinner','open','overOdds',
           'overUnder','price','provider','spread','spreadWinner','underOdds']
'teamtotal' 포함: False   'first five' 포함: False   '5 innings'… 포함: False
```

**ESPN 은 주지 않는다.** 그런데 odds-api.net 은 준다 (같은 방식으로 1회 호출,
신시내티-컵스 3,664행):

```
bet_type × period 분포
   player prop      full time        2401
   total            full time         340
   handicap         full time         189
   team total       full time         182   ← 팀토탈
   handicap         5 innings          47
   total            5 innings          40   ← F5 총점
   moneyline        5 innings          16   ← F5 승패
   total            1st inning         41
   handicap         3 innings          37
   handicap         7 innings          33
```

우리 수집기가 둘 다 버리고 있었다. 이유는 코드 두 줄이다:

```python
LEAGUES = {"kbo": "Korean KBO", "npb": "Japan NPB"}   # MLB 가 없다
PERIOD = "full time"                                   # 5이닝을 버린다
```

`LEAGUES` 옆 주석은 "MLB·축구는 ESPN 무료로 이미 된다"였는데, **이 두 마켓에는
그 전제가 틀렸다** — 위 실측이 그것을 보여준다.

⚠️ 팀토탈 **파싱은 이미 맞게 돼 있다**(`name = f"{team} {direction}"`, 팀은
`side` 필드). 고칠 것은 "어느 리그·어느 기간을 통과시키나"뿐이다.

## 2. 어디를 고치나

`app/collectors/oddsapinet.py` — `LEAGUES` · `PERIOD` → `PERIODS` · `to_rows` 분기.

## 3. 영향 지도 5문

**① 5이닝을 같은 칸에 넣으면.**
디빅이 통째로 어긋난다. 5이닝 총점 3.5 와 정규 총점 8.5 는 **다른 시장**이고,
한 칸에 섞이면 `implied_probs` 가 서로 다른 사건의 확률을 합쳐 1.0 으로 만든다.
그래서 `totals_f5`·`h2h_f5` 로 **칸을 나눈다**. 종전 주석이 이미 그 경고를 적고
있었고, 이 수정은 그 경고를 지키는 쪽이다.

**② 새 market 값이 기존 소비자를 깨나.**
현재 값은 `h2h`(48,597) · `spreads`(22,180) · `totals`(19,093) · `team_totals`(6,792)
넷이다. `_f5` 는 새 값이라 기존 질의(`market='totals'` 등)에 걸리지 않는다.
읽는 쪽이 아직 없으므로 **쌓아두는 값**이고, 소비자가 생기면 이 형식을 쓴다.

**③ 정규 승패를 싣게 되나.**
아니다. `moneyline` + `full time` 은 그대로 버린다 — oddsportal 이 이미 그 칸을
채우고, 두 소스가 같은 칸을 채우면 디빅이 흔들린다. **F5 승패만** 새로 싣는다
(그 칸은 아무도 안 채운다).

**④ 모르는 기간이 들어오면.**
`1st inning`·`3 innings`·`7 innings` 도 실제로 온다. **아는 칸만 싣는다** —
모르는 기간을 실으면 그게 어느 시장인지 읽는 쪽이 알 수 없다. 계약이 셋을
버리는지 확인한다.

**⑤ 크레딧이 늘어나나.**

🔴 **처음에 "0이다"라고 적었고 그것은 틀렸다.** 코드를 다시 읽고 잡았다:

```python
for sport in ON.LEAGUES:        # ← 잡이 LEAGUES 를 그대로 돈다
    evs = await ON.fetch_events(sport)
```

`LEAGUES` 에 MLB 를 넣는 순간 잡이 MLB 를 긁는다. 실측으로 MLB 는 창 안에
**27경기**이고, 경기마다 스냅샷 1콜 × 하루 2회 = **월 1,620콜**이다.
월 1,000 크레딧이 터지고 다음 달까지 이 소스가 통째로 죽는다 — KBO·NPB 까지
같이 죽는다.

그래서 **두 목록을 나눴다**:
- `LEAGUES` — 파서가 읽을 수 있는 리그(MLB 포함)
- `JOB_LEAGUES = ("kbo", "npb")` — 정기 잡이 **실제로 긁는** 리그

"파서가 읽을 수 있다"와 "정기로 긁는다"는 다른 말인데 한 이름을 쓰고 있었다.
MLB 는 게이트 대상 경기만 따로 긁는다(ODN-3). 이 단위의 요청 증가는 0이다.

## 4. 안 하는 것

- 잡을 건드리지 않는다(요청 0 증가).
- 내보내기에 싣지 않는다 — 그건 EXP-5 다.
- `player prop` 2,401행은 버린다. 우리 모델에 읽는 곳이 없다.
