# STR-1 — 총점을 **의도적으로 건너뛴다.** 그런데 모델은 있었다

## 왜

`structure.candidates`:
```python
elif market == "totals":
    # ⚠️ 득점 환경 모델이 없다. 시장을 그대로 쓰면 edge 가 0 이다 —
    #    **후보로 만들지 않는다**(지어내지 않는다).
    continue
```

🔴 **그 주석이 틀렸다.** `scoring.game_distribution` 이 총점 확률을 **이미 낸다**:
```python
out["totals"][line] = {"Over": round(over, 4), "Under": round(1 - over, 4)}   # scoring.py:453
```
그리고 `pipeline:4008` 이 그것을 **받아 놓고 버린다** — λ 스칼라·trace·missing
만 `jg` 에 남기고 `dist["probs"]` 는 어디에도 안 실린다.

오늘만 네 번째로 본 같은 병이다(analyze · reweigh · report · need). 이번은
**"만든 값을 안 싣는다"** 쪽이다.

사용자 목표 분석(2026-09-17)이 쓰는 계산이 정확히 이것이다 —
> "언더 1.91 **요구 52.4% vs 내 추정 52~54%**"

## ⚠️ 축구가 먼저 이득이다

실측 14일: `soccer totals 150건 · spreads 90건` 은 **이미 쌓여 있다.**
야구는 오늘 ODF-1 로 뚫렸다(다음 사이클부터). 즉 이 `continue` 하나가
**축구 총점 후보를 이미 있던 재료 위에서 막고 있었다.**
→ **종목으로 가르지 않는다.**

## ① 이 함수/상태를 읽는 곳 **전부**

```
structure.candidates              ← 고치는 곳 (ours_totals 인자)
scoring.game_distribution         ← 확률의 **원본**. 안 건드린다
pipeline:4008 dist["probs"]       ← 버리던 자리. jg["model_probs"] 로 남긴다
pick_ledger:구조 픽 (ST.candidates 호출) ← 다음 단위(LAM-1)가 잇는다
structure.AH_LINES · EDGE_MIN_PP  ← 문턱. 안 바꾼다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **우리 확률이 없으면 종전대로 건너뛴다.** 시장을 그대로 쓰면 edge 가 0 이고
  그건 지어내는 것이다. 계약이 잰다.
- 🔴 **문턱(`EDGE_MIN_PP`)을 안 바꾼다.** 얇은 엣지는 그대로 걸러진다 —
  실측: 우리 54% vs 시장 52.4% = 1.6%p → 후보 아님. 계약이 잰다.
- 🔴 **핸디 경로를 안 건드린다.** `spreads` 는 종전 그대로다.
- 🔴 **상관 픽 하나 규칙(`_one_per_direction`)도 그대로다.**
- 🔴 **종목으로 가르지 않는다** — 축구·야구 같은 코드다.
- ⚠️ `jg["model_probs"]` 는 이번엔 **담기만 한다.** 원장·분석까지 잇는 것은
  다음 단위다(LAM-1) — 한 커밋에 둘을 섞지 않는다.

## ③ 되돌리기

커밋 1개 revert. 인자 하나·분기 한 덩어리·pipeline 한 줄.

## ④ 측정

①과 **같은 명령**이 통과한다:
```
우리 60% vs 시장 52.4% → totals/Under edge 7.6  후보
우리 54% vs 시장 52.4% → 1.6%p → 후보 아님(문턱)
우리 확률 없음          → 후보 아님(종전)
```

## ⑤ 계약

12건 — 총점 후보가 나온다 · 우리 확률 없으면 안 나온다 · 얇으면 걸러진다 ·
Over/Under 양쪽 · **축구(draw_p)에서도 된다** · 핸디 불변 · 문턱 불변 ·
상관 픽 하나 · 라인 없으면 건너뜀 · pipeline 이 probs 를 남긴다 ·
scoring 이 총점 확률을 낸다(전제) · 종목으로 안 가른다.
