#!/bin/bash
# 서명 회귀 — **커밋은 코드 변경이 아니다.**
#
# 실측 2026-09-06: worktree_sig 가 `git rev-parse HEAD` 를 포함해, 테스트를
# 통과시키고 커밋하는 순간 마커가 무효가 됐다. 코드는 한 글자도 안 바뀌었는데
# 배포 게이트가 "검증 안 됐다"고 막았다 — 정상 워크플로가 매번 걸린다.
cd "$(dirname "$0")/../.." || exit 1
source .claude/hooks/lib.sh
PASS=0; FAIL=0
ok() { if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "  ✅ $3"; else FAIL=$((FAIL+1)); echo "  🔴 $3"; fi; }

A=$(worktree_sig)
echo "  기준 서명: ${A:0:12}…"

# ① 빈 커밋 — 코드는 그대로다. 서명이 바뀌면 안 된다.
#
# 🔴 **`git reset --hard` 를 쓰지 않는다.** 처음에 그렇게 썼다가 커밋 안 된
#    lib.sh 수정을 통째로 날렸다(실사고 2026-09-06). `--soft` 는 HEAD 만
#    되돌리고 작업트리·인덱스를 건드리지 않는다.
git commit -q --allow-empty -m "probe(자동): 서명 불변 확인" >/dev/null 2>&1
B=$(worktree_sig)
git reset --soft HEAD~1 >/dev/null 2>&1
ok "$A" "$B" "빈 커밋 후에도 서명 불변 (${B:0:12}…)"

# ② 파일 수정 — 서명이 바뀌어야 한다.
TMPF="docs/.sig_probe.tmp"
echo "probe" > "$TMPF"
C=$(worktree_sig)
rm -f "$TMPF"
if [ "$A" != "$C" ]; then PASS=$((PASS+1)); echo "  ✅ 미추적 파일 추가 → 서명 변함"; \
   else FAIL=$((FAIL+1)); echo "  🔴 미추적 파일을 못 본다"; fi

# ③ 추적 파일 수정 — 서명이 바뀌어야 한다.
#    ⚠️ 원본을 복사해 두고 되돌린다. `git checkout --` 은 그 파일에 대한
#       커밋 안 된 다른 수정까지 함께 지운다.
BAK=$(mktemp); cp README.md "$BAK"
printf '\n' >> README.md
D=$(worktree_sig)
cp "$BAK" README.md; rm -f "$BAK"
if [ "$A" != "$D" ]; then PASS=$((PASS+1)); echo "  ✅ 추적 파일 수정 → 서명 변함"; \
   else FAIL=$((FAIL+1)); echo "  🔴 추적 파일 수정을 못 본다"; fi

# ④ 🔴 새 파일이 커밋되며 미추적→추적으로 바뀌어도 서명은 그대로여야 한다.
#    같은 사고를 두 번 겪었다 — blob 해시와 미추적 내용을 섞어 해싱했더니
#    표현이 바뀌면서 서명이 달라졌고, 배포가 또 막혔다.
NEWF="docs/.newfile_probe.md"
echo "새 파일 내용" > "$NEWF"
F=$(worktree_sig)
git add "$NEWF" >/dev/null 2>&1
git commit -q -m "probe(자동): 새 파일 커밋 후 서명 확인" >/dev/null 2>&1
G2=$(worktree_sig)
git reset --soft HEAD~1 >/dev/null 2>&1
git restore --staged "$NEWF" >/dev/null 2>&1
rm -f "$NEWF"
ok "$F" "$G2" "새 파일 커밋 후에도 서명 불변 (${G2:0:12}…)"

# ⑤ 원상 복구 확인
E=$(worktree_sig)
ok "$A" "$E" "정리 후 원래 서명으로 복귀"

echo
echo "  통과 $PASS · 실패 $FAIL"
[ $FAIL -eq 0 ]
