# LDG-1 영향 지도 — 원장에 판정자(judge_by)

## 1. 무엇이 틀렸나 (재현 원문)

```
$ PYTHONPATH=. uv run pytest tests/ledger/test_1_4_judge_by.py -q -x
AssertionError: judge_by                                             exit=1

운영 DB:
  SELECT column_name … WHERE table_name='pick_ledger' AND column_name ILIKE '%by%'
  →  ['regraded_by']            ← 판정자를 적는 칸이 없다
  SELECT count(*) t, count(structure_pick) s FROM pick_ledger
  →  t=1382,  s=0               ← 파생 마켓 픽을 적은 적이 한 번도 없다
```

사람이 건 픽(페이블 채팅 판정 · 승률 모드)을 봇 판정과 **같은 game_id 로 나란히**
둘 수 없다. 그러면 "봇 vs 페이블"을 숫자로 비교할 수 없다(지시문 7-2).

## 2. 어디를 고치나

| 파일 | 무엇 |
|---|---|
| `db/schema.sql` | 컬럼 5개 ALTER · 유니크 인덱스 재정의 |
| `tools/ledger_add.py` (신규) | 사람이 한 줄 넣는 도구 |

## 3. 영향 지도 5문

**① 유니크를 넓히면 무엇이 풀리나.**
`(game_id) WHERE is_final` → `(game_id, judge_by) WHERE is_final`.
⚠️ **`judge_by` 가 NULL 이면 유니크가 풀린다** — Postgres 는 유니크 인덱스에서
NULL 을 서로 다른 값으로 본다(기본 `NULLS DISTINCT`). 그래서 컬럼을
`NOT NULL DEFAULT 'bot_v14'` 로 만든다. 기존 1,382행이 그 자리에서 채워지고
(PG11+ 는 표를 다시 쓰지 않는다) NULL 이 없으니 유니크가 온전하다. → FORKS F-19

**② `CREATE UNIQUE INDEX IF NOT EXISTS` 로 충분한가.**
아니다. **이미 있으면 아무 일도 하지 않는다** — 옛 정의가 그대로 남고 새 정의는
적용되지 않는다. 그래서 `DROP INDEX IF EXISTS` 를 먼저 둔다. 계약이 DROP 이
CREATE 앞에 있는지 센다.

**③ 기존 쓰기 경로가 깨지나.**
`pick_ledger.record_*` 는 `judge_by` 를 적지 않는다 → 기본값 `bot_v14` 가 들어간다.
`ON CONFLICT (game_id)` 를 쓰는 곳이 있으면 인덱스가 바뀌어 터진다 —
`rg "ON CONFLICT" app/engine/pick_ledger.py` 로 확인하고, 있으면 충돌 대상을
함께 고친다.

**④ 새 컬럼이 판정에 끼어드나.**
아니다. `judge_by`·`market`·`market_side`·`line`·`odds_taken` 은 **기록 전용**이다.
판정 경로(`prior`·`gate`·`hypothesis`·`confidence`)는 이 칸들을 읽지 않는다.
읽는 것은 리포트(1-5)와 비교(7-2)다.

**⑤ 무엇이 조용히 0이 되나.**
도구가 모르는 판정자·마켓을 받으면 **거부하고 1로 나간다**. 조용히 NULL 로
넣으면 유니크가 풀리고(①) 집계에서 사라진다. 계약이 거부를 확인한다.

## 4. 안 하는 것

- 기존 1,382행의 다른 칸을 손대지 않는다. 채워지는 것은 `judge_by` 기본값뿐이다.
- 채점·CLV 자동 기입은 여기서 하지 않는다(7-3).
- `predicted_side`(home|away)의 뜻을 넓히지 않는다 — over/under 는 `market_side` 다.
