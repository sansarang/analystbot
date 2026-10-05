# 🔴🔴 인계 — 다음 세션이 **먼저 읽을 것** (2026-10-06 새벽)

## 한 줄

인계 ①(결함 둘)을 **끝냈다.** 남은 것은 ②(검수표 실측)·③(§8 합격표 3경기)이고,
둘 다 **예산과 시계**에 걸려 있다.

## 끝낸 것 — 커밋 다섯

| 커밋 | 무엇 |
|---|---|
| `b73c8eb` | **①-1** fotmob `roundName` → `match_format` 사슬 5칸 + §3-3 자동 보강 |
| `4d01131` | **①-2** `starts_kst` 는 순간이다 — 질의 7자리·수집기 7곳·계약 4 |
| `6518820` | 원장만으로 §8 수치 측정(비용 ✓ · 벽시계 ✗ · 비용 28% 미귀속) |
| `7477f04` | `tools/run_stage8.py` — 실제 핸들러 실행기(`--at HH:MM` 대기) |

**스위트 2021 통과 · 0 실패 · ruff 통과.** pyright 255(기준 커밋 실측 **252** —
`questions/2026-10-05_pyright_errors.md` 의 "246" 은 낡았다).

### ①-1 — `roundName` 을 안 읽었다

라이브로 받아 확인했다: fotmob `6232991` → `"roundName":"final"` ·
`FIFA ASEAN Cup Premier Division`. 그런데 수집기가 그 칸에 `None` 을 박아 두고
*"못 읽는다"* 고 적어 뒀다. 이은 사슬:

```
fotmob.round_note(j)   content.matchFacts.infoBox.Tournament.roundName
→ games.round_note     (ingest 가 이미 COALESCE 로 받는다)
→ MatchRef.round_note  입구가 행을 ref 로 바꾸는 그 한 곳
→ classify.Game.round_note (scheduler 두 자리도)
→ standings.match_format   analyze.build 가 구조 사실로 올린다
→ require_draw             §3-3 90분 무승부
```

번호→형식은 **표**가 한다 — `config/scenario_rules.yaml` `match_format`
(순서가 규칙 · `semi-final` 이 `final` 로 안 새게 `not`). 못 맞추면 `unknown`.

🔴 고치면서 `require_draw` 가 **막기만** 하는 것을 발견해 §3-3 의
`on_missing: 추가` 로 바꿨다 — 안 바꾸면 이 수정이 **단판 결승마다 카드를
막는다**(`from_deepseek` 가 `added_by="template"` 인 C 초안을 버린다).
조건부 필수형 `90분_무승부형`(`when_formats: draw_90`)을
`config/scenario_required.yaml` 에 넣고, 형식이 맞을 때만 DeepSeek
`required_types` 에 내려가게 했다.

⚠️ **DB 까지는 아직 못 봤다** — fotmob 행의 `round_note` 는 **분석 중에** 경기
   페이지를 열 때 채워진다(슬레이트 수집은 그 페이지를 다시 안 연다. 실측:
   `games.id=116` 의 `updated_at` 이 수집 뒤에도 그대로였다). 단위·배선·라이브
   페이지로는 확인했다.

### ①-2 — `starts_kst` 는 **순간**이다(이름이 거짓)

```
라이브 52행 중 starts_kst = starts_utc   → 52/52 (전부)
그중 UTC 날짜 ≠ KST 날짜                  → 16/52
sources.DbSources.slate(2026-10-06)      종전 0건 → 고친 뒤 1건 (France–Belgium)
/health 의 "오늘 경기수"                  종전 3   → 고친 뒤 4
```

변환이 사는 곳을 셋, 각각 하나로: `timefmt.db_instant`(넣는 값·UTC) ·
`kst_label`(표시) · `sql_kst_day`/`SQL_TODAY_KST`(질의). 계약 넷이 **AST 로**
문자열 상수를 본다. 돌연변이 4종 전부 빨강 확인(M111~M113 + 스키마 naive 칸).

🔴 **계약 둘이 거짓을 못 박고 있었다** — `starts_kst.hour == 14`,
   `utcoffset() == +9`. DB 에 닿는 순간 사라지는 값이라 초록인데 아무것도
   지키지 않았다. 참인 것(같은 순간 + 표시 변환)으로 고쳐 썼다.

🔴 **남은 결정** — 절대규칙 2 의 *"현지 시각도 저장한다"* 는 이 스키마로 못
   지킨다 → `questions/2026-10-05_starts_kst_is_an_instant.md` (보기 A~D).
   고르기 전까지 코드는 **A**(그냥 두고 계약으로 막기)로 돈다.

## 🔴 다음에 할 것

### ⓪ 먼저 **시계를 확인하라** — 이 세션에서 어긋났다

| 출처 | 값 |
|---|---|
| 기계 `date` | 2026-10-06 **00:20 KST** |
| 구글 응답 헤더 `Date` | `Mon, 05 Oct 2026 15:20:34 GMT` = **00:20 KST** (일치) |
| 🔴 **사용자 진술** | *"한국시간 **3:45** 새벽이다"* |

🔴 **3시간 25분 차이**다. 사용자 쪽이 맞으면 France–Belgium(03:45 KST 킥오프)은
**이미 시작했고**, 아래 대기 중인 실행은 ②에 쓸 수 없다(M97 *"예측 아님"* 표기
확인용으로만 쓴다). ⚠️ 봇의 시간축 전부가 기계 시계를 쓴다(`today_kst`·36시간
창·`rerun.due`) — 기계가 틀렸다면 그것이 더 큰 문제다. **사용자에게 물어라.**

### ① 대기 중이던 실행 — 세션이 끊기면 죽는다

```
PYTHONPATH=. nohup .venv/bin/python tools/run_stage8.py "France vs Belgium" \
    --at 02:35 > /tmp/stage8_fra_bel.log 2>&1 &
```

pid 30229 로 02:35 KST(= T-70분)를 기다리고 있었다. 세션 재시작 뒤
`pgrep -fl run_stage8` 로 살아 있는지 보고, 죽었으면 **킥오프 전인지 먼저
확인한 뒤** 다시 띄운다. 끝나면 `/tmp/stage8_fra_bel.log` 에 §8 수치가 찍힌다.

### ② 검수표 — 창 안에 **단판 경기가 없다**

| 항목 | 기대 | 지금 |
|---|---|---|
| XI 변수 | 5백 `goals_down`·벤치 `absence`·복귀 | T-70분 실행으로 잴 것 |
| 평균 보정 | "9-2 제외 시" 표기 + 회귀 시나리오 | 같은 실행 |
| 형식 | `final_single` → 90분 무승부 | 🔴 **창 안에 단판·결승이 없다 — 이번엔 실측 불가** |
| 대입 | `1-0` 들어가면 오버 1.5 `△` | 같은 실행 |
| 검증 변수 | 8개 이상 | 같은 실행 |

### ③ §8 합격표 3경기 — **사용자 결정 받았다**(2026-10-06)

1. **축구 1** = France–Belgium, **T-70분**에 돌린다(위 ①).
2. **KBO 1** = Kia Tigers vs Samsung Lions · 18:30 KST (예산 리셋 뒤).
3. **사용자 선택 1** → 🔴 **미등록 리그 경기로 대체**(§8 의 명시된 대체안 ·
   오픈월드 ⑥단 검증 겸). ⚠️ 창 안에 실제로 있는 것에서 고른다 — 지어내지
   않는다. fotmob 날짜 페이지는 일정을 `/api/*`(robots 금지)로만 줘서 공짜로
   못 뽑았다. 09:00 KST 뒤 `scheduler.run_once` 로 10-07 을 쌓고 거기서 고른다.
   ⚠️ France–Belgium 의 리그(`UEFA Nations League A Grp. 1`)도 **미등록**이다 —
   3번은 그와 **다른** 경기여야 한다.

### 🔴 예산이 벽이다

```
오늘(UTC 10-05) 쓴 돈 $4.2647 / 상한 $5.00  → 남은 $0.7353
리셋은 UTC 자정 = 09:00 KST   (사용자 결정 2026-10-06: 하루는 UTC 그대로 둔다)
실행당 실측 비용 $0.14 ~ $0.39  → 한 경기는 들어가고 세 경기는 안 들어간다
```

## §8 수치 — 원장으로 이미 쟀다(돈 0)

`fotmob:6232991`(it7)을 5분 공백으로 실행 단위로 가르니 **같은 경기를 6번**
돌렸다. 실행당:

| | 값 | §8 상한 | |
|---|---|---|---|
| 비용 | 최대 **$0.3878** | ≤ $0.5 | ✓ |
| 벽시계 | **6.6 ~ 11.7분** | ≤ 6분 | 🔴 ✗ |

⚠️ 합계 $1.2573 은 *여섯 번 돌린 값*이다 — 경기당이 아니다.
⚠️ 인계(10-05)의 *"스위트 24초(전 11분)"* 는 **시험 스위트**이고 경기 실행이
   아니다. 두 수를 섞어 *"빨라졌다"* 로 읽으면 안 된다.
🔴 **원인은 아직 추측이다** — Solar 줄 464개가 전부 `stage: None` 이라 어디서
   시간을 쓰는지 원장이 말하지 못한다.

## 새로 적은 questions 셋 (🔴 §9 가 서치 층 밖 코드 변경을 금지해 **안 고쳤다**)

| 파일 | 무엇 |
|---|---|
| `2026-10-05_starts_kst_is_an_instant.md` | 칸을 없앨까·바꿀까(보기 A~D) |
| `2026-10-06_cost_ledger_has_no_match.md` | 🔴 비용 **28%($1.1910)** 가 어느 경기 것인지 모른다 · Solar 줄에 `stage` 없음 · 하루 경계가 UTC |
| `2026-10-06_stage8_wallclock_over.md` | §8 벽시계 ✗ 의 실측 표 |

## ⚠️ 이 세션에서 다친 자리

1. 🔴 **`git checkout` 이 미커밋 작업을 지웠다**(`slate.py`·`sources.py`·
   `espn.py`). 돌연변이 복원에 `git checkout` 을 쓴 것이 원인이다 — CLAUDE.md
   #9(실행 전 WIP 커밋)를 내가 어겼다. 🔴 **돌연변이는 WIP 커밋 뒤에** 돌린다.
2. ⚠️ `test_resolve.py::test_색인이_현지_표기를_짝지어_둔다` 가 **한 번** 빨개졌다가
   재실행에 통과했다(`LI.cached_index()` 를 보는 병렬 경합으로 보인다).
   원인 못 짚었다 — 내 변경과는 무관하다.
3. ⚠️ 새 계약을 쓰면서 **내 주석이 계약에 걸렸다**(D46) — 스키마 주석의
   `TIMESTAMP` 글자. 계약이 SQL 주석을 걷게 고쳤고, 걷은 뒤 선언이 남아 있는지도
   함께 센다(퇴로 막기).
