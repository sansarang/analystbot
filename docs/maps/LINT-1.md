# LINT-1 — 린터. 스위트가 못 잡는 종류를 막는다

## 왜

```
재현 3건:
  ruff 가 없다 — 린터가 아예 없다 (pyproject 에 ruff·flake8·mypy 설정 0건)
  커밋 게이트에 린트 단계가 없다
  중복 정의(F811)를 잡는 검사가 없다
```

🔴 **스위트가 못 잡는 종류가 있다는 것을 실물로 쟀다.** 2026-09-15, 같은
파일에 이미 있던 `record_analysis`(원장 저장 본체)를 뒤에 다시 정의했다.
뒤 정의가 앞을 덮으면 **원장이 통째로 멈춘다.** 증명(2026-09-16 실측):

```
app/engine/rules.py 에 중복 정의를 넣고 전체 스위트 실행
  → 4395 passed, 4 skipped     ← 스위트는 못 잡는다
  → ruff check                  → F811 Redefinition of unused `from_file`
```

덮인 함수를 부르는 테스트가 그 경로까지 안 가면 스위트는 영원히 조용하다.

착수 시점 위반 실측 (`ruff check --select F app tools crawler tests`):
```
97 F401 unused-import      18 F841 unused-variable
 2 F821 undefined-name       1 F811 redefined-while-unused
 1 F541 f-string-missing-placeholders          합 119건
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
pyproject.toml [tool.ruff] · [tool.ruff.lint]        ← 규칙의 원본
.claude/hooks/guard-bash.sh (a) 커밋 게이트          ← 여기에 가지 하나 추가
  └ 기존 순서: SKIP_TEST_GATE → GREEN 없음 → GREEN 낡음 → (신규) 린트
.venv/bin/ruff                                       ← 없으면 막지 않는다
app/collectors/statcast.py:473                       ← F811 1건(자동 수정)
app/research/deep.py:510 · tests/test_kbo_usage.py:186 ← F821 2건(LINT-1-b)
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **스타일로 커밋을 막지 않는다.** 게이트 규칙은 **실행 중에 터지는 것**
  넷뿐이다(F811·F821·F822·F823). 스타일로 막으면 사람이 게이트를 통째로 끈다.
- 🔴 **F401 97건·F841 18건을 지금 고치지 않는다.** 고치면 수십 파일이 한
  커밋에 섞여 되돌리기가 불가능해진다. 게이트에서 빼고 보고만 한다(LINT-1-c).
- 🔴 **ruff 가 없으면 막지 않는다.** 없는 도구로 커밋을 막으면 저장소가 통째로
  잠긴다. `[ -x .venv/bin/ruff ]` 로 가드한다.
- 🔴 착수 시점 F821 2건은 **숨기지 않고 표시**한다 — `per-file-ignores` 에
  파일명과 사유를 적고 LINT-1-b 로 등록한다. **새 F821 은 그대로 막힌다.**
- ⚠️ `crawler/` 는 Go 다 — `exclude` 에 넣는다.
- ⚠️ 규칙 이름을 훅에 적지 않는다(사본 금지). 원본은 pyproject 하나다.

## ③ 되돌리기

커밋 1개 revert. `pyproject.toml` 의 `[tool.ruff]` 블록과 `guard-bash.sh` 의
린트 가지를 떼면 끝이다. 운영 코드는 `statcast.py` 의 중복 import 한 줄만
지웠으므로 되돌려도 동작이 같다. 배포와 무관하다(훅은 로컬 도구다).

## ④ 측정

중복 정의를 넣고 **전체 스위트를 통과시킨 뒤** 훅을 태워, 차단 사유가
'린터'로 찍히는 원문. (앞선 시도는 '마커 낡음'으로 막혀 증명이 아니었다.)

## ⑤ 계약

```
test_ruff가_설치돼_있다
test_게이트_규칙은_버그급만                  ← 반대 위험(스타일로 막으면 게이트가 꺼진다)
test_중복정의를_잡는다
test_없는_이름을_잡는다
test_훅에_규칙이름을_적지_않았다              ← 사본 금지
test_ruff가_없으면_막지_않는다                ← 반대 위험(저장소 잠김)
test_F401은_게이트가_아니다
test_현재_코드는_게이트_규칙을_통과한다
```
