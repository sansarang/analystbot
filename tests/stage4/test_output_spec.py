"""출력 규격 계약 — **규격 ↔ 카드**가 어긋나지 않게.

사용자 지시 2026-10-01:

> 경기에 대해 예측해줘 했을 때 봇이 알아서 … 해서 나한테 **결과만 이런 식으로**
> 대답하는 거야

🔴 그 "이런 식"이 `docs/fable/output_spec.md` 의 **블록 열 개**다.

## 🔴 2026-10-02 — **견주는 대상을 바꿨다**

전 판은 규격을 **정답지**(`golden_v4.yaml`)와 견줬다. 사용자 지시로 그 파일을 지웠다:

> 정답지는 없다... 정답은 없는거다... 명심해라... 정답지는 지운다...
> 데이타가 쌓이고 그럼 그거가지고 분석을 하고... 스포츠는 정답이 없는거다...

그래서 이제 규격을 **카드 렌더러**와 견준다 — *내가 전에 쓴 분석*이 아니라 **봇이
실제로 내는 글**이다. ⚠️ 그 편이 애초에 맞았다: 규격이 묻는 것은 *"봇이 그 블록을
내는가"* 이고, 내 옛 글이 그 블록을 들고 있는지는 **아무 것도 증명하지 않는다.**
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from app import analyze
from app.types import Market

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "fable" / "output_spec.md"

#: 규격 블록 → **카드 글의 제목**. 🔴 이 대응만 손으로 적는다 — 블록 이름은 규격이
#  정하고(아래 파서), 빠진 블록은 계약이 찾아낸다.
WHERE = {
    "자료 한계 고백": "1 자료 한계",
    "기준 XI": "2 기준 XI",
    "폼": "3 폼",
    "뒤집는 변수": "4 뒤집는 변수",
    "팀별 가설 + 무너지는 조건": "5 가설",
    "시나리오 A~E": "6 시나리오",
    "보드 대입": "7 보드 대입",
    "결론": "8 결론",
    "방향 판정": "9 방향 판정",
    "방아쇠 ①~④": "10 방아쇠",
}


def _spec_blocks() -> list[str]:
    """🔴 규격 표에서 블록 이름을 **읽는다** — 베끼지 않는다."""
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*\*\*(.+?)\*\*[^|]*\|",
                      SPEC.read_text(encoding="utf-8"), re.M)
    got = [name.strip() for _, name in rows]
    assert len(got) >= 10, (
        f"규격에서 블록을 {len(got)}개만 읽었다 — 정규식을 보라 ({got})")
    return got


def _card_text() -> str:
    spec = importlib.util.spec_from_file_location(
        "t_sc4", ROOT / "tests/stage4/test_scenarios.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    facts, st = t._collect()
    if st is None:
        pytest.skip("카세트가 없다")
    game = t._game()
    board = [Market(market_type="home"), Market(market_type="draw"),
             Market(market_type="away"),
             Market(market_type="total", team="over", line=2.5),
             Market(market_type="handicap", team=game.home, line=-0.5)]
    return analyze.render(analyze.build(facts, game, board=board))


def test_규격_블록이_전부_대응표에_있다():
    """🔴 규격에 블록이 늘면 **여기가 먼저 빨개진다.**"""
    missing = [b for b in _spec_blocks() if b not in WHERE]
    assert missing == [], (
        f"규격에 생긴 블록이 대응표에 없다: {missing} — 카드 어디에 내는지 적어라")
    stale = [b for b in WHERE if b not in _spec_blocks()]
    assert stale == [], f"규격에서 사라진 블록이 대응표에 남았다: {stale}"


def test_카드가_규격의_블록을_전부_낸다():
    """🔴 **이것이 정답지를 대신한다.** 규격이 요구한 블록을 봇이 내는지 본다.

    ⚠️ *"내용이 맞나"* 는 묻지 않는다 — **스포츠에 정답이 없다**(사용자 지시). 맞았나는
       경기가 끝난 뒤 `ledger` 가 **실제 결과로** 센다.
    """
    text = _card_text()
    missing = [f"{b} → ■ {WHERE[b]}" for b in _spec_blocks()
               if f"■ {WHERE[b]}" not in text]
    assert missing == [], f"카드가 안 내는 블록: {missing}"


def test_블록_순서가_규격_순서다():
    """🔴 순서가 규격이다 — 결론이 시나리오보다 먼저 나오면 읽는 사람이 속는다."""
    text = _card_text()
    at = [text.index(f"■ {WHERE[b]}") for b in _spec_blocks()]
    assert at == sorted(at), dict(zip(_spec_blocks(), at))


def test_결론에_배당_숫자가_없다():
    """🔴 §6-c-5 · §7 R8 — 배당 숫자는 파싱에서 버린다. 결론 문장에 0건."""
    body = _card_text().split("■ 8 결론")[1].split("■ 9")[0]
    assert "배당" not in body
    # 🔴 생존·확률은 숫자가 맞다 — 가격이 아니다. 가격 낱말이 없는지로 본다
    for bad in ("odds", "price", "배당률"):
        assert bad not in body


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **D — 사람이 읽을 수 있게** (사용자 지적 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# 종전 카드의 변수 줄 다섯이 `(칸 없음)` 이었다 — 질문 id 와 빈칸뿐이라 **무슨
# 사실인지 사람이 모른다.** 그런데 판정 사유에는 그 내용이 이미 들어 있었다.


def test_변수_줄이_판정_사유를_적는다():
    """🔴 `text` 가 `(칸 없음)` 이어도 `why` 에는 내용이 있다 — 그것을 적는다.

    ══════════════════════════════════════════════════════════════
    🔴 **글자 검사를 행동 검사로** (2026-10-05)
    ══════════════════════════════════════════════════════════════

    ⚠️ 종전엔 `render` 소스에 `c.why` 라는 **글자**가 있나만 봤다. 🔴 그 줄이
       `analyze.var_line` 으로 옮겨가자 빨개졌다 — **옮긴 것은 결함이 아니다.**
    🔴 그래서 **낸 글**을 본다: 사유가 실제로 줄에 들어오나.
    """
    import datetime as dt

    from app import analyze, classify
    c = classify.Classified(
        text="", source_url="https://x/a", type="absence",
        direction="home", hardness="soft", team="Portugal",
        why="§3 에이전트 + §5 검증층 통과 · 등급 `local`(무게 1)",
        published_at=dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc))
    got = analyze.var_line(c)
    assert "등급" in got and "§" in got, (
        f"🔴 변수 줄이 판정 사유를 **안 적는다**: {got}")
    # 🔴 그리고 **사실이 있으면 그것이 먼저**다(독자가 읽는 것)
    c2 = classify.Classified(
        text="호날두가 징계로 빠진다", source_url="https://x/a",
        type="absence", direction="home", hardness="soft", team="Portugal",
        why="§3 에이전트 · 등급 `local`",
        published_at=c.published_at)
    said = analyze.var_line(c2)
    assert said.index("호날두") < said.index("등급"), said
    # 🔴 출처도 적는다 — 되짚을 수 있어야 한다. ⚠️ 그 줄은 **카드**가 낸다
    #    (`var_line` 다음 줄의 `↳ URL`) — 그래서 `render` 를 본다.
    import inspect

    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze.render))
    assert "source_url" in body, "변수 줄이 출처를 안 적는다"


def test_시나리오_줄이_어느_변수에서_왔나를_적는다():
    """🔴 사용자 분석은 *"B … (R1·R2·R6·R8) → 0-1 / 1-1"* 꼴이다.

    ⚠️ 문장을 지어내지 않는다 — §5-e 는 그 일을 LLM L6 에 뒀고 아직 안 이었다.
       여기서 하는 것은 **`Draft` 가 들고 있는 것을 보이는 것**뿐이다.
    """
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.render))
    assert "d.variables" in src and "d.why" in src, src[:200]


def test_가설_블록이_어느_변수인지_적는다():
    """🔴 사용자 분석의 가설 블록이 *"무너지는 조건: R1·R2·R3"* 꼴이다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.render))
    assert "h.supports" in src and "h.breaks" in src


def test_렌더러가_표시_없이_자르지_않는다():
    """🔴🔴 #3 조용한 0 금지 — **자르면 잘렸다고 적는다**(실측 2026-10-03).

    블록 4 가 `why[:150]` 으로 날것으로 잘랐고 그 줄이 이렇게 끝났다:

    ```
    … → hardness hard→likely(§4 sampl
    ```
    ⚠️ 읽는 사람은 그것이 사유의 **전부인지 잘린 것인지** 알 수 없다. 🔴 같은 일을
       하는 `_fold` 가 이미 *"그리고 N자 더"* 를 붙이고 있었다 — 이 자리만 빠졌다.

    🔴 **주소는 아예 자르지 않는다** — 잘린 주소는 열리지 않으므로 *"되짚을 수
       있어야 한다"* 는 그 줄의 목적이 사라진다.
    """
    import ast

    from app import analyze
    src = Path(analyze.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        # `x[:N]` 꼴 — 상한이 상수인 슬라이스
        if not isinstance(node, ast.Subscript) or \
                not isinstance(node.slice, ast.Slice):
            continue
        up = node.slice.upper
        if node.slice.lower is not None or not isinstance(up, ast.Constant) \
                or not isinstance(up.value, int):
            continue
        name = ast.unparse(node.value)
        # ⚠️ 목록 자르기(`rows[:4]`)는 다른 것이다 — **글** 을 자르는 자리만 본다
        if name.split(".")[-1].split("(")[0] not in (
                "why", "text", "src", "one", "body", "snippet"):
            continue
        bad.append(f"analyze.py:{node.lineno} — {ast.unparse(node)}")
    assert not bad, (
        "🔴 글을 표시 없이 잘랐다 — `_clip`(또는 `_fold`)을 쓴다:\n  "
        + "\n  ".join(bad))
    # 🔴 `_clip` 이 **실제로 표시를 붙이는지** 본다(이름만 맞으면 뜻이 없다)
    assert "…" in analyze._clip("가" * 50, 10)
    assert analyze._clip("가" * 5, 10) == "가" * 5


def test_방아쇠가_확인_시각을_시계로_적는다():
    """🔴🔴 **분석 과정 10단계** — *"확인 항목 첨부"*(사용자 지시 2026-10-03).

    사용자 글: **`방아쇠 (KST 10:00 XI)`** — 시계 시각이 박혀 있다.
    ⚠️ 봇은 `T-70분` 만 적었다. 그것은 *"언제 보라"* 는 말이 아니다 — 받는 사람이
       머리로 킥오프에서 빼야 하고, 거기서 틀리면 **확인 자체를 놓친다**.
    🔴 킥오프를 모르면 상대 시각만 적는다(지어내지 않는다).
    """
    from datetime import datetime, timezone

    from app import triggers
    kick = datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)   # = 11:00 KST
    got = triggers.when_of("recent_pattern", kick)
    # 🔴 T-70분 → 09:50 KST. **변환을 거쳐야** 한다(절대규칙 2)
    assert got.startswith("10-03 09:50 KST"), got
    assert "T-70분" in got, "상대 시각도 함께 남아야 한다 — 둘은 쓰임이 다르다"
    # ⚠️ 킥오프를 모르면 **시계 시각을 짓지 않는다**
    assert "KST" not in triggers.when_of("recent_pattern")
