"""🔴🔴 **보드 파서** — 사용자가 붙여 넣은 글 → `Board`(축구 완성 지시서 §4).

> 사용자가 보드를 텍스트로 붙여 넣는다. **배당 숫자는 받지 않고, 있으면 버린다**
> (사용자 규칙: 시장 배제).
>
> 파서는 **코드**(정규식 + 사전)로: 마켓 이름 사전을 `config/board_words.yaml` 에.
> 못 읽은 줄은 카드에 *"보드 줄 못 읽음: …"* 으로 그대로 보여 준다(조용히 버리지 않는다).

🔴 **LLM 이 보드를 읽지 않는다** — 모델이 마켓을 지으면 그것이 거짓 보드가 되고,
   그 거짓이 판정 수에 곧바로 들어간다(절대규칙 6 이 막는 자리).
"""
from __future__ import annotations

import re

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
    point = _point_of(low, box)
    for row in box.get("markets") or []:
        if not any(str(w).lower() in low for w in (row.get("words") or [])):
            continue
        market = str(row.get("market"))
        side_team = str(row.get("side_team") or "")
        if row.get("expand"):
            return _expand([str(x) for x in row["expand"]], point), ""
        if market == "handicap":
            # 🔴 핸디는 **줄 하나에 두 쪽**이다(§6-c-3) — 기준선 부호가 쪽을 말한다
            if point is None:
                return [], "핸디 기준선을 못 읽었다"
            return ([BoardLine(market="handicap", side="home", point=point),
                     BoardLine(market="handicap", side="away", point=-point)],
                    "")
        if market == "total":
            if point is None:
                return [], "총점 기준선을 못 읽었다"
            side = f"{side_team}_" if side_team else ""
            return ([BoardLine(market="total", side=f"{side}over", point=point),
                     BoardLine(market="total", side=f"{side}under", point=point)],
                    "")
        return [BoardLine(market=market, side="")], ""   # type: ignore[arg-type]
    return [], "마켓 이름을 사전에서 못 찾았다"


def _expand(names: list[str], point: float | None) -> list[BoardLine]:
    """🔴 `승무패` 처럼 **여러 줄로 펼치는** 마켓."""
    table = {"win_home": ("win", "home"), "win_away": ("win", "away"),
             "draw": ("draw", ""), "unbeaten_home": ("unbeaten", "home"),
             "unbeaten_away": ("unbeaten", "away"),
             "btts_yes": ("btts", "yes"), "btts_no": ("btts", "no")}
    out: list[BoardLine] = []
    for name in names:
        got = table.get(name)
        if got is None:
            continue
        out.append(BoardLine(market=got[0], side=got[1]))  # type: ignore[arg-type]
    return out


def _point_of(low: str, box: dict) -> float | None:
    """🔴 기준선 하나 — ⚠️ **배당 숫자는 받지 않는다**(§4 금지).

    🔴 그래서 **첫 숫자 하나만** 쓴다: 보드 줄의 꼴은 `언더오버 2.5` 이고 배당은
       그 뒤에 붙는다(`2.5 1.85`). ⚠️ 두 번째 숫자는 **버린다** — 그 사실이 이
       독스트링이다(조용한 처리가 아니다).
    """
    got = re.findall(str(box.get("point") or r"[-+]?\d+(?:\.\d+)?"), low)
    if not got:
        return None
    try:
        return float(got[0])
    except ValueError:
        return None
