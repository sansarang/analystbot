# 🔴 리그 선언을 **늘려야** 그 리그 경기를 찾는다 — 사용자 결정이 필요하다

## 무엇을 봤나

실측 2026-10-10 — 사용자가 시킨 **우니온 데 산타페(아르헨티나)** 테스트:

```
PYTHONPATH=. python tools/run_stage8.py "Union vs Defensa y Justicia" --deep
→ 🔴 openworld_not_found (0.8분 · $0.0014)
[findgame] 검색 언어 ['en'] — `리그 미상`·팀 ['Union','Defensa y Justicia']
          둘 다 선언이 없고 **나라도 모른다**(클럽이다) — 영어만
```

🔴 경기는 **있다**. fotmob `112`(= `Liga Profesional` · `ccode ARG` · 받아서 확인)
의 일정에 `2026-10-10T00:45Z Unión vs Defensa y Justicia · Clausura Round 12` 가
있다. 못 찾은 까닭은 하나다 — **그 리그가 `config/leagues.yaml` 에 없다.**

같은 병으로 이미 **다섯 경기**가 실패했다(2026-10-07~08):
터키컵 · 이탈리아 세리에D · 애들레이드(호주) · 라이언시티(싱가포르) · 그리고 이것.

## 내가 한 것 — **통로만** 만들고 선언은 안 늘렸다

`teams_from: fotmob:<리그번호>` 꼴을 새로 지원한다(`app/league_index.py`).
실측: `fotmob:112` → **30팀**(Aldosivi·Argentinos Juniors·Boca Juniors …).
대회 표에도 `league:ARG1` 을 넣었다(fotmob 112 · 받아서 확인).

🔴 **그런데 `config/leagues.yaml` 에 리그를 더하자 계약이 빨개졌다**:

```
🔴 선언된 리그가 9개다(기준 7) — 리그를 넣어 인수 테스트를 우회하는 것이
   지시서 금지 1번이다. 늘리려면 사용자 결정이 먼저다
```

계약이 맞다. **되돌렸다.** 지금 저장소는 리그 7개 그대로다.

## 🔴 묻는 것 — 어느 리그를 선언에 넣나

| 보기 | 무엇 |
|---|---|
| **A** | 지금 실패한 리그만 넣는다 — 아르헨티나·J1(이미 자체 Elo 가 있다) |
| **B** | `competitions.yaml` 에 든 **12개 전부** 를 선언에 넣는다(표가 이미 받아서 확인한 리그들이다) |
| **C** | 선언 기준 7 을 **없앤다** — 그 수는 v5 인수 테스트의 범위였고 지금은 범위가 더 넓다 |
| **D** | 다른 것 |

⚠️ **지금은 아무것도 안 넣은 상태**다 — 그래서 아르헨티나·터키·호주·싱가포르
   경기는 **여전히 못 찾는다**. 통로(`teams_from: fotmob:…`)는 준비돼 있어서
   선언 한 줄만 추가하면 바로 돈다.
🔴 `tests/contracts/test_v5_8_3_wo3_pages.py::test_wo3_2` 의 기준 수도 그때 함께
   고쳐야 한다(그 계약이 이 결정을 지키는 자리다).
