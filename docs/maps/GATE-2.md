# GATE-2 — 사전값·게이트를 아무도 부르지 않는다 (PRI-1·GATE-1 배선)

## 왜

`PRI-1`(티어 사전값)·`GATE-1`(괴리 게이트)이 순수 함수를 만들었지만 **호출부가
0** 이었다. `pick_ledger.p_prior·prior_src·gate_reason` 은 영원히 NULL 이었고,
Part 4 조건 A("게이트 분류가 시장 과대/가치 의심이고 |gap| ≥ 4")가 읽을 값이
없었다. 오늘 티어 표가 채워졌으므로(192/193) 계산할 값이 생겼다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_gate2.py
  → ImportError: cannot import name 'record_prior' from 'app.engine.pick_ledger'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "prior\.\|gate\.classify\|p_prior\|prior_src\|gate_reason" app/ tests/
app/engine/prior.py    load_tiers · team_elo · soccer_prior · baseball_prior · form_pp
app/engine/gate.py     classify · select
   → 둘 다 app/ 안 호출부 **0** (analyze.build_input 이 문자열로만 언급)
pick_ledger.p_prior·prior_src·gate_reason  → 쓰는 곳 0 · 읽는 곳 0
```
쓰는 자리는 `record_analysis` 안, `record_clv`·`record_move` 옆이다 — 같은
커넥션·같은 규약(저장 전용·실패해도 판정을 막지 않는다).

## ② 만드는/바꾸는 상태

| 칸 | 값 |
|---|---|
| `p_prior` | 티어 사전값의 **홈 확률**(축구 3-way 도 홈 칸) |
| `prior_src` | `tier` 또는 `tier:미기입` — prior 모듈이 정한 규약 |
| `p_market` | 비어 있을 때만 채운다(`COALESCE`) — 기존 경로를 덮지 않는다 |
| `gate_reason` | `"{라벨} · {사유}"` |

🔴 **게이트 라벨을 별도 칸에 복사하지 않는다.** 라벨은 `gate_reason` 의 첫
   토큰이고 구분자는 `" · "` 다. 같은 사실을 두 칸에 적으면 한쪽만 고쳐진다
   (사본 금지 — 워치독 오탐 4건이 전부 그 실수였다).

새 컬럼·새 테이블 없다. 새 외부 호출도 없다 — 티어는 파일, 시장은
`odds_snapshots` 의 이름표 붙은 기준선이다.

## ③ 리그·종목·경로 분기가 생기는가

생긴다. 명시한다:
- 티어 파일 키: **야구는 종목**(`mlb`·`kbo`·`npb`), **축구는 리그 라벨→키**
  (`league_labels()`). 축구 리그 라벨이 표에 없으면 `None` → 기록하지 않는다.
- 사전값 함수도 갈린다: 축구 `soccer_prior`(3-way) · 야구 `baseball_prior`
  (2-way, 절사는 `scoring.cap_probability` 원본).
- 시장 확률은 같은 devig(`market_edge.implied_probs`)를 쓴다 — 3-way 는 그
  함수가 이미 가른다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 티어 표가 없으면(리그 미상·파일 없음) **기록하지 않고** 사유를 로그에 남긴다.
- 기준선 시장이 없으면 역시 기록하지 않는다 — 사전값만으로 게이트를 만들면
  "괴리"가 아니라 사전값 그 자체가 되어 버린다.
- 티어가 비어 있는 팀이 하나라도 있으면 `prior_src="tier:미기입"` 이 남는다.
  조용히 중앙값(3)으로 메우고 끝내지 않는다.
- 성공하면 경기별 로그 한 줄에 사전값·시장·라벨·gap·side 가 전부 찍힌다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 티어 elo 표·무승부 곡선·홈 이점·임계 4%p·딥서치 예산을 **코드에 적지
  않는다.** `prior`·`gate` 상수가 원본이다.
- 기준선 선택(`open` 우선)도 다시 만들지 않는다 — `odds_move.baseline` 을 쓴다.
- 마진 제거도 `market_edge.implied_probs` 원본.
- 스냅샷 → 확률 변환은 `MOV-2` 가 만든 `_snap_probs`·`_best_provider` 를
  그대로 쓴다(같은 파일).

⚠️ **올해 성적(승·무·패)은 아직 안 붙였다.** `team_elo(w=d=lose=0)` 이라
   지금은 티어만으로 계산한다. 붙이는 자리는 이 함수 한 곳이다.
