#!/bin/bash
# [Stop · CC-2 2026-09-25] 갈림길에서 멈춘 세션의 **질문을 파일로 남긴다.**
#
# 🔴 왜. CLAUDE.md §2갈래는 "갈리면 사용자에게 묻고 멈춘다"고 한다. 그런데 그
#    질문이 채팅에만 남으면 사용자가 페이블에 **복붙**해야 하고, 복붙은 빠진다.
#    이 훅이 `docs/fable/questions/` 에 파일로 떨궈 그 왕복을 없앤다.
# 🔴 **판단하지 않는다.** 마지막 어시스턴트 메시지를 **그대로** 옮긴다 —
#    요약하면 그 요약이 곧 내 취향이고, 갈림길에서 취향은 금지다.
# ⚠️ **막지 않는다.** 항상 exit 0 이다 — 이 훅은 기록이지 게이트가 아니다.
#    (게이트는 `claim-gate.sh` 가 따로 본다. 같은 자리에 둘이 물린다.)
# ⚠️ 오늘 날짜 파일이 이미 있으면 덮지 않는다 — 사용자가 손으로 쓴 질문을
#    자동 생성물이 지우면 안 된다.
set -u

IN=$(cat)
TRANSCRIPT=$(printf '%s' "$IN" | jq -r '.transcript_path // ""' 2>/dev/null)
[ -f "$TRANSCRIPT" ] || exit 0

REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$REPO" ] || exit 0
DIR="$REPO/docs/fable/questions"
[ -d "$DIR" ] || exit 0

DAY=$(TZ=Asia/Seoul date '+%Y-%m-%d')
# 오늘 질문이 이미 있으면(손으로 썼든 자동이든) 건드리지 않는다.
if ls "$DIR"/"$DAY"_*.md >/dev/null 2>&1; then exit 0; fi

# 🔴 문구 표는 **여기 한 곳**이다. 늘릴 때 오탐을 재라 — 아무 메시지나 걸리면
#    질문 폴더가 쓰레기통이 되고, 그러면 사용자가 안 본다.
python3 - "$TRANSCRIPT" "$DIR/${DAY}_auto.md" "$DAY" <<'PY' 2>/dev/null || exit 0
import json, sys, pathlib

TRIGGERS = ("어느 쪽으로 갈까요", "지시가 필요", "지시를 기다린다",
            "갈림길", "어느 쪽을 고를까", "묻는다 — 코드를 먼저 쓰지 않는다")

src, out, day = sys.argv[1], sys.argv[2], sys.argv[3]
last = None
for line in open(src, encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except ValueError:
        continue
    if row.get("type") != "assistant":
        continue
    content = ((row.get("message") or {}).get("content")) or []
    if isinstance(content, str):
        text = content
    else:
        text = "\n".join(c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text")
    if text.strip():
        last = text

if not last or not any(t in last for t in TRIGGERS):
    raise SystemExit(1)

p = pathlib.Path(out)
p.write_text(
    f"# 갈림길 질문 (자동 저장 · {day})\n\n"
    "🔴 이 파일은 `on_stop.sh` 가 **마지막 어시스턴트 메시지를 그대로** 옮긴\n"
    "   것이다. 요약하지 않았다 — 갈림길에서 요약은 곧 취향이다.\n"
    "⚠️ 사용자가 이 파일을 페이블에 올리고, 답은 `docs/fable/answers/` 에 넣는다.\n\n"
    "---\n\n" + last + "\n", encoding="utf-8")
print(out)
PY
exit 0
