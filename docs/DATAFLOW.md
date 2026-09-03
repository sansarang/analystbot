# 데이터 흐름 — 수집에서 감시까지

> 이 문서는 **"어느 숫자가 어디서 와서 어디로 갔는가"**의 지도다.
> 특정 경기의 실측 증명은 [PIPELINE_PROOF_2026-09-02.md](PIPELINE_PROOF_2026-09-02.md)에 있다.
> 규율은 [DISCIPLINE.md](DISCIPLINE.md), 모델·한계값은 [MODEL.md](MODEL.md)가 원본이다.

## 한 줄 요약

```
수집 → 재료 조립 → 판정 → 게이트 → 발송 │ ← 여기까지가 v1.3 동결 구간
                                        └→ 감시 3층 (사후·섀도)
```

🔴 **세로줄 오른쪽은 왼쪽으로 되돌아가지 않는다.** 감시는 판정을 읽기만 한다.
   되먹임이 생기는 순간 "우리 판정"이 사실은 감시를 베낀 것이 되고, 감시가
   무엇을 검증하는지 알 수 없게 된다. `tests/test_shadow_contract.py`가
   import 경계로 강제한다.

---

## ① 수집 — 숫자는 API로

| 재료 | 모듈 | 소스 |
|---|---|---|
| 경기·박스스코어 | `collectors/mlb.py` · `kbo.py` · `npb.py` | statsapi · KBO 기록실 · npb.jp |
| 확정 타순 | `collectors/lineups.py` | statsapi boxscore · 크롤러 스냅샷 |
| 선발 최근 5등판 | DB `pitcher_appearances` | 위 수집기가 적재 |
| 선발 시즌 라인 | `collectors/starter_season.py` | 3리그 전부 (KBO는 세션 유지 POST) |
| 타순 9명 시즌 타격 | `collectors/lineup_season.py` | 재현(`replay=True`)에서는 붙이지 않는다 |
| 불펜 ERA | `collectors/mlb_team_pitching.py` · KBO·NPB 팀 투수 | 자료9 |
| 뉴스 | `collectors/news_rss.py` | Google News RSS (무인증·무료) |
| 배당 | `collectors/odds_free.py` → `registry.ODDS_PROVIDERS` | ESPN · oddsportal 등 |

⚠️ 배당은 여기서 갈라져 **판정을 우회한다.** ④ 게이트에서만 다시 만난다.

## ② 재료 조립 — `engine/matchup.py`

자료1 박스스코어 · 2 뉴스 · 3 타순 슬롯 · … · 8 타선 시즌 · 9 불펜.
`{{...}}_JSON` 자리표시자로 `engine/prompts.py`의 `MATCHUP`에 렌더된다.

- 게이트는 **폼이 아니라 박스스코어**에 걸린다 — 숫자가 없으면 판정하지 않는다.
- 렌더 직후 프롬프트 원문을 Redis에 24h 보관한다(`fact_audit.PROMPT_KEY`).
  **기록이지 입력이 아니다** — 감시층이 "그때 그 원문"을 봐야 하기 때문이다.

## ③ 판정 — Claude

`MODEL_MATCHUP`(기본 `claude-sonnet-5`) 호출 → `p_home` 클립 **0.32–0.68**.
절단(`stop=max_tokens`)이면 한도를 2배로 올려 1회 재시도한다 —
"짧게 쓰라"고 지시하지 않는다. 고칠 것은 출력이 아니라 그릇이다.

## ④ 게이트 — `engine/value_gate.py` · `engine/market_edge.py`

확률 하한 58%(원정 63%) + 라인업 확정 + 확신도 거부권 → 그 **뒤에** 배당이
가치 게이트·시장 괴리·엣지 라벨로 붙는다.

## ⑤ 발송 — `engine/pregame_push.py`

`🕐 잠정` → `✅ 최종` 2단계. 결과는 전건 `dispatch_stats`에 사유와 함께 기록된다
— **"조용한 0"은 결함이다.**

---

## ⑥ 감시 3층 (2026-09-03 신설 · 전 층 섀도)

전부 **발송이 끝난 뒤** 돈다. 카드 텍스트를 바꾸지 않는다.

| 층 | 모듈 | 무엇을 보는가 | 저장 | 경보 |
|---|---|---|---|---|
| **L1 사실 감시** | `engine/fact_audit.py` | 근거의 "숫자+단위"가 그 판정의 프롬프트 원문에 실제로 있는가 | `judgement_audit` | `W-FACT-MISMATCH` |
| **L2 검사역** | `engine/shadow_panel.py` | 판정의 **결함**을 찾는다(모순·무시·과신·자기모순) | `judge_review` | `W-JUDGE-OBJECTION` |
| **L3 독립 판정** | `engine/shadow_panel.py` | 같은 자료로 **혼자** 판정해 주심과의 편차 | `shadow_panel` | `W-PANEL-DIVERGE` |

- L1은 3단 분류다: `verified` / `derived`(재계산 ±0.05) / `not_found`(환각
  **후보** — 확정 아님) / `mismatch`(같은 단위 값이 다름). 경보는 `mismatch`에만.
- L2·L3는 Gemini(`llm/gemini.py`, REST 직접 호출). `GEMINI_API_KEY`가 없으면
  **휴면** — 기동 로그 1줄을 남기고 조용히 꺼지지 않는다.
- 🔴 **L3 프롬프트에 주심 판정이 들어가면 독립이 아니라 추인이다.**
  플래그 분기가 아니라 `build_independent_prompt(materials)`의 **시그니처에
  verdict 인자가 없다** — 실수로 넘길 방법이 없다.
- 층 자체의 예외는 `W-MONITOR-DOWN` 한 줄 + 그 건 skip. **감시 실패가 발송을
  막지 않는다.**

### 계측 3건 — `engine/monitor_metrics.py`

| # | 무엇 | 어디서 | 원본 |
|---|---|---|---|
| M-1 | 라인업 상태 **역행**(확정→비확정) | 폴러 전이 지점 | Redis 카운터 |
| M-2 | 자료8 **주입률** (수집률과 따로 센다) | `matchup` 렌더 직후 | Redis 카운터 |
| M-3 | 타순 길이 ≠ 9 | `lineups` 테이블 | **DB가 원본** — 카운터로 베끼지 않는다 |

일일 요약 한 줄로 나온다:

```
🔍 감시: 사실 v/d/nf/m · 검사역 이의 k(유효 j) · 패널 편차>8%p m건
   · 계측: 역행 r건, 자료8 주입 p%, 타순 길이 이상 n건
```

⚠️ **재료가 없으면 줄이 아예 안 나온다.** 매일 `0/0/0/0`을 보내면 휴면과
   정상을 구분할 수 없다.

---

## 스케줄러 잡 (id는 `scheduler.build_scheduler()`가 원본)

`prefetch_dawn`·`prefetch_evening`·`prefetch_asia` · `lineup_poll_30m` ·
`asia_pregame_5m`·`npb_pregame_2m`·`mlb_pregame_5m` · `odds_snapshot_30m` ·
`research_retry_45m` · `watchdog_5m` · `daily_summary_*` · `ingest_finals_13h` ·
`calibration_weekly` · `heartbeat_2m`

⚠️ **주기를 이 표에 적지 않는다.** 트리거 객체(`_JOB_TRIGGERS`)가 원본이다 —
   여기 옮겨 적는 순간 사본이 되고, 사본이 어긋나면 워치독이 오탐을 낸다
   (실사고 4건이 전부 이 유형이었다 → `app/registry.py` 머리말).
