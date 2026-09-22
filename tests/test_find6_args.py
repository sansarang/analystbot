"""[FIND-6] 박스스코어 백필이 `_FIND` 에 인자를 **하나 덜** 넘긴다.

🔴 KBO 적재가 09-12 에서 끊긴 **진짜 원인**이다. robots 게이트는 09-21 에
   생겼으니 그보다 9일 앞선다 — 게이트를 켜도(KBO-ON) 여전히 0행이었다.

실측 2026-09-23 운영, 게이트를 켠 직후 백필:
```
asyncpg.exceptions._base.InterfaceError:
    the server expects 6 arguments for this query, 5 were passed
after : 최신 2026-09-12 · 2367행  (증가 0)
```

`_FIND` 의 `$6` 은 **출처 접두사**다(`game_match` 머리말):
```sql
AND NOT (ext_id IS DISTINCT FROM $6
         AND split_part(ext_id, ':', 1) = split_part($6::text, ':', 1))
```
> "가르는 기준은 `ext_id` 의 접두사다 — **같으면 다른 경기, 다르면 병합**"

🔴 박스스코어는 **다른 출처**다. 그래서 접두사가 다른 ext_id 를 넘겨 "같은
   경기의 다른 소스"로 병합되게 한다.
⚠️ `None` 을 넘기면 안 된다 — `split_part(NULL,':',1)` 이 NULL 이라 `AND` 가
   NULL 이 되고 `NOT NULL` 도 NULL 이라 **ext_id 가 있는 행이 전부 탈락**한다.
"""
from __future__ import annotations

import ast
import inspect

import pytest


def _find_calls(mod) -> list:
    """`_FIND` 를 쓰는 호출이 넘기는 **SQL 파라미터 개수**.

    ⚠️ `fetchval(_FIND, a, b, …)` 에서 첫 인자는 질의 자체다 — 빼고 센다.
       처음에 그걸 안 빼서 5개짜리 호출이 6으로 보였고 계약이 **거짓 통과**
       했다(이 저장소의 "거짓 통과" 유형).
    """
    tree = ast.parse(inspect.getsource(mod))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        args = node.args
        if args and isinstance(args[0], ast.Name) and args[0].id == "_FIND":
            out.append(len(args) - 1)
    return out


@pytest.mark.parametrize("modname", ["app.collectors.kbo_boxscore",
                                     "app.collectors.npb_boxscore"])
def test_인자를_여섯_개_넘긴다(modname):
    """🔴 다섯 개면 실행 시점에 `InterfaceError` 다 — 적재가 통째로 0 이 된다."""
    import importlib

    mod = importlib.import_module(modname)
    calls = _find_calls(mod)
    assert calls, f"{modname} 이 _FIND 를 안 쓴다(계약이 낡았다)"
    assert all(n == 6 for n in calls), f"{modname}: 인자 개수 {calls}"


def test_질의가_정말_여섯_개를_요구한다():
    """⚠️ 계약이 낡지 않도록 **질의 원문에서 센다** — 6 을 손으로 적지 않는다."""
    import re

    from app.collectors.game_match import _FIND

    n = max(int(m) for m in re.findall(r"\$(\d+)", _FIND))
    assert n == 6, f"_FIND 가 ${n} 까지 쓴다 — 계약을 맞춰라"


@pytest.mark.parametrize("modname", ["app.collectors.kbo_boxscore",
                                     "app.collectors.npb_boxscore"])
def test_None_을_넘기지_않는다(modname):
    """🔴 `None` 은 조용히 **전건 미일치**를 만든다(NULL 전파)."""
    import importlib

    mod = importlib.import_module(modname)
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (node.args and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "_FIND"):
            continue
        last = node.args[-1]
        assert not (isinstance(last, ast.Constant) and last.value is None), \
            f"{modname}: _FIND 마지막 인자가 None 이다"


@pytest.mark.parametrize("modname,sport", [
    ("app.collectors.kbo_boxscore", "kbo"),
    ("app.collectors.npb_boxscore", "npb"),
])
def test_접두사가_일정과_달라야_병합된다(modname, sport):
    """🔴 이것이 이 수정의 **의미**다.

    `game_match` 머리말: "가르는 기준은 `ext_id` 의 접두사다 —
    **같으면 다른 경기, 다르면 병합**".
    박스스코어는 일정과 **다른 출처**이므로 접두사가 달라야 기존 경기 행에
    병합된다. `kbo:` 를 그대로 쓰면 같은 경기가 둘로 갈린다.
    """
    import importlib

    mod = importlib.import_module(modname)
    tree = ast.parse(inspect.getsource(mod))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (node.args and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "_FIND"):
            continue
        last = node.args[-1]
        text = ast.unparse(last)
        assert ":" in text, f"{modname}: 접두사 없는 ext_id — {text}"
        assert not text.strip("f'\"").startswith(f"{sport}:"), \
            f"{modname}: 일정과 같은 접두사를 쓴다 — {text}"
        checked += 1
    assert checked, f"{modname} 에서 _FIND 호출을 못 찾았다"
