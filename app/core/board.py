"""🔴🔴 **보드 글 → 경기 단서**(축구 완성 지시서 §1-1 ①).

🔴🔴 **배당은 읽지 않는다 — 사용자 지시 2026-10-19**
> 시장배당은 **아예 쓰지도 않는다.**

⚠️ 종전 이 파일은 보드 글에서 **마켓과 배당을 읽어** `BoardLine.price` 에 담았다
   (네 층 지시서 §2-6 · 2026-10-06 결정). 🔴 그 결정은 **걷혔다** — `parse` 와
   배당 읽기(`_price_of`·`_prices_of`·`_expand`·`_point_of`·`_numbers`)를 지웠다.
🔴 남은 일은 **하나다** — 보드 글에서 *"어느 경기인가"*(날짜·시각·두 팀·리그
   표기)를 읽는 것. 그것은 배당이 아니라 **신원 단서**이고 §1-1 ① 이 쓴다.
⚠️ 그래서 낱말표(`config/board_words.yaml`)는 **남는다** — 배당 줄을 *읽기 위해*
   가 아니라 **건너뛰기 위해** 쓴다(`_head_of`).

🔴 **LLM 이 보드를 읽지 않는다** — 모델이 지은 글자가 신원 단서가 되면 엉뚱한
   경기를 분석한다(절대규칙 6 이 막는 자리).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


def words() -> dict:
    """🔴 낱말표 — `config/board_words.yaml` 하나가 원본이다(사본 금지)."""
    from app import rules
    return dict(rules._load("config/board_words.yaml") or {})


def _norm(said: str) -> str:
    return " ".join(str(said or "").lower().split())


def _head_of(line: str, box: dict) -> str:
    """🔴 그 줄이 **배당 줄인가**(`보드:`·`추가:`·`승무패 …`) — 아니면 빈 글자.

    ⚠️ 배당을 **읽으려고** 쓰는 것이 아니다 — `hint_of` 가 그 줄을 **건너뛰려고**
       쓴다(배당 줄에는 경기 신원이 없다).
    """
    low = _norm(line)
    heads = dict(box.get("heads") or {})
    for kind in ("extra", "base"):
        for w in heads.get(kind) or []:
            if low.startswith(f"{str(w).lower()}:") or low.startswith(f"{w} :"):
                return kind
    return ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **보드에서 경기 단서를 읽는다** — 사용자 지시 2026-10-10(재작성) §1-1 ①
# ══════════════════════════════════════════════════════════════════
#
#  > 보드가 있으면 보드의 **날짜·시각·두 팀·리그 표기를 먼저 읽는다**(이게 가장
#  > 정확한 단서다).
#
#  🔴 **배당 줄은 건너뛴다**(`_head_of`) — 거기에는 경기 신원이 없다. ⚠️ 종전에는
#     그 줄을 `parse` 가 **읽었다**(배당) — 그 길은 2026-10-19 에 지웠다.
#  ⚠️ 배당 숫자와 시각을 **섞지 않는다**: `1.66` 은 배당이고 `20:00` 은 시각이다.
#     그래서 시각은 `HH:MM` 꼴(콜론)만, 날짜는 `M/D`·`M.D`·`YYYY-MM-DD` 만 읽는다.

#: 🔴 `20:00`·`03:45` — ⚠️ 앞뒤에 숫자가 붙으면 안 읽는다(배당 소수와 가른다)
_TIME = re.compile(r"(?<![\d.])([01]?\d|2[0-3]):([0-5]\d)(?![\d.])")
#: 🔴 `2026-10-10`·`10/10`·`10.10` — ⚠️ `10.10` 은 배당일 수도 있어 **맨 뒤**다
_DATE_FULL = re.compile(r"(20\d\d)[-./](\d{1,2})[-./](\d{1,2})")
_DATE_MD = re.compile(r"(?<![\d.])(\d{1,2})[/](\d{1,2})(?![\d.])")
#: 🔴 두 팀을 가르는 글자 — `vs`·`VS`·`대`·`-`(공백 있는 것만)
_VS = re.compile(r"\s+(?:vs\.?|VS\.?|v\.?|대|–|—|-)\s+")


@dataclass
class BoardHint:
    """🔴 보드가 말하는 **경기 단서**. ⚠️ 못 읽은 칸은 비어 있다(지어내지 않는다)."""

    home: str = ""
    away: str = ""
    league: str = ""
    day: date | None = None
    hhmm: str = ""
    why: str = ""

    def has_match(self) -> bool:
        """🔴 두 팀을 읽었나 — §1-3 *"0개인데 보드가 있다"* 가 이것을 본다."""
        return bool(self.home and self.away)


def hint_of(text: str, *, today: date | None = None) -> BoardHint:
    """🔴🔴 §1-1 ① — 보드 글에서 **날짜·시각·두 팀·리그 표기**를 읽는다.

    🔴 읽는 규칙(실측으로 고친다):
      · **두 팀** — `A vs B`·`A 대 B`·`A - B` 꼴이 있는 **첫 줄**. ⚠️ 배당 머리말
        (`승무패`·`언더오버`·`핸디`)이 든 줄은 건너뛴다(그 줄은 배당이다).
      · **시각** — `HH:MM` 만(배당 소수 `1.66` 과 가른다).
      · **날짜** — `YYYY-MM-DD` 가 먼저, 없으면 `M/D`. ⚠️ `10.10` 은 배당과
        구분이 안 되므로 **읽지 않는다**(모르는 것을 지어내지 않는다).
      · **리그** — 팀 줄의 **앞쪽 대괄호·소괄호** 안 글자(`[터키컵]`) 또는
        `리그:`·`대회:` 로 시작하는 줄.
    ⚠️ 날짜가 `M/D` 뿐이면 **해**를 `today` 로 채운다 — 그 사실이 `why` 에 남는다.
    """
    from app import window as _w
    base = today or _w.now_utc().date()
    got = BoardHint()
    said: list[str] = []
    box = words()
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = _norm(line)
        # 🔴 대회 줄 — `리그:`·`대회:`
        hit = re.match(r"\s*(?:리그|대회|league|competition)\s*[:：]\s*(.+)$",
                       line, re.I)
        if hit:
            got.league = hit.group(1).strip()
            said.append(f"대회 줄 → `{got.league}`")
            continue
        if _head_of(line, box):
            continue        # 🔴 배당 줄이다(`승무패 1.66 …`) — 신원이 아니다
        if not got.has_match():
            _two(line, got, said)
    for raw in str(text or "").splitlines():
        hit = _DATE_FULL.search(raw)
        if hit and got.day is None:
            y, m, d = (int(x) for x in hit.groups())
            got.day = date(y, m, d)
            said.append(f"날짜 `{got.day}`")
        hit = _TIME.search(raw)
        if hit and not got.hhmm:
            got.hhmm = f"{int(hit.group(1)):02d}:{hit.group(2)}"
            said.append(f"시각 `{got.hhmm}`")
    if got.day is None:
        for raw in str(text or "").splitlines():
            hit = _DATE_MD.search(raw)
            if hit:
                m, d = (int(x) for x in hit.groups())
                if 1 <= m <= 12 and 1 <= d <= 31:
                    got.day = date(base.year, m, d)
                    said.append(f"날짜 `{m}/{d}` → 해는 올해({base.year})로 봤다")
                    break
    got.why = " · ".join(said) if said else "보드에서 경기 단서를 못 읽었다"
    return got


def _two(line: str, got: BoardHint, said: list[str]) -> None:
    """🔴 그 줄에서 **두 팀**(과 앞에 붙은 대회 표기)을 읽는다."""
    head = re.match(r"\s*[\[(【]([^\])】]{1,30})[\])】]\s*(.+)$", line)
    rest = line
    if head:
        if not got.league:
            got.league = head.group(1).strip()
            said.append(f"대회 표기 `{got.league}`(대괄호)")
        rest = head.group(2)
    # 🔴 시각·날짜 글자를 떼고 본다 — 그것이 팀 이름에 붙어 오는 일이 많다
    rest = _TIME.sub(" ", _DATE_FULL.sub(" ", rest)).strip()
    parts = [x.strip(" ·|") for x in _VS.split(rest) if x.strip(" ·|")]
    if len(parts) == 2 and all(len(x) >= 2 for x in parts):
        got.home, got.away = parts[0], parts[1]
        said.append(f"두 팀 `{got.home}` ↔ `{got.away}`")
