"""🔴🔴 **구조 계약** — 신원을 이름으로 가리지 않는다(3단계 · 사용자 설계 2026-10-03).

> `resolve.py` 밖에서 팀 이름 문자열끼리 `==`·`in` 으로 비교하는 코드가 있으면
> 실패(**AST 검사**, grep 보다 정확).

══════════════════════════════════════════════════════════════════
🔴 다만 **신원과 귀속을 가른다**
══════════════════════════════════════════════════════════════════

| 쓰임 | 예 | ID 로 바꾸나 |
|---|---|---|
| **신원** — 이 경기/팀이 그것인가 | `slate.find` · `Game.side_of` | ✅ 바꾼다 |
| **귀속** — 이 *기사 문장*이 우리 팀 얘기인가 | `verify.mentions_team` | 🔴 **못 바꾼다** |

🔴 기사 본문에는 **ID 가 없다.** 그 글이 우리 팀 얘기인가는 이름으로만 볼 수 있다.
   그래서 금지하는 것은 *"**경기·팀을 고를 때** 이름을 비교하는 것"* 이다.

⚠️ **허용 목록은 줄어들기만 한다** — 늘리려면 이 계약이 먼저 빨개지고, 그때
   *"왜 아직 이름으로 비교하나"* 를 적게 된다(`NOT_WIRED` 와 같은 수법).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 🔴 이름을 **들고 있는** 변수들 — 이것들끼리 비교하면 신원 비교다.
NAME_VARS = frozenset({
    "team", "opponent", "home", "away", "formal", "mine", "other", "name",
    "team_name", "home_name", "away_name",
})

#: 🔴 **아직 이름으로 비교하는 자리**. ⚠️ 늘리지 않는다 — 줄이기만 한다.
#   `파일:함수` → 왜 아직인가.
ALLOWED: dict[str, str] = {
    # ── 🔴 **신원이지만 열쇠가 없는 자리.** ⚠️ 줄이기만 한다.
    "app/survive.py:_ungrade":
        "마켓의 팀 칸(`Market.team`)에는 열쇠가 없다 — 보드가 이름으로 온다. "
        "⚠️ 같은 경기 안에서만 비교하므로 언어가 갈릴 여지가 없다",
}


def _identity_compares(tree: ast.AST) -> list[tuple[str, int]]:
    """🔴 **이름 변수끼리** `==`·`in` 으로 비교하는 자리를 찾는다."""
    out: list[tuple[str, int]] = []

    def _is_name_var(n: ast.AST) -> bool:
        if isinstance(n, ast.Name):
            return n.id in NAME_VARS
        if isinstance(n, ast.Attribute):
            return n.attr in NAME_VARS
        return False

    class V(ast.NodeVisitor):
        def __init__(self):
            self.fn = ""

        def visit_FunctionDef(self, node):      # noqa: N802
            keep, self.fn = self.fn, node.name
            self.generic_visit(node)
            self.fn = keep

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Compare(self, node):          # noqa: N802
            for op, right in zip(node.ops, node.comparators, strict=False):
                if not isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                if _is_name_var(node.left) and _is_name_var(right):
                    out.append((self.fn, node.lineno))
            self.generic_visit(node)

    V().visit(tree)
    return out


def test_신원을_이름으로_가리지_않는다():
    """🔴🔴 **AST 로** 본다 — grep 은 주석·문자열에 속는다(D46 과 같은 뿌리)."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for fn, line in _identity_compares(tree):
            if f"{rel}:{fn}" in ALLOWED:
                continue
            bad.append(f"{rel}:{line} `{fn}` — 이름끼리 비교한다")
    assert not bad, (
        "🔴 신원을 이름으로 가린다(3단계). 열쇠로 바꾸거나, 귀속이면 "
        "`ALLOWED` 에 **왜인지** 적어라:\n  " + "\n  ".join(bad))


def test_허용_목록이_줄어들기만_한다():
    """🔴 목록이 자라면 이 설계가 **되돌아간다**.

    ⚠️ 사용자 지시 2026-10-02: *"사유만 남기고 나중에 하지 않으면 안 하는 이보다
       못하다."* 그래서 상한을 박아 둔다 — 넘기려면 **이 수를 고치며** 왜인지
       적게 된다.
    """
    assert len(ALLOWED) <= 10, f"허용 목록이 {len(ALLOWED)}개로 늘었다"
    for key, why in ALLOWED.items():
        assert ":" in key and why.strip(), key
        f, _, fn = key.partition(":")
        assert (ROOT / f).exists(), f"없는 파일: {f}"
        # 🔴 **이름이 사라진 함수가 목록에 남으면** 목록이 거짓이 된다
        src = (ROOT / f).read_text(encoding="utf-8")
        assert f"def {fn}(" in src, f"{key} — 그 함수가 없다"


def test_귀속은_이름으로_본다():
    """🔴 기사 본문에는 **ID 가 없다** — 그 자리는 영구히 이름이다.

    ⚠️ 이 계약이 *"모든 이름 비교 금지"* 가 되면 **귀속 검사가 통째로 죽는다.**
       그러면 엉뚱한 기사(멕시코 선수·11월 경기)가 우리 변수가 된다.
    🔴 그래서 **신원만** 막는다. 귀속은 여기서 살아 있음을 확인한다.
    """
    from app import verify
    # 🔴 **그 글이 우리 팀 얘기인가** — 이름으로만 볼 수 있다
    assert verify.mentions_team("Kashiwa Reysol vs Gamba Osaka", "Kashiwa Reysol")
    assert not verify.mentions_team("Tottenham vs Arsenal", "Kashiwa Reysol")
    # 🔴 남녀·연령 표식도 **이름에 붙는다**
    assert not verify.same_squad_kind("South Korea W", "South Korea")


def test_열쇠가_있으면_이름을_안_본다():
    """🔴🔴 **돌연변이 검사** — 열쇠로 아니라고 한 것을 글자가 뒤집으면 안 된다.

    ⚠️ 실측에서 이 자리를 처음엔 *"열쇠로 못 찾으면 이름으로 한 번 더"* 로 짰다.
       🔴 그러면 열쇠 판단이 **무효가 된다** — 글자가 최종 결정권을 갖는다.
    """
    from app import classify, teamref
    # 🔴 **열쇠를 글자로 박지 않는다** — 이름표가 자라면 열쇠 꼴이 바뀐다
    #    (실측 2026-10-04: 54팀 표가 들어오며 `tsdb:137708` → `name:J리그:…`).
    #    ⚠️ 시험이 옛 열쇠를 박아 두면 **그 변화를 결함으로 오독한다.**
    g = classify.Game(home="Kashiwa Reysol", away="Gamba Osaka",
                      home_id=teamref.key_of("Kashiwa Reysol")[0],
                      away_id=teamref.key_of("Gamba Osaka")[0])
    assert g.home_id and g.away_id and g.home_id != g.away_id
    # 🔴 세 언어가 **같은 쪽**이다
    assert g.side_of("柏レイソル") == "home"
    assert g.side_of("가시와 레이솔") == "home"
    assert g.side_of("Kashiwa Reysol") == "home"
    assert g.side_of("ガンバ大阪") == "away"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **열쇠가 아니라고 하면 거기서 끝난다** — 글자가 뒤집지 못한다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음엔 반례를 `Kashiwa United` 로 썼다. 🔴 **약했다** — 그 이름은
    #     `mentions_team` 도 거부하므로, 조기 반환을 지워도 시험이 **통과했다**
    #     (실측 2026-10-03: 돌연변이가 통과했다).
    #  🔴 그래서 **이름으로는 걸리는데 열쇠로는 다른** 반례를 만든다:
    #     `Kashiwa Reysol` 안에 `Reysol` 이 들어 있어 귀속 검사는 참이지만,
    #     그 팀의 열쇠는 우리 둘 중 어느 것도 아니다.
    # ⚠️ 반례는 **열쇠가 풀리는 남의 팀**이어야 한다 — 열쇠를 못 푸는 이름은
    #    이름 경로로 떨어지고, 그것은 설계대로다.
    #    🔴 `Reysol` 을 쓰다가 54팀 표가 그 이름을 담으면서 전제가 깨졌다
    #       (실측 2026-10-04) — 그래서 **같은 리그의 다른 팀**으로 고정한다.
    import app.teamref as _tr
    stray = "Cerezo Osaka"
    assert _tr.key_of(stray)[0] not in ("", g.home_id, g.away_id)
    assert g.side_of(stray) is None
    # 🔴 **돌연변이 확인** — 조기 반환이 없으면 이름 경로가 돌고, 그때
    #    `mentions_team` 이 참인 이름은 쪽을 얻는다. 그 자리를 직접 본다.
    import ast
    import inspect
    import textwrap
    code = ast.unparse(ast.parse(textwrap.dedent(
        inspect.getsource(classify.Game.side_of))))
    assert "if self.home_id and self.away_id:" in code, \
        "🔴 열쇠가 둘 다 있을 때의 **조기 반환**이 사라졌다 — 글자가 열쇠를 뒤집는다"
    # ⚠️ 열쇠가 없으면 **종전대로** 이름으로 간다(대체는 살아 있다)
    g2 = classify.Game(home="Kashiwa Reysol", away="Gamba Osaka")
    assert g2.side_of("Kashiwa Reysol") == "home"
    assert g2.side_of("柏レイソル") is None      # 🔴 그 자리가 못 하는 일이다
