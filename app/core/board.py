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
