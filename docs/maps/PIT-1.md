# PIT-1 영향 지도 — 투구수를 파서가 뽑는데 DB 가 버렸다

## 1. 무엇이 틀렸나 (실측 원문)

파서는 이미 뽑고 있다:

```python
# app/collectors/mlb_boxscore.py:52-68
pit = st.get("numberOfPitches")
if pit is None:
    pit = st.get("pitchesThrown")
...
row["pitches"] = pit
```

KBO 박스스코어에도 투구수 칸이 있고(`kbo_boxscore.py:95` 헤더 목록),
NPB 야후 파서도 넣는다(`yahoo_npb.py:359`).

그런데 표에 그 칸이 없다:

```
pitcher_appearances: ['id','game_id','sport','team','opponent','pitcher',
                      'is_starter','innings','batters','hits','hr','k','bb',
                      'r','er','source']
```

그래서 적재(`pitcher_log._UPSERT`)에서 통째로 사라지고, 내보내기는 이렇게 적는다:

```json
"pitches": null, "pitches_reason": "투구수 저장 없음"
```

투구수는 **한도 신호의 원천**이다(로커 65구). 없으면 `innings_cap_flag` 를
지어낼 수밖에 없다.

## 2. 어디를 고치나

| 파일 | 무엇 |
|---|---|
| `db/schema.sql` | `pitcher_appearances.pitches INT` |
| `app/collectors/pitcher_log.py` | INSERT·UPDATE 에 한 칸 |
| `app/export/for_fable.py` | `days_rest` · `innings_cap_flag` 순수 함수 + 배선 |

## 3. 영향 지도 5문

**① 소급은 어떻게 되나.**
**이미 도는 잡이 채운다.** `mlb_boxscore.backfill(APPEARANCE_DAYS=21)` ·
`npb_boxscore.backfill(28)` 이 일일 잡(`mlb_lineup_history` 05:15 등)으로
돌고, `_UPSERT` 가 `ON CONFLICT … DO UPDATE` 라 기존 행이 갱신된다.
**새 요청 0** 이고, 내일 아침이면 21~28일치가 채워진다.

**② 컬럼을 늘리면 기존 쓰기가 깨지나.**
아니다. `ADD COLUMN IF NOT EXISTS` 이고 nullable 이다. `_UPSERT` 의 자리표가
하나 늘지만 호출부는 한 곳(`record_appearances`)뿐이다.

**③ `innings_cap_flag` 를 모르면 무엇을 내나.**
🔴 **`None` 이다. `False` 가 아니다.** "한도가 없다"와 "모른다"는 다르고,
읽는 쪽이 `False` 를 "한도 없음"으로 읽으면 그게 곧 틀린 확신이다.
계약이 투구수 없는 입력에 `None` 이 나오는지 확인한다.

**④ 문턱 75 는 어디서 왔나.**
지시문 2-5 가 준 값이다(최근 3등판 중 2회 이상 ≤75). 내가 정한 값이 아니므로
상수로 두고 주석에 출처를 적는다. 바꾸려면 근거가 따로 있어야 한다.

**⑤ 오프너 뒤 등판은 어떻게 세나.**
"선발 아닌 투수가 1회를 시작"이 로그에 남아야 센다. 지금은 그 판단 재료가
없으므로 **인자로 받되 기본 0** 이다 — 세는 쪽이 생기면 넘기면 된다.
지어내지 않는다.

## 4. 안 하는 것

- 박스스코어를 지금 다시 긁지 않는다(일일 잡이 한다).
- 투구수를 판정 입력에 잇지 않는다 — 내보내기 표시값이다.
- KBO·NPB 파서를 손대지 않는다(이미 뽑고 있다).
