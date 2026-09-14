# MOV-2 — 이동 규칙을 아무도 부르지 않는다 (배당 이동 분류 배선)

## 왜

`MOV-1`(2026-09-13)이 이동 분류 규칙(`news`·`money`·`contra`·`none`)을
만들었지만 **호출부가 없다.** 기준선(`open`)을 고르는 `baseline()` 도, 두
시점 차를 재는 `move_between()` 도 부르는 곳이 0이었다. 이름표를 붙이는
쪽이 오늘 생겼으므로(`TRG-2`, 운영 실측 21행) 이제 읽을 값이 있다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_mov2.py
  → ImportError: cannot import name 'record_move' from 'app.engine.pick_ledger'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "odds_move\|move_class\|odds_open" app/ tests/
app/engine/odds_move.py            baseline·series·move_between·classify·confirm·cancels
   → 호출부 **0** (이 배선이 최초)
tests/engine/test_odds_move.py     순수 함수 단위 테스트만
pick_ledger.odds_open·move_class·move_reason  → 쓰는 곳 0 · 읽는 곳 0
```
쓰는 자리는 `record_analysis` 안, **`record_clv(at="verdict")` 바로 뒤**다.
그 자리를 고른 이유: 원장 행이 방금 확정됐고(트랜잭션 안), 커넥션이 이미
열려 있고, "저장 전용·실패해도 판정을 막지 않는다"는 규약이 이미 그 자리에
적혀 있다. 새 잡·새 트랜잭션을 만들면 타이밍이 갈린다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `pick_ledger.odds_open` | 기준선 시점의 **고른 쪽** 배당 |
| `pick_ledger.move_class` | `news`/`money`/`contra`/`none` |
| `pick_ledger.move_reason` | 규칙이 적은 사유 원문 |

세 칸 모두 **이미 있는 컬럼**이다(스키마 확인). 다른 곳이 이 칸을 쓰지
않는다(①). 새 테이블·새 컬럼·새 소스 호출 없다 — `odds_snapshots` 에 이미
있는 값만 읽는다.

🔴 `odds_open` 은 `odds_at_verdict`·`odds_closing` 과 **같은 쪽**(고른 쪽)이다.
   `predicted_side` 헬퍼를 그대로 쓴다 — 한쪽은 홈, 다른 쪽은 원정 배당이
   들어가면 세 값을 한 줄로 못 읽는다(CLV-3 이 같은 실수를 이미 잡았다).

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** 승부(`h2h`) 시장만 보고, 3-way(축구 무승부)는
`market_edge.implied_probs` 가 이미 처리한다 — 야구는 `draw` 슬롯이 없을
뿐 같은 경로다. 종목 분기를 넣지 않았다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 이름표 붙은 배당이 없으면 **아무것도 쓰지 않고** 사유를 로그에 남긴다.
  `none`(안 움직였다)으로 채우지 않는다 — "모른다"와 "안 움직였다"는 다르다.
- 기준선 뒤 시점이 아직 없으면 같은 이유로 기록하지 않는다.
- 호출부는 CLV 와 같은 규약으로 예외를 잡아 경고만 남긴다 — 이동 분류 실패가
  판정 기록을 되돌리면 안 된다.
- 성공하면 경기별로 `[move] game=… 소스 open→lineup money (사유)` 한 줄.

⚠️ **지금은 `news` 를 넘겨 주는 배선이 없다**(SCT-3·ANL-1 이 다음 단위).
   그래서 분류는 `money`/`none` 만 나온다. 이것은 `odds_move` 가 문서로
   선언한 정상 동작이다 — 근거 없이 `news` 를 붙이면 확증이 거짓으로 선다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 임계값(2%p·3%p)·기준선 우선순위·분류 규칙을 **다시 적지 않는다.**
  `odds_move.MOVE_MIN_PP`·`BASELINE_ORDER`·`classify` 가 원본이다.
- 마진 제거도 새로 만들지 않는다 — `market_edge.implied_probs` 를 쓴다
  (2-way·3-way 를 이미 가른다).
- 고른 쪽 판정도 `predicted_side` 원본을 쓴다.
