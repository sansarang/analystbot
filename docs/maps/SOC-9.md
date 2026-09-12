# SOC-9 — Flashscore 라인업을 `lineups` 테이블에 저장한다

사용자 지시 2026-09-13: "lineups 테이블에 저장해라"

## 왜

실측 2026-09-12 23:52 (운영). 라인업이 **캐시에만** 있고 DB에는 없다:
```
games        lineup_status · lineup_confirmed_at   ← 상태만, 명단 없음
lineups      804행 · 전부 야구 (source=statsapi …)
```
같은 실행에서 12경기 전부 "라인업 아직 미발표"였다 — 킥오프 **68분 전**이라
피드에 아직 없었다. **배선은 돌았지만 끝까지 가본 적이 없다.**

## ① 읽는 곳 전부
```
satellite.run_satellite(pool, …) → gather(jg, redis, …) → _ADAPTERS[sport]
   pool 이 어댑터까지 오지 않는다  ← 고칠 자리
save_lineup(pool, game_id, side, status, source, parsed, caller=) — 야구가 쓰는 원본
```
빌려 쓰는 원본: `collectors.lineups.save_lineup` · `satellite._article`

## ② 상태
| 상태 | 성격 |
|---|---|
| `gather(..., pool=None)` | 인자 추가. 야구 어댑터는 **안 받는다**(soccer 만 전달) |
| `lineups` 행 | `source='flashscore'` · `batting_order`=선발 11명 · `starter`=포메이션 |

🔴 **새 테이블·새 컬럼을 만들지 않는다.** 야구가 쓰는 자리 그대로다.
🔴 `save_lineup` 은 타순 9가 아니면 `[lineups-anomaly]` 를 남긴다 — 축구는 11
   이라 매 경기 남는다. **그래서 축구는 그 경로를 타지 않고 직접 INSERT 한다**
   (같은 SQL·같은 충돌키). 야구 계측을 축구 소음으로 덮지 않는다.

## ③ 분기
축구만 pool 을 받는다. 야구 어댑터 시그니처는 건드리지 않는다.

## ④ 조용히 실패하는가
| 위험 | 대응 |
|---|---|
| 🔴 DB 저장 실패가 재료까지 없앤다 | try/except + 경고. 기사는 그대로 반환(계약) |
| 🔴 pool 이 안 와서 저장 0건 | `gather`·`run_satellite` 소스에 `pool=pool` 단언 |
| 라인업이 아직인데 빈 행을 쓴다 | 선발 0명이면 **아무것도 안 쓴다**(계약) |
| 야구 라인업 경로가 바뀐다 | `save_lineup` 을 고치지 않는다. 축구는 자체 INSERT |
| 충돌키가 달라 중복 쌓인다 | `(game_id, side, source, status)` — 야구와 같은 키 |

⚠️ 못 잰 것: 킥오프 1시간 안에서 12경기 중 몇 건이 실제로 채워지는가.
   이번 재분석에서 **처음으로** 잰다(01:00·01:30 경기가 창 안에 들어왔다).

## ⑤ 사본
- 테이블·컬럼·충돌키를 새로 정하지 않는다 — 야구가 쓰는 그대로.
- 팀 정규화·경기 매칭을 다시 만들지 않는다 — `tm_key` · `FS.find_fixture`.
