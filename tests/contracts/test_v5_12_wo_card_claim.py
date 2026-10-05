"""🔴🔴 **카드의 변수 줄이 "무엇을 말하는지"를 적는다** — 사용자 지시 2026-10-05.

> 포르투갈–노르웨이 **카드 전문**을 그대로 붙여라 (**변수별 문장·인용·URL**,
> 팀별 가설과 근거 변수 번호, DeepSeek 시나리오와 반증 추가분, 결론).

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-05 — 변수 줄에 **사실이 없다**
══════════════════════════════════════════════════════════════════

```
R4 [absence·home·soft] §3 에이전트 + §5 검증층 통과 · 등급 `local`(무게 1) ·
                       힌트 `away` → **코드가 정한 쪽** `home`(§5-4)
                       ↳ https://worldsoccertalk.com/news/why-is-cristiano-…
```

⚠️ 유형·방향·등급·힌트·URL 은 있는데 **무슨 결장인지**가 없다. 🔴 독자가
   *"호날두가 왜 빠지나"* 를 **URL 을 열어야** 안다 — 카드가 그 일을 해야 한다.

🔴 `Classified.text` 에 **이미 담겨 있다**(`claim — 인용 「quote」`) —
   카드가 `why` **또는** `text` 중 **하나만** 찍었다(#2 꼴의 구멍).
"""
from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc


def _var(**kw):
    from app import classify
    base = {"text": "호날두가 징계로 빠진다 — 인용 「Ronaldo will serve a ban」",
            "source_url": "https://x/a", "type": "absence",
            "direction": "home", "hardness": "soft",
            "why": "§3 에이전트 + §5 검증층 통과 · 등급 `local`(무게 1)",
            "team": "Portugal",
            "published_at": dt.datetime(2026, 10, 4, 6, tzinfo=UTC)}
    base.update(kw)
    return classify.Classified(**base)


def _card(rows):
    from app import analyze
    card = analyze.Card()
    card.variables = list(rows)
    return analyze.render(card) if hasattr(analyze, "render") else ""


def test_wo_card_변수_줄에_사실이_있다():
    """🔴🔴 **문장**(`claim`)이 카드에 보여야 한다 — URL 을 열지 않고 읽는다."""
    from app import analyze
    got = analyze.var_line(_var())
    assert "호날두" in got, (
        f"🔴 변수 줄에 **무슨 일인지**가 없다 — 독자가 URL 을 열어야 안다: "
        f"{got}")


def test_wo_card_인용도_같이_적는다():
    """🔴 §5-1 이 대조한 **그 인용**을 보여 준다 — 근거가 눈에 보여야 한다."""
    from app import analyze
    got = analyze.var_line(_var())
    assert "Ronaldo will serve a ban" in got, got


def test_wo_card_규칙_사유도_남는다():
    """⚠️ **둘 중 하나만** 찍지 않는다 — `why`(판정 경로)도 필요하다.

    🔴 그것이 *"코드가 정한 쪽"*·*"등급 무게"* 를 말한다(§5-4 감사 흔적).
    """
    from app import analyze
    got = analyze.var_line(_var())
    assert "§5" in got or "등급" in got, got


def test_wo_card_사실이_없으면_사유만_적는다():
    """🔴 **조용한 빈칸 금지**(#3) — `claim` 이 없으면 그 사실이 보여야 한다."""
    from app import analyze
    got = analyze.var_line(_var(text=""))
    assert got.strip(), got
    assert "§3" in got or "등급" in got, got


def test_wo_card_길이를_잘라도_표시한다():
    """⚠️ 긴 문장을 자를 때 **자른 사실**을 적는다(종전 `_clip` 규율)."""
    from app import analyze
    long = "가" * 400
    got = analyze.var_line(_var(text=long + " — 인용 「" + "x" * 300 + "」"))
    assert "…" in got or "자" in got, got[-80:]


def test_wo_card_카드_렌더러가_그_함수를_쓴다():
    """🔴 **배선**(#2) — 함수를 만들고 카드가 안 쓰면 없는 코드다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze))
    i = body.index("■ 4 뒤집는 변수")
    seg = body[i:i + 900]
    assert "var_line(" in seg, (
        "🔴 카드가 `var_line` 을 **안 쓴다** — 변수 줄이 그대로다(#2)")
