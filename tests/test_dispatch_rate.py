"""DSP-1 — 발송률이 **다 보낸 경기를 미발송으로 세지 않는다.**

🔴 운영 실측 2026-09-07 (`dispatch:mlb:2026-09-07`):
     window_not_open 133 · sent 11 · unchanged 239 · revised 6
     card_cap 186 · card_reserved 1
   종전 셈법으로 발송률 256/443 = **57.8%**, "미발송 186건 — 카드 2장 상한 도달".
   그런데 그 186건은 미발송이 아니다 — **카드 2장을 이미 다 보낸 경기**를
   5분 폴링이 계속 다시 집어서 그때마다 하나씩 적은 것이다.
   목표가 100%인 지표가 **잘 돌아갈수록 낮아졌다.**

`window_not_open` 을 분모에서 빼는 것과 같은 이유로 뺀다 — "지금 보낼 상황이
아닌 것"이다. ⚠️ 다만 **숨기지 않는다.** 상한 도달은 별도 항목으로 계속 보인다.
예비 재판정이 2장째를 먹어 최종 카드가 막히는 진짜 결함이 그 안에 있다.
"""
from app.engine import dispatch_stats as ds

# 운영 실측값 그대로 (2026-09-07 MLB)
REAL_0907 = {"window_not_open": 133, "sent": 11, "unchanged": 239,
             "revised": 6, "card_cap": 186, "card_reserved": 1}


def _summary(counts: dict) -> dict:
    """`summary` 의 집계부만 떼어 쓴다 — Redis 없이 같은 규칙을 검사한다."""
    return ds.classify(counts)


def test_다_보낸_경기는_미발송이_아니다():
    s = _summary(REAL_0907)
    assert s["misses"] == {}, f"미발송이 남았다: {s['misses']}"
    assert ds.rate(s) == 1.0, f"발송률이 100%가 아니다: {ds.rate(s)}"


def test_상한_도달은_분모에서_빠지되_보인다():
    s = _summary(REAL_0907)
    assert s["target"] == 11 + 239 + 6, "상한 도달·창 전이 분모에 남아 있다"
    assert s["reached"], "상한 도달이 통째로 사라졌다 — 숨기면 진짜 결함을 못 본다"
    assert sum(s["reached"].values()) == 187


def test_진짜_미발송은_여전히_잡힌다():
    """반대 위험 — 관대해져서 실제 실패를 놓치면 안 된다."""
    s = _summary({"sent": 1, "cache_missing": 2, "send_failed": 1, "unjudged": 3})
    assert s["target"] == 7
    assert ds.rate(s) == 1 / 7
    assert s["misses"] == {"판정 캐시 없음": 2, "텔레그램 발송 실패": 1, "판정 없음": 3}


def test_요약_문구가_상한_도달을_미발송이라_부르지_않는다():
    lines = ds.render(_summary(REAL_0907), "MLB")
    body = "\n".join(lines)
    assert "미발송" not in body, f"상한 도달을 미발송이라 적었다:\n{body}"
    assert "100%" in body
    assert "187" in body, "상한 도달 건수가 사라졌다"


def test_모든_사유가_셋_중_하나로_분류된다():
    """분류 누락이 생기면 조용히 미발송으로 흘러간다 — 그 자체가 이 결함이었다."""
    known = set(ds.REASON_KR)
    unclassified = known - set(ds.DELIVERED) - set(ds.NOT_TARGET) - set(ds.FAILED)
    assert not unclassified, f"어디에도 속하지 않는 사유: {sorted(unclassified)}"
