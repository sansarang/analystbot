"""🔴🔴 **대회 이력 칸 외부 대조**(수정 지시 2026-10-14c ③).

```
PYTHONPATH=. python tools/comp_record_verify.py --comp league:UCL --seasons 2 \
    --teams "Sporting CP,Lens"
```

> 3 외부 대조 (UEFA·AFC 공식 결과) — 스포르팅 2024/25·2025/26 · 랑스 · 알사드 ·
>   알힐랄 · 부리람 표를 공식 결과와 대조한 표 보고(경기별 스코어까지).
>   불일치 0 될 때까지 이 칸은 🔴 "검증 전 — 판단에 쓰지 말 것" 꼬리표.

🔴🔴 **공식 사이트는 숫자를 안 준다 — 받아서 확인했다**(2026-10-14):
   · `uefa.com/uefachampionsleague/fixtures-results/` → 200 · 78KB · **스코어 0개**
     (JS 렌더) · 페이지·번들에 `match.uefa.com` **호스트만** 있고 경로가 없다.
     ⚠️ 경로를 추측해 두 번 던졌고 둘 다 404 였다 → **추측을 멈췄다**(#4).
   · `the-afc.com/.../matches.html` → 200 · 30KB · **스코어 0개**(JS 렌더).
   · 위키백과 `/w/` (API·action=raw)는 **robots 가 막는다**(절대규칙 3).
🔴 그래서 **독립 외부 원천**으로 위키백과 *단계별 문서*의 경기 상자를 쓴다 —
   `class="fhome"/"fscore"/"faway"` 가 경기마다 홈·스코어·원정을 들고 있다
   (UEFA 리그 단계 144 + 녹아웃 45 · ACLE 96 + 19 · 실측).
⚠️ **이것은 공식이 아니다.** 그래서 불일치가 0 이어도 판의 `verified` 는
   **올리지 않는다** — 기록만 `cross_checks` 에 남기고 카드 꼬리표는 그대로 🔴 다.
"""
from __future__ import annotations

import argparse
import asyncio
import html as _h
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 대회별 **단계 문서 이름틀**(위키백과 · 시즌은 `2025–26` 꼴 · 엔 대시)
PAGES = {
    "league:UCL": ("{s}_UEFA_Champions_League_league_phase",
                   "{s}_UEFA_Champions_League_knockout_phase"),
    "league:ACLE": ("{s}_AFC_Champions_League_Elite_league_stage",
                    "{s}_AFC_Champions_League_Elite_knockout_stage"),
    "league:ACL2": ("{s}_AFC_Champions_League_Two_league_stage",
                    "{s}_AFC_Champions_League_Two_knockout_stage"),
}

BOX = re.compile(
    r'class="fdate"(?P<d>.{0,600}?)class="fhome"(?P<h>.{0,4000}?)</th>\s*'
    r'<th class="fscore">(?P<s>.{0,200}?)</th>\s*'
    r'<th class="faway"(?P<a>.{0,4000}?)</th>', re.S)

#: 🔴 `fdate` 칸에 든 **ISO 날짜**(`( 2026-02-17 )`)
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _name(cell: str) -> str:
    """🔴 상자 한 칸에서 **팀 이름**만 — 링크 title 이 가장 깨끗하다."""
    got = [g for g in re.findall(r'title="([^"]+)"', cell)
           if "Flag" not in g and "Football" not in g and "Overtime" not in g]
    if got:
        return _h.unescape(got[-1])
    # ⚠️ title 이 없으면 **속성 꼬리를 떼고** 글자만 남긴다(`itemprop=…` 소음)
    txt = re.sub(r"<[^>]+>", " ", cell.split(">", 1)[-1])
    return _h.unescape(re.sub(r"\s+", " ", txt)).strip()


def season_slug(said: str) -> str:
    """🔴 `2025/2026` → `2025–26`(위키백과 표기 · 엔 대시)."""
    got = re.match(r"^(\d{4})/(\d{4})$", str(said or "").strip())
    if not got:
        return str(said or "")
    return f"{got.group(1)}–{got.group(2)[2:]}"


async def outside(comp: str, season: str, *, net) -> tuple[list[dict], str]:
    """🔴 그 시즌의 **외부 경기 목록** — 단계 문서 둘을 합친다."""
    tmpl = PAGES.get(comp)
    if not tmpl:
        return [], f"🔴 `{comp}` 의 외부 문서 이름틀이 없다"
    out: list[dict] = []
    why: list[str] = []
    for one in tmpl:
        page = one.format(s=season_slug(season))
        got = await net.get(f"https://en.wikipedia.org/wiki/{page}")
        t = getattr(got, "text", "") or ""
        if not t:
            why.append(f"⬜ `{page}` 못 받았다")
            continue
        add = 0
        for m in BOX.finditer(t):
            said = _h.unescape(re.sub(r"<[^>]+>", "", m.group("s")))
            said = said.replace("–", "-").strip()
            hit = re.match(r"^(\d+)\s*-\s*(\d+)", said)
            if not hit:
                continue
            day = DATE.search(m.group("d") or "")
            out.append({"home": _name(m.group("h")),
                        "away": _name(m.group("a")),
                        "hg": int(hit.group(1)), "ag": int(hit.group(2)),
                        "score": said, "page": page,
                        "day": day.group(0) if day else ""})
            add += 1
        why.append(f"`{page}` {add}경기")
    return out, " · ".join(why)


def _within(mine: str, theirs: str, *, days: int = 1) -> bool:
    """🔴 두 날짜가 `days` 안인가(시간대 때문에 하루가 밀린다)."""
    from datetime import date
    try:
        a = date.fromisoformat(mine)
        b = date.fromisoformat(theirs)
    except ValueError:
        return False
    return abs((a - b).days) <= days


def pair_of(one: dict, ours: list[dict]) -> tuple[dict | None, str]:
    """🔴🔴 외부 경기 하나를 우리 경기에 **짝으로** 맞춘다.

    ⚠️ 이름 하나씩 맞추면 흔한 이름에서 막힌다(실측 2026-10-14: `Real Madrid CF`
       의 속 낱말 `madrid` 가 `Atlético Madrid` 와 **같은 점수**라 못 골랐다 ·
       그렇게 87경기가 떨어졌다). 🔴 **홈·원정을 함께** 보면 갈린다.
    🔴 점수는 `core/teamname.share` 하나가 만든다(사본 금지).
    """
    from app.core import teamname as _tn
    best: tuple[float, dict | None] = (0.0, None)
    second = 0.0
    # 🔴🔴 **날짜가 먼저 가른다** — 같은 짝이 리그 단계와 녹아웃에 두 번 나오면
    #    이름만으로는 1.00 대 1.00 이 된다(실측 2026-10-14: 58경기가 그랬다).
    said_day = str(one.get("day") or "")[:10]
    if said_day:
        near = [r for r in ours
                if _within(str(r.get("utc") or "")[:10], said_day)]
        if near:
            ours = near
    for r in ours:
        # 🔴 흔한 낱말을 뺀 점수(0.7)와 **안 뺀 점수**(0.3)를 섞는다 —
        #    뒤쪽이 `Real`·`Atlético` 처럼 꾸밈말로 갈리는 이름을 가른다
        got = sum(
            0.7 * _tn.share(one[k], r[k]) + 0.3 * _tn.share(one[k], r[k],
                                                            weak=False)
            for k in ("home", "away")) / 2.0
        if got > best[0]:
            second = best[0]
            best = (got, r)
        elif got > second:
            second = got
    if best[1] is None or best[0] < 0.75:
        return None, f"맞춤 점수 {best[0]:.2f} < 0.75"
    if best[0] - second < 0.1:
        return None, f"후보가 둘 이상이다(1위 {best[0]:.2f} · 2위 {second:.2f})"
    return best[1], f"맞춤 {best[0]:.2f}"


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--teams", default="")
    # 🔴 대조 **기록만** 판에 남긴다 — `verified` 는 **안 올린다**(공식이 아니다)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])

    from app.net import Net
    import fit_comp_record as fcr
    net = Net(cache=True)
    mine, why_mine = await fcr.rows_of(args.comp, seasons=args.seasons)
    print(f"# 🔴🔴 {args.comp} 대회 이력 **외부 대조**(위키백과 단계 문서)")
    print()
    print(f"- 우리 쪽 — {len(mine)}경기({why_mine})")

    want = [x.strip() for x in str(args.teams or "").split(",") if x.strip()]
    rows_out: list[dict] = []
    miss = 0
    gap: list[str] = []
    for season in sorted({str(r["season"]) for r in mine}, reverse=True):
        got, why = await outside(args.comp, season, net=net)
        print(f"- 외부 {season} — {len(got)}경기({why})")
        ours = [r for r in mine if str(r["season"]) == season]
        from app.core import teamname as _tn
        for one in got:
            m, why_pair = pair_of(one, ours)
            if m is None:
                gap.append(f"{season} {one['home']} vs {one['away']}"
                           f"({why_pair})")
                continue
            same = (m["hg"], m["ag"]) == (one["hg"], one["ag"])
            if not same:
                miss += 1
            # 🔴 **불일치는 언제나 적는다** — 고른 팀 밖이어도(③ 의 목적이다)
            mine_team = ((not want) or any(
                _tn.share(w, m["home"]) >= 0.5 or _tn.share(w, m["away"]) >= 0.5
                for w in want))
            if mine_team or not same:
                rows_out.append({
                    "season": season, "home": m["home"], "away": m["away"],
                    "ours": f"{m['hg']}-{m['ag']}",
                    "theirs": f"{one['hg']}-{one['ag']}",
                    "same": same, "stage": m.get("stage") or "",
                    "score_raw": one["score"]})
    print()
    print("| 시즌 | 단계 | 홈 | 원정 | 우리 | 외부 | 같나 |")
    print("|---|---|---|---|---|---|---|")
    for r in sorted(rows_out, key=lambda x: (x["season"], x["home"]),
                    reverse=True):
        print(f"| {r['season']} | {r['stage']} | {r['home']} | {r['away']} | "
              f"{r['ours']} | {r['theirs']} | "
              f"{'✅' if r['same'] else '🔴 다르다'} |")
    print()
    print(f"- 🔴 **스코어 불일치 {miss}건** · 대조한 경기 "
          f"{len(rows_out)}건(표에 적은 것) · 못 맞춘 경기 {len(gap)}건")
    for g in gap[:20]:
        print(f"  · {g}")
    if len(gap) > 20:
        print(f"  · ⚠️ {len(gap) - 20}건 더 있다")
    print()
    print("⚠️ **공식이 아니다** — UEFA·AFC 공식 페이지는 스코어를 HTML 로 주지 "
          "않는다(실측 · 머리글 참조). 그래서 판의 `verified` 는 올리지 않고 "
          "카드 꼬리표는 🔴 **검증 전** 그대로다.")
    if args.write:
        import yaml
        from app.core import comprecord as _cr
        box, why = _cr.plate(args.comp)
        path = _cr.latest(args.comp)
        if not box or path is None:
            print(f"⬜ 판을 못 찾아 기록을 못 남겼다({why})")
            return 0
        rows = list(box.get("cross_checks") or [])
        rows.append({"source": "wikipedia(단계 문서)", "official": False,
                     "mismatch": miss, "compared": len(rows_out),
                     "unmatched": len(gap), "seasons": args.seasons})
        box["cross_checks"] = rows
        path.write_text(yaml.safe_dump(box, allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
        print(f"🔴 **기록을 남겼다** — `{path.relative_to(ROOT)}`"
              f"(`cross_checks` {len(rows)}줄 · `verified` 는 그대로 False)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
