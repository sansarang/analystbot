"""🔴🔴 **⑯ 묶음이 실제로 만들어지나** — 실사고 2026-10-17(라이브).

⚠️ **이 파일의 대상이 바뀌었다**(사용자 지시 2026-10-17: *"옛 코드는 더이상
   필요하지 않다"*). 처음 쓸 때 나는 **옛 묶음**(`core/saybundle`)을 세고
   있었다 — 그것은 지운 글 경로(`s9_say`)의 묶음이고, 지금 ⑯ 평의 묶음은
   `stages/s6_verdict.chain_of` 다. 🔴 그 자리로 옮겨 센다.

⚠️ 시미즈 경기를 실제로 돌렸더니 수집·딥서치·⑤-b2 를 **다 지난 뒤** 마지막
   단계에서 카드가 통째로 죽었다:

```
🔴 카드가 터졌다: AttributeError(
     "module 'app.core.strategy' has no attribute 'stat_of'")
```

🔴 뿌리 — `strategy.stat_of` 를 *"부르던 곳이 함께 없어졌다"* 며 지웠는데
   `saybundle._stat_of` 가 **아직 부르고 있었다**. ⚠️ 그리고 **스위트는
   초록**이었다 — ⑯ 묶음을 **실제로 만드는** 시험이 없었다(글자 검사·단위
   시험만 있었다). 9분을 버리고 라이브에서 알았다.

🔴 그래서 이 계약은 **묶음을 실제로 만든다** — 그 경로에 **없는 함수**가 있으면
   그 자리에서 빨개진다(v6 §9 가 글자 검사 테스트를 금지한 까닭).
"""
from __future__ import annotations

import inspect
import re

from app.core.stages import s6_verdict as _vd


def test_bl1_app_전체가_없는_함수를_안_부른다() -> None:
    """🔴🔴 **`app/` 전체** — 지운 함수를 부르는 자리가 남아 있나.

    ⚠️ 이 계약을 처음 쓸 때 **`saybundle` 만** 봤다. 그래서 `stat_of` 를
       고친 뒤 **그 다음 지뢰**(`layer1.player_pool` ← `stages/s9_audit`)가
       라이브에서 또 터졌다 — 같은 처분(지시서 2026-10-12 셋째)에서 함께 생긴
       병이라 **한 파일만 보면 못 잡는다**.
    🔴 그래서 범위를 `app/**/*.py` 전체로 넓혔다. 별칭 표는 **소스의
       `import` 를 읽어** 자라게 한다(손 표는 한 발 늦는다 — 처음에 `_b` 를
       `core.backfill` 로 적었고 실제는 `stages.s2b_base` 였다).
    ⚠️ `hasattr` 로 막아 둔 호출은 **위반이 아니다**(그 줄은 없을 때를 안다).
    """
    import ast
    import importlib
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]
    bad: list[str] = []
    n_files = 0
    for path in sorted(root.glob("app/**/*.py")):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        n_files += 1
        alias: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    alias[a.asname or a.name] = f"{node.module}.{a.name}"
            elif isinstance(node, ast.Import):
                for a in node.names:
                    alias[a.asname or a.name] = a.name
        for said, mod_path in sorted(alias.items()):
            if not mod_path.startswith("app."):
                continue
            try:
                got = importlib.import_module(mod_path)
            except Exception:                               # noqa: BLE001
                continue                  # 모듈이 아니라 그 안의 이름이다
            for name in sorted(set(
                    re.findall(rf"\b{re.escape(said)}\.(\w+)\s*\(", src))):
                if hasattr(got, name):
                    continue
                # ⚠️ `hasattr(mod, "name")` 로 막아 둔 자리는 **위반이 아니다**
                if re.search(rf'hasattr\(\s*{re.escape(said)}\s*,\s*'
                             rf'["\']{re.escape(name)}["\']', src):
                    continue
                said_rel = path.relative_to(root).as_posix()
                bad.append(f"{said_rel} → {mod_path}.{name}")
    assert n_files > 50, f"🔴 파일을 {n_files}개만 읽었다(계약이 빈손이다)"
    assert not bad, ("🔴 **없는 함수**를 부르는 자리가 있다(라이브에서 카드가 "
                     "통째로 죽는다):\n  " + "\n  ".join(sorted(set(bad))))


# 🔴 **`test_bl1b_player_pool…` 을 지웠다** — 그 대상(`layer1.player_pool`)이
#    옛 글 경로(`stages/s9_audit` 검열 (j))와 함께 걷혔다(2026-10-17).
