"""🔴🔴 **v5 §8-1 — 어댑터는 `출처:경기ID` 를 받아야 한다.**

══════════════════════════════════════════════════════════════════
🔴 이관이 **깊이를 통째로 끊었다**(실측 2026-10-04 · 봇 실행)
══════════════════════════════════════════════════════════════════

`keymigrate` 가 `849825` → `statsapi:849825` 로 45건을 이관한 **직후** 실행:

```
· 세포 Milwaukee Brewers:깊이: 공식 깊이 소스가 없다 —
  이 리그 어댑터에 `sources_context` 가 없다
verified_vars: 6 → **0**
```

🔴 `mlb.sources_context` 가 이랬다:

```python
pk = str(ext_id or "").strip()
if not pk or not pk.isdigit():      # ⚠️ `statsapi:849825` 는 **숫자가 아니다**
    return []                       # 🔴 조용히 빈 목록
```

⚠️ 그리고 그 빈 목록이 **거짓 사유**를 낳았다 — `analyze` 가 *"어댑터에
   `sources_context` 가 없다"* 고 적었다. **있다.** 빈 목록을 냈을 뿐이다
   (§8-6 이 막는 거짓 사유다 · CLAUDE.md #3 조용한 0 금지).

🔴 §11-1 — **증상을 고치지 않는다.** 이 계약이 막는 것은 *"MLB 가 숫자만
   받는다"* 가 아니라 **모양**이다: 어댑터가 열쇠를 받는 함수는 전부
   `matchkey.id_of` 를 지나야 한다.
"""
from __future__ import annotations

import pytest

from app import matchkey
from app.collect import ingest

#: 🔴 열쇠를 **인자로 받는** 어댑터 함수 이름. ⚠️ 손으로 세지 않는다 — `ingest`
#  가 고르는 함수가 이것들이다(`context_of`·`followup_of`).
KEY_TAKERS = ("sources_context", "sources_followup")

#: ⚠️ 어댑터마다 **열쇠 꼴이 다르다** — npb 는 날짜+팀코드로 짓는다(공식 경기
#  id 가 없다). 🔴 그 꼴을 그 어댑터가 쓰는 그대로 넣어야 시험이 뜻을 가진다.
_SAMPLE = {"npb": "20261004-f-m"}


def _adapters():
    """🔴 **표에서 자란다** — 어댑터 목록을 손으로 적지 않는다."""
    seen = {}
    for src, mod in ingest.SOURCE_ADAPTERS.items():
        seen.setdefault(mod.__name__, (src, mod))
    return sorted(seen.values())


@pytest.mark.parametrize(("src", "mod"), _adapters(), ids=lambda x: str(x))
def test_v5_8_1_어댑터가_표준_열쇠를_받는다(src, mod):
    """🔴🔴 **표준 열쇠와 맨숫자가 같은 결과를 내야 한다.**

    ⚠️ 어댑터가 자기 출처가 아닌 열쇠를 받으면 `[]` 가 맞다 — 그것은 라우팅이
       막는다. 여기서 보는 것은 **자기 출처의 표준 열쇠**다.
    """
    if not isinstance(src, str):
        pytest.skip("표 모양")
    for fname in KEY_TAKERS:
        fn = getattr(mod, fname, None)
        if not callable(fn):
            continue
        # ⚠️ `sources_followup(facts, ext_id)` 는 **인자가 둘**이다 — 열쇠는
        #    마지막이다. 🔴 수를 세어 맞춘다(이름을 손으로 적지 않는다).
        import inspect
        nargs = len(inspect.signature(fn).parameters)
        mid = _SAMPLE.get(src, "849825")
        canon = matchkey.make(src, mid)
        # 🔴 **옛 꼴**이다 — `출처-ID`. ⚠️ 맨숫자로 견주면 안 된다: 맨숫자는
        #    `statsapi` 의 옛 꼴이지만 다른 어댑터에게는 **남의 열쇠**다
        #    (실측 2026-10-04: fotmob·espn 이 MLB 번호 `849844` 를 집었다).
        legacy = f"{src}-{mid}"
        call = (lambda k: fn(k)) if nargs == 1 else (lambda k: fn([], k))
        got_legacy = call(legacy)
        got_canon = call(canon)
        assert len(got_canon) == len(got_legacy), (
            f"🔴 `{mod.__name__}.{fname}` 가 표준 열쇠 `{canon}` 에서 "
            f"{len(got_canon)}개, 옛 꼴 `{legacy}` 에서 {len(got_legacy)}개를 "
            f"냈다 — §8-1 이관 뒤 **깊이가 통째로 끊긴다**(실측 2026-10-04: "
            f"`verified_vars` 6 → 0)")
        # 🔴 **남의 맨숫자는 집지 않는다** — 맨숫자가 자기 옛 꼴인 어댑터만 예외
        if src != "statsapi":
            assert not call("849844"), (
                f"🔴 `{mod.__name__}.{fname}` 가 **맨숫자 열쇠**(남의 경기)를 "
                f"집었다 — 야구 경기에 그 어댑터 페이지를 붙인다(§17-g-3)")


def test_v5_8_1_열쇠를_받는_함수는_id_of_를_지난다():
    """🔴🔴 **모양을 막는다**(§11-1) — 숫자 검사를 **열쇠 글자에** 걸지 않는다.

    ⚠️ 어느 어댑터든 `ext_id` 를 받아 `isdigit()`·`startswith`·슬라이스로
       **직접** 가르면 열쇠 꼴이 바뀔 때 또 끊긴다. 🔴 `matchkey` 가 떼어 준다.
    """
    import ast
    import inspect
    import pathlib
    bad = []
    for src, mod in _adapters():
        if not isinstance(src, str):
            continue
        path = pathlib.Path(inspect.getfile(mod))
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in KEY_TAKERS:
                continue
            args = {a.arg for a in node.args.args}
            if "ext_id" not in args:
                continue
            body = ast.dump(node)
            # ⚠️ **열쇠를 안 쓰는 함수는 뺀다**(`del ext_id` 로 버린다) — kbo 가
            #    그 꼴이다(일정 소스만 있고 경기별 깊이가 없다). 🔴 안 쓰는데
            #    `matchkey` 를 부르라고 하면 그것이 장식 코드다.
            if any(isinstance(n, ast.Delete)
                   and any(getattr(t, "id", "") == "ext_id" for t in n.targets)
                   for n in ast.walk(node)):
                continue
            # 🔴 열쇠를 받는 함수는 **반드시** `matchkey` 를 지난다
            if "id_of" not in body and "matchkey" not in body:
                bad.append(f"{mod.__name__}.{node.name}")
    assert not bad, (
        "🔴 §8-1 — 열쇠를 받는데 `matchkey.id_of` 를 지나지 않는 함수: "
        f"{bad}. 이관 뒤 그 어댑터의 깊이가 **조용히 0** 이 된다")


def test_v5_8_1_깊이_사유를_한_줄로_박지_않는다():
    """🔴🔴 *"어댑터에 `sources_context` 가 없다"* 는 **거짓이었다.**

    ⚠️ MLB 어댑터에는 **있다.** 이관 뒤 `pk.isdigit()` 이 실패해 **빈 목록**을
       냈을 뿐이다. 그 카드를 읽은 사람은 **엉뚱한 곳을 고친다**(§8-6).

    🔴 그래서 그 자리는 **고정 문장**이 아니라 `depth_why(game)` 이어야 한다 —
       세 경우(어댑터 없음 · 열쇠 없음 · 빈 목록)가 **다른 글자**를 받는다.
    ⚠️ 글자 비교가 아니라 AST 다(`depth_why` 안에서는 그 글자를 **써야** 한다).
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    # ⚠️ 그 자리는 `gather` 다(`build` 가 아니다) — 깊이 세포는 수집 쪽이다.
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.gather)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", "")) == "depth_why"]
    assert calls, (
        "🔴 `analyze.build` 가 깊이 사유를 **고정 문장**으로 적는다 — 세 경우를 "
        "가려 적어라(`depth_why`)")
    # 🔴 그리고 그 고정 문장이 `build` 안에 **남아 있지 않아야** 한다
    lits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "sources_context" in n.value]
    assert not lits, (
        f"🔴 `build` 에 옛 고정 사유가 남아 있다: {lits}")


def test_v5_8_1_두_경우를_가려_적는다():
    """🔴 **둘을 가리는 함수가 있나** — 글자가 달라야 한다."""
    from app import analyze
    # ⚠️ 어댑터가 **없는** 리그
    none_ = analyze.depth_why({"league": "없는리그", "ext_id": ""})
    # 🔴 어댑터는 있는데 **열쇠로 못 만든** 경우
    empty = analyze.depth_why({"league": "MLB", "ext_id": "쓰레기"})
    assert "없다" in none_ and none_ != empty, (none_, empty)
    assert "빈 목록" in empty or "못 만들었다" in empty, empty
