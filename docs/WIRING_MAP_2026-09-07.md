# 판정 배선 지도 — v1.4 (2026-09-07)

> **읽기 전용 문서다.** 코드·설정을 바꾸지 않았다.
> 전부 **현재 배포 코드(HEAD `4c00863`)** 기준이고, 화살표마다 `파일:라인` 을 병기했다.
> 계획·과거·희망은 적지 않는다 — **무엇이 무엇을 실제로 부르는가**만 그린다.
>
> 이번 주 사고 다수가 "코드는 있는데 배선이 안 된" 유형이었다:
> `ensure_analysis_cache` 호출처 0곳(09-01) · `p_market` 이 게이트보다 뒤(09-06) ·
> 평의회 심의가 사슬 1순위에 막혀 영구 빈 dict(09-06) ·
> L1 이 자료12 를 대조 안 함(09-06). 그래서 이 지도의 값은 §3 의 **빈 칸**에 있다.

호출 방식 표기: `→` 직접 호출 · `⏰` 잡 스케줄 · `⌁` Redis 경유 · `?` 조건부

---

## 1. 마스터 흐름도

```
⏰ prefetch_asia_job          scheduler.py:276   (KST 14:00 · kbo,npb)
⏰ prefetch_job               scheduler.py:45    (04:30/18:30 · mlb,soccer)
        │
        └─→ build_analysis                        pipeline.py:1248
             │
             ├─ [수집] 종목 분기                   pipeline.py:813/883/900
             │    kbo  → crawler_feed·kbo_park·kbo_usage·kbo_roster·kbo_news
             │           weather                   pipeline.py:1711~1774
             │    npb  → yahoo_npb·npb_stats·npb_form·crawler_feed·weather
             │                                     pipeline.py:1829~1874
             │    mlb  → statcast·mlb_team_pitching·weather
             │    저장: ⌁ Redis(수집기별 키) + DB `games`
             │
             ├─ [판정 전 조립] 축구·야구 분기       pipeline.py:1995 `if sport not in _BB`
             │    _attach_lineup_intent            pipeline.py:1996   ← 야구는 **건너뜀**
             │    _attach_cell_verdicts            pipeline.py:1997   ← 야구는 **건너뜀**
             │    _attach_card_compare             pipeline.py:1998   ← 야구는 **건너뜀**
             │
             ├─?[야구] `if sport in _BB`            pipeline.py:2015
             │    └─→ _run_baseball_matchups       pipeline.py:2036 (allow_final 없음 → 1차)
             │
             └─?[축구] else                        pipeline.py:2077
                  └─→ Judge().judge                pipeline.py:2079
                       ⚠️ `SOCCER_JUDGE_ENABLED=false` 라 빈 판정 반환
                                                   engine/judge.py:250 부근

_run_baseball_matchups                             pipeline.py:2625
  │  ① 자료12 레이팅 로드 (슬레이트당 1회)          pipeline.py:2645~2652
  │       team_elo.load ⌁ → 없으면 team_elo.refresh(DB `games` 전수 리플레이)
  │  ② 경기 루프: 자료 재조립 (§2 의 REBUILD 열)
  │       attach_starter_recent  (자료4)            pipeline.py:2664
  │       bullpen_recent.attach  (자료9)            pipeline.py:2679
  │       variable_ref.attach_opp_starter_era       pipeline.py:2691
  │       variable_ref.attach_material10 (자료10)   pipeline.py:2692
  │       mlb_team_pitching.attach ?mlb             pipeline.py:2700
  │       context_recent.attach   (자료11)          pipeline.py:2707
  │  ③ judge_matchup                                pipeline.py:2712 → matchup.py:527
  │  ④ p_market_send 새김  (게이트보다 **앞**)      pipeline.py:2723~2729
  │  ⑤ _spawn_fact_audit  [감시 L1]                 pipeline.py:2732 → pipeline.py:689
  │  ⑥ variable_ledger.record                       pipeline.py:2737 → variable_ledger.py:71
  └─────────────────────────────────────────────────────────────

judge_matchup                                      matchup.py:527
  │  최종 여부 판정 (allow_final ∧ 타순확정 ∧ 락)   matchup.py:196/210/224
  │  role = MATCHUP_ROLE | PRELIM_ROLE              llm/judge_route.py:22/27
  │  situation.attach   [상황 태그]                  matchup.py:648
  │  council.run        [평의회 · 퍼플렉시티]        matchup.py:666
  │  render_matchup_prompt                          matchup.py:546
  │  complete_json(role=…)                          matchup.py:734 → team_form.py:281
  │       ├ 무료 사슬  team_form.py:190 `_complete_free`
  │       └ 유료(최종) team_form.py:318 anthropic SDK
  │       temperature: `_sampling_allowed` 가 거부하면 안 보냄  team_form.py:83
  │  apply_matchup → clip_p_home(0.32~0.68)         matchup.py:359 / 27
  └──────────────────────────────────────────────

[게이트] 호출 순서 그대로
  ① 확률 하한        qualifies                     pipeline.py:3016 (마지막 `p >= need`)
  ② 확신도 거부권    gate_result_of                pick_ledger.py:43 (`judge_pass`/low 먼저)
  ③ 시장 동의        market_disagreement           pipeline.py:3064 ← qualifies 안에서 호출
  ④ 가치            value_gate.classify           value_gate.py:72
  카드 쪽 같은 판단  rec_label                     form_card.py:57 (③을 같은 함수로 부름)

[트리거] deepsearch.triggers                        deepsearch.py:62
  T1 경계확률(±3%p)  :70  · T2 시장괴리 :80  · T3 추가확인 :85
  T4 선발변경        :89  · T5 라인업이상 :92 · T6 최초확정 :918(상한 면제)
        └─→ deepsearch.run_for_slate               pipeline.py:2058
             investigate → RSS 0건이면 **조사 생략**  deepsearch.py:526

[카드·발송]
  render_form_card                                 form_card.py:147
  compose_card                                     pregame_push.py:238
⏰ lineup_poll_job                                  scheduler.py:361
   ├─→ mlb_pregame_poll                            scheduler.py:370
   ├─→ crawler_lineup_poll                         scheduler.py:604
   │     └─→ rejudge_after_lineup                  pipeline.py:5348
   │          └─→ _run_baseball_matchups(allow_final=True)  pipeline.py:5450/5599
   └─→ guarantee_first_cards (T-30 보장)           scheduler.py:860
  send_game_prediction                             pregame_push.py:533
        └ _send_card → 텔레그램                     pregame_push.py:339

[원장]
  pick_ledger  ← _record_ledger                    pipeline.py:5102 부근
  variable_ledger.record                           variable_ledger.py:71
  market_baseline.record_send                      pregame_push.py:679

[채점]
⏰ ingest_finals_13h                                scheduler.py:1846
   └─→ finals.ingest_finals                        collectors/finals.py:18
        └─→ pick_ledger.grade_pending               pick_ledger.py:186
             └─→ market_baseline.grade              pick_ledger.py:214

[감시 3층]
  L1 사실감시  _spawn_fact_audit                   pipeline.py:689 (판정 직후, 비동기)
                fact_audit.audit                    fact_audit.py:490
  L2 검사역 ┐  _run_shadow_panel                    scheduler.py:934
  L3 독립판정┘   └─→ shadow_panel.run_panel          shadow_panel.py:112
                 호출처: scheduler.py:486(mlb) · scheduler.py:852(asia)
```

---

## 2. 자료별 배선표

`REBUILD` = 재판정마다 다시 붙는다(`_run_baseball_matchups` 루프 안) ·
`CACHE` = 프리페치에서 한 번 붙고 캐시로 산다 ·
`판정내부` = `judge_matchup` 안에서 매번 만든다.

| 자료 | 수집기 | 저장소 | 조립부 | 주입 | 갱신 | L1 |
|---|---|---|---|---|---|---|
| **1** 박스스코어 | 종목별 수집기 | jg.research | `boxscore_payload` matchup.py:82 | `BOXSCORE_JSON` prompts.py:46 | **CACHE** | ✅ ip/r/er |
| **2** 뉴스태그 | kbo_news 등 → 팀 폼 | jg.research·팀폼 | `news_payload` matchup.py:226 | `NEWS_JSON` :51 | **CACHE** | — |
| **3** 오늘 타순 | crawler_feed·lineups | jg.today_nine / research | `lineups_payload` matchup.py:54 | `LINEUPS_JSON` :61 | **CACHE** | — |
| **4** 선발 최근등판 | starter_recent | DB `pitcher_appearances` | `starters_recent_payload` matchup.py:295 | `STARTERS_RECENT_JSON` :64 | **REBUILD** pipeline.py:2664 | ✅ ip/r |
| **5** 직전 판정 | — | jg(이전 판정) | `prev_verdict` matchup.py:448 | `PREV_VERDICT_JSON` :66 | 판정내부 | — |
| **6** 라인업 의도 | interpreter(LLM) | jg | `intent_payload` matchup.py:260 | `LINEUP_INTENT_JSON` :67 | **CACHE** ⚠️ 야구는 `_attach_lineup_intent` 를 **건너뛴다**(pipeline.py:1995) | — |
| **7·8** | — | — | **폐지** prompts.py:71 | — | — | — |
| **9** 불펜 | bullpen_recent · mlb_team_pitching | DB | `bullpen_payload` matchup.py:112 | `BULLPEN_JSON` :76 | **REBUILD** pipeline.py:2679/2700 | ✅ ip/r |
| **10** 변수 대장 | variable_ref | DB+⌁ | `material10_payload` matchup.py:129 → `insert_ledger` matchup.py:203 | `[판정 규칙]` 앞에 삽입 matchup.py:223 | **REBUILD** pipeline.py:2692 | ✅ p25/p50/p75 |
| **11** 맥락 | context_recent | jg | `ledger_payload` matchup.py:197 → 같은 블록 `[맥락]` matchup.py:157 | 〃 | **REBUILD** pipeline.py:2707 | 부분 |
| **12** 실력 레이팅 | `team_elo.refresh`(DB `games` 전수) | ⌁ `elo:{sport}:{date}` TTL 26h | `elo_payload` matchup.py:178 | `ELO_JSON` prompts.py:87 | **REBUILD** pipeline.py:2645~2652 | ✅ elo/elo_gap/elo_rel fact_audit.py:52~55 |
| **13** 전개 계산기 | *(미존재)* | — | — | — | — | — |
| 상황 태그 | news_rss·x_search·grounding | jg.situation_tags | `situation.attach` | 자료2 확장 | 판정내부 matchup.py:648 | — |
| 상황·심의 | perplexity(조사)+무료사슬(심의) | ⌁ `council:rec:*` | `council.payload` matchup.py:250 | 자료2 확장 | 판정내부 matchup.py:666 | — |

🔴 **자료6은 야구에서 조립되지 않는다.** `pipeline.py:1995` 가 `if sport not in _BB` 라
`_attach_lineup_intent` 를 축구에서만 부른다. 프롬프트 자리(`LINEUP_INTENT_JSON`)는
있고 `intent_payload` 도 있는데, 야구 경로에서 채워지는 곳이 없다 — **미배선 의심.**

---

## 3. 경로별 진입점 매트릭스

열: **P**=프리페치 · **R**=폴링 재판정 · **G**=T-30 강제 · **M**=수동(`tools/resend`) · **H**=리허설(`tools/rehearsal_*`)

| 기능 | P | R | G | M | H |
|---|---|---|---|---|---|
| 자료1·2·3 조립 | ✅ build_analysis pipeline.py:1248 | ⌁ 캐시 재사용 | ⌁ 캐시 | ⌁ 캐시 | ✅ |
| 자료4·9·10·11·12 재조립 | ✅ pipeline.py:2664~2707 | ✅ 같은 함수 | ✅ (R 경유) | ❌ 미배선 | ✅ |
| 자료6 라인업 의도 | 🔴 **미배선(야구)** pipeline.py:1995 | 🔴 미배선 | 🔴 미배선 | 🔴 | 🔴 |
| 판정 호출 | ✅ pipeline.py:2036 (1차) | ✅ pipeline.py:5450/5599 (최종 가능) | ✅ R 경유 scheduler.py:911 | ❌ 판정 안 함 | ✅ |
| p_market_send 새김 | ✅ pipeline.py:2723 | ✅ 같은 코드 | ✅ | ⚠️ 발송 시점만 pregame_push.py:588 | — |
| 게이트(확률·거부권·시장·가치) | ✅ pipeline.py:3016 | ✅ | ✅ | ✅ 카드 렌더 시 form_card.py:57 | — |
| 트리거 T1~T6 | ✅ deepsearch.py:62 | ✅ | ✅ | ❌ | — |
| 딥서치 조사 | ✅ pipeline.py:2058 | ✅ pipeline.py 재판정 경로 | ✅ | ❌ | — |
| 상황 태그 | ✅ matchup.py:648 | ✅ 같은 함수 | ✅ | ❌ | ✅ |
| 평의회(퍼플렉시티) | ✅ matchup.py:666 | ✅ | ✅ | ❌ | ✅ |
| L1 사실감시 | ✅ pipeline.py:2732 | ✅ 같은 자리 | ✅ | ❌ | ❌ |
| L2 검사역 / L3 독립 | ❌ | ❌ | ❌ | ❌ | ❌ — **발송 후 별도 잡** scheduler.py:486/852 |
| 정찰(scout) | ❌ | ✅ scheduler.py:681 | ✅ | ❌ | ❌ |
| 카드 발송 | ❌ (창 밖) | ✅ pregame_push.py:533 | ✅ scheduler.py:911 | ✅ | ❌ |

### 빈 칸이 말하는 것

- 🔴 **자료6(라인업 의도)은 야구 전 경로에서 미배선이다.** 조립부·프롬프트 자리·
  payload 함수가 다 있는데 부르는 곳이 야구에 없다. 09-01 `ensure_analysis_cache`
  와 같은 유형(코드는 있고 호출이 없다).
- ⚠️ **`tools/resend` 는 자료를 재조립하지 않는다.** 캐시의 판정을 그대로 보낸다 —
  "재발송"이지 "재판정"이 아니다. 의도된 설계다(resend.py 독스트링).
- ⚠️ **수동 경로에는 L1 이 없다.** `_spawn_fact_audit` 은 `_run_baseball_matchups`
  안에만 있어(pipeline.py:2732), resend 로 나간 카드는 감사되지 않는다.
- ⚠️ **정찰(scout)은 프리페치에 없다.** 폴링에서만 돈다(scheduler.py:681) —
  T-3h 이전 상태는 관측 기록이 없다.

---

## 4. 리그 분기 지도

| 지점 | 파일:라인 | 분기 사유 |
|---|---|---|
| 수집기 선택 | pipeline.py:813 / 883 / 900 | 리그별 소스가 다르다(네이버·Yahoo·statsapi) — 정당 |
| 판정 경로 | pipeline.py:2015 `if sport in _BB` | 야구=폼·매치업 / 축구=구 Judge — 정당 |
| 판정 전 조립 3종 | pipeline.py:1995 `if sport not in _BB` | 🔴 자료6 이 야구에서 사라지는 자리 |
| 구 Judge 차단 | engine/judge.py:246 | 야구는 구 Judge 안 쓴다 — 정당(한 곳에서 막는다) |
| NPB 표본 게이트 | pipeline.py:3025 `npb_last3_verified` | NPB 검증 전 추천 금지 — 정당 |
| 원정 하한 +5%p | pipeline.py:3013 부근 · form_card.py:88 | 전 리그 공통 — 정당 |
| 발송 창 | pregame_push.py:101 `SEND_OPEN_MIN` | kbo 70 · npb 40 · mlb 180 — 리그 관행 |
| 재판정 마감 | pregame_push.py:96~98 | KBO T-20 · NPB T-15/T-10 — 리그 관행 |
| 상황 창 | situation.py `SITUATION_WINDOW_BY_SPORT` | mlb 36h · 그 외 24h — MLB 하루가 KST 로 걸침 |
| 시장 소스 | registry `provider_for` | mlb=espn · kbo/npb=oddsportal — 🔴 **소스와 종목이 완전히 겹쳐** 괴리 분석에서 분리 불가(DIVERGENCE_ANALYSIS §2 H4) |
| ELO 홈 이점 | models/team_elo.py:37 `HOME_ADV=15.0` | 3리그 공통 상수 — 표본이 리그별로 못 나눌 만큼 적다(주석에 명시) |

---

## 5. 자료13(전개 계산기) 접합 예정지

아래는 **제안뿐이다.** 이 문서는 코드를 바꾸지 않았다.

| 항목 | 제안 위치 | 근거 |
|---|---|---|
| 계산 시점 | `_run_baseball_matchups` 루프 안, 자료11 부착 **뒤** — pipeline.py:2707 다음 | 읽을 재료(자료9·10·11)가 그 시점에 다 붙어 있다 |
| 재조립 목록 | **REBUILD** 등재(자료4·9·10·11·12와 같은 줄) | 재판정마다 타순·불펜이 바뀌면 전개도 바뀐다 |
| 조립부 | `matchup.py` 에 `tempo_payload(jg)` — `elo_payload` matchup.py:178 옆 | 같은 파일의 payload 규약을 따른다(팀당 값, 집계표 금지) |
| 주입점 | `render_matchup_prompt` 의 `fill(...)` 에 `TEMPO_JSON=` — matchup.py:566 다음 | 자료12 가 붙은 자리와 동일 패턴 |
| 프롬프트 자리 | prompts.py:87 자료12 블록 **뒤** = `13.` | 번호 순서 유지 |
| L1 등록 | `fact_audit.UNIT_PATTERNS` 에 단위 추가 — fact_audit.py:52~55 (elo 3종 옆) | 자료12 가 감시 없이 배포됐던 실수를 되풀이하지 않기 위해 **같은 커밋에서** |
| 계약 테스트 | `tests/test_material12_elo.py` 를 본으로 | 팀당 값·집계표 금지·표본 하한·오탐 전후 측정 |

⚠️ **자료8은 폐지 상태다**(prompts.py:71). 지시서의 "읽을 재료 자료8"은
현재 코드에 없다 — 타선 시즌 라인을 되살리려면 대원칙(`app/engine/CLAUDE.md` §대원칙)을
먼저 고쳐야 한다. 자료13이 타선 정보를 쓰려면 **자료1(최근 3경기 박스스코어)** 또는
**자료3(오늘 타순)** 에서 가져오는 것이 현행 규칙 안이다.

---

## 부록. 잡 스케줄 (scheduler.py:1836~1900)

| 잡 | 주기 | 진입점 |
|---|---|---|
| prefetch_evening / prefetch_dawn | cron | scheduler.py:1836/1838 |
| prefetch_asia | KST 14:00 | scheduler.py:1842 |
| lineup_poll_30m | 30분 | scheduler.py:1867 |
| watchdog_5m | 5분 | scheduler.py:1844 |
| odds_snapshot_30m | 30분 | scheduler.py:1845 |
| ingest_finals_13h | KST 13:00 | scheduler.py:1846 |
| research_retry_45m | 45분 | scheduler.py:1866 |
| soccer_trial_10m | 10분 | scheduler.py:1849 ⚠️ `SOCCER_TRIAL_ENABLED=false` 로 즉시 반환 |
| daily_summary_asia / overseas / soccer | cron | scheduler.py:1852/1857/1860 |
| elo_refresh_weekly | 주 1회 | scheduler.py:1891 ⚠️ **축구 ClubElo 전용** — 야구 자료12 와 무관 |
