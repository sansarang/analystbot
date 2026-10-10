"""🔴🔴 **보드 파서** — 사용자가 붙여 넣은 글 → `Board`(축구 완성 지시서 §4).

> 사용자가 보드를 텍스트로 붙여 넣는다.

🔴🔴 **배당을 버리지 않는다 — 네 층 지시서 §2-6**(사용자 결정 2026-10-06)

> 보드 파서가 마켓과 배당을 읽는다(파서는 배당을 **버리지 않고** `BoardLine.price`
> 에 담는다).

⚠️ 종전 이 파일은 *"배당 숫자는 받지 않고, 있으면 버린다"* 였다 — 그 규칙은 **걷혔다.**
🔴 쓰임은 **확률**까지다: 기대값·금액은 어디에도 만들지 않는다(§0 금지).
>
> 파서는 **코드**(정규식 + 사전)로: 마켓 이름 사전을 `config/board_words.yaml` 에.
> 못 읽은 줄은 카드에 *"보드 줄 못 읽음: …"* 으로 그대로 보여 준다(조용히 버리지 않는다).

🔴 **LLM 이 보드를 읽지 않는다** — 모델이 마켓을 지으면 그것이 거짓 보드가 되고,
   그 거짓이 판정 수에 곧바로 들어간다(절대규칙 6 이 막는 자리).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.core.schema import Board, BoardLine


def words() -> dict:
    """🔴 낱말표 — `config/board_words.yaml` 하나가 원본이다(사본 금지)."""
    from app import rules
    return dict(rules._load("config/board_words.yaml") or {})


def _norm(said: str) -> str:
    return " ".join(str(said or "").lower().split())


def _head_of(line: str, box: dict) -> str:
    """🔴 그 줄이 `보드:` 인가 `추가:` 인가 — 아니면 빈 글자(이어지는 줄)."""
    low = _norm(line)
    heads = dict(box.get("heads") or {})
    for kind in ("extra", "base"):
        for w in heads.get(kind) or []:
            if low.startswith(f"{str(w).lower()}:") or low.startswith(f"{w} :"):
                return kind
    return ""


def _after_head(line: str) -> str:
    return line.split(":", 1)[1] if ":" in line else line


def parse(text: str) -> tuple[Board, list[str], list[str]]:
    """🔴🔴 보드 글 → `(Board, 추가 옵션 줄, 못 읽은 줄)`.

    🔴 `추가:` 줄의 마켓은 **별도 목록**으로 돌려준다 — 카드가 *"추가 옵션에 있으면"*
       묶음으로 적는다(§4 · 사용자 규칙).
    ⚠️ **전반·후반 마켓은 대입하지 않는다** — 그 사실을 못 읽은 줄이 아니라 **사유와
       함께** 돌려준다(시나리오는 90분 스코어다).
    """
    box = words()
    base: list[BoardLine] = []
    extra: list[str] = []
    bad: list[str] = []
    kind = "base"
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        got = _head_of(line, box)
        if got:
            kind = got
            line = _after_head(line).strip()
            if not line:
                continue
        for part in re.split(r"[/·,]| {2,}", line):
            said = part.strip()
            if not said:
                continue
            rows, why = _one(said, box)
            if not rows:
                bad.append(f"{said} — {why}")
                continue
            if kind == "extra":
                extra += [f"{r.market} {r.side}"
                          f"{(' ' + str(r.point)) if r.point is not None else ''}"
                          for r in rows]
            base += rows
    return Board(lines=base), extra, bad


def _one(said: str, box: dict) -> tuple[list[BoardLine], str]:
    """🔴 한 조각 → 줄들. ⚠️ 못 읽으면 **사유를 돌려준다**(조용히 버리지 않는다)."""
    low = _norm(said)
    half = dict(box.get("halves") or {})
    for w in half.get("words") or []:
        if str(w).lower() in low:
            return [], str(half.get("why") or "반 단위 마켓")
    for row in box.get("markets") or []:
        if not any(str(w).lower() in low for w in (row.get("words") or [])):
            continue
        market = str(row.get("market"))
        side_team = str(row.get("side_team") or "")
        # 🔴🔴 **기준선을 쓰는 마켓만** 첫 숫자를 기준선으로 본다(§2-6).
        #    ⚠️ 실측 2026-10-06: 그 구분이 없어 `승무패 1.66 3.79 4.55` 의 **1.66 을
        #       기준선으로** 읽고 배당 셋을 잃었다. 승무패·더블찬스·양팀득점에는
        #       기준선이 없다 — 그 줄의 숫자는 **전부 배당**이다.
        has_point = not row.get("expand")
        point = _point_of(low, box) if has_point else None
        price = _price_of(low, box, point=point)
        prices = _prices_of(low, box, point=point)
        if row.get("expand"):
            return _expand([str(x) for x in row["expand"]], point,
                           price=price, prices=prices), ""
        if market == "handicap":
            # 🔴 핸디는 **줄 하나에 두 쪽**이다(§6-c-3) — 기준선 부호가 쪽을 말한다
            if point is None:
                return [], "핸디 기준선을 못 읽었다"
            # ⚠️ 배당 하나는 **그 줄이 적은 쪽**의 것이다 — 반대쪽에 복사하지 않는다
            return ([BoardLine(market="handicap", side="home", point=point,
                               price=price),
                     BoardLine(market="handicap", side="away", point=-point)],
                    "")
        if market == "total":
            if point is None:
                return [], "총점 기준선을 못 읽었다"
            side = f"{side_team}_" if side_team else ""
            return ([BoardLine(market="total", side=f"{side}over", point=point,
                               price=price),
                     BoardLine(market="total", side=f"{side}under", point=point)],
                    "")
        return [BoardLine(market=market, side="",                 # type: ignore[arg-type]
                          price=price)], ""
    return [], "마켓 이름을 사전에서 못 찾았다"


def _expand(names: list[str], point: float | None, *,
            price: float | None = None,
            prices: list[float] | None = None) -> list[BoardLine]:
    """🔴 `승무패` 처럼 **여러 줄로 펼치는** 마켓."""
    table = {"win_home": ("win", "home"), "win_away": ("win", "away"),
             "draw": ("draw", ""), "unbeaten_home": ("unbeaten", "home"),
             "unbeaten_away": ("unbeaten", "away"),
             "btts_yes": ("btts", "yes"), "btts_no": ("btts", "no")}
    out: list[BoardLine] = []
    # 🔴🔴 §2-6 — `승무패 1.66 3.79 4.55` 처럼 **줄 수만큼** 배당이 오면 순서대로 붙인다.
    #    ⚠️ 수가 안 맞으면 **아무 쪽에도 안 붙인다** — 어느 쪽 배당인지 모르기 때문이다
    #       (실측 설계: 둘만 온 승무패 줄에 홈/무를 찍어 주면 확률이 거짓이 된다).
    many = list(prices or [])
    ordered = many if len(many) == len(names) else []
    for i, name in enumerate(names):
        got = table.get(name)
        if got is None:
            continue
        mine = ordered[i] if ordered else (price if len(names) == 1 else None)
        out.append(BoardLine(market=got[0], side=got[1],        # type: ignore[arg-type]
                             price=mine))
    return out


def _point_of(low: str, box: dict) -> float | None:
    """🔴 기준선 — **첫 숫자**다(`언더오버 2.5 1.85` 의 2.5).

    ⚠️ 두 번째 숫자는 기준선이 아니다 — **배당**이고 `_price_of` 가 가져간다(§2-6).
    """
    got = _numbers(low, box)
    return got[0] if got else None


def _prices_of(low: str, box: dict, *, point: float | None) -> list[float]:
    """🔴 그 줄의 배당 **전부**(순서대로). ⚠️ `승무패 1.66 3.79 4.55` 처럼 셋이 올 수 있다."""
    got = _numbers(low, box)
    said = got[1:] if point is not None and got else got
    return [v for v in said if v >= 1.01]


def _price_of(low: str, box: dict, *, point: float | None) -> float | None:
    """🔴🔴 §2-6 — **배당**을 읽는다. ⚠️ 없으면 `None`(0 이 아니다).

    🔴 어느 숫자가 배당인가 — 규칙 하나로 가른다:
         기준선이 있는 줄(`언더오버 2.5 1.85`) → **두 번째** 숫자
         기준선이 없는 줄(`승 1.66`)          → **첫** 숫자
    ⚠️ 소수 배당은 **1.01 이상**이다 — 그보다 작으면 배당이 아니므로 안 담는다
       (실측: `핸디 -0.5 1.95` 에서 `-0.5` 를 배당으로 읽으면 확률이 거짓이 된다).
    """
    got = _prices_of(low, box, point=point)
    return got[0] if got else None


def _numbers(low: str, box: dict) -> list[float]:
    out: list[float] = []
    for raw in re.findall(str(box.get("point") or r"[-+]?\d+(?:\.\d+)?"), low):
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **보드에서 경기 단서를 읽는다** — 사용자 지시 2026-10-10(재작성) §1-1 ①
# ══════════════════════════════════════════════════════════════════
#
#  > 보드가 있으면 보드의 **날짜·시각·두 팀·리그 표기를 먼저 읽는다**(이게 가장
#  > 정확한 단서다).
#
#  🔴 위 `parse` 는 **배당 줄만** 읽는다 — 경기 신원은 안 본다. 여기서 읽는다.
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
