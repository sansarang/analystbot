"""🔴🔴 **§5 — 재정렬 2단**(지시서 2026-10-05 딥서치 재구축).

> 모델 — `BAAI/bge-reranker-v2-m3`(다국어 크로스인코더: 영·한·일·스페인어 전부).
> **모듈 전역 싱글턴**으로 한 번만 로드한다(하위 8개가 공유).
>
> 폴백 사다리(M62) — ① `bge-reranker-v2-m3` → ② FlashRank
> `ms-marco-MultiBERT-L-12`(다국어) → ③ **재정렬 없음**(현재 순서 그대로) +
> `rerank_unavailable` 로그. **어느 단계에서도 분석은 멈추지 않는다.**
>
> **1단 — 받기 전**: 기존 필터 순서 유지(도메인 등급 → 신원 선필터 → 날짜 힌트)
> → **그 생존자들만 재정렬** → 상위에서 fetch 상한(하위당 2)까지 받는다.
> 🔴 재정렬은 **순서만** 바꾼다 — fetch 수를 늘리지 않고, 필터를 통과 못 한
> 결과를 되살리지 않는다.
>
> **2단 — 본문 문단**: BM25 상위 20 → reranker 로 재점수 → **상위 8 문단만**
> 하위 에이전트 프롬프트에 넣는다.

⚠️ **라이브 모델에 기대는 계약은 금지**다(기존 규칙) — 그래서 이 파일은
   ① 사다리가 **끝까지 도는지** ② `fetch` 수가 **안 늘는지** ③ 고정물에서
   **동의어를 잡는지**를 본다. 모델이 없으면 ③단으로 가고 그래도 초록이다.
"""
from __future__ import annotations

import pytest

import ast
import inspect


def _hits(n: int = 5) -> list[dict]:
    return [{"title": f"t{i}", "snippet": f"s{i}", "url": f"https://a{i}.com/x"}
            for i in range(n)]


# ══════════════════════════════════════════════════════════════════
# M62 — 폴백 사다리: 어느 단계에서도 **분석이 멈추지 않는다**
# ══════════════════════════════════════════════════════════════════
def test_M62_사다리가_셋이고_순서가_적혀_있다():
    from app.research import rerank
    assert hasattr(rerank, "LADDER"), "🔴 `rerank.LADDER` 가 없다"
    assert [x["name"] for x in rerank.LADDER] == [
        "bge-reranker-v2-m3", "flashrank-multibert", "none"], rerank.LADDER
    # 🔴 **다국어 모델명을 명시로 박는다** — FlashRank 기본(MiniLM)은 영어 전용
    said = " ".join(str(x.get("model") or "") for x in rerank.LADDER)
    assert "BAAI/bge-reranker-v2-m3" in said, said
    assert "MultiBERT" in said, (
        "🔴 FlashRank 다국어 모델명이 없다 — 기본 MiniLM 은 영어 전용이다")
    assert "MiniLM" not in said, "🔴 영어 전용 모델이 사다리에 있다"


def test_M62_모델이_없어도_순서가_그대로_나온다():
    """🔴 ③단(재정렬 없음) — **분석이 멈추지 않는다.**"""
    from app.research import rerank
    rows = _hits(5)
    got, why = rerank.order("injury absence", rows, _force="none")
    assert [r["url"] for r in got] == [r["url"] for r in rows], (
        "🔴 ③단인데 순서가 바뀌었다")
    assert "rerank_unavailable" in why, why



def test_M62_재정렬이_fetch_수를_안_늘린다():
    """🔴 *"재정렬은 순서만 바꾼다"* — 받는 건수는 그대로다."""
    from app.research import rerank
    rows = _hits(30)
    got, _ = rerank.order("x", rows, _force="none")
    assert len(got) == len(rows), (
        f"🔴 재정렬이 건수를 바꿨다({len(rows)} → {len(got)})")
    picked = rerank.take(got, cap=2)
    assert len(picked) == 2, f"🔴 fetch 상한을 안 지킨다: {len(picked)}"


def test_M62_필터_통과_못한_것을_되살리지_않는다():
    """🔴 1단은 **생존자만** 재정렬한다 — 되살리는 자리가 없어야 한다."""
    from app.research import rerank
    src = inspect.getsource(rerank)
    tree = ast.parse(src)
    # 🔴 `order` 는 **받은 목록 밖에서** 행을 가져오지 않는다
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "order"]
    assert fn, "🔴 `order` 를 못 찾았다"
    called = {n.func.attr for n in ast.walk(fn[0])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not (called & {"query", "get", "search", "fetch"} - {"get"}), (
        f"🔴 `order` 가 밖에서 자료를 가져온다{sorted(called)}")


# ══════════════════════════════════════════════════════════════════
# M65 — 문단 하이브리드: BM25 가 놓치는 **동의어**를 잡는다
# ══════════════════════════════════════════════════════════════════
@pytest.mark.slow
def test_M65_동의어_문단이_상위에_든다():
    """🔴 `"will not feature"` 만 있는 문단이 `absence` 질의에서 상위 8 에 든다.

    ⚠️ BM25 단독이면 빠진다 — 질의 낱말(`absent`·`injured`)이 그 문단에 없다.
    🔴 고정물로 본다(라이브 웹 금지).
    """
    import json
    import pathlib
    from app.research import rerank
    # 🔴 **싱글턴을 비우고 시작한다** — 다른 계약이 가짜 로더를 주입해
    #    `_MODEL = False` 를 남기면 이 계약이 늘 skip 된다(순서 오염).
    rerank.reset()
    box = json.loads(pathlib.Path(
        "tests/fixtures/research/paragraphs.json").read_text(encoding="utf-8"))
    paras = [str(x) for x in box["paragraphs"]]
    target = str(box["target"])
    assert target in paras, "🔴 고정물에 목표 문단이 없다"
    # 🔴 **모델이 정말 없을 때만** 건너뛴다. ⚠️ 실사고 2026-10-05: 사유에
    #    `rerank_unavailable` 이 있으면 건너뛰게 했더니 **R17**(2단 재정렬을
    #    끄는 돌연변이)이 그 길로 빠져나가 초록이 됐다 — skip 이 퇴로가 됐다.
    #    🔴 모델이 **있으면** 반드시 잡아야 한다.
    # 🔴 **예열**이 모델을 올린다(지연 로드는 지웠다 · 지시 2)
    rerank.warm()
    have = bool(rerank.loads()) and "rerank_unavailable" not in rerank.why()
    got, why = rerank.paragraphs(box["query"], paras)
    assert len(got) <= 8, f"🔴 상위 8 을 넘겼다: {len(got)}"
    if not have:
        import pytest
        pytest.skip(f"재정렬 모델이 이 기계에 **없다** — ③단으로 돌았다: {why}")
    assert target in got, (
        f"🔴 모델이 있는데 동의어 문단이 상위 8 에 **없다** — BM25 단독과 "
        f"같다(2단이 꺼졌나): {why}")


def test_M65_유형군마다_재정렬_질의가_있다():
    """🔴 그 질의가 동의어를 잡는 자리다 — 표가 든다(#1 사본 금지)."""
    from app.research import subtasks
    for g in subtasks.GROUPS:
        said = str(g.get("rerank_query") or "")
        assert len(said.split()) >= 4, (
            f"🔴 `{g['key']}` 의 `rerank_query` 가 너무 짧다: {said!r}")
    a = [g for g in subtasks.GROUPS if g["key"] == "A"][0]
    assert "feature" in a["rerank_query"], (
        "🔴 `A`(결장) 질의에 `feature` 가 없다 — `will not feature` 를 못 잡는다")





def test_M62_느리면_사유를_남긴다():
    """🔴 §5: *"넘으면 … 2단을 BM25 상위 8로 폴백(사유 `rerank_slow`)."*"""
    from app.research import rerank
    assert hasattr(rerank, "SLOW_AT"), (
        "🔴 `rerank.SLOW_AT`(몇 초를 느리다고 보나)이 없다")
    assert hasattr(rerank, "slow_note"), "🔴 `rerank.slow_note` 가 없다"
    said = rerank.slow_note(rerank.SLOW_AT + 1)
    assert "rerank_slow" in said, said
    assert not rerank.slow_note(0.1), "🔴 빠른데 느리다고 한다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **지운 계약 넷 — 승계 번호**(사용자 지시 2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  지운 것: `로드_실패가_위로_안_던져진다` · `모델을_한_번만_로드한다` ·
#  `동시에_불러도_한_번만_로드한다` · `추론은_직렬이다`
#
#  **승계 사유**: 넷은 **싱글턴 + 락**을 전제로 썼다. 🔴 사용자 지시가
#  *"락 추가로 땜질하지 않는다"* 로 그 전제를 걷고 **MPS 단일 스레드 소유**
#  (전용 `ThreadPoolExecutor`)로 바꿨다 — PyTorch #197805.
#  🔴 승계는 `tests/contracts/test_v5_5_mps_owner.py` 다:
#    · `test_mps1_추론이_전용_스레드에서만_돈다`(직렬 → **소유**)
#    · `test_mps2_로드는_한_번이고_횟수를_센다`(싱글턴 → **예열 1회 + 카운터**)
#    · `test_mps1_로드도_전용_스레드에서_돈다`(락 → 소유)
#    · `test_mps2_지연_로드가_없다`(위로 안 던진다 → **지연 로드 자체를 지웠다**)
#
#  ⚠️ 실사고가 그 전환을 요구했다: 락을 넣었더니 로드가 **4→11회로 늘고**
#     봇이 두 번 죽었다. 락은 *"같은 스레드"* 를 보장하지 않는다.
