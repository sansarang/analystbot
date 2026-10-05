# 갈림길 — 유지된 `evidence.used_in` 의 값이 폐기된 개념을 가리킨다 (2026-09-29)

## 무엇이 갈렸나

v4 §8 **유지**:
> v3 §12 딥서치 방법론(검색 순서·쿼리 규칙·검증기 7종·병렬 예산·**증거 카드 필드**)

그 증거 카드 필드는 v3 §12-e 다:
> claim(문장), step(0~9), team, player_id, value, source_url, publisher,
> published_at, fetched_at, hardness(hard/likely/soft), **`used_in`(lean/counter/trigger)**

v4 §8 **폐기**:
> 동기 4등급, **lean**, 확신 상/중/낮, 간다/조건부/접는다, 방아쇠 통과에 따른
> 등급 상향/하향 · 반증 추적의 "확신 갱신" 로직 · v3 §9 **방아쇠** 유형표

🔴 **`used_in` 의 세 값이 전부 폐기된 개념이다.** `lean`·`counter`(반증 추적)·
   `trigger`(방아쇠). 필드는 유지인데 그 값이 가리키는 모델이 없다.

## 지금 코드 상태

`app/blackboard.py` 의 `_used_in()` 이 `question_id` 접두로 그 셋을 돌려준다.
단계 1 금칙 식별자 게이트는 통과한다(§9 단계 1 이 이름을 댄 것은 "동기 등급·확신·
등급·min_win_prob·p_claude"이고 `lean` 은 그 목록에 없다). **하지만 §8 폐기
목록에는 `lean` 이 있다.** 그래서 남겨 두는 것이 맞는지 모른다.

## 갈래

| 갈래 | | |
|---|---|---|
| (a) v4 용어로 바꾼다 | `variable` / `premise_check` / `opposite` / `scenario` | v4 §1~§3 의 실제 산출과 맞는다. 다만 v3 §12-e 를 "유지"라 한 문구를 고치는 것이다 |
| (b) 그대로 둔다 | `lean`·`counter`·`trigger` | v3 §12-e 를 글자 그대로 유지한다. 🔴 폐기된 개념 이름이 원장에 계속 쌓인다 |
| (c) 필드를 없앤다 | — | 증거가 **어디에 쓰였는지**를 잃는다. §10 채점("못 찾은 변수가 있었나")이 그것을 본다 |

## 🔴 고르지 않았다 — 페이블에게 물을 것

v4 §13-7: *"승인·갈림길 선택·예산·배포는 사용자, **규칙 해석**·정답지·채점은
페이블."* 이것은 **규칙 해석**이다 — "§8 유지가 v3 §12-e 의 필드 값까지 포함하나,
아니면 필드 이름만인가".

⚠️ 지금은 **(b) 상태로 두고 단계 1 을 닫는다.** 값을 내가 바꾸면 §13-1(범위 잠금)
   위반이고, 필드를 지우면 채점 재료를 잃는다. 단계 2(타입·스키마)에서 `variables`
   표를 세울 때 이 답이 필요하다.

## ✅ 닫혔다 — 사용자 결정 (2026-09-29)

> "#6 evidence.used_in: 값을 **variable / premise_check / opposite /
> lineup_rerun / grading** 으로 교체. 기존 행은 마이그레이션으로 variable,
> **원값은 `legacy_used_in` 열 보존**. `blackboard._used_in()` 수정."

(a) 로 정해졌고 값이 **다섯**으로 확정됐다(내가 적은 넷보다 하나 많다 —
`lineup_rerun`·`grading` 이 STEP 8 의 두 일을 가른다).
⚠️ **원값을 버리지 않는다** — `legacy_used_in` 열에 남긴다. 이미 쌓인 evidence 행의
   `used_in` 을 그냥 덮으면 "왜 그렇게 적혔나"를 잃는다.

---

## (종전) 물을 것 한 줄

**`evidence.used_in` 의 값을 v4 용어(`variable`/`premise_check`/`opposite`/
`scenario`)로 바꿀까요, v3 그대로 둘까요?**
