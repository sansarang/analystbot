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
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **규칙 글과 자료 글을 가른다** — 실측 2026-10-06
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음엔 **보내는 글 전체**에서 `context_only` 를 찾았다. 🔴 그 글자는
    #     자료(JSON)의 **열쇠 이름**으로도 들어 있어, 금지 문구를 지워도
    #     계약이 통과했다(돌연변이 M132b).
    #  🔴 금지는 **규칙 글**(`system_prompt`)에 있어야 한다 — 자료에 있는 것은
    #     금지가 아니라 그냥 칸 이름이다.
    rule = hypo.system_prompt()
    assert "context_only" in rule, "🔴 규칙 글에 그 칸 이름이 없다"
    assert "근거로 쓰지" in rule and "인용하지" in rule, rule[-500:]
    # 🔴 그리고 **그 번호가 자료로 실제로 간다**(모델이 무엇을 피할지 알게)
    said = "\n".join(str(m.get("content") or "")
                     for m in hypo.messages_of(inp))
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **행동 검사** — `_run_hypo` 를 **돌려서** 본다
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ 위 계약들은 조각(`split_basis`·`drop_cited`·`strip_cited`)만 봤다 — 그래서
#    돌연변이 셋이 통과했다(§9-5: 안 물리는 계약은 없는 계약이다):
#      · `variables` 에 제외 변수를 다시 넣기
#      · 프롬프트에서 금지 문구 빼기
#      · 출력 거르기 자체를 끄기
# 🔴 그래서 **DeepSeek 를 대역으로 두고 `_run_hypo` 를 실제로 돌린다.**


def _card_with_thin():
    from app import analyze, classify
    thin = classify.Classified(
        text="맞대결 1경기", source_url="https://x/1", hardness="soft",
        type="h2h_pattern", direction="home", why="§4",
        thin_sample=f"{classify.THIN_MARK} 맞대결 표본 1경기")
    solid = classify.Classified(
        text="최근 5경기", source_url="https://x/2", hardness="hard",
        type="recent_pattern", direction="home", why="§4")
    away = classify.Classified(
        text="원정 폼", source_url="https://x/3", hardness="hard",
        type="recent_pattern", direction="away", why="§4")
    game = classify.Game(home="Northern Ireland", away="Georgia",
                         sport="soccer", league="Nations League",
                         home_id="team:1", away_id="team:2")
    card = analyze.Card(game=game)
    card.variables = [thin, solid, away]      # 🔴 `R1` 이 표본 부족이다
    card.hypotheses = classify.hypotheses(card.variables, game)
    card.form = {}
    return card, game


def _run(monkeypatch, *, answer):
    """🔴 `_run_hypo` 를 돌린다 — DeepSeek 는 대역이고 **보낸 글을 붙잡는다**."""
    from app import analyze, hypo, scenarios
    seen: dict = {}

    def _fake(inp, *, now=None, _net=None):
        seen["sent"] = hypo.to_payload(inp)
        seen["prompt"] = "\n".join(str(m.get("content") or "")
                                   for m in hypo.messages_of(inp))
        from app.reasons import Reason
        return hypo.HypoResult(
            hypotheses=answer["hypotheses"], scenarios=answer["scenarios"],
            form={}, drops=[], missed=[], reason=Reason.OK, usd=0.0,
            why="대역")

    monkeypatch.setattr(hypo, "run", _fake)
    card, game = _card_with_thin()
    sc = scenarios.Result()
    got = analyze._run_hypo(card, game, [], {}, sc)
    return seen, got, sc, card


def test_M132_행동_제외_변수가_입력에_안_들어간다(monkeypatch):
    seen, _got, sc, _card = _run(monkeypatch, answer={
        "hypotheses": {"home": {"reasons": ["폼이 좋다(R2)."], "breaks": []}},
        "scenarios": []})
    ids = {r["id"] for r in (seen["sent"].get("variables") or [])}
    ctx = {r["id"] for r in (seen["sent"].get("context_only") or [])}
    assert "R1" not in ids, (
        f"🔴 표본 부족 변수 `R1` 이 **근거 목록**에 들어갔다: {ids}")
    assert "R1" in ctx, f"🔴 `context_only` 로도 안 갔다: {ctx}"
    assert {"R2", "R3"} <= ids, ids
    # 🔴 **그 사실을 사유로 남긴다**(#3)
    assert any("context_only" in str(n) for n in sc.notes), sc.notes


def test_M132_행동_프롬프트가_금지를_말한다(monkeypatch):
    seen, _got, _sc, _card = _run(monkeypatch, answer={
        "hypotheses": {}, "scenarios": []})
    from app import hypo
    rule = hypo.system_prompt()
    # 🔴 금지는 **규칙 글**에 있어야 한다(자료의 칸 이름이 아니다)
    assert "context_only" in rule and "근거로 쓰지" in rule \
        and "인용하지" in rule, rule[-500:]
    assert "R1" in seen["prompt"], (
        "🔴 그 번호가 보내는 글에 안 보인다 — 모델이 뭘 피할지 모른다")


def test_M133_행동_제외_번호_문장이_카드에_안_남는다(monkeypatch):
    seen, got, sc, card = _run(monkeypatch, answer={
        "hypotheses": {"home": {
            "reasons": ["폼이 좋다(R2).",
                        "h2h 가 count=1이지만 살아난다(R1)."],
            "breaks": []}},
        "scenarios": [{"id": "A", "driver_vars": ["R1"], "mechanism": "m",
                       "outcomes": ["1-0"]},
                      {"id": "B", "driver_vars": ["R1", "R2"],
                       "mechanism": "m", "outcomes": ["2-1"]}]})
    rows = (got.hypotheses.get("home") or {}).get("reasons") or []
    assert not any("R1" in r for r in rows), (
        f"🔴 제외 번호를 인용한 문장이 **살아남았다**: {rows}")
    assert any("cited_excluded:R1" in str(n) for n in sc.notes), sc.notes
    # 🔴 시나리오 — `A` 는 버려지고 `B` 는 번호만 빠진다
    by = {r["id"]: r for r in (got.scenarios or [])}
    assert "A" not in by, f"🔴 근거가 0개가 된 시나리오가 남았다: {by}"
    assert by.get("B", {}).get("driver_vars") == ["R2"], by.get("B")
    # 🔴 카드 문장에도 그 번호가 없다
    for h in (card.hypotheses or []):
        for line in (getattr(h, "win_why", []) or []):
            assert "R1" not in str(line), line
