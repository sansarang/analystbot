# EXT-2 영향 지도 — 추출이 게이트 라벨로 갈렸다 (STEP 1-g)

## 0. 재현 (실측 2026-09-20 KBO)

```
[gate]  g1766 — 사전값 0.638(tier+form 53/54) · 시장 0.634 · gap  +0.44 → 동의
[scout] Doosan Bears@KT Wiz — 게이트 동의 · 빅매치 아님 · LLM 추출 생략
[flow:n03] g1766 — 사전값 0.5655(team_elo)  · 시장 0.6752 · gap −10.97 → 시장과대
```

KBO 5경기가 기사를 **6~14건씩** 모아 놓고도 `out` 이 채워진 것은 **한 경기뿐**.
두산@KT 는 기사 12건을 쥐고도 여섯 변수 전건 미상이었다.

**게이트가 둘이다** — 위성은 구경로(`pick_ledger.gate_of`, tier+form)를 보고,
흐름은 `n01_prior`(team_elo)를 본다. 그래서 흐름의 가설이 수집에 닿지 못한다
(CLAUDE.md "가설이 수집을 지휘한다"가 깨진 자리 · 2026-09-20 절).

## 1. 결정 (`two_gates_0920` → 답 B · 범위를 추출로 한정)

> 추출 대상 = **기사가 1건 이상 모인 전 경기.** 게이트 라벨·빅매치로 가르지
> 않는다. 경기당 기사 상한은 **depth** 로. depth 가 없으면 `normal`.

## 2. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `app/collectors/satellite.py:1051` | 추출 조건 `gate_target or tag.big` **제거** |
| `app/collectors/satellite.py` | `get_depth()` 추가 · 기사 선별을 키워드 우선으로 · LLM 상한 |
| `config/rules.yaml` | `flow.depth_fallback` · `flow.depth_articles` · `llm.daily_call_cap` |
| `config/evidence_lexicon.yaml` (신규) | 키워드 사전 — v2 STEP 7-4 가 쓸 **그 파일** |
| `app/leagues.py` | 야구 리그 키가 비지 않게 |

**② 왜 `league_key` 가 비었나.**
`league_labels()` 는 `LEAGUES` 의 역매핑인데 그 표는 **축구 전용**이다
(`epl`·`la_liga`·…·`acl` 여덟). 야구가 없어 `.get("KBO")` 가 None 이고
`or ""` 로 빈 문자열이 됐다. 그 키는 `scout_config.rank(url, league)` 가
소스 tier 를 고르는 데 쓰므로, 비면 **야구 기사 등급이 전부 미상**이 된다.
🔴 그런데 `config/sources.yaml` 에는 `kbo`·`npb`·`mlb` 가 **이미 있다**
(tier1·tier2). 표가 있는데 키가 안 닿았을 뿐이다.

**③ 무엇이 늘어나나 — LLM 콜.**
종전에는 §3 예산으로 **최대 8경기**만 추출했다. 이제 기사가 있는 전 경기가
대상이므로 콜이 는다. 그래서 **두 겹으로 묶는다**:
경기당 기사 상한(depth: shallow 0 · normal 2 · deep 5) + **일일 상한**
(`llm.daily_call_cap`, 사전값 200 · 미검증). 상한 도달 시 추출을 건너뛰고
`reason="llm_cap"` 을 남긴다 — **예외를 던지지 않는다.**

**④ 무엇이 깨질 수 있나.**
🔴 가장 큰 위험은 **무료 한도 소진**이다(실측: groq TPD 200k 가 오늘 이미 한 번
소진됐다). 위 두 겹이 그것을 막고, 상한에 걸려도 파이프라인은 완주한다.
⚠️ `select_search_targets`(§3 예산)와 `gate_of` 호출은 **그대로 둔다** —
그것은 **기사 수집** 예산이지 추출 조건이 아니다. STEP 6 에서 한 번에 옮긴다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/pipeline/test_ext2_extract_all_games.py` —
게이트로 안 갈리는가 · depth 폴백 · 상한이 yaml 에 있는가 · 키워드 사전 ·
`test_league_labels_nonempty` · **`test_search_targets_move_to_flow_select`**
(STEP 6 이 `flow/select.py` 를 만드는 순간 교체를 잊으면 실패하는 잠금).

## 3. 이번에 하지 않는 것

- `satellite.py:1415·1422` `gate_of` · `:1443` `select_search_targets` →
  **STEP 6 에서 한 번에.** `test_pa15_search_budget` 3건도 그대로 둔다.
- `pick_ledger.py:986` 은 **원장 용도**라 계속 건드리지 않는다.
