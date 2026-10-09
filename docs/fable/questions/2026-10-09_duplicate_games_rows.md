# 🔴 `games` 표에 **같은 경기가 두 줄**로 쌓인다 (2026-10-09)

## 무엇을 봤나

실측 2026-10-09(가시마–감바):

```
 id  | league    | ext_id         | home            | away        | starts_utc
 194 | J. League | fotmob:5803602 | Kashima Antlers | Gamba Osaka | 2026-10-09 10:00:00+00
 193 | jpn.1     | espn:401877610 | Kashima Antlers | Gamba Osaka | 2026-10-09 10:00:00+00
```

유일 제약이 `(sport, ext_id)` 라 **출처가 다르면 막지 못한다.** 그래서 경기 확정이
후보 2건을 보고 `ambiguous` 로 멈췄고 **카드가 아예 안 나왔다.**

## 지금 한 것 — **뽑는 자리**에서 묶는다

`app/core/competition.pick_one` 이 두 팀과 킥오프 순간으로 같은 경기를 묶고
`config/competitions.yaml` 의 `source_priority`(fotmob → espn → …)로 하나를
남긴다. `app/resolve.py` 가 그것을 부른다. 계약으로 박았다.

🔴 **이것은 증상을 막은 것이다.** 표에는 중복이 **계속 쌓인다**.

## 🔴 묻는 것 — 넣는 자리를 어떻게 할까

| 보기 | 무엇 | 걸리는 것 |
|---|---|---|
| **A** | `games` 에 `(sport, home, away, starts_utc)` 유일 색인을 더하고 `ingest` 가 그 키로 `UPSERT` | 팀 이름 표기가 출처마다 갈린다(`Kashima Antlers` ↔ `Kashima`) — 지금은 안 갈렸지만 갈리면 또 둘이 된다 |
| **B** | 경기에 **우리 열쇠**를 발급하고(`match:000123`) `ext_id` 를 그 아래 여러 줄로 둔다 | 스키마 변경 + 이관. 가장 바른 모양이고 가장 크다 |
| **C** | 지금처럼 **뽑을 때만** 묶는다(중복은 둔다) | 표가 계속 커진다 · 채점(`ledger`)이 어느 줄에 붙나가 애매해진다 |
| **D** | 다른 것 |

⚠️ **C 로 돌고 있다.** 🔴 채점이 걸린다 — `ledger` 는 `game_id` 로 붙으므로 같은
   경기에 두 줄이 있으면 *"예측을 안 했다"* 와 *"틀렸다"* 를 가르는 셈이 흐려진다
   (CLAUDE.md: 그 둘을 섞으면 성적이 거짓이 된다).
🔴 고르기 전까지 스키마는 **손대지 않았다.**
