"""🔴🔴 **도메인 등급표** — v5 §4-3. [#4]

> 등급표는 `config/domains.yaml`, 미등록 도메인은 **`local` 취급**하되 종목
> 낱말이 제목에 없으면 버린다(럭비·드라마 차단).

⚠️ 원본은 yaml 이다 — 이 파일은 **읽고 가린다**(사본 금지).
🔴 등급은 **처리**를 정한다: 본문을 받나 · hardness 몇인가 · 자르나.
"""
from __future__ import annotations

DOMAINS = "config/domains.yaml"

#: 🔴 §4-3 이 이름 댄 **일곱 등급**. ⚠️ 순서가 뜻이다 — 앞이 센 출처다.
TIERS: tuple[str, ...] = ("official", "national", "local", "aggregator",
                          "wiki", "tip", "deny")


def table() -> dict:
    from app import rules
    return dict(rules._load(DOMAINS) or {})


def _host(url: str) -> str:
    raw = str(url or "")
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    return raw.split("/")[0].lower()


def tier_of(url: str) -> str:
    """🔴 그 주소의 등급. ⚠️ 미등록은 **`local`**(§4-3).

    🔴 **`deny` 를 먼저 본다** — 등급이 겹치면 거부가 이긴다(위키 경제 문서처럼
       같은 호스트에 둘이 섞인다).
    """
    cfg = table()
    low = str(url or "").lower()
    host = _host(url)
    # 🔴 `deny` → `tip` → 나머지. ⚠️ 주소 **전체**를 본다(경로까지)
    for tier in ("deny", "tip"):
        for pat in (cfg.get(tier) or []):
            if str(pat).lower() in low:
                return tier
    for tier in ("official", "national", "local", "aggregator", "wiki"):
        for pat in (cfg.get(tier) or []):
            p = str(pat).lower()
            if p in host or p in low:
                return tier
    return str(cfg.get("unknown_tier") or "local")


def handling(tier: str) -> dict:
    """🔴 그 등급의 처리. ⚠️ 모르는 등급은 **거부한다**(오타가 조용히 통과하면
    그 호스트가 아무 등급도 없이 돈다)."""
    if tier not in TIERS:
        raise ValueError(f"🔴 모르는 **등급**이다: {tier!r} — §4-3 이 이름 댄 것은"
                         f" {list(TIERS)}")
    return dict(((table().get("handling") or {}).get(tier) or {}))


def may_fetch(tier: str) -> bool:
    """🔴 §4-3 — `tip`·`deny` 는 **본문을 안 받는다.**"""
    return bool(handling(tier).get("fetch"))


def hardness_of(tier: str) -> int:
    """🔴 §4-3·§5-5 — 등급이 무게를 준다.

    ⚠️ `national` 은 **2매체 일치면 2** 다(§4-3 표) — 그 판단은 등급 하나로
       못 하므로 여기서는 **단일 기준**(1)이고 §5-5 가 올린다.
    """
    return int(handling(tier).get("hardness") or 0)


def max_chars(tier: str) -> int | None:
    """🔴 §4-3 — `wiki` 는 **5만 자 절단**(배경이다)."""
    got = handling(tier).get("max_chars")
    return int(got) if got else None


def verdict(url: str, *, sport: str = "",
            title: str = "") -> tuple[bool, str, str]:
    """🔴🔴 그 주소를 **받나**. `(받는다, 등급, 사유)`.

    🔴 §4-3 의 두 문을 한 자리에서 묻는다: **등급**과 **종목 낱말**.
    ⚠️ 미등록(`local`)이어도 종목이 안 맞으면 버린다 — 그것이 럭비·드라마를
       막는 자리다(실측 2026-10-04: 럭비 15건 · 드라마 출연진 8건).
    """
    from app import rules
    tier = tier_of(url)
    if not may_fetch(tier):
        return False, tier, (
            f"🔴 등급 `{tier}` — 본문을 받지 않는다(§4-3)"
            + (" · 변수 근거 금지" if tier == "tip" else " · 검색 결과에서 제거"))
    if (why := rules.other_sport(url, sport, title=title)):
        return False, tier, why
    if (why := rules.not_sport_host(url)):
        return False, tier, why
    return True, tier, f"등급 `{tier}` · hardness {hardness_of(tier)}"
