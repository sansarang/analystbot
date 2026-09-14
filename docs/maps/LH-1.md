# LH-1 — `lineup_history` 에 리그·킥오프 칸 (사용자 지시)

## 왜

소급 적재는 성공했다(**18,507행 · 527경기 · 선수 11,723명**). 그런데
**리그별 건수를 낼 수 없다** — 표에 `game_id`(FotMob id)·`team_id` 만 있고
리그를 묶을 키가 없다. 건수는 백필 함수의 반환값에만 있었고 그 출력은
유실됐다.

사용자 지시: `league`·`kickoff_date` 칸을 더하고 **다음 적재부터 채운다.**
과거분은 **날짜별 목록(24회)만으로** 역매핑해 채우되 **경기 상세 재호출은
금지**. 재크롤 수백 건은 하지 않는다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_lh1.py
  → 🔴 칸이 없다 {'ccode', 'kickoff_date', 'league'}
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
db/schema.sql                     lineup_history 정의(FOT-5)
app/collectors/fotmob.py          save_lineup_history · backfill
tests/test_lineup_history.py      계약
   → 읽는 곳(주전 판정)은 아직 없다 — 지금 고치기 가장 싼 때다
```

## ② 만드는/바꾸는 상태

| 무엇 | 성격 |
|---|---|
| `lineup_history.league` · `.ccode` · `.kickoff_date` | **칸 셋 추가**(`ADD COLUMN IF NOT EXISTS`) |

기존 18,507행은 **NULL 로 남는다.** 역매핑이 채우는 만큼만 찬다 —
못 채운 행을 "리그 없음"으로 읽지 않는다(NULL 이 곧 "모른다").

🔴 **역매핑은 날짜별 목록만 쓴다**(`matches?date=`). 경기 상세는 **부르지
   않는다**(사용자 지시). 목록에 `id·ccode·league·utc` 가 다 들어 있어
   그것만으로 `game_id → (리그, 킥오프)` 를 만들 수 있다.

## ③ 리그·종목·경로 분기가 생기는가

생기지 않는다. 축구만 쓰는 표다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 역매핑에서 못 찾은 `game_id` 는 **건드리지 않는다**. 갱신 행 수를 날짜별로
  찍어 "몇 건이 남았는지"가 로그에 남는다.
- 리그별 집계는 NULL 을 **별도 줄**로 보여준다 — 0으로 합치지 않는다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 국가 코드 목록은 `BACKFILL_CCODES` 원본.
- 날짜 목록 호출은 `slate()` 원본(간격 2초 포함).
