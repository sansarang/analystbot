# MBL-2 — 선발 투수를 식별하지 못했다 (`isStarter` 는 없는 키다)

## 왜

MBL-1 적재 실행 결과: 2024시즌 **2,429경기 전부 `home_sp = NULL`**.

```
2024  {'games': 2432, 'pitch': 20723, 'bat': 50817, 'requests': 2433, 'sec': 32.3}
시즌별 적재
   2024  경기 2429   선발있음 0   ← 전부 비었다
```

원인: 내가 `player["gameStatus"]["isStarter"]` 를 가정했는데 **그 키가 없다.**
실측(statsapi boxscore 원문):
```
gameStatus: {'isCurrentBatter': False, 'isCurrentPitcher': False,
             'isOnBench': False, 'isSubstitute': False}      ← isStarter 없음
stats.pitching: {'gamesPlayed': 1, 'gamesStarted': 1, ...}   ← 여기 있다
teams.home.pitchers: [571760, 592351, ...]                   ← 첫 번째가 선발
```

**선발은 야구 모델의 가장 큰 입력이다**(지시문: "선발 하나가 승률을 10%p 넘게
움직이는 종목"). 이게 비면 3단계 선발 축이 통째로 사전값이 된다.

## ① 이 함수/상태를 읽는 곳 **전부**
```
load.parse_pitching → role("SP"/"RP")
load.starters       → games.home_sp / away_sp
3단계 model.sp_ra9  (아직 없음)
```

## ② 만드는/바꾸는 상태
| 상태 | 성격 |
|---|---|
| `parse_pitching` 의 `role` 판정 | `gamesStarted == 1` 우선, 없으면 `pitchers[0]` |

🔴 두 신호를 **둘 다** 쓴다 — 하나가 빠진 응답이 있을 수 있고, 조용히 NULL 이
   되는 것이 이번 결함의 본질이다.

## ③ 리그·종목·경로 분기

분기를 만들지 않는다. 선발 판정은 종목과 무관하게 `gamesStarted` 하나로 하고,
KBO·NPB 는 6단계에서 각자 소스의 동등한 신호를 찾아 같은 `role` 값을 채운다.

## ④ 조용히 실패하는가
| 위험 | 대응 |
|---|---|
| 🔴 **또 전부 NULL 이 된다** | 두 신호 각각의 계약 + 적재 후 `선발있음` 수를 표로 확인 |
| 폴백이 잘못된 투수를 고른다 | `pitchers[0]` 는 등판 순서다. 계약이 두 번째를 RP 로 단언 |
| 이미 적재된 2024 가 그대로 남는다 | 재적재로 덮는다(upsert) |

⚠️ 못 잰 것: 옛 시즌(2018~2020)에도 `gamesStarted` 가 있는가. 재적재 표로 확인한다.

## ⑤ 사본
- 선발 판정을 3단계에서 다시 하지 않는다 — `role` 이 원본이다.
