# 게이트2 2판 — 실측이 집은 것 (2026-10-04)

## MLB ✅ `verified_vars: 11` (완료 조건 ≥6)

```
| 경기 | 턴 | done | 검색 ok/거부/중복 | verified_vars | in | cache | out | USD |
| mlb  | 13 |  13  |      34/20/0      |      11       | 205,470 | 175,168 | 15,861 | $0.0912 |

깔때기(build) queries:23 → hits:1105 → kept_identity:139 → kept_date:26
              → fetched:112 → agent_vars:19 → verified_vars:11
탈락 query_too_bare 26 | domain_denied 9 · robots_denied 5
     | llm_unavailable 1 | agent_zero 6 · insufficient 6 · quote_not_found 4 · stale_sample 2
```

### 🔴 둘이 눈에 걸린다

**① 한쪽 에이전트가 예산에 잘려 변수 0개**

```
에이전트 Milwaukee Brewers — budget_cut: 경기당 출력(추론 포함) 20312/20000 토큰
                             · 모델이 도구 없이 글을 냈다(턴 10) → 변수 **0개**
에이전트 San Diego Padres  — done(턴 13) · 후보 10개 → 검증 통과 6개 · $0.0912
```

⚠️ 입력도 넘었다 — **205,470/150,000**. 🔴 `verified_vars 11` 은 **한쪽만**으로
얻은 수다. ⬛ 예산을 올릴지는 사용자 결정이다(§2 예산은 사용자가 정한 돈).

**② 검색어 거부가 에이전트에선 줄었다**

| | 1판 | 2판 |
|---|---|---|
| 에이전트 질의 거부 | 26 / 49 (**53%**) | 20 / 54 (**37%**) |
| 깔때기 `query_too_bare` | 26 | 26 |

🔴 깔때기의 26 은 **세포 질의**다(에이전트 것이 아니다) — 세포 쪽은 안 줄었다.
⚠️ 세포 질의는 `app/queries.py` 가 `parts=` 를 **선언해서** 던진다. 거기서
   무엇이 2개로 세어지는지 **아직 안 쟀다**(#4).

## NPB 🔴 **크래시** — 실제 버그다

```
File "app/analyze.py", line 856, in roster_of
    for nm in (val.get("squad") or []) + (val.get("players") or []):
TypeError: can only concatenate list (not "dict") to list
```

🔴 NPB 어댑터는 `players` 를 **dict** 로 준다(이름 → 선수 페이지 URL):

```
players={'デュプランティエ': 'https://npb.jp/bis/players/13715150.html',
         '東克樹': 'https://npb.jp/bis/players/5115513…', …}
```

⚠️ `squad` 는 **목록**(fotmob 기준 XI)이다 — 두 어댑터가 **다른 모양**을 넣는데
`roster_of` 가 목록만 가정했다. 🔴 `+` 가 터지면 **경기 전체가 죽는다**
(`gather` 입구다).

### 🔴 고치는 순서 (§11-1)

증상은 *"NPB 가 터진다"* 다. 모양은 **"어댑터가 넣는 모양을 `roster_of` 가
모른다"** 다. → 계약을 **어댑터가 실제로 넣는 모양들**로 짓고(목록·dict·빈 것),
빨간 것을 보고, 그 다음 고친다.
⚠️ 그리고 **왜 지금까지 안 터졌나**: NPB 경기를 이 경로로 **처음** 돌렸다
(1판은 `match_not_found` 로 입구에서 끝났다).

## ⚠️ 체인이 도는 중이라 아직 안 고쳤다

코드를 지금 바꾸면 **경기마다 다른 코드**가 돌아 게이트2 증거가 더러워진다.
→ KBO·북마케도니아·크로아티아가 끝난 뒤에 고치고 **NPB 만 다시** 돈다.
🔴 그때 보고에 **경기마다 커밋 해시**를 적는다(섞인 것을 숨기지 않는다).
