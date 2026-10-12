# ⚠️ 이 계약은 **걷혔다** — 그 단계가 지시서 2026-10-12(셋째) §1 으로 지워졌다

처분표: **㉔ 최종 평·논평(LLM) → 코드 템플릿** · **전술 전문가 예측 → 삭제**
(계약 **X2**: LLM 호출은 `s4_extract`(사실 추출)·라인업 캡처 판독만).

🔴 **없는 단계를 시험하면 그 계약이 거짓을 지킨다** — 그래서 파일을 지운다.
🔴 지금 그 자리를 지키는 계약은 `tests/contracts/test_v15_1_cleanup.py`(X1·X2)와
   `test_v6_6_final_say.py` 가 아니라 **코드 템플릿 계약**이다:
   `layer1.template_lines` 가 결론 문단을 짓고, 그 문장은 숫자에서만 나온다.

## 2026-10-12(셋째) §1 처분 ③ — ⑭⑮⑰⑱⑳㉒ 와 함께 걷은 계약

지운 모듈: `s6_hypo`(가설·무너뜨릴 조건) · `s6c_check`(가설 검증표) ·
`s5b_falsify`(반증 딥서치) · `reweight`(시나리오 재가중) · `condhypo`(조건 가설).

그 단계만 시험하던 계약 파일(삭제):
- `test_v10_5_cond_hypo.py` · `test_v11_1_break_conditions.py` ·
  `test_v11_2_falsify_stage.py` · `test_v11_3_stance.py` ·
  `test_v11_4_rerun_once.py` · `test_v8_f6_hypo_order.py` ·
  `test_v5_6_2_dec1_scenario_letters.py` · `test_v5_6_2_required.py` ·
  `tests/stage4/test_scenarios.py`
- 🔴 **왜 지우나** — 없는 단계를 시험하면 그 계약이 **거짓을 지킨다**. 그리고
  빨간 채로 두면 다음 사람이 *"원래 깨져 있다"* 를 배운다(그게 더 나쁘다).

살아남은 보장이 **어디로 갔나**:
| 옛 계약이 지킨 것 | 지금 그것을 지키는 자리 |
|---|---|
| 생존이 시나리오 무게로 세지지 않는다(F5·R7) | `s7_judge._one` — 격자 하나 · `test_v12_1_prob_path` |
| 거짓 1.0(죽을 자리가 없어 생존 1.0) | **격자가 모든 스코어를 센다** — 그 병이 구조적으로 없다 |
| 등급을 내리는 길이 하나다(㉒ 반증 판정) | §11 판정 행동 — `upset.folds`·`infoquality.apply`(U4·C14-1) |
| 방향 한 줄(⑨ 블록) | `pipeline._direction` — **확률**로 센다 |
| 양상(저득점·난타전) | `shape.of(격자)` — 입력이 시나리오 무게에서 **격자**로 바뀌었다 |
