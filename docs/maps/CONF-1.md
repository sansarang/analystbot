# CONF-1 — 확신 등급을 코드가 정한다 (1차 결정 3 · 2차 결정 C)

## 왜

```python
# app/engine/verdict.py — 종전. 코드가 하는 일은 라벨 정규화뿐이다
def level(raw) -> str:
    t = str(raw or "").strip()
    return t if t in LEVELS else "하"
```
등급을 정하는 것은 **전적으로 LLM**이었고, AUC 0.5122 짜리 판정에 AI가 스스로
붙인 등급을 그대로 실어 보냈다. 같은 맥락의 자기모순 실측(2026-09-13):
`DB본것` 에는 "선발 최근 등판을 봤다"고 적고 서술에는 "확인하지 못했다"고 썼다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "verdict.level\|from app.engine.verdict import level" app/
app/engine/verdict.py  decide() 안 1회 — 유일한 호출부
$ grep -rn "engine.confidence" app/
app/engine/pick_ledger.py:97  probe() — **기록 전용**, 게이트에 닿지 않는다
필수 축 이름의 원본: app/engine/dbref.py ITEMS
```

⚠️ **`app/engine/confidence.py` 는 이미 있다.** 2차 지시문은 "신설"이라 했으나
   신설하면 사본이 된다 — 기존 모듈에 `REQUIRED_AXES`·`by_code`·`divergence_pp`
   를 **더한다.** 기존 `probe`(계측 전용)는 건드리지 않는다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `confidence.REQUIRED_AXES` | 종목별 필수 축. **이름은 `dbref.ITEMS` 에서 온다** |
| `confidence.by_code(jg, have)` | 규칙표대로 등급 결정 |
| `confidence.divergence_pp(p_code, p_market)` | 정의 고정 = Σadj |
| `verdict.level(raw, expected=None)` | **입력값 복사 검증**으로 교체 |

🔴 `DB본것`·채택 자료 수·뉴스 건수를 **입력에서 뺀다**(자기보고).
🔴 `expected` 가 없으면 종전처럼 정규화한다 — 아직 기대값을 못 주는 호출부가 있다.

## ③ 리그·종목 분기

`REQUIRED_AXES` 표 하나를 종목으로 조회한다. 분기문을 늘리지 않는다.

⚠️ **모호한 자리를 보수적으로 해석했다.** 지시문의 필수 축은 야구 2종
   (양 선발 최근 등판 + 불펜 가용성), 축구 2종(라인업 + 결장)인데 "중" 조건은
   "2/3 이상"이다. 2종에서 2/3 은 1.33 이라 **올림하여 2종 전부**로 읽었다 —
   느슨한 쪽(1종)으로 읽으면 등급이 쉽게 올라간다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **자기보고가 슬쩍 입력이 된다** | 자기보고 키를 넣어도 등급이 같은지 계약 |
| 🔴 뼈대 없이 등급이 붙는다 | `p_market` NULL → 무조건 하. 계약 |
| 잠정 타순으로 상이 나온다 | 라인업 잠정 → 무조건 하. 계약 |
| 필수 축 이름을 베껴 적는다 | `dbref.ITEMS` 대조 계약 |
| `level()` 교체로 종전 경로가 깨진다 | `expected` 없으면 종전 동작. 계약 |

⚠️ **아직 못 잰 것**: 등급별 브라이어가 상 < 중 < 하 순서인가.
   100건마다 내야 하고, 순서가 깨지면 규칙 재검토 보고다(지시문).
⚠️ 조정이 붙기 전에는 `adj_pp` 항목이 0~1 이라 **상이 거의 안 나온다** —
   지시문이 "상이 드문 것이 정상"이라고 명시했다.

## ⑤ 사본

- 등급 눈금(`상·중·하`)을 새로 정의하지 않는다 — `verdict.LEVELS`.
- 필수 축 이름을 손으로 적지 않는다 — `dbref.ITEMS`.
- 기존 `confidence.probe` 계측을 건드리지 않는다.
