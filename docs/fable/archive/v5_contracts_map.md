# v5 계약 지도 — **옛 경로만 지키던 계약은 v6 의 어디로 갔나** (2026-10-06)

v6 지시서 §6 마지막 줄이 요구한 문서다:

> 옛 경로만 지키던 계약 테스트 — 삭제 전에 **목록과 "v6 에서 이 보장은 어디로
> 갔나"**(스키마/`llm.py`/E2E 불변식/단위)를 한 줄씩 적은 표를
> `docs/fable/archive/v5_contracts_map.md` 로 남긴다

## 🔴 이 파일은 **기계로 모았다**

목록을 손으로 적으면 한 발 늦는다(CLAUDE.md #1). 아래 표는 `tests/` 전체를 훑어
§6 *"지운다"* 목록의 부품 이름(`agentloop`·`searchcells`·`cells`·`querygate`·
`run_subtask`·`hypo`·`redteam`·`blackboard`·`agentschema`)이 **나오는 파일**을 모은
것이다. ⚠️ 이름이 나오는 것과 **그 파일이 옛 경로만 지키는 것**은 다르다 — 그래서
삭제는 파일 단위가 아니라 **조항 단위**로 본다(아래 "어떻게 지우나").

## v6 에서 그 보장이 사는 곳 — 부품별

| 옛 부품(§6 "지운다") | v6 에서 그 보장 |
|---|---|
| `agentloop`·`done` 도구·```json 블록 추출·산문 JSON 파서·`DONE_RESERVE` | `app/core/llm.py` — `response_format=json_schema(strict)` 와 `out.model_validate_json`. 🔴 **산문을 파싱할 자리가 없다.** `finish_reason=="length"` 는 실패(`llm_truncated`)다 |
| 하위 과제 에이전트 경로 · `subtasks.run_subtask` | `s4_extract.run` — 하위마다 추출 **1회**(+0개면 좁히기 1회). 루프가 없다 |
| 세포 검색 계획기 · 세포 장부 | `s3_docs.run`(질의 2개 · 문지기 하나 · 상위 3건) · `RunState.book`(장부) |
| 날짜 저장 함수 여럿(`store_doc` 계열) | `s3` 캐시 하나 — `Doc` 에 **본문과 발행일이 한 몸**이다(§3) |
| 문지기 둘(`querygate.gate`·`llm.query_ok`) | `s3_docs.gate_ok` 하나 — 🔴 `tests/contracts/test_v6_7_static.py` 가 **둘째 정의를 막는다** |
| `direction_hint` 처리 | 없다 — LLM 출력 모델에 **방향 칸이 없고**(`schema.py`), 방향은 `s5_verify.favors_of`(카탈로그 규칙)가 정한다. 계약: `test_v6_7_static.py::…코드가_정할_칸이_없다` |
| 프롬프트에 enum 목록 적는 코드 | 없다 — `llm.strict_schema(enums=…)` 가 **요청마다 스키마에 박는다** |
| `hypo`(가설)·`redteam`(반증) | `s6_hypo.run` — `HypoOut`/`RedTeamOut` 스키마. 근거 밖 인용은 `cited_excluded`/`unknown_var` 로 **버린다**(불변식 5) |
| `blackboard` 독립 출처 세기 | `s5_verify._merge` + `verifylayer.independent_sources`(기사 본문으로 센다) |
| 판정 수학(생존·상한·사다리) | `s7_judge` — 수는 `survive`·`rules`·`thresholds` 표가 그대로 든다(사본 금지). 불변식 7·단위 `tests/unit_v6_s5_s7.py` |

## 어떻게 지우나 — 🔴 **파일이 아니라 조항 단위**

1. 그 조항이 **v6 에도 있는 보장**이면 → 위 표의 자리로 옮겨졌는지 확인하고 **삭제**.
2. 그 조항이 **v6 에 없는 보장**이면 → 🔴 삭제하지 않는다. v6 에 그 검사를 **먼저
   짓는다**(없으면 보장이 사라진다).
3. 그 조항이 **옛 경로의 결함 기억**이면(예: *"tuple 로 와도 카드가 죽지 않는다"*)
   → v6 에서는 타입이 그것을 막으므로 **삭제**하고, 그 사실을 이 표에 한 줄 남긴다.

## 목록 (기계 수집 · 파일 × 그 파일이 건드리는 부품)

| 계약 파일 | 나오는 옛 부품 | v6 에서 그 보장 |
|---|---|---|
| `tests/contracts/test_v5A_3_M41_M43_hypo.py` | hypo | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/contracts/test_v5A_4_M44_M46_redteam.py` | hypo, redteam | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/contracts/test_v5A_7_drop_shape.py` | hypo | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/contracts/test_v5A_7_order.py` | redteam | s6 반증(추가만 · 생존율에 닿지 않는다) |
| `tests/contracts/test_v5_10_3_injection.py` | agentschema | schema.py 의 LLM 출력 모델(enum 강제) |
| `tests/contracts/test_v5_12_dates_3layer.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_1_skeleton.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_1_wo_subtask_flow.py` | agentloop, cells, run_subtask | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_2_subtasks.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_2_wo4_llm_status.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_2_wo_query_rules.py` | querygate | s3.gate_ok 하나(§7 정적 계약이 둘을 막는다) |
| `tests/contracts/test_v5_3_2_dec3_agent_hunts.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_2_dec3_cells_ledger.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/contracts/test_v5_3_2_tools_wired.py` | agentloop, blackboard, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_3_prompt.py` | agentloop, agentschema | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_4_wo_catalog.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_6_wo_hint_enum.py` | agentloop, agentschema | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_6_wo_schema_audit.py` | agentloop, agentschema | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_7_loop.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_8_model_iface.py` | agentloop, querygate | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_agent.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_3_wo_date_single.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_4_1_dec5_6_query_axes.py` | querygate | s3.gate_ok 하나(§7 정적 계약이 둘을 막는다) |
| `tests/contracts/test_v5_4_5_limits.py` | agentloop, agentschema, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_4_fb_pipeline.py` | agentloop, hypo, querygate, redteam | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_4_m109_dates.py` | agentloop, cells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_4_query_rules.py` | querygate | s3.gate_ok 하나(§7 정적 계약이 둘을 막는다) |
| `tests/contracts/test_v5_4_tools.py` | agentloop, querygate | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_4_wo_hypo_basis.py` | hypo | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/contracts/test_v5_5_1_wo1_quote_wiring.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_5_4_bridge.py` | agentschema | schema.py 의 LLM 출력 모델(enum 강제) |
| `tests/contracts/test_v5_5_4_wo_favors.py` | agentschema | schema.py 의 LLM 출력 모델(enum 강제) |
| `tests/contracts/test_v5_5_verify.py` | agentschema | schema.py 의 LLM 출력 모델(enum 강제) |
| `tests/contracts/test_v5_6_1_strength.py` | agentloop, agentschema | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_6_wire.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_6_wo_card_ds.py` | hypo, redteam | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/contracts/test_v5_7_5_r5gate.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/contracts/test_v5_8_1_names_of_key.py` | agentloop, querygate | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_8_3_dec4_roster_list.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/contracts/test_v5_8_3_fact_schema.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/contracts/test_v5_8_3_wo3_pages.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_8_4_short_club_names.py` | querygate | s3.gate_ok 하나(§7 정적 계약이 둘을 막는다) |
| `tests/contracts/test_v5_8_7_tz.py` | agentloop, agentschema | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/contracts/test_v5_9_2_rules_M.py` | agentschema | schema.py 의 LLM 출력 모델(enum 강제) |
| `tests/contracts/test_v5_9_3_M18.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/contracts/test_v6_7_static.py` | querygate | s3.gate_ok 하나(§7 정적 계약이 둘을 막는다) |
| `tests/e2e/test_v6_replay.py` | hypo, redteam | s6 가설·시나리오(HypoOut 스키마 강제) |
| `tests/stage2/test_schema.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage3/test_gate_19g.py` | blackboard, cells, searchcells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage3/test_queries.py` | searchcells | s3 문서 수집(질의 2개 · 문지기 하나 · 상위 3건) |
| `tests/stage3/test_timeline.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage4/test_analyze.py` | agentloop | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |
| `tests/stage4/test_angles.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage4/test_catalog.py` | blackboard, cells, searchcells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage4/test_classify.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_depth_all_sports.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_extract_wired.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_fotmob_lineup.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_identity.py` | blackboard, cells, searchcells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage4/test_intent_attribution.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_league_measures.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/stage4/test_narrow_ask.py` | searchcells | s3 문서 수집(질의 2개 · 문지기 하나 · 상위 3건) |
| `tests/stage4/test_prekick.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_question_budget.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_scenarios.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/stage4/test_triggers.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_collect.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/test_extract_wiring.py` | searchcells | s3 문서 수집(질의 2개 · 문지기 하나 · 상위 3건) |
| `tests/test_form_shapes.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_funnel.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_kbo.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_query_shape.py` | cells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_resolve.py` | cells, searchcells | s3 캐시(Doc 통째로) · RunState.book(장부) |
| `tests/test_search.py` | blackboard, cells | s5 병합(independent_sources) · Variable.usable_as_basis |
| `tests/test_wiring.py` | agentloop, blackboard, cells, hypo, redteam, searchcells | llm.py(구조화 출력 · 산문 파싱 없음) · s4 추출 1회 |

⚠️ **합계 75개 파일** — 이름이 나오는 파일 수다. 🔴 그 전부가 옛 경로 전용은
아니다(`tests/test_wiring.py` 처럼 **양쪽을 함께** 보는 파일이 있다).

## 🔴 아직 지우지 않은 까닭 (§8 5단계 보고)

삭제는 **범위 밖 모듈을 깨뜨린다**. 실측:

| 지우려는 것 | 그것을 `import` 하는 **범위 밖** 모듈 |
|---|---|
| `app/analyze.py`(옛 조율자) | `app/scheduler.py` — **세 자리**에서 `from app import analyze`(`analyze.gather`·`analyze.build`·채점). §6 이 스케줄러·채점을 **범위 밖**으로 선언했다. ⚠️ `rerun.py`·`live.py` 는 직접 import 하지 않는다(실측) |
| `app/cells.py` | `app/classify.py` · `app/verify.py` · `app/collect/*` 가 질문 꼴(`cells.Question`)로 쓴다 |
| `app/verifylayer.py` | 🔴 **v6 s5 가 쓴다**(`quote_ok`·`similarity`·`independent_sources`) — 지우면 그 내용을 s5 로 **복사**해야 한다 |

🔴 그래서 **사용자 결정이 필요하다**(CLAUDE.md: 묻는 곳은 하나):

- **A** 옛 조율자를 지우고 스케줄러·채점도 v6 로 옮긴다(범위가 늘어난다)
- **B** 옛 경로는 **남기고** 입구만 v6 로 둔다(지금 상태 — 사본이 둘 남는다)
- **C** `app/analyze.py` 에서 **하위 과제·에이전트 루프 경로만** 지우고 채점·
  스케줄러가 쓰는 부분은 남긴다(부분 삭제 · 중간)
