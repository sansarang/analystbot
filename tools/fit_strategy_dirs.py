"""🔴🔴 **전략 갈래 → 방향 표를 딥서치로 채운다** — 사용자 지시 2026-10-15.

> 예: 수비 라인 낮음 → 총골 down, 압박 높이 낮음 → 상대 유리 **딥서치해서 넣어라**

```
PYTHONPATH=. uv run python tools/fit_strategy_dirs.py            # 전부
PYTHONPATH=. uv run python tools/fit_strategy_dirs.py --only "수비 라인"
```

🔴🔴 **규율 넷**
  ① 값은 **문서에서** 온다 — 모델 기억이 아니다. 인용(`quote`)과 주소(`url`)가
     없으면 그 줄은 **안 쓴다**(#4 추측 금지).
  ② 모델이 내는 것은 **고른 글자**(`goals`·`favors`)와 **원문 인용**뿐이다.
     수(계수·가중)는 **없다** — 계약이 그것을 센다.
  ③ 못 찾은 갈래는 **⬜ 로 남긴다**(0 으로 채우지 않는다 · #3).
  ④ 쓰는 곳은 `config/strategy_dirs.yaml` 하나이고, 그것을 읽는 곳은
     `app/core/strategy_llm.vars_of` 하나다(사본 금지).

⚠️ 이 표는 **문헌 근거**이지 우리 원장 측정이 아니다 — 그래서 모든 줄에
   `fit: "문헌"` 이 박힌다(원장으로 계수를 맞추는 것은 금지다).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "config" / "strategy_dirs.yaml"

#: 🔴 갈래마다 던질 **영어 질의**(문지기 규칙: 낱말 1~6 · 연산자·연도 금지)
QUERIES: dict[str, list[str]] = {
    "압박 높이": ["high press effect goals", "low block press goals conceded"],
    "수비 라인": ["deep defensive line goals", "high defensive line goals"],
    "빌드업": ["slow buildup fewer goals", "direct play more goals"],
    "측면 집중": ["wing play crosses goals", "crossing conversion rate"],
    "중원 수싸움": ["midfield control possession goals", "double pivot goals"],
    "역습 성향": ["counter attack goals efficiency", "transition goals rate"],
    "세트피스": ["set piece goals share", "corner conversion rate"],
    "교체 운용": ["substitutions impact goals", "fresh legs late goals"],
}
#: 🔴 한 갈래에 열 문서 수 상한
OPEN_CAP = 3


class DirRead:
    """자리 표시 — 아래에서 pydantic 으로 다시 만든다."""


def _schema():
    from pydantic import BaseModel, Field

    class Out(BaseModel):
        #: 🔴 총골 방향 — `up`·`down`·`none`(모르면 `none`)
        goals: str = "none"
        #: 🔴 유불리 — `subject`(그 전략을 쓰는 팀)·`opponent`·`both`
        favors: str = "both"
        #: 🔴 **원문 인용** — 없으면 그 줄을 버린다
        quote: str = ""
        why: str = Field(default="", description="한 줄 근거")

    return Out


async def one(kind: str, *, net, chain, state) -> dict:
    """🔴 갈래 하나 — 검색 → 본문 → 모델이 **문서에서** 방향을 읽는다."""
    from app.core import llm
    from app.core.search import fetch as _ft

    said_docs: list[tuple[str, str]] = []
    for q in QUERIES.get(kind, []):
        try:
            hits = await chain.query(q, lang="en")
        except Exception as exc:                            # noqa: BLE001
            print(f"  🔴 검색 실패 `{q}` — {exc!r}", flush=True)
            continue
        print(f"  · `{q}` → {len(hits)}건", flush=True)
        for h in list(hits)[:OPEN_CAP]:
            url = str(getattr(h, "url", "") or "")
            if not url or any(url == u for u, _ in said_docs):
                continue
            try:
                body, _when, _rungs = await _ft.body_of(net, url)
            except Exception:                               # noqa: BLE001
                continue
            if len(str(body or "")) < 400:
                continue
            said_docs.append((url, str(body)[:4000]))
            if len(said_docs) >= OPEN_CAP:
                break
        if len(said_docs) >= OPEN_CAP:
            break
    if not said_docs:
        return {"goals": "none", "favors": "both", "fit": "문헌",
                "why": "⬜ 문서를 못 받았다 — 비워 둔다", "url": "", "quote": ""}

    Out = _schema()
    said_body = "\n\n".join(f"[{i+1}] {u}\n{b[:1800]}"
                            for i, (u, b) in enumerate(said_docs))
    msgs = [
        llm.Message(role="system", content=(
            "너는 **문서에서 사실만 뽑는 사람**이다. 네 기억으로 답하지 말고 "
            "아래 글에 **적힌 것만** 고른다. 글에 없으면 `none`·`both` 로 둔다.")),
        llm.Message(role="user", content=(
            f"전술 갈래: **{kind}**\n\n{said_body}\n\n"
            "🔴 위 글이 이 갈래에 대해 말하는 것을 고른다.\n"
            "  · `goals` — 그 전술이 **경기 총 득점**을 올리나(`up`)·내리나"
            "(`down`)·말이 없나(`none`)\n"
            "  · `favors` — 그 전술을 **쓰는 팀**에 유리(`subject`)·"
            "**상대**에 유리(`opponent`)·모름(`both`)\n"
            "  · `quote` — 그 판단의 **원문 한 문장**(글자 그대로 · 없으면 비움)\n"
            "  · `why` — 한 줄 근거(60자 안)\n"
            "⚠️ 수(퍼센트·계수)를 적지 않는다. 글에 없으면 `none`·`both` 다.")),
    ]
    got, said_pv = llm.ask_first(purpose="recall", messages=msgs, out=Out,
                                 state=state)
    if not isinstance(got, Out):
        return {"goals": "none", "favors": "both", "fit": "문헌",
                "why": f"⬜ 모델 실패({said_pv})", "url": "", "quote": ""}
    quote = str(got.quote or "").strip()
    url = next((u for u, b in said_docs if quote and quote[:40] in b), "")
    if not quote or not url:
        # 🔴 인용이 문서에 없으면 **안 쓴다**(지어낸 것이다 · #4)
        return {"goals": "none", "favors": "both", "fit": "문헌",
                "why": "⬜ 인용을 문서에서 못 찾았다 — 비워 둔다",
                "url": "", "quote": ""}
    return {"goals": str(got.goals or "none"), "favors": str(got.favors or "both"),
            "fit": "문헌", "why": str(got.why or "")[:120], "url": url,
            "quote": quote[:200]}


async def main(argv: list[str]) -> int:
    import yaml

    from app import rules  # noqa: F401
    from app import search as _search
    from app.core.state import RunState
    from app.net import Net

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv[1:])

    kinds = [args.only] if args.only else list(QUERIES)
    net, chain, st = Net(cache=True), _search.build_chain(), RunState()
    box: dict = {}
    if OUT.exists():
        box = dict(yaml.safe_load(OUT.read_text(encoding="utf-8")) or {})
    rows = dict(box.get("rows") or {})
    for kind in kinds:
        print(f"\n## {kind}", flush=True)
        got = await one(kind, net=net, chain=chain, state=st)
        rows[kind] = got
        print(f"  → goals **{got['goals']}** · favors **{got['favors']}** · "
              f"{got['why'][:70]}", flush=True)
    out = {"source": "딥서치(문헌) — 사용자 지시 2026-10-15",
           "rule": ("🔴 값은 문서에서 온다 · 인용 없는 줄은 비운다 · "
                    "원장으로 맞추지 않는다"),
           "rows": rows}
    OUT.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    filled = sum(1 for v in rows.values()
                 if str(v.get("goals")) != "none" or str(v.get("favors")) != "both")
    print(f"\n🔴 채운 갈래 **{filled}/{len(rows)}** — {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
