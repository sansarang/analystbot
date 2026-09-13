# LLMS-1 — LLM 판정 출력을 무료 섀도로 기록한다 (2차 결정 D)

## 왜

(a) 구조에서 승자는 `p_code` 가 정한다. 그러면 `verdict.decide` 의 `승자`·`확신`
출력이 버려지는데, **그것을 버리면 "LLM 이 나은 조합이 있었는가"를 영영 못 잰다.**
300건 시점에 `llm_winner` 의 AUC 를 `p_code` 와 나란히 보고, LLM 이 나은 변수
조합이 있다면 그것이 조정 변수 후보가 된다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
verdict.decide            승자·확신 반환 — 호출부는 matchup._judge_v3 하나
dbref.recheck             승자 변경 경로(현재는 실제로 바꾼다)
pipeline:3401             market_agree_required 게이트 — `p_home` vs `p_market_send`
pick_ledger._row_from_game 원장 행 조립
```

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `pick_ledger.llm_winner` · `llm_level` | 새 칸 2개. **기록 전용** |
| `dbref.recheck` 승자 변경 | **승자를 바꾸지 않는다.** `반대근거` 로만 남긴다 |
| `scoring.ADJ_AGREE_MAX_PP` · `market_disagree_by_adj` | 시장 동의 정의를 Σadj 로 |

🔴 **카드·발송에는 LLM 등급을 쓰지 않는다** — `confidence` 는 코드 등급이다(CONF-1).
🔴 `recheck` 가 승자를 바꾸면 (a) 구조가 깨진다. 반대 의견은 **서술의 재료**다.

## ③ 리그·종목 분기

없음.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **LLM 승자가 발송에 새어 든다** | 카드 경로가 `llm_*` 를 안 읽는지 계약 |
| 🔴 `recheck` 가 여전히 승자를 바꾼다 | 승자 불변 + `승자변경 False` 계약 |
| 반대 의견이 조용히 사라진다 | `반대근거` 키로 남기고 계약이 단언 |
| 시장 동의 게이트가 무의미해진다 | 정의를 Σadj 로 바꾸고 임계 4%p 계약 |

⚠️ **아직 못 잰 것**: `llm_winner` 의 AUC. 300건 필요하다(결정 D).

## ⑤ 사본

- 등급 눈금·승자 표기를 새로 만들지 않는다.
- 임계값(4%p)은 `scoring` 한 곳에만 둔다.
