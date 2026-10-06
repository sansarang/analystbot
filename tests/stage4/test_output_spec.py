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




def test_규격_블록이_전부_대응표에_있다():
    """🔴 규격에 블록이 늘면 **여기가 먼저 빨개진다.**"""
    missing = [b for b in _spec_blocks() if b not in WHERE]
    assert missing == [], (
        f"규격에 생긴 블록이 대응표에 없다: {missing} — 카드 어디에 내는지 적어라")
    stale = [b for b in WHERE if b not in _spec_blocks()]
    assert stale == [], f"규격에서 사라진 블록이 대응표에 남았다: {stale}"








# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **D — 사람이 읽을 수 있게** (사용자 지적 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# 종전 카드의 변수 줄 다섯이 `(칸 없음)` 이었다 — 질문 id 와 빈칸뿐이라 **무슨
# 사실인지 사람이 모른다.** 그런데 판정 사유에는 그 내용이 이미 들어 있었다.










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
