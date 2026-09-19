# LIN-1 영향 지도 — KBO·NPB 확정 시각이 한 번도 안 적혔다

## 1. 무엇이 틀렸나 (실측 원문)

```
최근 7일 확정 시각 분포
   npb: 33경기 · 확정 0 · 평균 T-None분
   kbo: 61경기 · 확정 0 · 평균 T-None분

오늘 지금
   npb g10759 14:00  status=confirmed  at=None
   npb g10755 14:00  status=confirmed  at=None
   npb g10758 14:00  status=confirmed  at=None
```

상태는 `confirmed` 로 올라가는데 **시각이 안 적힌다.**

확정을 쓰는 경로가 **둘**이고 한쪽만 시각을 적기 때문이다:

```sql
-- app/collectors/lineups.py:258  (MLB)
SET lineup_status = $2,
    lineup_confirmed_at = CASE WHEN $2='confirmed' THEN now() ELSE lineup_confirmed_at END

-- app/pipeline.py:785  sync_lineup_status  (KBO·NPB)
SET lineup_status = 'confirmed', updated_at = now()          ← 시각이 없다
```

그래서 MLB 는 "라인업이 T-190분에 떴다"를 잴 수 있고(1-2 에서 15경기 표를
냈다), KBO·NPB 는 **영원히 못 잰다.** 내보내기의 `lineup.posted_kst` 도 같은
이유로 두 리그에서 null 이다.

## 2. 어디를 고치나

`app/pipeline.py` `sync_lineup_status` 의 UPDATE 한 줄.

## 3. 영향 지도 5문

**① 왜 두 경로가 있나.**
MLB 는 statsapi 라 `lineups.py` 가 쓰고, KBO·NPB 는 크롤러 스냅샷이라
`promote_lineup_status` → `sync_lineup_status` 가 쓴다. 주석이 이미
"종전에는 KBO 블록 안에만 있었다"는 같은 종류의 사고를 적고 있다 —
**같은 사실을 두 곳이 쓰면 한 곳이 빠진다.**

**② 이미 적힌 시각을 덮나.**
🔴 덮지 않는다. **첫 확정이 사실**이다. 재판정 때마다 갱신하면 T-N 이 0 에
수렴해 "라인업이 경기 직전에 떴다"는 거짓이 된다.
`COALESCE(games.lineup_confirmed_at, now())` 로 첫 값을 지킨다.

**③ MLB 를 건드리나.**
아니다. 계약이 `lineups.py` 의 `CASE WHEN` 이 그대로인지 센다 — 고치려다
이미 되던 쪽을 깨는 것이 이 저장소의 반복 사고다.

**④ 과거는 소급되나.**
안 된다. 지난 7일의 확정 시각은 **영영 모른다** — 그때 안 적었다.
소급으로 `now()` 를 넣으면 그건 지어내는 것이다. 내일부터 쌓인다.

**⑤ 무엇이 조용히 0이 되나.**
이 수정 뒤에도 하루는 표본이 0이다. 그래서 1-2 같은 표를 KBO·NPB 로 내려면
**내일 슬레이트를 기다려야 한다** — 그 사실을 보고에 적는다.

## 4. 안 하는 것

- 과거 시각을 지어내지 않는다.
- `lineups` 표에 KBO·NPB 행을 새로 만들지 않는다(→ 2-9-b 로 등록).
- 크롤러·폴러 주기를 건드리지 않는다.
