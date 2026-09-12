# SOC-5 — 위성이 경기의 리그를 모른 채 어댑터를 불렀다. 축구는 늘 빈손.

## 왜

실측 2026-09-12 22:11 (운영 수동 실행) — 대상 12경기 **전부**:

```
[satellite] 축구 (리그 없음) — 이 리그는 위성 소스가 없다
[satellite] 수집 사이클 — 대상 12경기 · 기사 0건 (soccer)
```

`_DUE_SQL` 이 `league` 를 뽑지 않고, `run_satellite` 가 만드는 `jg` 에도
그 키가 없다:

```python
_DUE_SQL = "SELECT id, sport, home, away, starts_at FROM games ..."
jg = {"sport": …, "game_id": …, "home": …, "away": …, "starts_at": …}
```

야구 어댑터는 리그를 안 보므로 **아무도 몰랐다.** 축구 어댑터는 리그로 소스를
가르므로(`_SOCCER_SOURCE`) 전부 "소스 없음"으로 떨어졌다.

🔴 **그래서 SAT-S1~S3 의 축구 위성은 `run_satellite` 를 통해서는 한 번도
   재료를 가져온 적이 없다.** 실측은 전부 `gather_soccer` 를 **직접** 부른
   것이었다 — 기억해 둔 "프로브 ≠ 파이프라인"에 정확히 걸렸다. 이번에는
   반대 방향이다: 프로브는 되는데 파이프라인이 안 됐다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "_DUE_SQL" app/          satellite.py 정의 · run_satellite 1회
$ grep -rn "run_satellite" app/     scheduler.py 1회 (주기 잡)
어댑터가 jg 에서 읽는 키:
  gather_mlb/kbo/npb  → sport · game_id · home · away · starts_at
  gather_soccer       → + **league**   ← 유일하게 더 읽는 것
```

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `_DUE_SQL` 선택 칼럼 | `league` 추가 | 아니다 |
| `jg["league"]` | 새 키 | 아니다. 야구 어댑터는 안 읽는다 |

⚠️ DB 스키마·Redis·env·프롬프트를 건드리지 않는다. `games.league` 는 이미 있다.

## ③ 리그·종목·경로 분기

분기를 만들지 않는다. **모든 종목에 같은 키를 넣는다** — 야구는 안 읽을 뿐이다.
종목별로 다른 jg 를 만들면 그것이 곧 다음 사본이다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **야구 동작이 바뀐다** ← 반대 위험 | 야구 jg 키 전수와 sport 값을 계약으로 고정 |
| SQL 만 고치고 jg 를 안 고친다(또는 반대) | 계약을 둘로 나눴다 — SQL 문자열 · 어댑터가 받는 값 |
| `league` 가 NULL 인 경기 | 축구 어댑터는 지금도 "(리그 없음)" 로그를 남긴다(SAT-S1). 그대로 둔다 |

⚠️ **아직 못 잰 것**: 고친 뒤 축구 위성이 경기당 몇 건을 긁는가.
   직접 호출 실측은 111건(SAT-S2)이었지만 파이프라인 경로는 처음이다.

## ⑤ 이미 있는 사실을 다시 적는가

- 리그 라벨을 위성이 다시 만들지 않는다 — `games.league` 를 그대로 싣는다.
- "소스 없는 리그" 로그는 이미 `gather_soccer` 에 있다. 여기서 또 판단하지 않는다.
