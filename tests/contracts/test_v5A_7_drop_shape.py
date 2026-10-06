"""🔴🔴 **반증 폐기 줄의 꼴** — 실측 2026-10-06(카드 렌더러가 터졌다).

```
File "app/judgeorder.py", line 137, in <genexpr>
    f"{r.get('id') or '?'}(…)"
AttributeError: 'tuple' object has no attribute 'get'
```

🔴 `hypo.check_scenarios` 는 `(id, 사유, 까닭)` **튜플**을 쌓고 렌더러는 `dict` 로
   읽었다 — **카드가 통째로 안 나왔다.**
⚠️ 인계가 적어 둔 그 병이다: *"꼴 불일치로 봇이 두 번 죽었다."*
🔴 렌더러는 분석을 **죽이지 않는다** — 못 읽는 꼴이면 그 사실을 적는다(#3).
"""
from __future__ import annotations

from app import judgeorder
from app.reasons import Reason


def test_폐기_줄이_두_꼴을_다_읽는다():
    assert "A" in judgeorder._drop_line({"id": "A", "why": "까닭"})
    # 🔴 `hypo` 가 실제로 쌓는 꼴
    said = judgeorder._drop_line(("B", Reason.UNKNOWN_VAR, "근거 변수가 아니다"))
    assert "B" in said and "unknown_var" in said and "근거" in said, said
    # 🔴 모르는 꼴이면 **그 사실을 적는다**(조용한 빈칸 금지)
    assert "모르는 폐기 꼴" in judgeorder._drop_line(object())


def test_카드_블록이_튜플에_터지지_않는다():
    """🔴🔴 **돌려서** 본다 — 터지면 그 경기 카드가 통째로 사라진다."""
    out = judgeorder.Outcome(steps=("반증",))
    out.dropped = [("A", Reason.UNKNOWN_VAR, "x"),
                   {"id": "B", "why": "y"}]
    rows = judgeorder.card_block(out)
    joined = "\n".join(rows)
    assert "폐기" in joined and "A" in joined and "B" in joined, joined
