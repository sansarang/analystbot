#!/bin/bash
# [Stop] 증거 없는 "완료" 주장을 막는다.
#
# 🔴 이 세션의 실사고: `railway variable set` 이 조용히 실패했는데 출력을 버리고
#    "✓ 설정 완료" 라고 보고했다. 확인 없이 성공을 주장한 것이다.
#    "완료" 는 [테스트 수치 + 실행 시각 + 커밋 해시] 셋을 동반해야 한다.
source "$(dirname "$0")/lib.sh"

IN=$(cat)
TRANSCRIPT=$(printf '%s' "$IN" | jq -r '.transcript_path // ""' 2>/dev/null)
[ -f "$TRANSCRIPT" ] || exit 0

# 무한 루프 방지 — 이미 이 훅이 한 번 막았으면 그냥 통과시킨다.
printf '%s' "$IN" | jq -e '.stop_hook_active == true' >/dev/null 2>&1 && exit 0

# 이번 턴(마지막 사용자 메시지 이후)의 어시스턴트 텍스트와 도구 호출을 본다.
EV=$(python3 - "$TRANSCRIPT" <<'PY'
import json, sys
rows = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except Exception:
        pass
# 마지막 사용자 입력 이후만
start = 0
for i, r in enumerate(rows):
    if r.get("type") == "user" and isinstance(r.get("message"), dict):
        c = r["message"].get("content")
        if isinstance(c, str) or (isinstance(c, list) and any(
                b.get("type") == "text" for b in c if isinstance(b, dict))):
            start = i
# 🔴 [2026-09-06] **파일을 고친 턴에만 본다.** 조사·보고만 한 턴에서
#    "확인 완료" 같은 말에 헛울렸다 — 코드를 안 고쳤으면 돌릴 테스트도 없다.
#    헛경보가 쌓이면 이 훅은 곧 꺼지고, 꺼진 훅은 없는 훅이다.
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
#: Bash 로 파일을 고치는 흔한 형태(이 저장소는 python 힙독 패치를 쓴다).
WRITE_HINTS = ("> ", ">>", "sed -i", "tee ", "io.open(", "patch ")

text, ran_tests, edited = [], False, False
for r in rows[start:]:
    m = r.get("message") or {}
    for b in (m.get("content") or []) if isinstance(m.get("content"), list) else []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            text.append(b.get("text") or "")
        if b.get("type") == "tool_use":
            if b.get("name") in EDIT_TOOLS:
                edited = True
            cmd = str((b.get("input") or {}).get("command") or "")
            if "pytest" in cmd:
                ran_tests = True
            if any(h in cmd for h in WRITE_HINTS):
                edited = True
print(json.dumps({"text": "\n".join(text)[-4000:], "ran_tests": ran_tests,
                  "edited": edited}, ensure_ascii=False))
PY
)
CLAIM=$(printf '%s' "$EV" | jq -r '.text' | grep -cE '완료(했|됐|입니다|\.|$)|끝냈|다 됐|해결했' || true)
RAN=$(printf '%s' "$EV" | jq -r '.ran_tests')

EDITED=$(printf '%s' "$EV" | jq -r '.edited')

[ "${CLAIM:-0}" -eq 0 ] && exit 0
[ "$RAN" = "true" ] && exit 0
# 파일을 안 고친 턴은 통과 — 조사·보고만 한 것이다.
[ "$EDITED" = "true" ] || exit 0

# 문서·설정만 만진 턴은 테스트가 없을 수 있다 — 그래도 알린다(차단은 아님).
log_audit "CLAIM-GATE 완료 주장에 테스트 실행 없음"
cat >&2 <<'MSG'
⚠️ 이번 턴에 "완료"라고 썼는데 테스트를 돌린 기록이 없다.

완료 보고는 세 요소를 갖춘다:
  ① 테스트 수치   — "2051 passed" 처럼 실제 출력의 숫자
  ② 실행 시각     — 언제 돌렸는지
  ③ 커밋 해시     — 무엇이 그 상태인지

코드를 고쳤다면 지금 돌려라:  PYTHONPATH=. uv run pytest tests -q
문서·설정만 고쳤다면 그 사실을 한 줄로 명시하고 마무리하라 —
"완료"라는 단어보다 무엇을 확인했는지가 중요하다.
MSG
exit 2
