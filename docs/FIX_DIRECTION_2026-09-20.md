# FIX-DIR — 증거에 방향을 싣는다 (2026-09-20)

지시문 `fix_direction_0920` FIX-1~6 의 수행 기록.

| 항목 | 값 |
|---|---|
| 착수 HEAD | `3544b25` |
| 커밋 | **`9fbe5bb`** (FIX-1~6) · **`ea3892e`** (FIX-1 `lineup_out` 배선) |
| 배포 | `analystbot-scheduler` SUCCESS 08:59:29 · 09:08:18 (KST 2026-09-20) |
| 발송 스위치 | `pipeline_v14_send = False` — **끈 채로 유지했다** |

---

## 0. 무엇이 틀렸나 (착수 근거)

운영 로그 원문. 상대 선발이 **잘 던진 경기와 무너진 경기에 같은 값**이 나갔다.

```
WSH@STL  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 6.0이닝 1자책
NYY@ARI  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 6.7이닝 6자책
MIA@SD   starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 4.0이닝 5자책
MIN@LAA  starter_recent3  pp=3.0 sign=1.0 strength=1.0   상대 선발 4.0이닝 4자책
```

⑦은 `sides` 의 **항목 수**만 읽었다. 내용을 안 봤다.

---

## 1. Phase 0 — 전제 대조 (착수 HEAD `3544b25`)

| | 전제 | 판정 |
|---|---|---|
| P1 | `n07_adjust._direction` 이 `sides` 의 쪽별 항목 수만 본다 | **참** |
| P2 | `strength` 는 `raw_excerpt` 에 숫자가 있으면 1.0 (`_NUM`) | **참** |
| P3 | `bullpen_3d`·`lineup_out` 은 양쪽 자료가 있으면 부호 0 으로 빠진다 | **참** |
| P4 | ⑨의 A 조건은 핵심 confirmed≥2 **그리고** \|Σadj\|≥3.0 → ⑦의 ±3.0 하나로 충족 | **참** |
| P5 | ⑪이 `max(cands, key=edge_pp)` 로 전 마켓 최대 edge 를 고르고, 파생에 시장 동의·상한·등급 필터가 없다 | **참** |
| P6 | λ 절사 사실이 `LambdaResult` 에 남지 않는다 | 🔴 **다르다 — 아래** |
| P7 | ⑬이 확신 등급을 발송 조건으로 보지 않는다 | **참** |
| P8 | `bp_pitches_3d` 에 `ip_last3d` 를 넣고, 없는 피처를 0 으로 둔다 | **참** |

🔴 **P6 정정.** 절사 사실은 **`trace` 문자열에는 남아 있었다** —
`scoring.py` 의 `trace.append(f"{side} λ 범위 절사 ({raw:.2f} → {lam[side]:.2f})")`.
다만 **읽는 쪽이 문자열을 파싱해야** 해서 ⑪이 쓸 수 없었다. "없다"가 아니라
**"구조화돼 있지 않다"** 가 맞다. 그래서 FIX-4d 는 새로 만드는 것이 아니라
`clipped` 라는 **칸으로 승격**하는 일이었다.

### 추가 보고 — STR-2(`51ed877`)가 `starter_recent3` row 에 넣던 실제 모양

운영 g10938 스냅샷 원문 1건:

```
value       = ["4.0이닝 4자책", "4.0이닝 2자책"]
sides       = {"away": 2}
raw_excerpt = "4.0이닝 4자책 · 4.0이닝 2자책"
```

ERA3 는 **문자열 안에만** 있었다. 구조화된 편차가 없으니 ⑦이 읽을 것이
항목 수밖에 없었다 — P1 은 ⑦의 결함이 아니라 **⑤가 안 실어준 결과**다.

---

## 2. 무엇을 고쳤나

| FIX | 무엇 | 파일 |
|---|---|---|
| 1 | 변수별 방향 판정 — **순수 함수**, DB·LLM·HTTP 0건 | `app/flow/direction.py` (신규) |
| 1 | 문턱 — **미검증 사전값**, 채점 30건 뒤 데이터로만 고친다 | `config/rules.yaml` `flow.direction.*` |
| 1 | 증거 row 에 `direction` 을 싣는다 (선발·불펜·타순 셋 다) | `n05_evidence.py` |
| 1 | "모르면 −1" 폐기 → **0**, 조정 행 자체를 안 만든다 | `n07_adjust.py` |
| 2 | `_NUM` 삭제 · `strength = min(1.0, \|dev\|/dev_full)` | `n07_adjust.py` |
| 3 | \|Σadj\| 는 **방향이 판정된 조정만** · `struct_grade` 분리 | `n09_conf.py` |
| 4a | `max()` 전수 스캔 폐기 → ④가 지정한 마켓 하나 | `n11_value.py` · `n04_hyp.py` |
| 4b | 시장 동의(디빅 · open→현재 이동) · **open 없으면 fail closed** | `n11_value.py` |
| 4c | edge 상한 = `flow.gate_pp.freeze`(12.0 재사용) → "오류의심" | `n11_value.py` |
| 4d | `LambdaResult.clipped` 승격 · 잘린 경기는 구조 후보 0 | `scoring.py` · `n11_value.py` |
| 4e/f | 픽 반대 증거가 1개라도 있으면 **철회**(라인 조정 금지). 승패도 같은 규칙 | `n11_value.py` |
| 5 | 발송 조건에 등급 — 승패 `grade==A` · 구조 `struct_grade==A` | `n13_send.py` |
| 6 | `bp_pitches_3d` 에 투구수 합 · 결측이면 `None` 반환 | `models/lambda_model.py` |

⚠️ **덤으로 하나 잡혔다.** `soccer_lambdas` 가 `LambdaResult` 를 **위치 인자**로
돌려주고 있어서, `clipped` 를 5번째 칸에 넣자 종전 5번째(`usable`)가 조용히
밀렸다. `test_soccer_lambda_from_xg` 가 잡았다 — 키워드 인자로 바꿨다.

---

## 3. 완료 조건 1) — pytest 전체 출력 마지막 20줄

```
  tests/test_satellite_soccer.py::test_위성_소스가_있는_리그는_전부_부상표도_받는다
      → news.google.com
  tests/test_satellite_soccer.py::test_표에_없는_팀은_부상자가_없다고_말하지_않는다
      → news.google.com
  tests/test_satellite_soccer.py::test_한_팀이_터져도_나머지가_산다
      → news.google.com
  tests/test_satellite_split.py::test_축구가_공용_검색을_쓴다
      → news.google.com
  tests/test_scope_combos.py::test_flagged_pick_never_recommended_regression
      → generativelanguage.googleapis.com, news.google.com, statsapi.mlb.com
  tests/test_soccer_fixture_sources.py::test_football_data가_막혀도_배당_리그는_산다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_둘_다_막히면_빈손이지_예외가_아니다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_목모드_football_data는_부르지_않는다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_배당이_막혀도_메이저_리그는_산다
      → www.fotmob.com
5177 passed, 4 skipped in 103.35s (0:01:43)
```

### 계약 테스트 (⑤)

지시문이 이름을 준 픽스처 넷 + 기존 회귀가 `tests/pipeline/test_fix_direction_0920.py`
(16건)에 있다. **수정 전 코드에서 실패하는가**를 두 번 쟀다.

```
# HEAD~1(3544b25) 워크트리에 이 파일만 얹어서
15 failed in 0.17s          ← 수정 전
15 passed in 0.07s          ← 지금

# `lineup_out` 배선은 9fbe5bb 사본에 얹어서 (훅 자동 판정)
▶ (a) 지금 코드에서 통과하는가       1 passed
▶ (b) 수정 전 코드(HEAD)에 얹으면    1 failed
✅ ⑤ 계약 테스트 — 지금 통과(0) · HEAD 에서 실패(1)
```

⚠️ 첫 번째는 훅이 자동 판정하지 못했다 — 훅은 **`HEAD` 사본**에 테스트를 얹는데
이미 커밋해서 `HEAD` 가 수정본이었기 때문이다. 같은 절차를 `HEAD~1` 로 손으로
돌렸고, 사유를 감사 로그에 남겼다(`step.sh skip FIXDIR 5`).

---

## 4. 완료 조건 2) — 오늘 6경기 전/후

저장된 입력으로 운영에서 재실행(`run_slate` 에 행을 직접 넘겨 창을 우회).
**전**은 같은 경기의 종전 `analysis_runs` 스냅샷이다.

### 4-1. ⑦ 조정 — 부호·강도가 내용을 읽기 시작했다

| 경기 | 전 | 후 |
|---|---|---|
| WSH@STL (10933) | `starter_recent3` sign **+1.0** str **1.0** pp **+3.0** (dev·basis 없음) | sign **0** — `dev=-0.151 · ERA3 3.566 — 기준 근처` → **행 없음** |
| SEA@COL (10934) | ⑦ 행 없음 | `bullpen_3d` sign **0** — `3일 15.0이닝·2연투 3명 \| 3일 8.33이닝·2연투 3명` (양쪽 악재 상쇄) |
| NYY@ARI (10935) | `starter_recent3` sign **+1.0** str **1.0** pp **+3.0** | sign **0** — `dev=0.2407 · ERA3 5.211 — 기준 근처` |
| MIA@SD (10936) | `starter_recent3` sign **+1.0** str **1.0** pp **+3.0** | `starter_recent3` **+1.0** / **1.0** / **+3.0** — `dev=1.1952 · ERA3 9.22 (기준 4.2)` ✅ 같은 값이지만 **이번엔 근거가 있다** |
| " | — | `bullpen_3d` **−1.0** / **0.5** / **−1.00** — `3일 10.0이닝·2연투 3명` |
| " | — | `lineup_out` **−1.0** / **1.0** / **−2.50** — `평소 주전 2명 제외` |
| SF@LAD (10937) | ③ 보드고정에서 멈춤 | 같음 (③ −17.89%p) |
| MIN@LAA (10938) | `starter_recent3` sign **+1.0** str **1.0** pp **+3.0** | sign **0** — `표본 부족(이닝합 8.0 < 9.0) · 짧은 등판` ✅ 픽스처 `f0920_laa` 가 실측으로 재현됐다 |

🔴 **MIA@SD 가 이 수정의 요지다.** 전에는 세 변수 중 하나만, 근거 없이 `+3.0`
이었다. 후에는 셋이 각각 판정돼 **+3.0 / −1.00 / −2.50 = −0.50%p** 가 된다.
같은 자료에서 **부호가 뒤집혔다.**

### 4-2. 판정·등급·픽

| 경기 | p_code 전→후 | grade 전→후 | struct_grade | pick_type | 철회 사유 (후) |
|---|---|---|---|---|---|
| WSH@STL | 0.5169 → **0.4869** | A → **B** | None | 보드 | 지정 마켓 `total` 후보 0 |
| SEA@COL | 0.5718 → **0.5718** | B → **B** | None | 보드 | **시장 동의 실패**(open 없음 · 반대 이동) |
| NYY@ARI | 0.6260 → **0.5960** | A → **B** | None | 보드 | 가설이 마켓을 지정하지 않았다 |
| MIA@SD | 0.6178 → **0.5828** | A → **B** | None | 보드 | 지정 마켓 `total` 후보 0 |
| SF@LAD | None → None | None | None | — | ③ 보드고정(−17.89%p)에서 멈춤 |
| MIN@LAA | 0.5600 → **0.5339** | A → **B** | None | 보드 | 지정 마켓 `total` 후보 0 |

🔴 **A 가 넷에서 0 으로 줄었다.** 종전 A 는 전부 ⑦의 근거 없는 `+3.0` 하나로
\|Σadj\|≥3.0 을 채운 것이었다(P4). 그 `+3.0` 이 사라지자 A 도 사라졌다 —
**등급이 내려간 것이 아니라 없던 등급이 드러난 것이다.**

⚠️ `struct_grade` 는 여섯 경기 모두 `None` 이다. 구조 후보가 한 건도 가드를
통과하지 못했기 때문이고, ⑪이 후보를 세운 뒤에야 채워지는 칸이다.

⚠️ **⑨ 스냅샷에 `sum_adj` 칸이 없다.** 지금은 grade A 일 때만 `reason`
문자열에 들어간다. 위 표의 합은 같은 스냅샷의 ⑦ 행 `pp` 를 더해 냈다.
칸으로 올릴지는 **지시를 기다린다**(범위 밖).

### 4-3. 발송 0건 증빙

```
발송 스위치 pipeline_v14_send = False
흐름 결과: {"games": 6, "stopped": {"n11_no_value": 3, "n06_unknown": 2, "n03_freeze": 1}, "sent": 0}
```

🔴 **⑬의 `why` 는 여섯 경기 모두 `null` 이다 — ⑬까지 간 경기가 없기 때문이다.**
③·⑥·⑪에서 먼저 멈췄다. 지시문이 요구한 "⑬ why 로 증빙"을 문자 그대로 대지
못하므로, 대신 **`sent: 0` 과 멈춤 사유 분포**를 증거로 낸다. ⑬의 `등급미달`·
`섀도` 경로 자체는 테스트가 덮는다(`test_한_번만_보낸다` · `test_SEND가_켜지면_보낸다`).

⚠️ 한 번의 재실행에서 MIA@SD·MIN@LAA 가 `n06_unknown` 으로 빠졌는데, 사유는
**슬레이트 검색 예산 소진**(`[flow:n05] 슬레이트 예산 소진 — 나머지는 미상`)
이었지 이번 수정이 아니다. 두 경기만 따로 돌리자 증거 3건·2건으로 정상
진행했다. 6경기를 한 슬레이트로 돌리면 예산 10 이 앞 세 경기에서 소진된다 —
**등록해 두는 별건**이다.

---

## 5. 보고만 (수정하지 않았다)

### 5-1. ③ 보드고정·시장과대 중 \|gap\| ≥ 4%p — **16건 / 판정 134건** (최근 14일)

```
09-19 07:40 [mlb] Chicago Cubs @ Cincinnati Reds            시장과대  -7.06%p
09-19 07:40 [mlb] Kansas City Royals @ Pittsburgh Pirates   시장과대  -7.82%p
09-19 08:10 [mlb] Athletics @ Cleveland Guardians           시장과대  -9.03%p
09-19 18:00 [npb] Hiroshima Toyo Carp @ Hanshin Tigers      시장과대  -4.37%p
09-20 08:10 [mlb] Atlanta Braves @ Houston Astros           시장과대  -4.82%p
09-20 09:10 [mlb] New York Yankees @ Arizona Diamondbacks   시장과대  -5.56%p
09-20 10:10 [mlb] San Francisco Giants @ Los Angeles Dodgers 보드고정 -17.89%p
09-20 18:00 [npb] Hiroshima Toyo Carp @ Chunichi Dragons     시장과대  -6.33%p
09-20 18:00 [npb] Yokohama DeNA BayStars @ Hanshin Tigers    보드고정 +20.36%p
09-20 14:00 [npb] Orix Buffaloes @ Hokkaido Nippon-Ham       시장과대 -11.36%p
09-19 17:00 [kbo] Samsung Lions @ Lotte Giants               시장과대 -11.53%p
09-19 17:00 [kbo] Doosan Bears @ KT Wiz                      시장과대 -10.58%p
09-20 14:00 [kbo] Samsung Lions @ Lotte Giants               보드고정 -20.96%p
09-20 14:00 [kbo] Doosan Bears @ KT Wiz                      시장과대 -11.27%p
   (NYY@ARI · SF@LAD 는 재실행으로 같은 날 두 번 잡혀 16건 중 2건이 중복이다)
```

🔴 **"① 사전값에 선발이 없어서" 인가 — 16건 전부 그렇다. 다만 이유가 다르다.**

① 스냅샷이 가진 칸 **전체**가 이것뿐이다:

```
['asof', 'elo', 'p_away', 'p_draw', 'p_home', 'source']     source = "team_elo"
```

`app/flow/nodes/n01_prior.py:98·113` 이 쓰는 칸이 그게 전부고,
**`n01_prior.py` 와 `app/engine/prior.py` 를 통틀어 "선발·starter·pitcher"
라는 낱말이 0건이다.** 즉 선발이 **빠진** 것이 아니라 **들어갈 자리가 없다.**
① 은 팀 Elo 하나로 만든 값이고, 시장은 선발을 이미 가격에 넣는다. 그 차이가
곧 `gap` 이다 — 위 16건은 "모델이 틀렸다"가 아니라 **"모델이 선발을 모른다"** 다.

⚠️ ① 은 **동결 대상**이라 손대지 않았다. 고칠지·어떻게 고칠지는 사용자 결정이다.

### 5-2. `rules_from_failure_0919` R1~R7 — **원문이 이 세션에 없다**

R1~R7 의 내용이 이 대화에도, `docs/` 에도, `~/Downloads/analystbot_export/`
에도 없다(`STATUS_2026-09-19.md` 에는 다른 내용이 들어 있다). **없는 규칙을
있다고 짐작해 예/아니오를 적지 않는다.** 원문을 주면 항목별로 파일:행과 함께
답한다.

---

## 6. 남은 것 (지시 대기)

| 무엇 | 왜 멈췄나 |
|---|---|
| ⑨ 스냅샷에 `sum_adj` 칸 | 범위 밖. 지금은 grade A 일 때만 `reason` 에 들어간다 |
| 슬레이트 검색 예산이 뒤 경기를 굶긴다 | 6경기에 예산 10 — 앞 세 경기가 다 쓴다 |
| ① 사전값에 선발 자리 | **동결 대상.** 5-1 참고 |
| `flow.direction.*` 여덟 값 | **미검증 사전값.** 채점 30건 전에는 고치지 않는다 |
