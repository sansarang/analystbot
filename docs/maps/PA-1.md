# PA-1 — `adjust` 가 문자열 `starts_at` 에서 전건 실패한다

## 왜

PART A 실측(2026-09-16 09:50 KST · 커밋 `9ca4ef8` · MLB 2경기)에서 경기당 4건,
합 8건이 같은 원인으로 죽었다:

```
[adjust] game=8312 home 주전결장 실패: invalid input for query argument $3:
  '2026-09-16T01:38:00+00:00' (expected a datetime.date or datetime.datetime
  instance, got 'str')
[adjust] game=8312 away 주전결장 실패: (같음)
[adjust] game=8312 불펜 연투 실패: 'str' object has no attribute 'date'
[adjust] game=8312 이동연전 실패: (같음)
```

`attach` 는 `jg["starts_at"]` 을 **그대로** 쓴다. 파이프라인이 넣는 값은 ISO
**문자열**이라 asyncpg 의 TIMESTAMPTZ 파라미터에 못 들어가고, `starts.date()`·
`starts - timedelta(...)` 도 문자열에서 터진다.

🔴 **U8 가중이 통째로 죽는다.** 주전결장·불펜연투·이동연전이 전부 `missing`
으로 빠지고, `main_axis`(결정축)는 |contrib| 상위로 뽑으므로 **뽑을 것이
없어진다.** PART A 에서 `main_axis` 0/2 였던 것과 맞물린다.

⚠️ CLAUDE.md 가 이미 적어둔 종류다 — ODP-2·LH-2 의 원인이 같았다
(`$n::date` 는 `datetime.date`, TIMESTAMPTZ 는 `datetime` 이어야 한다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
adjust.attach(jg, pool)                    ← 고치는 곳
  ├ _REGULARS  $3 = starts   (TIMESTAMPTZ 비교)
  ├ _PEN       $2,$3 = lo, starts
  ├ _TRIP      $3 = starts
  └ starts.date() · starts - timedelta(...)
starter_recent._aware                      ← **원본 도우미.** 이미 있다
  └ 이미 쓰는 곳: batter_recent:117 · bullpen_recent:148 · branch_resolve:569
     🔴 `adjust` 만 안 쓴다. 그게 이 결함이다.
adjust.attach 를 부르는 곳: pipeline(판정 전 가중 부착)
adjust.axes / contrib_out / importance     ← adj 값을 읽어 결정축을 뽑는다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **새 파서를 만들지 않는다.** `starter_recent._aware` 가 원본이고 이미
  세 모듈이 쓴다. 여기서 `fromisoformat` 을 다시 적으면 사본이 되고,
  원본이 바뀔 때 따라가지 않는다(실사고 2026-09-02 워치독).
- 🔴 **`None` 은 그대로 `None` 이다.** 시간을 모르는 경기를 "지금"으로
  채우면 과거 경기를 미래로 읽는다. `_aware` 가 None 을 주면 종전처럼
  미계산으로 남긴다.
- 🔴 **이미 datetime 인 값은 안 건드린다.** 스케줄러 경로는 asyncpg 가
  datetime 을 주므로 지금도 정상이다 — 거기서 동작이 바뀌면 안 된다.
- ⚠️ 고치면 세 변수가 **처음으로 값을 갖는다.** `p_code` 가 달라질 수 있다.
  그게 목적이지만, 첫 사이클에서 조정 폭을 확인해야 한다(⑨).

## ③ 되돌리기

커밋 1개 revert. 바뀌는 것은 `attach` 안의 한 줄(정규화)뿐이다. 되돌리면
종전처럼 세 변수가 `missing` 으로 빠진다 — 판정은 계속 나온다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 배포 뒤 첫 사이클에서 `[adjust] … 실패`
가 0건이고 `adj_pp` 에 주전결장·필승조연투·이동연전이 실제로 찍히는 원문.

## ⑤ 계약

```
test_문자열_starts_at도_datetime으로_간다
test_이미_datetime이면_그대로                 ← 반대 위험(정상 경로 변경)
test_None이면_미계산으로_남는다                ← 반대 위험(지금으로 채우기)
test_Z접미사도_읽는다
test_파서를_다시_만들지_않았다                 ← 사본 금지 (_aware 를 쓴다)
test_불펜_today는_date다
```
