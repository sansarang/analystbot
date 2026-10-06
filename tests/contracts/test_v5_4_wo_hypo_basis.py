"""🔴🔴 **§4 가설 근거 구멍 막기** — 지시서 2026-10-06 §4 (M132·M133).

원문(실측 2026-10-06 카드): 북아일랜드 근거에서 `R1`(h2h 표본 1)은 **뺐는데**,
DeepSeek 문장 *"h2h 패턴이 count=1로 단일 근거지만 … 전방 압박이 살아난다(R1)"*
이 통과했다. 원인: 제외 표시는 **판정층에만** 있고 DeepSeek 입력에는 R1 이
그대로 들어갔다.

> **두 겹으로 막는다**
> 1. **입력에서 뺀다**(원인 제거) — `HypoInput.variables` 에는 가설 근거로 쓸 수
>    있는 변수만. 표본 부족·검증 탈락·충돌 버림은 `context_only` 로 따로 보내고,
>    프롬프트에 *"`context_only` 의 변수는 번호로 인용하지 마라. 근거로 쓰지
>    마라"* 를 적는다. 반증 단계(단계 4)도 같은 분리.
> 2. **출력에서 거른다**(안전망) — 가설 문장은 **그 문장을 버리고** 사유
>    `cited_excluded:R1` 을 블록 5 에 적는다(문장을 고쳐 쓰지 않는다).
>    시나리오는 그 번호만 `driver_vars` 에서 빼고, 남은 driver 가 0개면 버린다.
> 문장이 다 버려진 팀 — 그 팀 가설이 0문장이 되면 "근거 변수 없음" 경로로 간다.
"""
from __future__ import annotations

import datetime as dt


def _inp(**kw):
    from app import hypo
    base = dict(home="team:1", away="team:2", sport="soccer",
                competition="Nations League", match_key="fotmob:1")
    base.update(kw)
    return hypo.HypoInput(**base)


# ══════════════════════════════════════════════════════════════════
# M132 — 제외 변수는 `variables` 에 없다
# ══════════════════════════════════════════════════════════════════

def test_M132_입력에_칸이_갈려_있다():
    from app import hypo
    assert "context_only" in hypo.HypoInput.__dataclass_fields__, (
        "🔴 `HypoInput.context_only` 가 없다 — 제외 변수를 보낼 칸이 없으면 "
        "`variables` 에 섞여 들어간다(지시서 §4-1)")


def test_M132_카드가_제외_변수를_그_칸으로_보낸다():
    """🔴🔴 **행동 검사** — `analyze` 가 실제로 갈라 넣는지 돌려서 본다."""
    from app import analyze, classify
    thin = classify.Classified(
        text="맞대결", source_url="https://x/1", hardness="soft",
        type="h2h_pattern", direction="home", why="§4",
        thin_sample=f"{classify.THIN_MARK} 맞대결 표본 1경기")
    solid = classify.Classified(
        text="폼", source_url="https://x/2", hardness="hard",
        type="recent_pattern", direction="home", why="§4")
    basis, ctx = analyze.split_basis([thin, solid])
    assert solid in basis and thin not in basis, (basis, ctx)
    assert thin in ctx, ctx


def test_M132_프롬프트가_그_금지를_적는다():
    """🔴 칸만 만들고 **말하지 않으면** 모델은 그 번호를 쓴다."""
    from app import hypo
    inp = _inp(variables=[{"id": "R2", "type": "recent_pattern"}],
               context_only=[{"id": "R1", "type": "h2h_pattern"}])
    # 🔴 **실제로 보내는 메시지**를 본다 — `run` 이 부르는 그 함수다(고아 금지).
    said = "\n".join(str(m.get("content") or "")
                     for m in hypo.messages_of(inp))
    assert "context_only" in said, "🔴 프롬프트에 그 칸 이름이 없다"
    assert "근거로 쓰지" in said or "인용하지" in said, said[-400:]
    # 🔴 **그 번호가 실제로 보인다**(모델이 무엇을 피해야 하는지 알아야 한다)
    assert "R1" in said, said[-400:]


# ══════════════════════════════════════════════════════════════════
# M133 — 출력 거르기(안전망)
# ══════════════════════════════════════════════════════════════════

def test_M133_제외_번호를_인용한_문장은_버려진다():
    from app import hypo
    said = {"home": {"reasons": ["흐름이 이어진다(R2).",
                                 "h2h 가 count=1이지만 살아난다(R1)."],
                     "breaks": ["체력이 떨어지면 실점한다(R2)."]}}
    kept, dropped = hypo.drop_cited(said, excluded={"R1"})
    rows = (kept.get("home") or {}).get("reasons") or []
    assert len(rows) == 1 and "R2" in rows[0], rows
    # 🔴 **문장을 고쳐 쓰지 않는다** — 버리고 사유를 남긴다
    assert any("cited_excluded:R1" in d for d in dropped), dropped
    assert not any("R1" in r for r in rows), rows


def test_M133_시나리오는_번호만_빼고_0개면_버린다():
    from app import hypo
    rows = [{"id": "A", "driver_vars": ["R1", "R2"], "mechanism": "m",
             "outcomes": ["1-0"]},
            {"id": "B", "driver_vars": ["R1"], "mechanism": "m",
             "outcomes": ["0-1"]}]
    kept, dropped = hypo.strip_cited(rows, excluded={"R1"})
    by = {r["id"]: r for r in kept}
    assert set(by) == {"A"}, by
    assert by["A"]["driver_vars"] == ["R2"], by["A"]
    assert any("B" in d and "cited_excluded" in d for d in dropped), dropped


def test_M133_카드_경로가_그_둘을_부른다():
    """🔴 #2 배선 — 만들고 **안 부르면** 없는 것이다."""
    import ast
    import inspect

    from app import analyze
    tree = ast.parse(inspect.getsource(analyze._run_hypo))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for name in ("drop_cited", "strip_cited"):
        assert name in called, (
            f"🔴 카드가 `hypo.{name}` 을 **안 부른다** — 제외 변수를 인용한 "
            f"문장·시나리오가 그대로 통과한다(실측 2026-10-06)")


def test_M133_문장이_다_버려지면_근거_없음_경로다():
    """🔴 *"그 팀 가설이 0문장이 되면 '근거 변수 없음' 경로로 간다."*"""
    from app import hypo
    said = {"home": {"reasons": ["h2h 로 산다(R1).", "또 R1 이다(R1)."],
                     "breaks": []}}
    kept, _dropped = hypo.drop_cited(said, excluded={"R1"})
    assert not ((kept.get("home") or {}).get("reasons") or []), kept
