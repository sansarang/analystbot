# U0-b — 첫 값 태그가 한 행에만 붙었다. 그리고 종목 분기 계약이 없었다

## 왜

SNAP-1 소급 실측(2026-09-15 16:0x KST):
```
backfill_open_tags: {'pairs': 354, 'open': 7, 'open_proxy': 347, 'skip': 0}
NULL 48,547 → 48,193 (99.6% → 98.8%)
g=8199 open_proxy **1행** / None 35행   (ACL 4경기 동일)
```
한 스냅샷의 홈·무·원정은 `captured_at` 이 마이크로초 단위로 다르다(행마다 따로
INSERT 한다). `_TAG_OPEN_SQL` 이 `captured_at = min(captured_at)` 로 잡으니
**세 행 중 하나만** 붙었다. "첫 **값**"은 그 시점의 묶음 전체여야 한다.

그리고 D-10 을 검증할 때 내가 **축구를 야구 규칙으로 쟀다** —
`p_code=0.4473` 이라 "원정"으로 계산했는데, 3-way 최대값(홈 45.1 / 무 27.1 /
원정 27.9)은 **홈승**이다. `code_pick` 이 이미 종목으로 가르는데 그 사실을
잠그는 계약이 없어서, 사람이 같은 실수를 반복할 수 있다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
odds_free._TAG_OPEN_SQL   ← tag_open ← store_rows · backfill_open_tags
prob.code_pick            ← matchup.apply_code_verdict (유일 호출부)
pick_ledger._snap_probs   ← record_move  (snap_tag IS NOT NULL 로 거른다)
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 창을 넓히면 **다음 스냅샷까지 삼킬 수 있다.** 1초로 좁힌다 — 스냅샷 잡은
  분 단위로 돌고(실측: 같은 pass 안의 행들은 같은 초), 다음 회차는 최소 몇 분
  뒤다. 그래도 `NOT EXISTS`(open 계열 이미 있으면 생략)가 2차 방어다.
- 🔴 트리거가 붙인 `pre`·`lineup` 은 여전히 덮지 않는다(`snap_tag IS NULL`).
- ⚠️ 규칙 정정(사용자 2026-09-15): 목표는 NULL 0% 가 **아니다**.
  "경기당 open 계열 **1묶음** + pre/lineup/late/close 각 최신 묶음"이고
  나머지 NULL 은 **이름 없는 중간값으로 정상**이다. 대신 그 NULL 이 이동·CLV
  계산에서 자동으로 빠지는지 계약이 본다.

## ③ 되돌리기

커밋 1개 revert. 데이터는 `UPDATE … SET snap_tag=NULL WHERE snap_tag IN
('open','open_proxy')` 로 되돌린다(멱등이라 다시 붙일 수 있다).

## ④ 측정

`repro_u0b.py` 재실행 + 운영에서 소급 재실행 후 경기당 태그 **묶음** 행수.

## ⑤ 계약

```
test_첫값은_같은_묶음_전체에_붙는다
test_창은_1초다_다음_스냅샷을_삼키지_않는다        ← 반대 위험
test_NULL_행은_이동계산에서_빠진다
test_code_pick이_종목으로_갈린다                    ← 8199 실수 재발 방지
```
