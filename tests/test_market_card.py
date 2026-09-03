"""[시장 기준선 C2] 카드 표기·요약 — 그리고 **재발송 규칙 무영향.**

🔴 배당은 30분마다 흔들린다. 시장 줄이 `verdict_hash` 에 들어가면
   **배당 변동만으로 수정 카드가 계속 나간다.** 이 파일이 그걸 잠근다.
"""
from pathlib import Path

import pytest

from app.engine.market_baseline import market_line
from app.engine.pregame_push import verdict_hash

CARD = Path("app/engine/form_card.py").read_text(encoding="utf-8")
PUSH = Path("app/engine/pregame_push.py").read_text(encoding="utf-8")


# ═════════ 형식 ═════════

def test_line_format_is_fixed():
    # 0.72 − 0.63 = 0.09 → -9.0%p (내 첫 기대값 -9.2 는 de-vig 결과
    # 0.7215 를 머릿속에서 섞은 것이었다. 계산은 입력 그대로 한다.)
    assert market_line(0.72, 0.63) == "시장 72% vs 우리 63% (-9.0%p — 시장 이견)"
    # 실배당 de-vig 값으로도 확인 — 반올림이 라벨을 흔들지 않는다
    assert market_line(0.7215, 0.63) == "시장 72% vs 우리 63% (-9.2%p — 시장 이견)"


def test_agree_label_below_threshold():
    from app.config import get_settings

    assert get_settings().market_divergence_pp == 4.0
    assert "시장 동의" in market_line(0.62, 0.639)      # 1.9%p
    assert "시장 이견" in market_line(0.62, 0.665)      # 4.5%p


def test_threshold_is_read_from_config_not_hardcoded():
    src = Path("app/engine/market_baseline.py").read_text(encoding="utf-8")
    i = src.index("def market_line")
    seg = src[i:]
    assert "market_divergence_pp" in seg
    assert "4.0" not in seg.split("def ")[1]


def test_no_line_when_market_is_missing():
    """🔴 "미수집" 문구를 발명하지 않는다 — 가치 줄이 이미 그 역할을 한다."""
    assert market_line(None, 0.63) is None
    assert market_line(0.72, None) is None


def test_card_omits_the_line_when_absent():
    assert 'lines.append(_ml)' in CARD
    assert "if _ml:" in CARD
    assert "시장 미수집" not in CARD


def test_no_reason_sentence_is_generated():
    """이견 사유를 만들면 판정 프롬프트를 건드려야 한다 — 동결 위반이다."""
    src = Path("app/engine/market_baseline.py").read_text(encoding="utf-8")
    i = src.index("def market_line")
    seg = src[i:i + 1200]
    for banned in ("사유", "왜냐", "때문"):
        assert banned not in seg.split('"""')[2], banned


# ═════════ 🔴 재발송 규칙 무영향 ═════════

def test_verdict_hash_ignores_market_value():
    """배당만 바뀐 두 판정의 해시가 **같아야** 한다."""
    base = {"p_claude": 0.63, "matchup": {"우세": "home", "확신도": "중"}}
    a = {**base, "p_market_send": 0.72}
    b = {**base, "p_market_send": 0.55}
    assert verdict_hash(a) == verdict_hash(b)


def test_verdict_hash_source_has_no_market_field():
    i = PUSH.index("def verdict_hash")
    seg = PUSH[i:PUSH.index("\ndef ", i + 10)]
    assert "market" not in seg, "시장값이 해시에 들어갔다 — 배당 변동이 재발송을 부른다"


def test_market_value_is_attached_only_for_display():
    """`p_market_send` 는 표기 전용 — 판정 경로가 읽지 않는다."""
    for path in ("app/engine/matchup.py", "app/engine/prompts.py",
                 "app/engine/team_form.py", "app/engine/value_gate.py"):
        src = Path(path).read_text(encoding="utf-8")
        assert "p_market_send" not in src, path


def test_lineup_hash_untouched():
    i = PUSH.index("def lineup_hash")
    seg = PUSH[i:PUSH.index("\ndef ", i + 10)]
    assert "market" not in seg


# ═════════ 요약 ═════════

@pytest.mark.asyncio
async def test_summary_line_shape():
    from app.engine.daily_summary import market_lines

    class Pool:
        async def fetchrow(self, sql, *a):
            return {"m_w": 7, "m_l": 3, "o_w": 6, "o_l": 4,
                    "diverged": 4, "diverged_hit": 3}

    lines = await market_lines(Pool(), ("kbo",))
    assert lines == ["🎯 시장 7승3패 · 우리 6승4패 · 이견 4건 중 3적중"]


@pytest.mark.asyncio
async def test_summary_is_silent_without_material():
    from app.engine.daily_summary import market_lines

    class Pool:
        async def fetchrow(self, sql, *a):
            return {"m_w": 0, "m_l": 0, "o_w": 0, "o_l": 0,
                    "diverged": 0, "diverged_hit": 0}

    assert await market_lines(Pool(), ("kbo",)) == []
