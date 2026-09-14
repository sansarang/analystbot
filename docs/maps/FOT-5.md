# FOT-5 — 선발 이력 테이블 + 시즌 소급 적재 (사용자 지시)

## 왜

주전 판정("최근 10경기 선발 출장 수")을 **id 기준**으로 하려면 이력이 있어야
하는데 우리 DB에 없다. 그리고 FotMob 은 과거 날짜도 준다 — 실측:
```
20260906  Frosinone vs Venezia  lineupType=standard · 선발 11(id) · 벤치 15
20260823  Frosinone vs Juventus lineupType=standard · 선발 11(id) · 벤치 12
```
즉 **개막~오늘 소급 적재가 가능하다.**

🔴 **함정 하나를 실측이 잡았다** — 리그 이름이 겹친다. `"Serie A"` 로 거르면
   **에콰도르 세리에A**(Delfín vs Técnico Universitario)가 섞인다. 국가 코드
   (`ccode`)로 걸러야 한다. 사용자가 준 목록: ITA·ESP·ENG·GER·FRA·NED·KOR·JPN·POR.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_fot5.py
  → lineup_history 테이블: 없음
```

## ① 이 함수/상태를 읽는 곳 **전부**

새 표라 지금은 없다. 쓰는 곳 둘:
```
fotmob.save_lineup_history(pool, ...)  ← T-60 이후(confirmed) · 경기 후(standard)
tools/backfill_lineups.py              ← 소급 적재(1회성)
```
읽는 곳(다음 단위): 주전 판정 — 출장률.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `lineup_history` | **새 표.** (game_id, team_id, player_id, player_name, started, minutes, lineup_type, kickoff_utc) |

사용자가 칸을 지정했다. 같은 (game_id, team_id, player_id, lineup_type) 은
한 행이다 — 두 시점(confirmed·standard)을 **따로** 남긴다.

⚠️ `game_id` 는 **FotMob match id** 다. 우리 `games.id` 와 다르다 — 소급
   적재는 우리 일정에 없는 경기도 담기 때문이다. 우리 경기와 잇는 것은
   읽는 쪽의 일이고, 그 이음줄은 `fotmob_match_id` 로 따로 둔다.

## ③ 리그·종목·경로 분기가 생기는가

축구만이고, 리그는 **국가 코드 화이트리스트**로 거른다. 코드에 리그 이름을
적지 않는다(이름이 겹치는 것이 오늘의 실측 결함이다).

## ④ 실패하면 "시끄럽게" 실패하는가

- 소급 적재는 날짜별·리그별 **적재 경기 수**를 찍는다. 0이면 0이라고 남긴다.
- 선수 id 가 없는 행(실측: 에콰도르 리그에 `id=0` 이 있었다)은 **건너뛰고**
  센다 — 0을 키로 쓰면 서로 다른 선수가 한 사람이 된다.
- 요청 간격은 `fotmob.MIN_GAP_SEC`(2초) 원본을 그대로 쓴다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 스키마는 `db/schema.sql` 한 곳(스케줄러 기동 시 적용).
- 파싱은 `fotmob.parse_lineup` 원본. 간격·헤더도 그 모듈 상수.
