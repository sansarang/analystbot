# ACL-3 — FotMob 적재가 **가짜 ext_id** 를 돌려줘 슬레이트에 한 건도 안 들었다

## 왜

ACL 8경기를 저장하고도 러너가 판정에 못 갔다. 세 번 돌려 세 번 다 같았다:
```
[fotmob] acl 적재 — 슬레이트 172 · 해당 8 · 저장 8 · 제외 0
📌 2026-09-15 축구 5경기                      ← ACL 0경기
[v3]·[prob]·[verdict] 줄 = 0
```
DB 에는 분명히 있다:
```
슬레이트 쿼리(KST 09-15) → 6건
   fotmob:6049977  [ACL엘리트] Công An Hà Nội @ Gamba Osaka 10:00Z
   … 6건
```

🔴 **축구는 슬레이트를 DB 에서 다시 읽지 않는다.** `ext_id` 재조회 분기
   (`pipeline.py:1476`)는 **야구 전용**이다(`if sport == "kbo"` 안에 있다).
   축구는 `_load_soccer_fixtures` 의 **반환값이 곧 슬레이트**다:
```python
game_rows = await pool.fetch(
    "SELECT * FROM games WHERE sport = $1 AND ext_id = ANY($2::text[])", sport, ext_ids)
```
   그런데 ACL-1 이 심은 줄은
```python
out += [f"fotmob:{_k}"] * int(_r.get("saved") or 0)     # → 'fotmob:acl' × 8
```
   실제 `ext_id` 는 `fotmob:6049977` 이다. **하나도 안 맞는다.**

⚠️ 이건 ACL-1 이 만든 세 번째 회귀다(ACL-2 가 둘). 같은 뿌리다 —
   **새 소스를 붙이며 반환 계약을 확인하지 않았다.** `upsert_games_from_*` 는
   전부 "적재한 ext_id 목록"을 돌려주는데 나만 개수를 돌려줬다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
fotmob.upsert_slate            ← pipeline._load_soccer_fixtures (유일 호출부)
_load_soccer_fixtures 반환값   ← pipeline: SELECT … WHERE ext_id = ANY($2)
  ⚠️ 형제: upsert_games_from_football_data · upsert_games_from_odds_events
     둘 다 **ext_id 목록**을 돌려준다. 계약을 맞춘다.
```

## ② 깨뜨릴 수 있는 기존 동작

- `upsert_slate` 반환값 모양이 바뀐다. 호출부는 하나뿐이고 계약이 잠근다.
- 🔴 **개수와 목록을 같이 돌려준다** — `saved` 를 없애면 로그가 약해진다.
  `ext_ids` 를 더하고 `saved == len(ext_ids)` 를 계약이 단언한다.

## ③ 되돌리기

커밋 1개 revert 로 끝난다. 스키마·설정·데이터 변경이 없고, 바뀌는 것은
`upsert_slate` 반환 dict 에 `ext_ids` 칸이 하나 느는 것과 호출부 한 줄뿐이다.
이미 적재된 `fotmob:%` 경기 행은 그대로 두어도 무해하다 — 되돌리면 슬레이트에
안 들 뿐이고 잘못된 값이 남지는 않는다.

## ④ 측정

`repro_acl3.py` 재실행 + 러너에서 `축구 N경기` 가 ACL 을 포함하는지.

## ⑤ 계약

```
test_upsert_slate가_실제_ext_id를_돌려준다
test_saved와_ext_ids_길이가_같다
test_제외된_경기는_ext_ids에_없다              ← 조용한 누락 방지
test_형제_적재함수와_반환_계약이_같다
```
