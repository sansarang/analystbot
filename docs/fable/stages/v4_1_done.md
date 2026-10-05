# v4 단계 1 — 폐기 코드 제거 · **완료, 승인 대기**

## 1. 완료 조건 원문 (v4 §9 단계 1)

> **§8 폐기 목록의 코드·테스트 삭제. 동기 등급·확신·등급·min_win_prob·p_claude
> 참조 0건**

게이트: *"금칙 식별자 grep 0건, 스위트 초록"*

## 2. 삭제한 것 — v4 §8 폐기 목록 대조

| §8 폐기 항목 | 지운 것 |
|---|---|
| 동기 4등급 | `judge`: `TIERS`·`_TIER_RANK`·`motivation_tier`·`tier_gap`·`Motivation` · `sources.motivation()` · `standings→등급` 배선 |
| lean | `judge.build_lean`·`_provisional_confidence`·`Hypothesis`·`Basis` |
| 확신 상/중/낮 | `CONF_HIGH/MID/LOW`·`_CONF_RANK`·`_CONF_KR`·`conf_kr`·`_at_least`·`VerdictOut.confidence` |
| 간다/조건부/접는다 | `GO`·`CONDITIONAL`·`PASS_`·`_GRADE_KR`·`grade_kr`·`GradeOut`·`judge.grade()` |
| 방아쇠 등급 상향/하향 | `Trigger`·`TRIGGER_TYPES`·`_TRIGGER_FOR`·`triggers_from`·`regrade`·`run.evaluate_triggers`·`sources.lineup_confirmed` |
| 세 축 판정 규칙 | `build_lean` 의 가중 합산(`W_MOTIVATION`·`W_ABSENCE`·`W_STARTER`·`W_INTENT`·`W_HOME`) |
| 반증 추적의 확신 갱신(5-d) | `apply_counters`·`Counter`·`sources.close_counter` |
| v3 §9 방아쇠 유형표 | 위 방아쇠 일체 |
| v3 §15 정답지 승자·확신·등급 열 | `score_tags`·`TAGS`·`sources.score_finals` |
| min_win_prob·p_claude | **이미 0건이었다**(v3 단계 0 에서 걷혔다) — 실측으로 확인 |

**함께 간 것**: `run.run_game`·`run.run_slate`(→ `collect_game`·`collect_slate`) ·
`card.render_game`(→ `render_collected`) · `tg.send_card`·`MAX_SEQ` ·
스케줄러의 채점 주기 · 스키마 표 **8개**(`motivation`·`hypotheses`·`counters`·
`verdicts`·`grades`·`triggers`·`cards`·`ledger`).

**이관 대기**(§8 이관, 단계 5): `judge.OPPOSITE_SEED` — 종전 `COUNTER_RULES`.
🔴 **읽는 코드가 0곳**이고 계약이 그것을 잠근다(`OPPOSITE_SEED` 등장 1회).

## 3. 게이트 실측

```
금칙 식별자 25종 × app/** 코드(독스트링·주석 제외) → 남은 것 0개 ✅
  motivation_tier tier_gap TIER_TOP TIER_HIGH TIER_MID TIER_NONE
  build_lean _provisional_confidence CONF_HIGH CONF_MID CONF_LOW conf_kr
  CONDITIONAL grade_kr GradeOut VerdictOut triggers_from regrade
  TRIGGER_TYPES evaluate_triggers apply_counters min_win_prob p_claude
  p_final score_tags

한글 판정 어휘(확신·동기 등급·승자·간다·조건부·접는다) 코드 기준 각 1곳 —
  전부 `card.BANNED`(금지 목록 자체)다. 그것이 있어야 출력을 막는다.

`lean` 낱말 경계 1곳 — `blackboard._used_in()` 의 반환값 `"lean"`.
  🔴 v3 §12-e 증거 카드의 `used_in` 필드 값이고 v3 §12 는 **유지**다.
     값이 폐기된 개념을 가리키는 것 → 갈림길이라 **고르지 않았다**.
     → `docs/fable/questions/2026-09-29_evidence_used_in.md`
```

```
PYTHONPATH=. uv run pytest tests -q   → 263 passed in 3.78s
PYTHONPATH=. uv run ruff check app/ tests/ → All checks passed
db/schema.sql 적용 → 성공 · 표 11개
  absences evidence extraction_rejected games intent player_alias players
  runs standings starters team_form
```

## 4. 새 계약 목록과 절제 결과

`tests/test_judge.py` 를 v4 기준으로 다시 썼다(종전 계약 27건 중 폐기 대상 20건
삭제). 새로 넣은 것:

| 계약 | 절제(되돌리면 빨개지나) |
|---|---|
| `test_폐기된_식별자가_app에_0건이다` × **25** | ✅ 실측: 삭제 전 상태에서 `motivation_tier` 10곳·`TIER_*` 41곳·`CONF_*` 32곳이 잡혔다 |
| `test_폐기된_한글_어휘가_출력_경로에_0건이다` | ✅ `card` 에 "확신" 한 줄을 되살리면 빨개진다(금지 목록 블록은 제외한다) |
| `test_판정_함수가_사라졌다` | ✅ 이름이 아니라 `hasattr` 로 **존재**를 본다 — 다른 이름으로 되살리는 것도 막는다 |
| `test_스키마에서_판정_표가_사라졌다` | ✅ 표를 되살리면 빨개진다 |
| `test_스키마에_v4가_세울_표를_미리_만들지_않았다` | ✅ **반대 방향 계약** — 실측 2026-09-30: `db/schema.sql` 에 `CREATE TABLE IF NOT EXISTS variables` 를 넣으니 빨개졌다(`variables 표가 단계 2 보다 먼저 생겼다`) → 원복 → 초록 |
| `test_이관_대기_표가_남아_있고_아직_안_읽힌다` | ✅ `OPPOSITE_SEED` 를 단계 5 전에 읽으면 빨개진다 |
| `test_결론_줄을_만들지_않는다` | ✅ 실측 2026-09-30: `card.render_collected` 에 `"낸다"` 를 넣으니 빨개졌다 → 원복 → 초록. ⚠️ **처음 판은 거짓 통과였다**(리뷰 A6) — `R.Sources()` 가 슬레이트를 `[]` 로 돌려줘 경기 0건으로 돌았고 경기별 렌더러를 한 번도 타지 않았다. 경기 1건을 주는 `_Src` 로 고친 뒤에야 이 절제가 성립한다 |
| `test_수집_나열을_발송하지_않는다` | ✅ `run_once` 에 `tg.send` 가 들어오면 빨개진다(§11-11 발송 off) |
| `test_스케줄러가_수집만_돈다` · `test_흐름이_수집_소스를_부른다` | ✅ |

**지운 계약**: `test_judge.py` 20건 · `test_collect.py` 2건(동기 등급 배선) ·
`test_wiring.py` 9건(폐기된 배선). 🔴 **그 계약들이 검사하던 코드가 폐기됐다** —
계약만 남기면 없는 것을 검사한다.

## 5. 실측 로그 원문

`logs/v4_step1_실측.log` — 실물 API·실물 DB, 2026-09-29:

```
수집   MLB 4경기·순위 30팀 / NPB 4경기·라이브 4 / KBO "어댑터 없음"(사유 남김)
출력   종료(1-3)·순연·수집 나열 — 판정·등급·결론 줄 **0건**
DB     games 8 · standings 30 · starters 16 · players 8 · alias 8 ·
       evidence 36 · runs 6
금지 어구  0건 ✅
```

## 6. 범위 밖에서 발견한 것 — 안 고쳤다 (§13-1)

- 🔴 `evidence.used_in` 의 값이 폐기된 개념을 가리킨다 →
  `questions/2026-09-29_evidence_used_in.md` (**페이블에게 물을 것** — 규칙 해석)
- 🔴 `stage_gate.yaml` 이 없다(단계 0 에서 적었다) →
  `questions/2026-09-29_stage_gate_missing.md`

## 7. 쓴 도구 · 안 쓴 것

**쓴 것**: Bash(전수 grep·절제 측정·실물 실측) · Write/Edit · docker/psql(스키마
적용 확인) · `claude_ai_Claude_Docs`(§0~§3·§8 원문 확인).
**쓸 수 있었는데 안 쓴 것**:
- `contract-reviewer` — **이 저장소에서 삭제됐다.** 에이전트 목록에 없다.
  ⚠️ v4 §11-4·§11-5 가 리뷰어 PASS 를 요구한다. 그 항목을 **채울 수 없다** —
  단계 2 착수 전에 사용자 결정이 필요하다(아래 §9).
- Serena — 삭제 작업이라 심볼 탐색보다 전수 grep 이 정확했다(게이트가 grep 0건이다).
- WebSearch/WebFetch — 이 단계는 코드 삭제다. 웹 자료가 필요하지 않았다.

## 8. 하위 CLAUDE.md 전수

0개. 루트 `CLAUDE.md` 1개(122줄, 단계 0 에서 새로 씀).

## 9. 🔴 보고서 필수 항목 중 **채울 수 없는 것 하나**

v4 §11-5 는 완료 보고서에 **"리뷰어 PASS 원문"**을 요구한다. 🔴 `contract-reviewer`
에이전트가 이 저장소에서 삭제됐다(2026-09-27 전면 삭제). 그 항목을 비워 두는 것은
§11-5("하나라도 빠지면 미완료")에 걸린다.

**물을 것**: 리뷰어를 다시 만들까요, 아니면 그 항목을 면제할까요?
→ `docs/fable/questions/2026-09-29_reviewer_missing.md`

## 10. 승인 서명 (v4 §13-2)

> 🔴 이 칸은 2026-09-30 에 갱신됐다 — **이 파일 맨 아래 「승인 서명 … 갱신」**을
> 보라. 🔴 코드 커밋 `d0c6000` 은 이 칸이 `(대기)` 인 채로 나갔다(§11-10 위반,
> 사고 기록도 아래에 있다).

---

## 🔴 추가 (2026-09-29) — 리뷰어 PASS 원문을 **채울 수 없다**

`contract-reviewer` 를 읽기 전용으로 다시 만들었으나(사용자 지시 #5), **이 세션에서
띄울 수 없다** — 에이전트 목록이 세션 시작 때 고정된다. 두 번 시도해 같은 결과였다:

```
Agent type 'contract-reviewer' not found.
Available agents: claude, claude-code-guide, Explore, general-purpose, Plan,
                  statusline-setup
```

⚠️ `Explore`·`general-purpose` 로 대신하지 **않았다** — 둘 다 `Bash` 를 갖고,
   사용자 지시가 "Bash·Edit·Write 없음"이다. 도구를 회수해 **불가능하게** 만드는
   것이 D69 대응의 요지이므로 도구가 더 많은 에이전트로 대신하면 그 결정을 무른다.

→ `docs/fable/questions/2026-09-29_reviewer_session_reload.md` (갈래 4개)
🔴 그래서 단계 1 은 §11-5 기준 **이 항목이 빈 상태**다.

---

# 🔴 추가 (2026-09-30) — 리뷰어가 돌았고, **FAIL 이었다**

## 리뷰어 PASS 칸 — 채워지지 **않았다**

세션을 다시 시작하니 `contract-reviewer` 가 에이전트 목록에 보였다(추정이 맞았다 —
목록은 세션 시작 때 고정된다). 단계 0·1 소급 리뷰를 돌렸고 결과는 **FAIL**
(차단 8건·비차단 11건). 전문과 갈림길:
`docs/fable/questions/2026-09-30_stage1_review_fail.md`

🔴 **그러므로 §11-5 의 "리뷰어 PASS 원문" 칸은 여전히 비어 있다.** 이 보고서는
"PASS 를 받은 단계"가 아니라 **"FAIL 을 받고 일부를 고친 뒤 사용자가 승인한
단계"**다. 그 사실을 지우지 않는다.

## 🔴 사고 기록 — 승인 서명 없이 커밋했다 (§11-10 위반)

v4 §11-10 은 *"승인 서명 없는 커밋은 하지 않는다"* 이다. 단계 1 코드 커밋
`d0c6000` 은 이 파일의 서명 칸이 `> (대기)` 인 채로 나갔다. **리뷰어가 A1 로
잡아냈다**(2026-09-30).

- 원인: **커밋 게이트 훅이 없다.** 2026-09-27 전면 삭제 때 함께 갔다.
  기계가 막지 않으므로 사람·세션의 규율에만 의존한다.
- 같은 병의 다른 발현: 2026-09-28·29 에 **빨간 채로 커밋한 일이 두 번** 있었다.
- 사용자 결정 2026-09-30: *"승인 + 사고 기록으로 남긴다."* 소급 해소로 처리하지
  않고 **기록을 남긴 채** 단계 2 로 간다.

## 리뷰 FAIL 중 이 세션이 **고친 것** (전부 절제로 확인)

| 리뷰 | 무엇이 문제였나 | 절제 (주입 → 빨강 → 원복 → 초록) |
|---|---|---|
| A4 | `tests/test_wiring.py` 의 `NOT_WIRED` 가 **삭제된** `app.judge.score_tags` 를 들고 있었다. 표 목록 쪽은 **스키마에 없는** `ledger` 를 들고 있었다. 두 계약 다 "이어졌나"만 보고 **"아직 있나"는 안 봤다** — 목록이 거짓이 돼도 초록이었다 | ✅ 없는 이름을 넣으니 `없는 함수가 NOT_WIRED 에 남았다: ['app.judge.score_tags']` · `스키마에 없는 표가 NOT_WIRED 에 남았다: ['ledger']` |
| A6 | `test_결론_줄을_만들지_않는다` 가 **경기 0건**으로 돌았다. `R.Sources().slate()` 가 `[]` 라 경기별 렌더러(`card.render_collected`)를 한 번도 타지 않아, 잠그는 것이 나열 꼬리말 한 줄뿐이었다 | ✅ 경기 1건을 주는 `_Src` 로 고친 뒤 `render_collected` 에 `"낸다"` 주입 → 빨강 |
| A7 | 절제 결과가 빈 계약 2건 | ✅ 둘 다 실행해 위 §4 표에 실측으로 기입 |
| A3·A5 | 봇 배선 계약이 지워지고 대체가 없었다. 단계 1 이 `app/bot/main.py` 의 호출부를 `run_slate`→`collect_slate` 로 **직접 고쳐 놓고** 그것을 잠그던 계약을 같은 커밋에서 지웠다 | ✅ 되살렸다. ⚠️ **첫 판은 거짓 통과였다** — `"collect_slate" in src` 는 `import` 줄 때문에 호출을 지워도 참이었다(절제가 통과해 버렸다). **AST 로 부르는 자리**를 보도록 고친 뒤에야 빨개진다 |

## 리뷰 2차 PASS 뒤 — **비차단 M1 을 고쳤다** (사용자 지시 2026-09-30)

2차 리뷰는 PASS 였으나 비차단 M1 이 **내가 A6 를 고치며 넣은 줄**을 짚었다.

```python
assert "두산" in body          # ← 이것으로는 전체 경로를 잠그지 못한다
```

`"두산"` 은 머리글에 들어가고, 머리글은 순연·진행중·종료 **조기 반환에서도**
나온다(`app/card.py:43-47`). 그래서 이 계약이 전체 경로를 타는 진짜 근거는
`GameCtx.status` 기본값이 `"scheduled"` 라는 **테스트가 주장하지 않은 사실**
(`app/run.py:58`)이었다 — 그 기본값이 바뀌는 날 계약은 **말없이 다시 빈 채로
초록**이 된다. 🔴 **A6 를 낳은 것과 같은 모양이다.**

`"못 잰 칸"` 은 전체 경로에서만 나온다(`app/card.py:68-69`). 그것으로 바꿨다.

**실측 2026-09-30 — 네 칸을 다 재서 M1 을 확인했다:**

| | `status` 기본값 | 계약 | 결과 |
|---|---|---|---|
| ① | `scheduled` | `"두산"` | 초록 |
| ② | `postponed` | `"두산"` | 🔴 **초록** — 전체 경로를 **안 타는데도** 통과 |
| ③ | `postponed` | `"못 잰 칸"` | 빨강 (제대로 잡는다) |
| ④ | `scheduled` | `"못 잰 칸"` | 초록 |

**절제 2방향 — 둘 다 빨강 → 원복 → 초록:**
- A. `status` 기본값을 `postponed` 로 → `전체 경로를 안 탔다 — 조기 반환에서 끝났다`
- B. `card.render_collected` 에 `"낸다"` 주입 → `assert '낸다' not in body`

⚠️ **이 실험을 처음 돌렸을 때 바이트코드 캐시가 옛 값을 들고 있어 한 칸을
   잘못 읽었다.** `app/**/__pycache__` 를 지우고 다시 재서야 위 표가 나왔다.
   이 저장소에서 `status` 같은 **기본값을 바꿔 가며 재는 절제**는 캐시를 매번
   지워야 한다 — 안 그러면 절제 결과 자체를 오독한다.

## 🔴 미결 — 단계 1 이 **닫히지 않은 채** 넘어가는 항목

§13-3 대로 "나중에"로 미룬 것을 이름으로 남긴다.

| # | 무엇 | 왜 미뤘나 |
|---|---|---|
| 1 | `app/blackboard.py:186` `return "lean"` — §8 폐기 개념이 **코드**에 살아 있다(독스트링 아님) | 리뷰 A2. ✅ **답 왔다**(사용자 2026-09-30): **단계 2 본체에서 #6 으로 닫는다** — 마이그레이션이 스키마 작업이라 9표 작업과 함께 간다 |
| 2 | 지워진 유지-조항 계약 **4건**: `test_호출_예산이_20이다`(`BUDGET_PER_GAME`) · `test_검색어_규칙이_연산자와_연도를_막는다`(`query_ok`) · `test_L1이_원문_문장을_요구한다`(`evidence_sentence`) · `test_거절된_추출을_보관하는_표가_있다`(`extraction_rejected`) | 리뷰 A3. 대상 코드는 **전부 살아 있다**(`app/llm.py:30,46,49·218·134,136` · `db/schema.sql:111,121`). 사용자 결정 2026-09-30: *"봇 배선만 지금, 나머지 4건은 단계 2."* LLM·스키마 영역이라 단계 2 타입·스키마 작업과 함께 세운다 |
| 3 | 음성 계약 `test_게이트_라벨이_없다` | 리뷰 A3·Q4. ✅ **답 왔다**(사용자 2026-09-30): **되살린다 — 단계 2 에서.** v4 §6-d 가 그 감시를 요구하므로 이월된 계약 4건과 함께 열린다 |
| 4 | 보고서 수치가 "수집 N건(함수 M개)" 두 수로 안 적혔다 | 비차단 N7. #15 가 아직 남은 항목이다 |

## 실측 (2026-09-30, 위 수정 후)

```
PYTHONPATH=. uv run pytest tests -q        275 passed in 3.59s
                                           (수집 275 건 · 고유 테스트 함수 242 개)
PYTHONPATH=. uv run ruff check app/ tests/ All checks passed!
```
⚠️ 이 보고서 §5 의 `263 passed` 는 **커밋 `d0c6000` 시점**의 수다. 승인은 **지금
   트리(275)**에 대해 이뤄졌다. 두 수가 다른 것은 그 뒤의 커밋 4개와 이 세션의
   수정 때문이다.

⚠️ **ruff 초록은 죽은 import 의 증거가 아니다**(비차단 N2). 이 저장소의 ruff 설정은
   F401 을 잡지 않는다 — `app/scheduler.py:16` 의 `from app import tg` 가 죽은
   import 인데 초록이다. 단계 2 에서 본다.

## 10. 승인 서명 (v4 §13-2) — **갱신**

> APPROVED 2026-09-30 "승인 + 사고 기록으로 남긴다" — 사용자
>
> 🔴 리뷰어 PASS 가 **아니라** 사용자 승인이다. 리뷰는 FAIL 이었고, 위 「미결」
>    4항목을 연 채로 단계 2 에 들어간다.

---

# 추가 (2026-09-30) — 리뷰 비차단 **M3·M4** 정리 (사용자 지시)

## M3 — `CLAUDE.md` 의 rev 포인터가 낡았다

정본이 rev 15 로 올라갔는데 `CLAUDE.md:3` 은 `(**rev 14**)` 였다. §13-6 대조는
inbox 2행으로 하므로 단계 잠금이 풀리진 않았지만, 다음 세션이 **포인터의 rev 를
믿을** 위험이 있었다. `CLAUDE.md` 자신이 §사본 금지에서 경고하는 형태다.

🔴 **수를 고치는 것만으로는 또 낡는다.** 그래서 계약을 **원본에서 자라게** 짰다 —
`test_CLAUDE_md_의_rev_가_정본과_같다` 가 inbox 2행의 `<!-- rev: N -->` 을 읽어
대조한다. 정본이 올라가면 빨개져 "따라가라"고 말한다.

⚠️ 첫 판은 `CLAUDE.md` 전체에서 `rev N` 을 긁어 **거짓으로 빨개졌다** — 이 파일은
v3 얘기로 `rev 24`·`rev 29` 도 적는다(실사고 기록·archive 포인터). **정본을
가리키는 줄만** 보도록 좁혔다. D46 과 같은 병이다: *설명하는* 수와 *가리키는*
수는 다르다.

**절제 3방향** — 정본 rev↑ → 빨강 / 포인터 낡음(=M3 그 자체) → 빨강 /
v3 의 rev 29 가 거짓 빨강을 만드나 → **초록**(안 만든다).

## M4 — 고아 검사가 **손으로 유지되는 14개 목록**만 봤다

`app/search.py`·`config.py`·`db.py`·`main.py`·`version.py`·`secrets_mask.py`·
`scheduler.py`·`bot/**`·`collect/__init__.py` — **13개 모듈**이 고아 검사도
ghost 검사도 **받지 않았다**. 목록을 `(ROOT/"app").rglob("*.py")` + `importlib`
로 **자라게** 바꿨다.

🔴 **드러난 것 — 진짜 안 이어진 함수 6개** (전부 **단계 1 이전부터** 그랬다.
실측: `206ba5f` 시점에도 참조 0곳 — 단계 1 이 끊은 것이 아니다):

| 함수 | 비고 |
|---|---|
| `app.bot.aliases.find_team` · `kr_team` | 단계 5 — 별칭 표를 `data/team_aliases.yaml` 로 뺄 때(§8 추가 판정) |
| `app.secrets_mask.install_log_filter` | [infra] 🔴 **붙기 전까지 로그에 키가 샐 수 있다** |
| `app.secrets_mask.mask_field` | [infra] 카드·보고에 값을 찍는 자리가 생길 때 |
| `app.version.boot_line` · `uptime_text` | [infra] 기동 로그 · `/health` 가동 시간 |

이름과 이어질 단계를 `NOT_WIRED` 에 적었다(CLAUDE.md §배선 — 조용히 두지 않는다).

⚠️ **거짓 고아 3건을 먼저 걸렀다.** `cmd_slate`·`cmd_health`·`main.health` 는
`@dp.message(...)`·`@app.get(...)` 로 등록된다 — 이름이 어디서도 *참조*되지 않아
Name·Attribute 세기로는 고아로 보인다. **데코레이터가 곧 호출부다**. 그것을
세도록 고쳤다. 이 구분을 안 했으면 **이어져 있는 핸들러 3개를 "안 이어졌다"고
`NOT_WIRED` 에 적을 뻔했다** — 목록을 거짓으로 만드는 짓이다.

**절제 2방향** — `app/search.py`(종전 검사 밖)에 고아 추가 → 빨강 /
`cmd_slate` 의 데코레이터 제거 → 빨강. `ghosts` 계약도 새 `mods` 에서 여전히 문다.

## 실측

```
276 passed in 3.28s   (수집 276건)   ← 275 에서 +1 (rev 대조 계약)
ruff check app/ tests/  All checks passed
app/ · db/ 변경 0줄 — tests/ 1개 · CLAUDE.md · 이 보고서
```
