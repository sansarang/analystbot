# SNAP-1 — `snap_tag` 는 있는데 99.6% 가 비어 있다. `open_proxy` 는 아예 없다

## 왜

사용자 지시 2026-09-15. 실측:
```
snap_tag 분포(전체 48,310행)
  (NULL) 48,119 (99.6%)  ·  pre 53 · close 41 · lineup 41 · late 41 · open 15
ACL 7경기 × 24행 = 168행 — 전부 태그 0
```
⚠️ **정정**: 처음에 "컬럼이 없다"고 보고했는데 틀렸다. `db/schema.sql:571` 의
   `ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS snap_tag TEXT` 로
   이미 있다. CREATE TABLE 블록만 읽고 단정했다.

채우는 곳은 **트리거 루프 하나뿐**이다(`scheduler.py:2048-2051`, TRG-1).
오즈포털·무료 배당 적재 경로(`odds_free.store_rows`)는 태그 없이 넣는다.
그래서 `pick_ledger._snap_probs`(`snap_tag IS NOT NULL` 로 거른다)와
`record_move` 가 그 99.6% 를 **못 본다.**

그리고 `open` 의 정의는 킥오프 **T-24h**다(`triggers.KINDS`). 18일간 배당이
차단돼 있었으므로(P2-0) 지금 우리가 가진 첫 값은 진짜 개장가가 아니다 —
ACL 7경기 전부 T-4.7h ~ T-13.0h 에 처음 봤다. 그 둘을 같은 이름으로 부르면
이동 분석이 거짓말을 한다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
odds_snapshots.snap_tag
  ← scheduler.py:2048  트리거 루프가 쓴다(유일한 필자)
  ← pick_ledger._snap_probs(770)  `snap_tag IS NOT NULL` 로 거른다
  ← pick_ledger.record_move(822)  base/now 를 snap_tag 순서로 고른다
  ← triggers.KINDS                이름 원본 (open·pre·lineup·late·close)
odds_free.store_rows            ← 오즈포털·ESPN 등 무료 경로 전량
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **트리거가 붙인 태그를 덮으면 안 된다.** `pre`·`lineup` 이 `open_proxy`
  로 바뀌면 이동 분석의 기준선이 뒤집힌다. 새로 붙이는 것은 **태그가 없는
  가장 이른 행**에만, 그리고 그 (경기·provider) 에 open 계열이 아직 없을 때만.
- 🔴 **`record_move` 의 순서표에 `open_proxy` 를 넣어야 한다.** 안 넣으면
  `order.index()` 가 ValueError 로 터진다 — 이동 분석이 통째로 죽는다.
- ⚠️ 소급 태그는 **한 번만** 의미가 있다. 멱등이어야 하고, 이미 태그가 있는
  행은 건드리지 않는다.

## ③ 되돌리기

커밋 1개 revert + `UPDATE odds_snapshots SET snap_tag=NULL WHERE snap_tag IN
('open','open_proxy') AND provider <> 'theodds'`. 스키마 변경 없음(컬럼은 이미 있다).

## ④ 측정

`repro_snap1.py` 재실행 — NULL 비율과 ACL 7경기 태그 수.

## ⑤ 계약

```
test_open_proxy가_이름표에_있다
test_T24h_이전_첫값은_open_이후는_open_proxy
test_트리거가_붙인_태그를_덮지_않는다        ← 반대 위험
test_이동_순서표에_open_proxy가_있다          ← 반대 위험(ValueError)
test_소급_태그는_멱등이다
```
