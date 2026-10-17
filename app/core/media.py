"""🔴🔴 **리그별 현지 매체 표** — 사용자 지시 2026-10-17.

> 매체 표 구현하고 … **우선 일본 매체표만** 해봐라

🔴 **왜 생겼나 — 실측 2026-10-17(세 경기)**
질의 68개로 검색 결과 **1,913건**을 긁어 **기사 변수 2개**를 얻었다. 가장 큰
손실은 ④ **신원**이다 — 가시마 **749건**·세레소 283건이 *"이 경기 글이
아니다"* 로 떨어졌고 날짜에서 193~211건이 더 떨어졌다. 🔴 즉 검문이 센 것이
아니라 **엔진이 그 경기 글을 못 찾는다**.
⚠️ 그 와중에 `site:soccer-king.jp セレッソ大阪 日程` 은 **28건**을 줬다
   (같은 실행에서 ⑤-b3 2단이 던진 질의다).

🔴 그래서 **그 나라 매체로 먼저 좁힌다** — 질의 글자는 그대로 두고 `site:` 만
   붙인다. 던지는 통로·검문은 **그대로**다(새 엔진·새 fetch 경로 0).

## 🔴 잠금 넷
  ① 표는 **`config/media.yaml` 하나**다 — 코드에 매체를 박지 않는다
     (CLAUDE.md: *"엔진 품질을 코드에 박지 않는다"* · 그 결이다).
  ② **호스트만** 쓴다 — 꼴은 `querywriter.hosts` 가 검사하고 **robots 는
     `check_hosts` 가 받아 확인**한다(#4 지어낸 주소 금지). 이 파일은 **글자만**
     돌려주고 확인은 부르는 쪽이 한다.
  ③ 표에 없는 리그는 **빈 목록**이다 — `site:` 를 안 붙이고 종전처럼 돈다
     (없는 매체로 좁혀 0건을 만들지 않는다). 그 사실을 **사유로** 돌려준다(#3).
  ④ 대회 열쇠를 **여기서 다시 만들지 않는다** — `competition.kind_of` 가 만든
     그 열쇠(`league:J1`)를 받는다(사본 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 ① 표가 사는 곳(사람이 고친다 · §13-7)
CONF = "config/media.yaml"

_BOX: dict | None = None


def _load() -> dict:
    global _BOX
    if _BOX is None:
        import pathlib

        import yaml
        p = pathlib.Path(CONF)
        _BOX = (dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
                if p.exists() else {})
    return dict(_BOX)


def cap() -> int:
    """🔴 한 경기에서 `site:` 로 쓸 **매체 수 상한**(표가 든다)."""
    try:
        return int(_load().get("max_hosts") or 0)
    except (TypeError, ValueError):
        return 0


def hosts_of(key: object) -> tuple[list[str], str]:
    """🔴🔴 그 대회의 **현지 매체 호스트** — `(목록, 사유)`.

    🔴 `key` 는 `competition.kind_of` 가 만든 열쇠다(`league:J1`) — 여기서
       다시 만들지 않는다(④ 사본 금지).
    ⚠️ 표에 없으면 **빈 목록 + 사유**다(③) — 부르는 쪽이 그 사실을 적는다.
    """
    said = str(key or "").strip()
    if not said:
        return [], "⬜ 대회 열쇠가 없다 — 매체 표를 못 본다"
    box = dict(_load().get("by_league") or {})
    if not box:
        return [], f"⬜ 매체 표가 비었다(`{CONF}`)"
    rows = [str(x).strip() for x in (box.get(said) or []) if str(x).strip()]
    if not rows:
        return [], (f"⬜ `{said}` 는 매체 표에 없다 — `site:` 를 안 붙인다"
                    f"(표에 있는 대회 {len(box)}개)")
    n = cap()
    got = rows[:n] if n > 0 else rows
    return got, (f"매체 표 `{said}` — {len(got)}곳"
                 + (f" · 상한 {n} 으로 {len(rows) - len(got)}곳 잘랐다"
                    if len(got) < len(rows) else ""))


def key_of(ref, facts=None) -> str:
    """🔴 그 경기의 대회 열쇠 — 만드는 곳은 `s5_verify.comp_kind` 하나다.

    ⚠️ 못 알아보면 **빈 글자**다(지어내지 않는다).
    """
    try:
        from app.core.stages.s5_verify import comp_kind
        return str(comp_kind(ref, facts) or "")
    except Exception as exc:                                # noqa: BLE001
        logger.info("[매체표] 대회 열쇠를 못 만들었다 — %r", exc)
        return ""
