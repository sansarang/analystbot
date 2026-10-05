"""🔴🔴 **v5-A §2 — DeepSeek 호출 사양.** 단가는 **공식 문서**에서 왔다.

부록 v5-A §2 원문:

> 모델 — 추론 모드가 있는 모델을 쓴다. … Claude Code 가 **공식 api-docs·
> pricing 페이지를 직접 읽어** `config/llm.yaml` 의 `deepseek:` 칸에 모델
> ID·입력/캐시/출력 단가·확인 날짜를 적는다. **매체 수치는 쓰지 않는다.**
> 시작은 저가 모델(Flash 계열, 추론 켬).
> 키·결제 — 키는 로컬 `.env` 의 `DEEPSEEK_API_KEY`, **이름만** `.env.example`.
> 웹 차단 — DeepSeek 호출에는 **도구를 하나도 넘기지 않는다**(M42).
> 예산 — 경기당 입력 30,000 · 출력 15,000. 하루·월은 **Solar 와 합산**.

🔴 **읽은 곳**: `https://api-docs.deepseek.com/quick_start/pricing`
   (2026-10-04 · 봇이 직접 받아 글자를 뽑았다)
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _cfg() -> dict:
    from app import rules
    return rules.deepseek_cfg()


def test_v5A_2_켜진_값이_선언된_것이다():
    """🔴 `enabled` 는 네 값 중 하나다 — 그리고 지금은 `stage3+4` 다."""
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **켜졌다** — 사용자 지시 2026-10-05 (*"딥시크 켜라"*)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 계약은 *"꺼짐이 기본이다"* 를 지켰다 — 작업지시 §4 가
    #     *"`enabled` 기본값을 true 로 커밋 금지"* 라고 했기 때문이다.
    #  🔴 **그 금지가 걷혔다**: 사용자가 *"측정 비교 없이 켠다. 단계 3과 단계
    #     4를 enabled 로"* 라고 지시했다(2026-10-05). **직접 지시가 이긴다.**
    #  🔴 그래도 **지키는 것**은 그대로다 — M41~M46(특히 **M44 생존율 상승
    #     금지** · **M45 장애 시 Solar 로 끝까지**)은 아래 계약들이 본다.
    from app import rules
    said = rules.deepseek_cfg().get("enabled")
    # 🔴 **켜진 값이 선언된 넷 중 하나**여야 한다(아무 글자나 아니다)
    assert said in (False, "stage3", "stage3+4", True), said
    assert said == "stage3+4", (
        f"🔴 사용자가 **단계 3·4 를 켜라**고 했다(2026-10-05) — 지금 `{said}`")

def test_v5A_2_모델이_저가_추론_모델이다():
    """🔴 *"시작은 저가 모델(Flash 계열, **추론 켬**)"*."""
    m = _cfg()["model"]
    assert "flash" in m["name"], m
    assert m["thinking"] is True, m
    assert m["base_url"] == "https://api.deepseek.com", m
    assert int(m["timeout_sec"]) == 120 and int(m["retries"]) == 2


def test_v5A_2_단가가_공식_문서에서_왔다():
    """🔴🔴 *"**매체 수치는 쓰지 않는다**"* — 출처가 공식 문서여야 한다."""
    pr = _cfg()["price_usd_per_1m"]
    assert pr["source"].startswith("https://api-docs.deepseek.com"), pr
    assert str(pr["as_of"]) == "2026-10-04", pr
    assert pr["read_by_bot"] is True
    # ⚠️ 사용자 확인은 **아직 아니다** — 그 사실을 숨기지 않는다
    assert pr["verified_by_user"] is False


def test_v5A_2_피크와_오프피크를_둘_다_적는다():
    """🔴🔴 **피크가 두 배다** — 하나만 적으면 그 수가 절반 틀린다.

    공식 문서: *"Off-peak rates are **half** of the peak rates. Peak hours are
    01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday."*
    """
    pr = _cfg()["price_usd_per_1m"]
    off, peak = pr["off_peak"], pr["peak"]
    for k in ("input", "cached_input", "output"):
        assert peak[k] == pytest.approx(off[k] * 2), (k, off[k], peak[k])
    # 🔴 **캐시가 훨씬 싸다**(그래서 고정 프롬프트를 앞에 둔다 · v5-A §2)
    assert off["cached_input"] < off["input"] / 10


@pytest.mark.parametrize(("iso", "want"), [
    ("2026-10-05T02:00:00+00:00", "peak"),      # 월 02시 UTC
    ("2026-10-05T07:30:00+00:00", "peak"),      # 월 07시 UTC
    ("2026-10-05T12:00:00+00:00", "off_peak"),  # 월 12시 UTC
    ("2026-10-03T02:00:00+00:00", "off_peak"),  # 🔴 토요일 — 주말은 전부 오프피크
    ("2026-10-04T07:00:00+00:00", "off_peak"),  # 일요일
])
def test_v5A_2_시각으로_단가를_고른다(iso, want):
    """🔴 **코드가 시각으로 고른다** — 사람이 고르지 않는다.

    ⚠️ 문서: *"All other hours are off-peak, **including weekends** and Chinese
       public holidays in full."*
    🔴 중국 공휴일은 **모른다** — 그 사실을 적어 두고 **피크로 본다**
       (fail-closed: 비싸게 세는 쪽이 안전하다).
    """
    from datetime import datetime

    from app import llmprice
    got = llmprice.deepseek_band(datetime.fromisoformat(iso))
    assert got == want, (iso, got)


def test_v5A_2_예산이_부록_표_그대로다():
    """🔴 경기당 입력 30,000 · 출력 15,000(v5-A §2 표)."""
    b = _cfg()["budget"]["per_match"]
    assert int(b["input_tokens"]) == 30_000
    assert int(b["output_tokens"]) == 15_000
    # 🔴 하루·월은 **Solar 와 합산**이다 — 여기 다시 적지 않는다(사본 금지)
    assert _cfg()["budget"]["shared_with_solar"] is True
    from app import rules
    assert "per_day_usd" not in _cfg()["budget"]
    assert float(rules.llm_budget()["per_day_usd"]) == 3.0


def test_v5A_2_키는_로컬_env_에만_있다():
    """🔴 *"키는 로컬 `.env`, **이름만** `.env.example`"*."""
    ex = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in ex
    # 🔴🔴 **값이 있으면 안 된다**(예시에 키가 새면 그것이 유출이다)
    for line in ex.splitlines():
        if line.startswith("DEEPSEEK_API_KEY"):
            assert line.strip() == "DEEPSEEK_API_KEY=", line
    # ⚠️ `.env` 키 ⊆ `.env.example` 계약은 기존 것이 지킨다
    env = ROOT / ".env"
    if env.exists():
        assert "DEEPSEEK_API_KEY" in env.read_text(encoding="utf-8")
