# 갈림길 — 단계 3 의 **"NOT_WIRED 0건"은 어디까지인가** (2026-09-30) · ✅ 닫힘

## 무엇이 갈렸나

v4 §9 단계 3 완료 조건 원문:

> **완료 조건(전부)**: 세포·블랙보드·시간축·소스 점수표·SearXNG 어댑터 실측.
> **NOT_WIRED 0건**

🔴 **그 문장을 글자 그대로 읽으면 §13-2 와 충돌한다.** `tests/test_wiring.py`
의 두 NOT_WIRED 목록에는 항목마다 *"몇 단계에서 이어질 것"*이 적혀 있고, 그중
일부는 **단계 5~8 것**이다. 단계 3 에서 그것을 이으려면 단계 5 이후 코드를
써야 하는데, §11-2·§13-2 가 그것을 금지하고 `config/stage_gate.yaml` 이
**기계로 막는다**(승인 서명이 없으면 `tests/stage5` 이하가 수집조차 안 된다).

즉 **글자 그대로의 해석은 실행 불가능**하다 — 규율을 걷어내지 않는 한.

## 실측 — 목록에 무엇이 올라 있나 (커밋 `95134a0` 시점)

함수 21개 · DB 표 12개.

| 갈래 | 수 | 항목 |
|---|---|---|
| **단계 3** | 10 | `llm.call`·`llm.query_ok`·`cells.awake`·`ids.resolve_by_name`·`verify.dedupe`·`verify.slate_date_ok`·`verify.wins`·`collect.npb.parse_movement`·`collect.mlb.sources_transactions`·`collect.ingest.roster` |
| **단계 3 (표)** | 3 | `source_score`·`source_state`·`extraction_rejected` |
| 단계 5 | 6 | `rules.premise_types`·`rules.unimplemented_types`·`bot.aliases.find_team`·`bot.aliases.kr_team` + 표 `variables`·`background`·`premise_check` |
| 단계 6 | 3 | `rules.templates`·`rules.by_sec7_rule` + 표 `sufficiency`·`scenarios` |
| 단계 7 | 2 | 표 `board`·`survival` |
| 단계 8 | 2 | `tg.send` + 표 `ledger` |
| **[infra]** | 4 | `secrets_mask.install_log_filter`·`secrets_mask.mask_field`·`version.boot_line`·`version.uptime_text` |

⚠️ **표 `team_form`** 은 단계 2 가 *"수집기 대기"*로만 적어 단계를 안 남겼다.
STEP 3 축구 폼이므로 §9 로는 **단계 5** 다.

⚠️ 단계 2 가 10표에 붙인 주석 *"배선은 단계 3 이다(§9)"* 는 **틀렸다.** §9 는
STEP 1~3 을 단계 5, STEP 4·5 를 단계 6, STEP 6 을 단계 7, STEP 8 을 단계 8 로
배정한다. 그 주석은 단계 3 에서 표마다 실제 단계로 고친다.

## 🔴 사용자 답 (2026-09-30)

> **"단계 3 것 + 안전장치 4건"**

| 무엇 | 단계 3 에서 |
|---|---|
| 단계 3 로 적힌 함수 10개 · 표 3개 | **잇는다** |
| [infra] 4건 (로그 키 가리기·값 가리기·기동 줄·가동시간) | **잇는다** |
| 단계 5·6·7·8 로 적힌 13건 | 목록에 남긴다 — 그 단계에서 |

**왜 [infra] 를 지금인가**: `secrets_mask.install_log_filter` 가 안 붙은 동안은
로그에 API 키가 샐 수 있다. 단계 3 은 **라이브 검색을 실제로 처음 돌리는**
단계이므로(§9 게이트의 *"라이브 재현"*), 그때 안 막혀 있으면 그때 샌다.

## 분류표 행

| 날짜 | 무엇이 갈렸나 | 누가 | 답 | 근거 |
|---|---|---|---|---|
| 2026-09-30 | 단계 3 의 `NOT_WIRED 0건` 범위 | **사용자** | 단계 3 것 + [infra] 4건. 단계 5~8 것은 목록에 남긴다 | §9 가 STEP → 단계를 배정하고 §13-2 가 앞당기기를 금지한다 |
