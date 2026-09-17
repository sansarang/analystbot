# MDL-1 — v3 판정이 **어느 모델이 냈는지** 원장에 안 남는다

## 왜

실측 2026-09-17 운영 원장:
```
날짜    전체  model  model_src  analyze_model  llm_winner
09-12     6     6        0           0            0      ← v2
09-16    24    15       23          12           10
09-17    20   **0**     20           9           20      ← v3 전건. model 만 빈다
```

사슬:
```
verdict.decide → {"승자","확신","서술","추가요청"}          model 키 없음
_judge_v3 → apply_winner(jg, {"승자","확신","서술"})        model 키 없음
apply_winner → jg["matchup"] = {승자, "model": verdict.get("model")} → None
apply_code_verdict → pick model = jg["matchup"]["model"]              → None
pick_ledger:231 "model": jg.get("model") or matchup.get("model")      → None
                 ⤷ jg["model"] 은 v2 경로(matchup.py:752)에서만 세팅된다
```

🔴 **저장소가 이미 경고해 둔 자리다.**
- `matchup.py:888` — "v3 는 … `jg["model"]` 도 세팅하지 않아"
- `matchup.py:1621` — "폴백이 일어나면 어느 모델이 그 판정을 했는지가 사라지고,
  그러면 **모델별 성적을 영영 못 가른다**"
그 보정(`_real_model` → `jg["model"] = _actual`)은 **v2 경로에만** 걸려 있다.

⚠️ `model_src`(확률 모델 `model_baseball.v1`)·`analyze_model`(S11 분석 LLM
   `claude-opus-5`)은 **다른 호출**이다 — 승자를 낸 판정 LLM 을 대체하지 못한다.

**왜 지금 고치나** — docs/FORKS.md F-6("승자를 LLM 이 정하나 코드가 정하나")을
우리 원장으로 닫으려면 모델별로 갈라야 한다. 그 반론이 정확히 "우리 AUC 0.51
은 **소형 모델**을 잰 값"이기 때문이다. 오늘부터 20건/일이 쌓이는데 이 칸이
비면 **2~3주 뒤 표본이 반쪽**이 된다. 지난 행은 되살릴 수 없다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
matchup._judge_v3 (:1231 apply_winner 호출)  ← 고치는 곳
matchup._real_model                          ← 실제 응답 모델. **원본**. 안 건드린다
team_form.LAST_USAGE                         ← _real_model 이 읽는 원본
matchup.apply_winner                         ← jg["matchup"]["model"] 을 만든다
matchup.apply_code_verdict                   ← 그 값을 pick 으로 나른다(P0-1)
pick_ledger:231 "model"                      ← 원장 칸
v2 경로 (:752 · :1629)                       ← **안 건드린다**
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **v2 경로를 안 건드린다.** 거기는 이미 `_real_model` 보정이 있다.
  계약이 v2 라인이 그대로인지 잰다.
- 🔴 **승자·확신·서술을 안 바꾼다.** 칸 하나만 더 싣는다.
- 🔴 **모르면 NULL 이다.** `LAST_USAGE` 가 판정 역할이 아니면 설정값으로
  떨어지고, 그것도 없으면 **빈 문자열이 아니라 None** 을 쓴다 — `''` 를 쓰면
  "모름"과 "빈 이름"이 같아진다.
- 🔴 **실제 응답 모델이다. 설정값이 아니다.** 무료 사슬은 폴백한다 —
  실측 2026-09-05: `provider=nvidia` 인데 로그는 `claude-sonnet-5` 였다.
  `_real_model` 이 그걸 고치려고 있는 함수다.
- ⚠️ `LAST_USAGE` 는 **직전 호출**이다. v3 에서 승자를 내는 마지막 판정 호출은
  `dbref.recheck`(role=PRELIM_ROLE, JUDGE_ROLES 안)이고 그 직후에 읽는다 —
  순서가 맞다. 다른 역할이 끼면 `_real_model` 이 설정값으로 떨어진다.
- ⚠️ 지난 행은 **백필할 수 없다.** 애초에 안 잡힌 값이라 원본이 없다.

## ③ 되돌리기

커밋 1개 revert (한 줄).

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 배포 뒤 오늘 밤 슬레이트에서
`model` 칸이 채워지는지 원장으로 본다(⑨).

## ⑤ 계약

9건 — v3 가 model 을 넘긴다 · 실제 응답 모델이다(설정값 아님) · 폴백을 잡는다 ·
모르면 None(빈 문자열 금지) · 승자·확신이 안 바뀐다 · v2 경로 보존 ·
apply_code_verdict 가 그 값을 나른다 · 원장 칸까지 간다 · 다른 역할이 끼면 설정값.
