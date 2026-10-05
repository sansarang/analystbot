"""🔴🔴 **v5 §7-4 — 채점·원장.** 실패를 **두 종류로** 가르고 비용을 함께 쌓는다.

지시문 §7-4 원문:

> 경기 뒤 `realized_scenario_id`, `missed_variables`, `card_verdicts_result`,
> `premise_failures`, **비용**을 원장에 적는다. **결과 후 `survival.json` 수정
> 금지.** **실패 유형을 둘로 가른다**: *없던 시나리오가 터짐*(규칙 결함 → M 계약
> 후보) / *죽는 시나리오가 터짐*(무게 보정 대상). **적중률은 완벽 작동 정의에
> 넣지 않는다**(v4 그대로).

══════════════════════════════════════════════════════════════════
🔴 왜 **두 종류**인가 — 고칠 곳이 다르다
══════════════════════════════════════════════════════════════════

    없던 시나리오가 터졌다   🔴 **규칙 결함**이다 — 그 결과를 아예 못 그렸다
                             (§6-2 가 막으려는 것 · M 계약 후보)
    죽는 시나리오가 터졌다   ⚠️ 그릴 줄은 알았고 **무게를 잘못 줬다**

🔴 섞으면 *"시나리오를 안 만들었다"* 와 *"만들었는데 낮게 봤다"* 가 한 글자가
   되고, 어느 쪽도 안 고쳐진다(§8-6 과 같은 가름이다).

══════════════════════════════════════════════════════════════════
🔴🔴 **"무게 보정 대상" 은 이 저장소에서 금지다** — 사용자 지시 2026-10-02
══════════════════════════════════════════════════════════════════

> 쌓이는거는 우리 로직이 맞냐 틀렸냐만 **검증하는 방법으로만** 사용한다.

⚠️ §7-4 는 두 번째 종류를 *"무게 보정 대상"* 이라 불렀다. 🔴 **그 보정은 하지
   않는다** — 계수를 맞추지도, 문턱을 조정하지도 않는다(CLAUDE.md).
🔴 **이름만 가른다.** 가름은 *"어느 쪽 결함인가"* 를 세기 위한 것이고, 그 수로
   규칙을 고치는 코드가 생기면 `tests/test_wiring.py` 가 빨개진다.
"""
from __future__ import annotations


def test_v5_7_4_실패_유형이_둘로_갈린다():
    """🔴 §7-4 — 두 이름이 **코드에 있어야** 한다."""
    from app import ledgerkind
    assert ledgerkind.KINDS == ("uncovered", "underweighted")
    # 🔴 사람이 읽는 글이 **다르다**(같으면 가름이 없다)
    a = ledgerkind.say("uncovered")
    b = ledgerkind.say("underweighted")
    assert a != b and a and b
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **첫 판이 돌연변이 D 를 통과시켰다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `underweighted` 의 머리글을 `uncovered` 의 것으로 바꿔도 **초록이었다** —
    #  내가 `"무게" in b` 만 봤고 그 낱말이 **문장 뒤쪽에 남아** 있었다.
    #  🔴 **주장 자체**를 가린다: 어느 쪽이 *없던* 이고 어느 쪽이 *죽는* 인가.
    assert "없던 시나리오" in a and "죽는 시나리오" not in a, a
    assert "죽는 시나리오" in b and "없던 시나리오" not in b, b
    assert "규칙 결함" in a, a
    assert "무게" in b, b


def test_v5_7_4_결과를_보고_종류를_정한다():
    """🔴 **수가 정한다** — 사람이 고르지 않는다(§6-b 와 같은 결).

    ⚠️ `covered=False` 면 *없던 시나리오가 터진* 것이다(그릴 줄도 몰랐다).
       `covered=True` 인데 그 시나리오가 **죽어 있었으면** 무게 문제다.
    """
    from app import ledgerkind
    assert ledgerkind.classify(covered=False, realized_alive=None) == "uncovered"
    assert ledgerkind.classify(covered=True,
                               realized_alive=False) == "underweighted"
    # 🔴 덮였고 **살아 있었으면** 실패가 아니다
    assert ledgerkind.classify(covered=True, realized_alive=True) is None
    # ⚠️ **못 쟀으면** `None` 이 아니라 **모른다**고 말한다(#3)
    assert ledgerkind.classify(covered=None, realized_alive=None) == "unknown"


def test_v5_7_4_원장이_그_종류를_들고_있다():
    """🔴 스키마에 칸이 있어야 한다 — 없으면 세어도 사라진다."""
    import pathlib
    import re
    sql = pathlib.Path("db/schema.sql").read_text()
    # 🔴🔴 **`ADD COLUMN` 을 본다**(돌연변이 G 가 통과했다 · 2026-10-04).
    #    ⚠️ 그 줄을 지워도 **CHECK 제약 줄에 이름이 남아** 있어 `in sql` 이
    #       통과했다. 🔴 칸을 **만드는** 문장을 겨눈다.
    for col in ("failure_kind", "cost_usd"):
        assert re.search(
            rf"ALTER TABLE ledger ADD COLUMN IF NOT EXISTS\s+{col}\b", sql), (
            f"🔴 §7-4 칸 `{col}` 을 **만드는 문장**이 없다 — 이름이 제약 줄에만 "
            f"있으면 칸은 안 생긴다")


def test_v5_7_4_채점이_그_칸을_채운다():
    """🔴🔴 **안 채우는 칸은 없는 칸이다**(배선).

    ⚠️ `ALTER TABLE` 만 하고 `INSERT` 를 안 고치면 그 칸은 영영 `NULL` 이다 —
       이 저장소가 같은 병으로 다쳤다(CLAUDE.md #2).
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    src = textwrap.dedent(inspect.getsource(analyze.score_finished))
    lits = [n.value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    sql = " ".join(lits)
    for col in ("failure_kind", "cost_usd"):
        assert col in sql, (
            f"🔴 채점이 `{col}` 를 **안 적는다** — 칸만 만들고 아무도 채우지 "
            f"않으면 그 칸은 영영 NULL 이다")
    # 🔴 그리고 **분류 함수를 부른다**(수가 정한다)
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "classify"]
    assert calls, "🔴 `ledgerkind.classify` 를 안 부른다 — 종류를 손으로 적는다"


def test_v5_7_4_비용을_원장에서_읽는다():
    """🔴 §7-4 *"비용을 원장에 적는다"* — `solar` 의 디스크 원장에서 가져온다.

    ⚠️ 비용은 **경기마다** 다르다(도구 호출 수가 다르다). 🔴 그 수를 `solar` 가
       이미 줄 단위로 적고 있다(`ledger/cost_{YYYYMM}.jsonl`) — 거기서 그 경기
       줄만 합친다. **두 번째 계수기를 만들지 않는다**(#1 사본 금지).
    """
    from app import ledgerkind
    # 🔴 **M49**(작업 지시서 §1) — 원장이 쓰는 칸은 `usd` 다. ⚠️ 종전 이 시험이
    #    `cost_usd` 를 썼고 코드도 그것을 읽어 **둘이 같이 틀렸다** — 실물
    #    원장에서는 **늘 0** 이었다(이름이 갈리면 기록이 있어도 없는 것이다).
    rows = [{"match": "g1", "usd": 0.01}, {"match": "g2", "usd": 0.5},
            {"match": "g1", "usd": 0.02}]
    assert ledgerkind.cost_of("g1", rows) == 0.03
    assert ledgerkind.cost_of("없는경기", rows) is None   # 🔴 0 이 아니다


def test_v5_7_4_적중률이_아무것도_막지_않는다():
    """🔴🔴 *"적중률은 **완벽 작동 정의에 넣지 않는다**"*(v4 그대로).

    ⚠️ 적중률로 게이트를 걸면 운이 좋은 주에 통과하고 나쁜 주에 막힌다 —
       그것은 로직이 맞았나와 **다른 것**이다.
    🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다.
    """
    import pathlib

    from tests._helpers import strip_docs
    for path in ("app/analyze.py", "app/survive.py", "app/scheduler.py"):
        body = strip_docs(pathlib.Path(path).read_text())
        for bad in ("hit_rate", "accuracy", "적중률"):
            assert bad not in body, (
                f"🔴 {path} 가 `{bad}` 를 **코드에서** 쓴다 — 적중률은 완벽 작동 "
                f"정의에 들어가지 않는다(§7-4)")


def test_v5_7_4_원장으로_규칙을_고치지_않는다():
    """🔴🔴 **사용자 지시 2026-10-02** — 그 가름이 보정의 입구가 되면 안 된다.

    > 쌓이는거는 우리 로직이 맞냐 틀렸냐만 **검증하는 방법으로만** 사용한다.

    ⚠️ §7-4 는 두 번째 종류를 *"무게 보정 대상"* 이라 불렀다. 🔴 **그 보정은
       하지 않는다** — 이름만 가른다.
    """
    import inspect

    from app import ledgerkind
    src = inspect.getsource(ledgerkind)
    # 🔴 설정·문턱을 **쓰는** 코드가 없어야 한다
    for bad in ("yaml.safe_dump", "write_text", "thresholds.set", "open("):
        assert bad not in src, (
            f"🔴 `ledgerkind` 가 `{bad}` 를 쓴다 — 원장이 규칙을 고치는 입구가 "
            f"됐다(사용자 지시 2026-10-02)")
    # ⚠️ 그리고 그 충돌이 **글자로** 남아 있어야 한다(다음 세션이 또 밟지 않게)
    assert "검증" in src and "2026-10-02" in src, (
        "🔴 §7-4 의 *무게 보정* 과 사용자 지시의 충돌이 안 적혀 있다")
