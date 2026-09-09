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
    # 🔴 [v1.4 2026-09-07] 계약이 갈렸다. 지켜야 할 성질은 그대로다 —
    #    **시장 줄(`_ml`)은 값이 없으면 안 찍는다**(`if _ml:` 이 그것이다).
    #    바뀐 것은 베팅 자격 줄이다: 시장이 없어서 추천이 아니면 이제 그
    #    **사유를 적는다**(사용자 지시 "괴리 픽은 보드만+사유 표기").
    #    두 줄은 다른 줄이다 — 시장 줄은 여전히 침묵한다.
    seg = CARD[CARD.index("def market_line") if "def market_line" in CARD
               else 0:]
    assert "시장 미수집" in CARD, "사유 표기가 사라졌다"
    assert "_market_why" in CARD, "사유를 만드는 자리가 없다"


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


def test_card_market_line_uses_home_basis_not_favored_side():
    """🔴 [MKT-9 실측 2026-09-10] 카드가 같은 경기에서 우리 확률을 두 번 다르게
    말했다 — 상단 "시장 54% vs 우리 53% (시장 동의)" 인데 하단은 "시장 이견
    (우리 47% vs 시장 54%)".

    원인: `market_line` 호출부가 **우세팀 확률(0.53)** 을 넘기는데 시장값
    `p_market_send`(0.54)는 **홈 기준**이다. 원정 우세 경기에서 기준이 어긋나
    7%p 갈린 경기를 "동의"로 표시했다. 게이트(`market_disagreement`)는 홈끼리
    비교해 옳게 "이견"을 냈으므로, 틀린 쪽은 카드 줄이다.

    ⚠️ 홈 우세 경기는 p_fav == p_home 이라 증상이 없다 — **원정 우세에서만** 난다.
    """
    from app.engine.form_card import render_form_card

    jg = {
        "sport": "mlb", "league": "MLB",
        "home": "Detroit Tigers", "away": "Minnesota Twins",
        "p_claude": 0.47, "p_market_send": 0.54,
        "lineup_status": "confirmed",
        "matchup": {"p_home": 0.47, "우세": "away", "확신도": "중", "근거": []},
    }
    body = render_form_card(jg, "mlb")
    market_lines = [ln for ln in body.splitlines() if ln.startswith("시장 ")]
    assert market_lines, "시장 줄이 없다"
    line = market_lines[0]
    # 홈 기준(0.47 vs 0.54 = 7%p)이므로 '이견' 이어야 한다
    assert "시장 이견" in line, f"원정 우세인데 기준이 어긋났다: {line}"
    assert "우리 47%" in line, f"우세팀 기준(53%)을 쓰고 있다: {line}"


# ── [DS-4 2026-09-10] 딥서치 결과가 야구 카드에 드러나야 한다 ────────────

def test_baseball_card_shows_deepsearch_result():
    """🔴 실측 2026-09-10 (CLE@BAL): 딥서치가 실제로 돌아 발견 3건을 냈는데
    **카드에 한 글자도 안 나왔다.** form_card 가 `jg["deepsearch"]` 를 읽지
    않기 때문이다(축구 카드 soccer_trial.py:133 은 읽는다).

    사용자가 "조사가 됐는지"를 카드로 알 수 없으면 딥서치가 일하는지 확인할
    방법이 없다 — '조용한 0'과 구분되지 않는다.
    """
    from app.engine.form_card import render_form_card

    jg = {
        "sport": "mlb", "league": "MLB", "home": "H", "away": "A",
        "p_claude": 0.45, "lineup_status": "confirmed",
        "matchup": {"p_home": 0.45, "우세": "away", "확신도": "중", "근거": []},
        "deepsearch": {"발견": [{"사실": "헨더슨 무릎 타박 Day-to-Day"}],
                       "요약": "헨더슨 DTD — 결장 확정 아님",
                       "이동_pp": 0.0, "조정_사유": "근거 불충분"},
    }
    body = render_form_card(jg, "mlb")
    assert "추가 조사" in body, "딥서치 결과가 카드에 없다"
    assert "헨더슨" in body


def test_card_says_investigated_even_when_no_change():
    """조정 0이어도 '조사했다'는 사실은 보여야 한다 — 미조사와 구분되게."""
    from app.engine.form_card import render_form_card

    jg = {
        "sport": "mlb", "league": "MLB", "home": "H", "away": "A",
        "p_claude": 0.50, "lineup_status": "confirmed",
        "matchup": {"p_home": 0.50, "우세": "home", "확신도": "중", "근거": []},
        "deepsearch": {"발견": [], "요약": "괴리 원인 미확인",
                       "이동_pp": 0.0, "조정_사유": None},
    }
    body = render_form_card(jg, "mlb")
    assert "추가 조사" in body
    assert "미확인" in body


def test_no_deepsearch_key_means_no_line():
    """조사 자체가 없었으면 줄을 만들지 않는다 — 없는 것을 지어내지 않는다."""
    from app.engine.form_card import render_form_card

    jg = {"sport": "mlb", "league": "MLB", "home": "H", "away": "A",
          "p_claude": 0.50, "lineup_status": "confirmed",
          "matchup": {"p_home": 0.50, "우세": "home", "확신도": "중", "근거": []}}
    assert "추가 조사" not in render_form_card(jg, "mlb")
