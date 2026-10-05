# 측정 — **아직 아무것도 안 쟀다** (2026-10-04)

🔴 **조용한 0 금지**(CLAUDE.md #3). 아래 세 파일은 **없다** — 없다는 사실을
여기 적는다. 빈 파일로 때우면 `compare.py` 가 *"올랐다"* 를 거짓으로 말한다.

| 파일 | 무엇 | 지금 |
|---|---|---|
| `baseline_solar.json` | `enabled: false` · **Solar 단독** 기준선 | 🔴 **안 쟀다** |
| `stage3.json` | `enabled: stage3` · 가설·시나리오 | 🔴 **안 쟀다** |
| `stage34.json` | `enabled: stage3+4` · 반증까지 | 🔴 **안 쟀다** |

## 왜 아직 안 쟀나 — **순서가 막고 있다**

작업지시 §5 가 순서를 못 박았다:

```
게이트 3 → 게이트 4 → 게이트 5 를 **Solar 단독**으로 통과
  → 그 수치를 baseline_solar.json 으로 고정
  → enabled: stage3   → stage3.json
  → enabled: stage3+4 → stage34.json
  → compare.py 가 표로 보고
```

🔴 **게이트 2 도 아직 안 닫혔다**(§3 완료 조건: 5경기 중 4경기 `verified_vars ≥ 6`).
⚠️ 그리고 작업지시 §6 금지: *"정답지 재현 계약이 빨간 채로 DeepSeek 를 켜지
   않는다."* 지금 **셋 중 둘이 빨갛다** —
   `docs/fable/questions/2026-10-04_scenario_letters_full.md` (사용자 답 대기).

## 재는 법

```bash
PYTHONPATH=. uv run python -m metrics.compare     # 표 + 두 게이트 판정
```

## 🔴 이 수로 **규칙을 고치지 않는다**

사용자 지시 2026-10-02: *"쌓이는거는 우리 로직이 맞냐 틀렸냐만 검증하는
방법으로만 사용한다."* 여기서 나온 수가 답하는 것은 하나다 —
**단계 3·4 를 켤 수 있나.** 계수·문턱·가중치는 **건드리지 않는다.**
