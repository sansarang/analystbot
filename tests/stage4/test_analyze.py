"""배선 계약 — **질문 한 줄 → 카드 한 장** (사용자 지시 2026-10-02 *"배선해라"*).

🔴 이 파일이 검사하는 것은 **이어졌는가**다. 블록 하나하나의 규칙은 각 블록의 계약이
   본다(`test_classify`·`test_scenarios`·`test_survive`·`test_triggers`).
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

from app import analyze, scenarios, survive
from app.bot import main as B
from app.types import Market

ROOT = Path(__file__).resolve().parents[2]


def _golden():
    spec = importlib.util.spec_from_file_location(
        "t_sc3", ROOT / "tests/stage4/test_scenarios.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    facts, st = t._collect()
    if st is None:
        pytest.skip("카세트가 없다")
    return facts, t._game()


def _board(game):
    return [Market(market_type="total", team="over", line=2.5),
            Market(market_type="total", team="under", line=2.5),
            Market(market_type="handicap", team=game.home, line=-0.5),
            Market(market_type="home"), Market(market_type="draw"),
            Market(market_type="away")]


# ══════════════════════════════════════════════════════════════════
# 사슬이 끝까지 돈다
# ══════════════════════════════════════════════════════════════════


def test_사실에서_카드까지_한_줄로_돈다():
    """🔴 §4 → §5 → §6 → §7 이 **한 호출로** 이어진다."""
    facts, game = _golden()
    card = analyze.build(facts, game, board=_board(game))
    assert card.variables and card.hypotheses
    assert card.scenarios and card.scenarios.drafts
    assert card.survival and card.survival.rows
    assert card.triggers is not None
    # 🔴 **세 갈래를 따로** 들고 있다(§4) — 섞으면 고칠 곳을 못 찾는다
    assert card.background and isinstance(card.undecided, list)
    assert not (set(map(id, card.variables)) & set(map(id, card.background)))


def test_카드가_블록_열_개를_순서대로_낸다():
    """🔴 **순서가 규격이다**(`docs/fable/output_spec.md`)."""
    facts, game = _golden()
    txt = analyze.render(analyze.build(facts, game, board=_board(game)))
    heads = ["1 자료 한계", "2 기준 XI", "3 폼", "4 뒤집는 변수",
             "5 가설", "6 시나리오", "7 보드 대입", "8 결론", "9 방향 판정",
             "10 방아쇠"]
    at = [txt.find(f"■ {h}") for h in heads]
    assert all(i >= 0 for i in at), dict(zip(heads, at))
    assert at == sorted(at), "블록 순서가 어긋났다"


def test_조립을_시험이_아니라_app_이_한다():
    """🔴 **이 계약이 전에 깨져 있던 것을 잠근다.**

    §5-c 가 쓰는 보조 신호(맞대결 창·최근 평균)를 **시험 파일이** 조립하고 있었다 —
    그러면 운영은 그 조립을 안 하고, 시험만 초록인 자리가 된다.
    """
    st = analyze.context(_golden()[0])
    for key in ("league_avg_goals", "venue_averages", "h2h_window_avg_goals",
                "h2h_window_games", "recent_avg_goals"):
        assert key in st, f"{key} 가 조립되지 않았다"
    # 🔴 격자도 `app` 이 만든다
    facts, game = _golden()
    assert analyze.grid(st, game) is not None
    assert analyze.grid({}, game) is None
    # 🔴🔴 **그리고 카드가 그것을 실제로 썼는지 본다.** 전 판은 `context()` 를
    #    직접 불러 보기만 했고, `build()` 안에서 `st = {}` 로 바꾸는 돌연변이가
    #    **통과했다**. 쓴 흔적은 셋이다:
    card = analyze.build(facts, game, board=_board(game))
    #   ① 폼 블록의 리그 줄은 순위표 사실에서만 나온다
    assert "리그" in card.form and card.form["리그"].get("평균 총득점")
    #   ② 무게가 확률이다 — 격자는 `venue_averages` 가 있어야 선다
    assert all(d.probability is not None for d in card.scenarios.drafts)
    #   ③ 난타전(§5-c-1 ②)은 포아송이 서야 발동한다
    #      ⚠️ **템플릿 이름으로 보지 않는다**(2026-10-05 에 고쳤다) — 지시 ③
    #         이후 카드 시나리오는 **DeepSeek 것**이고 템플릿은 *코드 필수형
    #         보강일 때만* 남는다. 🔴 `soccer_open` 이 없는 것은 결함이 아니라
    #         **그 지시의 결과**다. 그래서 **효과**를 본다: 격자가 섰고(위 ②)
    #         난타전이 **덮였나**(합계 4골+ 스코어가 있나 · 지시 ④).
    sums = [sum(int(n) for n in sc.split("-"))
            for d in card.scenarios.drafts for sc in d.scores]
    assert any(n >= 4 for n in sums), (
        f"🔴 난타전이 안 덮였다 — 합계 {sums}. 템플릿이든 DeepSeek 이든 "
        f"합계 4골+ 가 하나는 있어야 `언더` 가 공짜 1.0 을 안 받는다(§6-7)")


def test_자료_한계_블록이_비지_않는다():
    """🔴 블록 1 이 비면 **그것이 거짓이다** — 못 잰 칸은 언제나 있다.

    모으는 곳: 미결정 · 세포 사유 · §5 기록 · §6 경고 · **세포 없는 §4 유형**.
    """
    facts, game = _golden()
    card = analyze.build(facts, game, board=_board(game),
                         states={"x:intent": "unknown — 자료가 없다"})
    assert card.limits
    assert any("세포가 없는" in x for x in card.limits), card.limits
    assert any("x:intent" in x for x in card.limits), card.limits


def test_세포_없는_유형_목록이_코드와_같다():
    """🔴 **배선이 찾은 결함이다.** yaml 의 `implemented` 가 전부 `false` 로 낡아
    있어서 `rules.unimplemented_types()` 가 **열네 개를 다 미구현으로** 냈다.

    그 목록이 카드 블록 1 에 그대로 올라가면 *"recent_pattern 은 세포가 없다"* 는
    **거짓**을 적는다. 🔴 코드가 원본이고 yaml 은 선언이다 — 둘을 대조한다.
    """
    from app import classify, rules
    assert rules.unimplemented_types() == sorted(classify.NOT_CLASSIFIED)
    # 🔴 구현한 것이 미구현 목록에 섞여 있지 않나
    assert not (set(classify.DIRECTION_OF) & set(rules.unimplemented_types()))


def test_살아남는_마켓이_없으면_그_말만_적는다():
    """🔴 §6-b · §6-e — *"카드엔 '살아남는 마켓 없음'만"*.

    ⚠️ 이름을 적으면 09-28 아르메니아(생존 0.7 인데 이름) 를 되풀이한다.
    """
    facts, game = _golden()
    card = analyze.build(facts, game, board=_board(game))
    txt = analyze.render(card)
    named = [r for r in card.survival.rows if r["verdict"] in ("name", "small")]
    if named:
        pytest.skip("이 경기는 살아남는 마켓이 있다")
    body = txt.split("■ 8 결론")[1].split("■ 9")[0]
    assert "살아남는 마켓 없음" in body
    for r in card.survival.rows:
        assert f"낸다: {r['name']}" not in body
        assert f"소액: {r['name']}" not in body


def test_카드에_배당이_들어올_칸이_없다():
    """🔴 §6-c-5 · §7 R8 — 배당 숫자는 파싱에서 버린다."""
    facts, game = _golden()
    txt = analyze.render(analyze.build(facts, game, board=_board(game)))
    assert "배당" not in txt
    assert not ({"price", "odds", "배당"} & set(Market.model_fields))
    # 🔴 카드를 만드는 코드가 가격 낱말을 아예 안 쓴다
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze))
    for bad in ("odds", "price"):
        assert bad not in src, f"카드 코드에 {bad} 가 있다"


# ══════════════════════════════════════════════════════════════════
# DB 적재 — 🔴 표와 코드가 **같은 어휘**를 쓰나
# ══════════════════════════════════════════════════════════════════


def _columns(table: str) -> set[str]:
    """`db/schema.sql` 에서 그 표의 칸 이름. 🔴 **스키마가 원본이다**."""
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);",
                  sql, re.S)
    assert m, table
    out = set()
    # 🔴 **마이그레이션으로 더한 칸도 센다** — `ALTER TABLE … ADD COLUMN`.
    #    ⚠️ CREATE 블록만 보면 `dateless_reason`(#7 마이그레이션)을 놓친다.
    for m2 in re.finditer(
            rf"ALTER TABLE {table} ADD COLUMN(?: IF NOT EXISTS)? (\w+)", sql):
        out.add(m2.group(1))
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("--", "CONSTRAINT", "UNIQUE", "PRIMARY",
                                    "FOREIGN", "CHECK")):
            continue
        out.add(ln.split()[0])
    return out


def test_적재_SQL_의_칸이_스키마에_다_있다():
    """🔴 **배선이 찾은 결함이다.** 코드가 `var_type`·`claim` 을 적고 표는
    `type`·`text` 였다 — 적재가 터진다. 어휘가 갈리면 여기서 빨개진다.
    """
    src = inspect.getsource(analyze.persist)
    for table in ("variables", "background", "sufficiency", "scenarios",
                  "board", "survival"):
        m = re.search(rf"INSERT INTO {table} \(([^)]*)\)", src)
        assert m, f"{table} 적재가 없다"
        named = {c.strip().strip('"') for c in
                 m.group(1).replace('"', " ").split(",") if c.strip()}
        named = {c for c in named if c and c.isidentifier()}
        missing = sorted(named - _columns(table))
        assert not missing, f"{table} 에 없는 칸 {missing}"


def test_무게를_numeric_으로_깎아_넣는다():
    """🔴 실측 2026-10-02: 파이썬 float `0.4` → NUMERIC `0.40000000000000002…`
    가 되어 `variables_weight_ck`(`weight = 0.4`)가 **거부했다.**

    ⚠️ 배선 전에는 적재하는 코드가 없어 아무도 몰랐다 — 스키마와 코드가 같은 수를
       다르게 보던 자리다.
    """
    src = inspect.getsource(analyze.persist)
    m = re.search(r"INSERT INTO variables.*?VALUES \(([^)]*)\)", src, re.S)
    assert m and "::numeric" in m.group(1), m.group(1) if m else "없다"


def test_적재가_멱등이다():
    """🔴 같은 경기를 다시 분석해도 줄이 겹치지 않는다 — `ON CONFLICT` 가 있나."""
    src = inspect.getsource(analyze.persist)
    for table in ("variables", "background", "sufficiency", "scenarios",
                  "board", "survival"):
        chunk = src.split(f"INSERT INTO {table}")[1][:600]
        assert "ON CONFLICT" in chunk, f"{table} 적재가 멱등이 아니다"


def test_자료_부족이면_시나리오를_적지_않는다():
    """🔴 §7 R5 — 부족이면 `sufficiency` 만 적고 멈춘다(지어내 채우지 않는다)."""
    src = inspect.getsource(analyze.persist)
    at_suff = src.index("INSERT INTO sufficiency")
    at_scen = src.index("INSERT INTO scenarios")
    at_stop = src.index("if card.insufficient:")
    assert at_suff < at_stop < at_scen, "부족 판정이 시나리오 적재를 못 막는다"


# ══════════════════════════════════════════════════════════════════
# 봇까지 이어졌나
# ══════════════════════════════════════════════════════════════════


def test_봇이_분석을_부른다():
    """🔴 ★ 명령이 사슬을 **부르지** 않으면 사용자에게 아무것도 안 간다.

    ⚠️ 문자열로 보면 안 된다 — `import` 줄만 있어도 참이 된다(실측 2026-09-30 에
       그 절제가 통과했다). **부르는 자리**를 본다.
    """
    tree = ast.parse(inspect.getsource(B))
    # 🔴 **`m.answer(...)` 와 가려야 한다.** 전 판은 `attr == "answer"` 만 봤고,
    #    아이오그램의 답장도 `answer` 라서 **호출을 지운 돌연변이가 통과했다.**
    #    받는 쪽(`A`)까지 본다.
    hit = [n for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == "answer"
           and isinstance(n.func.value, ast.Name)
           and n.func.value.id == "A"]
    assert hit, "봇이 `analyze.answer` 를 **부르지** 않는다"


def test_경기가_여럿이면_고르지_않는다():
    """🔴 §17-g-3 · M14 — **남의 경기를 분석하면 그 카드는 통째로 거짓이다.**

    ⚠️ 2단계(2026-10-03)로 그 판단이 **입구**(`resolve.match_of`)로 옮겨졌다 —
       이름 해석이 한 곳이어야 한다는 설계 때문이다. 🔴 **묻는 것은 그대로**다:
       여럿이면 고르지 않고, 그 사실이 사용자에게 보인다.
    """
    from app import resolve
    from app.matchref import Reason
    src = inspect.getsource(resolve.match_of)
    assert "len(found.games) > 1" in src
    assert "고르는 것은 사용자 몫" in src
    # 🔴 **실패한 조건이 사유를 정한다** — 사람이 문장을 짓지 않는다
    assert "Reason.AMBIGUOUS" in src
    # 🔴 그리고 그 사유가 **사용자 말**로 나온다(4단계: 표가 하나다)
    from app.matchref import say
    assert "하나를 지목해라" in say(Reason.AMBIGUOUS)
    assert Reason.AMBIGUOUS.fixable_by_asking_again
    # ⚠️ `answer` 는 **문장을 짓지 않는다** — 표에서 꺼낸다
    out = inspect.getsource(analyze.answer)
    assert "say(look.reason" in out


def test_발송은_스위치_뒤에만_있다():
    """🔴 §11-11 — 발송 스위치는 단계 9 전까지 off.

    ⚠️ 전 판 계약은 *"분석 코드에 `tg.send` 가 없어야 한다"* 였다. 사용자 지시
       2026-10-02(*"배선 안 된 것도 마무리 지어라 … 사유만 남기고 나중에 하지 않으면
       안 하는 이보다 못하다"*)로 **길을 이었다.**
    🔴 그래서 계약도 바뀐다 — 묻는 것은 *"있나"* 가 아니라 **"스위치 뒤인가"** 다.
    """
    from tests._helpers import strip_docs

    # 🔴 ① 카드를 **만드는** 함수들은 발송을 모른다
    for fn in (analyze.build, analyze.render, analyze.persist, analyze.answer):
        src = strip_docs(inspect.getsource(fn))
        assert "tg." not in src, f"{fn.__name__} 이 발송을 안다"

    # 🔴 ② 보내는 함수는 **스위치를 먼저 본다**
    src = strip_docs(inspect.getsource(analyze.deliver))
    at_switch = src.index("send_enabled")
    at_send = src.index("tg.send(")
    assert at_switch < at_send, "스위치를 보기 전에 보낸다"
    # 🔴 ③ 꺼져 있으면 **그 자리에서 돌아간다**
    assert "return" in src[at_switch:at_send], "스위치가 꺼져도 아래로 내려간다"
    # 🔴 ④ 왜 안 보냈는지 **돌려준다**(조용히 안 보내면 그것이 가장 나쁘다)
    assert '"why"' in src and '"sent"' in src

    # 🔴 ⑤ **주기가 아니라 1회성**에서만 부른다
    from app import scheduler as S
    loop_src = strip_docs(inspect.getsource(S.main))
    assert "deliver" not in loop_src, "상시 루프가 카드를 보낸다"
    cli_src = strip_docs(inspect.getsource(S._cli))
    assert "deliver" in cli_src, "1회성 입구가 없다"


def test_스위치가_꺼져_있으면_안_보낸다():
    """🔴 **코드를 읽는 것으로 끝내지 않는다** — 실제로 돌려 본다."""
    import asyncio

    spec = importlib.util.spec_from_file_location(
        "t_sc5", ROOT / "tests/stage4/test_scenarios.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)

    from app.config import get_settings
    if get_settings().send_enabled:
        pytest.skip("🔴 발송 스위치가 켜져 있다 — 이 시험은 꺼진 상태를 본다")

    sent: list = []

    class _Pool:
        async def fetch(self, *a, **k):
            return []

    async def _go():
        import app.tg as tg
        orig = tg.send

        async def _spy(text, **k):
            sent.append(text)
            return True

        tg.send = _spy                              # type: ignore[assignment]
        try:
            return await analyze.deliver(_Pool(), team="없는팀")
        finally:
            tg.send = orig                          # type: ignore[assignment]

    got = asyncio.run(_go())
    assert got["sent"] is False, got
    assert "SEND_ENABLED" in got["why"], got
    assert sent == [], "스위치가 꺼졌는데 발송 함수가 불렸다"


def test_판정이_수집기를_고치지_않는다():
    """🔴 `test_수집이_판정하지_않는다` 의 짝 — 반대 방향도 잠근다.

    분석은 세포를 직접 부른다. `app/collect/` 를 수정해 판정을 끼워 넣으면
    수집과 판정이 한 덩어리가 되고, 그러면 수집만 돌릴 수 없다.
    """
    # 🔴 **문자열로 보지 않는다** — 이 저장소가 두 번 속은 자리다(import 줄만
    #    있어도 참이 된다). **부르는 자리**를 AST 로 본다.
    #    ⚠️ 어댑터 표(`ADAPTERS`)를 **읽는 것**은 수집을 고치는 것이 아니다 —
    #       깊이 소스가 어느 어댑터에 있는지 알아야 하고, 그 표가 원본이다.
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.id if isinstance(n.func, ast.Name)
              else getattr(n.func, "attr", "")
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for bad in ("collect", "_game_cells", "_slate", "_absences"):
        assert bad not in called, f"분석이 수집 함수 `{bad}` 를 부른다"
    # 🔴 판정 함수들은 분석이 부른다
    assert {"classify_facts", "generate", "build"} <= called | {"build"}


def test_카드가_LLM_을_부르지_않는다():
    """🔴 §17-c — `direction`·`weight`·`strength`·`survival`·`verdict` 에 LLM 금지.

    서술(§5-e L6)은 아직 미배선이고, 그 빈칸을 **글로 메우지 않는다.**
    """
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **D46 — 부르는 것과 사유 이름은 다르다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `Reason.LLM_UNAVAILABLE`(§8-6 사유 코드)이 이 검사에 걸렸다. 🔴 그것은
    #     *"LLM 을 못 불렀다"* 는 **사유 이름**이고 **부르는 것이 아니다.**
    #  🔴 그래서 **호출 꼴**만 본다: `llm.<무엇>(` · `ollama` · `qwen`.
    #     ⚠️ 판정 필드(`direction`·`weight`·`strength`·`survival`·`verdict`)에
    #        LLM 이 닿지 않는다는 금지는 그대로다(§17-c).
    import re as _re
    low = src.lower()
    for bad in (r"\bllm\.\w+\(", r"\bfrom app import llm\b",
                r"\bimport llm\b", "ollama", "qwen"):
        assert not _re.search(bad, low), f"분석이 {bad} 를 부른다"
    # 🔴 §3 에이전트는 **`agentloop` 를 거쳐서만** 닿는다(직접 통로 금지)
    assert "solar.chat(" not in low, "분석이 Solar 를 직접 부른다(§3 을 거쳐라)"
    for d in analyze.build(*_golden()[::1], board=None).scenarios.drafts:
        assert d.to_scenario().narrative == ""


def test_블록_1_이_읽을_수_있다():
    """🔴 **라이브가 찾은 결함이다**(실측 2026-10-02 NPB).

    한 세포의 사유가 **3천 자 한 덩어리**로 나와 블록 1 을 읽을 수 없었다 — 열기
    20건의 사유를 그대로 이어 붙였기 때문이다.
    ⚠️ 그런데 **지울 수는 없다**(조용한 0 금지). 줄이고 **몇 자를 줄였는지 적는다.**
    """
    long = "ㄱ" * 3000
    folded = analyze._fold(long)
    assert len(folded) < 300, len(folded)
    assert "자 더" in folded and "로그" in folded, folded
    # 🔴 짧은 줄은 **건드리지 않는다**
    assert analyze._fold("짧다") == "짧다"
    # 🔴 같은 말은 **묶어 센다** — 지우는 것이 아니다
    assert analyze._tally(["a", "a", "b"]) == ["a ×2", "b"]

    facts, game = _golden()
    card = analyze.build(facts, game, board=_board(game),
                         # ⚠️ 라이브에서 온 꼴 그대로 — `unknown` 뒤에 사유가 길게 붙는다
                         states={"x:lineup": "unknown — 검색 " + long})
    assert all(len(x) < 300 for x in card.limits), \
        [len(x) for x in card.limits if len(x) >= 300]
    # 🔴 그래도 그 세포가 **멈췄다는 사실은 남는다**
    assert any("x:lineup" in x for x in card.limits), card.limits


def test_같은_미결정을_두_줄로_내지_않는다():
    """🔴 라이브 실측: *"플레이오프 경계를 모른다"* 가 양 팀으로 두 번 나왔다.

    같은 사유를 두 줄로 내면 블록이 길어지기만 하고 뜻이 늘지 않는다 — `×N` 으로 센다.
    """
    facts, game = _golden()
    card = analyze.build(facts, game, board=_board(game))
    plain = [x.split(" ×")[0] for x in card.limits]
    assert len(plain) == len(set(plain)), \
        [x for x in plain if plain.count(x) > 1]


def test_미배선_목록이_비었다():
    """🔴🔴 **사용자 지시 2026-10-02**:

    > 배선 안 된 거도 마무리 지어라 … 사유를 남기는 거는 좋지만 … **사유만 남기고
    > 나중에 하지 않으면 안 하는 이보다 못하다**

    🔴 이 계약은 목록이 **다시 자라는 것**을 막는다. 새로 미배선을 넣으려면 여기서
       먼저 빨개지고, 그때 *"왜 지금 안 잇나"* 를 적게 된다.
    """
    import re as _re

    src = (ROOT / "tests" / "test_wiring.py").read_text(encoding="utf-8")
    # 🔴 함수 목록 — `"app.…": "사유"` 꼴이 **하나도 없어야** 한다
    fns = _re.findall(r'^\s+"app\.[a-z_0-9.]+":', src, _re.M)
    assert fns == [], f"미배선 함수가 남았다: {fns}"
    # 🔴 표 목록 — 빈 집합이어야 한다
    assert "NOT_WIRED: set[str] = set()" in src, "미배선 표 목록이 비지 않았다"


def test_폼과_전제를_표에_적는다():
    """🔴 카드가 들고 있던 것을 **표에도** 적는다(미배선 마무리).

    ⚠️ `midweek` 는 **못 세서 `None`** 이다 — 0 으로 때우면 "주중 경기가 아니다"라는
       거짓이 된다. `premise_check` 는 `kept` 만 적힌다 — `replaced` 는 **반대 검색**이
       있어야 쓸 수 있고 그것은 아직 없다. 🔴 그 사실이 코드에 적혀 있어야 한다.
    """
    src = inspect.getsource(analyze.persist)
    assert "INSERT INTO team_form" in src and "INSERT INTO premise_check" in src
    assert "midweek" in src
    # 🔴 못 센 칸을 0 으로 때우지 않는다
    at = src.index("INSERT INTO team_form")
    chunk = src[at:at + 900]
    assert "None," in chunk, "못 센 칸을 0 으로 채웠는지 보라"
    # 🔴 `replaced` 를 쓸 수 없는 까닭이 적혀 있다
    assert "반대 검색" in src
    # 🔴 전제는 §4 `is_premise` 가 정한다 — 손으로 고르지 않는다
    assert "is_premise" in src


def test_사용자_말로_경기를_찾는다():
    """🔴 `다저스` 로 물어도 찾는다(별칭 배선). ⚠️ 바꿔서 못 찾으면 **원문으로 한 번 더** —
    별칭이 틀릴 수 있다."""
    from app.bot import aliases

    assert aliases.find_team("다저스 경기 분석해줘")[1] == "Los Angeles Dodgers"
    # 🔴 퍼지 경로가 **삭제된 모듈**을 부르고 있었다(실측 2026-10-02) — 고쳤다
    assert aliases.kr_team("Doosan Bears") == "두산 베어스"
    assert aliases.team_tokens("Manchester United") == frozenset({"manchester"})
    # ⚠️ 모르는 팀은 **원문 그대로** — 지어내지 않는다
    assert aliases.kr_team("없는팀 FC") == "없는팀 FC"
    # ⚠️ 2단계(2026-10-03)로 이름 해석이 **입구**로 옮겨졌다. 🔴 묻는 것은 그대로:
    #    표준 표기로 찾고, 못 찾으면 **원문으로 한 번 더** 본다(바꾼 것이 틀릴 수 있다).
    from app import resolve
    src = inspect.getsource(resolve.match_of)
    assert "canon(" in src and "원문으로" in src
    # 🔴 그리고 그 표준화는 **이름표**(1단계)가 한다 — 별칭표만 보지 않는다
    assert "teamref.key_of" in inspect.getsource(resolve.canon)


def test_카탈로그_템플릿없음을_한_줄로_묶는다():
    """🔴🔴 **라이브가 만든 계약이다**(2026-10-02 소프트뱅크–치바롯데).

    유형 14종 × 팀 2 = **28줄**이 블록 1 에 쏟아졌고 전부 같은 말이었다. 그것은
    **카탈로그의 성질**이고 이 경기에 대해 아무것도 말하지 않는다.
    ⚠️ 지우는 것이 아니라 **묶어 센다** — 조용한 0 금지는 *"세라"* 는 뜻이지
       *"스물여덟 줄로 적어라"* 는 뜻이 아니다.
    """
    src = inspect.getsource(analyze.gather)
    assert "템플릿없음" in src and "템플릿이 없는 유형" in src
    # 🔴 묶은 줄에 **몇 종인지와 이름**이 들어간다(수만 세면 어느 유형인지 사라진다)
    #    ⚠️ 같은 낱말이 위쪽 **주석**에도 있다 — 코드의 표식(`템플릿없음`)으로 찾는다
    at = src.index("템플릿없음")
    chunk = src[at:at + 260]
    assert "len(no_tpl)" in chunk and "sorted(set(no_tpl))" in chunk
    # 🔴 그 밖의 사유는 **그대로** 남는다(자리표 못 채움 등)
    assert 'if "템플릿이 없다" in why:' in src and "continue" in src
