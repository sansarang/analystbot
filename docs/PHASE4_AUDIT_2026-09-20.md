# Phase 4 — U0~U14·S0~S12 완료 여부 대조 (2026-09-20)

마스터 지시문 `AnalystBot 전수 확인·수정 마스터 지시문 (2026-09-19)` Phase 4.

🔴 **이 문서는 1차 보고를 정정한 것이다.** 09:41 에 낸 표에서 **다섯 항목이
틀렸고**, 전부 **내 계수기가 무엇을 세는지 확인하지 않아서** 생긴 오판이다
(§0-13 계수기 규율 위반). 정정 내역을 §2 에 남긴다.

---

## 1. 대조 표 (정정본)

| # | 항목 | 상태 | 근거 |
|---|---|---|---|
| 4-1 | U0 SNAP-1 `snap_tag` | **됨** | 경기 기준 open 계열 없음 **0 / 539 (0.0%)** · 쌍 기준 1/588 (0.2%) |
| 4-2 | U1 트리거 + `ingest_gap` | **됨** | `KINDS` 5 + `ACTIONS` 8 = 13종 · 최다 경기 13행(g8299) · `ingest_gap` 은 트리거가 아니라 대조 함수이고 `pipeline.py:1409` 가 부른다 |
| 4-3 | U2 파생 시장 + manual 북 | **됨** | `tools/manual_odds.py` |
| 4-4 | U3 티어 파일 | **됨** | `config/tiers/` 15개 · 미기입→NULL→보드고정은 오늘 축구 18경기가 증빙 |
| 4-5 | U4 게이트 4분류 | **됨** | 오늘 32경기 보드고정 21 · 동의 8 · 시장과대 4 · 가치의심 2 |
| 4-6 | U5 `hypothesis.py` 순수 | **됨** | LLM·HTTP·DB 매칭 0건 |
| 4-7 | U6 표적 수집(축구) | **미측정** | 오늘 축구 22경기가 ③에서 멈춰 ⑤에 닿지 않았다. 티어 값이 선행 |
| 4-8 | U7 confirmed/refuted/unknown | **고쳤다 → CNF-2** | 반증이 **구조적으로 불가능**했다. `2c6a087` 배포 09:48:54 |
| 4-9 | U8 `adjust.py`·importance·main_axis | **됨** | 446줄 · 각 4건 |
| 4-10 | U9 market_flow·steam·book_disagree | **부분** | `market_flow`·`flow_class` 채워진 행 **42 / 1,393 (3.0%)** · `clv_line_shift` **0건** |
| 4-11 | U10 structure·watch_state | 🔴 **안 됨** | `watch_state` 칸은 있는데 **1,393행 전건 NULL** — 상태기계가 한 번도 안 돌았다 |
| 4-12 | U11 `starter_changed` | **됨** | `n10_rejudge.py` 등 7파일 |
| 4-13 | U12 `fable_cases.yaml` | **대기** | 골격만(16줄) · 사례 0건. 파일 머리말이 "사용자가 채운다"고 적는다 |
| 4-14 | U13 CLV 3칸·태그·`source_score` | **부분** | 8칸 있음 · `source_score` 칸 없음. 함수는 `report.py:128` 에 있으나 **대조 자료(claimed/actual)가 원장에 없다** — `tools/report_vars.py:136` 이 그렇게 자백한다. 배선이 아니라 **미구축** |
| 4-15 | U14 v3 전환 | **폐기 후보** | v1.4 가 대체. 사용자 확인 대기 |
| 4-16 | P0-1 코드 승자 | **됨** | `apply_code_verdict` 4파일 |
| 4-17 | D1 북 비교 | **됨** | `book_gap.py` · 최근 24h 북 10종 이상 |
| 4-18 | ESPN 축구 예산 카운터 | **됨** | `api_calls:2026-09-19 = {'espn_soccer': '54'}` · `09-20 = '35'` |
| 4-19 | API-Football 호출 0 | **됨** | `pipeline.py:1543` — 호출이 `mock_football` 안에만 |
| 4-20 | sources.yaml tier0~4 | **됨** | tier4 는 설정 섹션이 아니라 `scout_config.RANK_UNLISTED = 4` 라는 **코드 등급**이다. 미상 도메인은 열거할 수 없다 |
| 4-21 | SCT-4 `undated` | **됨** | `satellite.py`·`scout_config.py` |
| 4-22 | 빅매치 `derbies.yaml` | **됨** | 존재 |
| 4-23 | 로컬 3B 추출 사슬 | **측정 결과: 미설치** | 컨테이너 한도 8.0GB → 3B Q4 는 올릴 수 있다. `/app/models`·`ollama`·`llama-cli` 없음 |
| 4-24 | CRW-6 크롤 주기 10m | **됨** | PID1 인자 `crawler -interval 10m` |
| 4-25 | P2-0 Odds API 차단기 | **폐기** | 유료 API 금지(§0-8)와 충돌 |
| 4-26 | 09-08 A군 11건 | **됨** | `docs/AUDIT_FIX_LOG_2026-09-08.md` |
| 4-27 | 09-08 B군 5건 | 🔴 **안 됨** | CR-1·VR-1·VR-2·BP-1·SAN-2 커밋 0건 |
| 4-28 | 09-14 P0 셋 | **됨(흡수)** | TRG-1·MOV-1·SCT-3·ANL-1·OBS-1 각 커밋 |
| 4-29 | 09-16 린터 부착 | **됨** | pre-commit 파일 대신 `guard-bash.sh:143` 이 커밋마다 `ruff check app tools tests` · 지금 `All checks passed!` |
| 4-30 | 09-16 PA-1~PA-28 | **부분** | 커밋 19/28 · 없는 9건(PA-3·4·5·8·9·10·11·25·26)은 영향지도도 없다 |

**집계: 됨 20 · 부분 3 · 안 됨 2 · 고쳤다 1 · 폐기 2 · 대기 1 · 미측정 1**

---

## 2. 1차 보고에서 틀렸던 것 (전부 계수기 오류)

| # | 1차 | 정정 | 무엇을 잘못 셌나 |
|---|---|---|---|
| 4-1 | 안 됨 (NULL 90.8%) | **됨 (0.0%)** | `snap_tag` 는 행 속성이 아니라 **시점 표지**다. 평시 폴링 행이 NULL 인 것은 설계다. 분모를 전체 행으로 잡았다 |
| 4-2 | 부분 (`ingest_gap` 없음) | **됨** | `ingest_gap` 은 트리거 `kind` 가 아니라 **별도 대조 함수**다. `kind` 목록에서 찾은 것이 잘못 |
| 4-18 | 안 됨 (카운터 0개) | **됨** | 키가 `budget:*` 가 아니라 **`api_calls:{날짜}` 해시의 `espn_soccer` 필드**다. 틀린 키를 스캔했다 |
| 4-20 | 부분 (tier4 없음) | **됨** | tier4 는 설정 섹션이 아니라 코드 등급 `RANK_UNLISTED = 4` 다 |
| 4-29 | 부분 (pre-commit 없음) | **됨** | 이 저장소는 `.claude/hooks/guard-bash.sh` 가 그 역할을 한다. 파일 이름만 찾았다 |

> §0-13: **"세기 전에 그 계수기가 무엇을 세는지 확인."** 다섯 번 다 그 한 줄을
> 건너뛰어서 났다. "파일이 없다 / 키가 없다"는 **없다는 증거가 아니라 내가 찾은
> 자리에 없다는 뜻**이다.

---

## 3. 이번에 고친 것 — CNF-2

⑥의 반증이 **구조적으로 불가능**했다(실측 최근 2h `{'unknown': 496,
'confirmed': 137}`). ⑤가 값 있는 것만 행으로 만들어 ⑥에 빈 값이 들어올 수
없었고, `len(v)==0 → REFUTED` 가지는 죽은 코드였다.

그냥 켜면 `lineup_out` 이 핵심 변수라 **결장 0명인 건강한 라인업이 전부
철회**된다. 갈림길이라 자료를 찾았다 → [FORKS F-20](FORKS.md).

> absence of evidence is evidence of absence **to the degree that evidence
> would have been expected had the claim been true** — 관건은 탐지 가능성이다.

→ 반증의 뜻은 **가설의 주장**에 달린다: `H_fade` 철회 · `H_break` 강화 ·
`H_deriv` 중립. 표의 원본은 `app/flow/labels.REFUTED_MEANS` 하나다.

- 커밋 `2c6a087` · 배포 SUCCESS **09:48:54 KST** · pytest **5181 passed · 4 skipped**
- ⑨ 첫 사이클 실측 — **반대 위험 0**: 철회가 늘지 않았다
  (`{"games": 31, "stopped": {"n03_freeze": 21, "n06_unknown": 9, "n11_no_value": 1}, "sent": 0}`)
  · 뜻 라벨이 게이트별로 붙는다(`중립`·`강화`·`철회`)

---

## 4. 진짜로 남은 것

| # | 무엇 | 왜 이번에 안 했나 |
|---|---|---|
| **4-11** | `watch_state` 상태기계가 한 번도 안 돌았다(전건 NULL) | **배선 대상.** 다음 수정 단위 후보 |
| **4-10** | `market_flow` 채움률 3.0% · `clv_line_shift` 0건 | 구경로에서만 돌고 v1.4 흐름이 안 쓴다 |
| **4-14** | `source_score` | 배선이 아니라 **미구축** — 대조 자료를 남기는 자리가 없다. 새 칸·새 수집 경로가 필요하다 |
| 4-27 | 09-08 B군 5건 | 동결 예외가 필요했던 별건 묶음 |
| 4-30 | PA 9건 | 미착수 별건 묶음 |
| 4-13 | 사례집 24건 | **사용자가 채우는 값** |
| 4-15 | U14 폐기 여부 | **사용자 결정** |
| 4-8-c | `scout_config.validate:427` 이 안 본 칸까지 `[]`/`""` 로 채운다 | 상자 경로를 ⑥이 아직 안 써서 범위 밖 |
