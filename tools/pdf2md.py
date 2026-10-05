"""🔴🔴 **PDF → 마크다운.** 기계 추출이다 — 손으로 옮겨 적지 않는다(v5 §11-5).

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 있나 — CLAUDE.md 머리글의 실사고
══════════════════════════════════════════════════════════════════

> 실사고 2026-09-29: 내가 v3 를 **손으로 옮겨 적어** `inbox/` 에 두고 "원본"이라
> 적었다. 그 파일은 rev 24 였고 §19·§20 이 **아예 없었다** — v3 는 그 사이 rev 29
> 까지 갔다. 나는 개정분을 **대화로만 알고** 일곱 커밋을 진행했다.

🔴 그래서 지시서는 **기계로 뽑아 파일로** 넣는다. ⚠️ 쪽 번호를 그대로 남긴다 —
   나중에 *"§2 가 뭐라고 했나"* 를 **그 쪽에서** 확인할 수 있어야 한다.

쓰는 법:

    uv run --no-project --with pypdf python tools/pdf2md.py <입력.pdf> <출력.md>

⚠️ `pypdf` 를 **저장소 의존성에 넣지 않는다** — 지시서를 받을 때만 쓰는 일회성
   도구다(`--with` 로 격리한다). 🔴 설치가 무거워지면 무엇이 살아 있는지 알기
   어려워진다(`pyproject.toml` 머리글의 규율).
"""
import sys, pathlib
import pypdf

src = pathlib.Path(sys.argv[1]); dst = pathlib.Path(sys.argv[2])
r = pypdf.PdfReader(str(src))
out = [f"# {src.name} — **기계 추출**(손으로 옮겨 적지 않는다 · §11-5)", "", "---", ""]
for i, page in enumerate(r.pages, 1):
    out += [f"## PDF Page {i}", "", (page.extract_text() or "").strip(), ""]
dst.write_text("\n".join(out), encoding="utf-8")
print(f"쪽수 {len(r.pages)} · {dst} · {dst.stat().st_size}바이트")
