# REJ-1 영향 지도 — ⑩ 재판정 신호가 주입된 적이 없다

## 1. 무엇이 틀렸나 (실측 원문)

```
analysis_runs 에 n10_rejudge 행 0건 (Phase 0 D-7)
```

```python
# app/flow/nodes/n10_rejudge.py:48
signals = (ctx.inject or {}).get("rejudge_signals") or {}
# app/flow/bridge.py
ctx.inject = {"model_probs": ...}        ← 신호가 없다
```

**영원히 빈 dict 였다.**

재료는 판정 캐시에 있다:

```
10086 lineup_just_confirmed = True     (confirmed 이고 확정 1시간 이내)
lineup_notes 에 "home 선발 변경: A → B" 줄이 들어온다(`lineups.py`)
```

⚠️ `lineup_just_confirmed` 의 정의는 `lineup_confirmed_at` 에 의존한다
   (`pipeline.py:1758`). **LIN-1 전에는 KBO·NPB 가 그 칸을 한 번도 안 적어서
   구조적으로 항상 False 였다.** 이 단위는 그 수정 위에 선다.

## 2. 어디를 고치나

`app/flow/bridge.py` — 신호 추출 순수 함수 + 주입 한 줄.

## 3. 영향 지도 5문

**① 선발 교체 신호를 어디서 읽나.**
🔴 `pipeline.starter_changed` 는 **쓰지 않는다.** 이름과 뜻이 다르다:

```python
"starter_changed": bool(g.get("lineup_status") == "conflict")
```

그건 *소스 불일치*이지 선발 교체가 아니다. n10 머리말은 트리거가
"`starter_change_notes` 가 낸 줄"이라고 적고 있으므로 **그 줄**을 쓴다
(`lineup_notes` 의 "선발 변경" 포함 여부).
⚠️ 저 칸은 `deep.needs_refresh` 가 쓰고 있어 **건드리지 않는다** → 3-5-b.

**② 매 사이클 재발동하지 않나.**
`lineup_just_confirmed` 는 **확정 1시간 이내**만 참이고, ⑩의 창은 킥오프
−90 ~ −20분이다. 두 조건이 겹치는 구간은 짧다. 그래도 같은 경기가 두 사이클에
걸릴 수 있는데, ⑩은 한 실행 안에서만 1회를 보장한다(상태가 사이클마다 새로
만들어진다) — **그 한계를 보고에 적는다.** 여기서 새 중복 방지 장치를 만들지
않는다(만들면 그게 또 하나의 상태다).

**③ 이걸 이으면 ⑩ 행이 바로 생기나.**
🔴 **아니다.** ⑩은 ⑥ 통과 뒤에 있다(`run.py:96`). 지금 `stop_reason` 이
`n06_unknown` 51건이라, ⑥이 `모름과반`인 한 ⑩은 여전히 0건이다.
**그 사실을 숨기지 않는다** — 신호 배선은 필요조건이고 충분조건이 아니다.

**④ 창 밖이면.**
안 쏜다. 계약이 T-200분에 신호가 있어도 `triggered=False` 인지 확인한다.

**⑤ 무엇이 조용히 0이 되나.**
캐시가 없는 경기는 신호가 빈 dict 다. 그때 ⑩은 `triggered=False` 이고
`in_window` 는 그대로 기록된다 — "창 밖이라 안 쐈다"와 "신호가 없었다"가
스냅샷에서 갈린다.

## 4. 안 하는 것

- `pipeline.starter_changed` 의 정의를 바꾸지 않는다(다른 소비자가 있다).
- ⑥의 채점 규칙을 건드리지 않는다.
- 새 중복 방지 상태를 만들지 않는다.
