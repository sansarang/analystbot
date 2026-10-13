"""🔴🔴 **1번 — 오프셋 검증**(후속 지시 2026-10-13 밤 1번).

```
PYTHONPATH=. python tools/offset_check.py
```

> 외부 순위와 순위 상관: UEFA 국가 계수(5시즌) · AFC 클럽 대회 순위 vs 우리
> 오프셋 → **스피어만 ρ** 보고. **ρ < 0.6 이면 적합 방식부터 의심.**
> 원인 점검: (1) 수축 K=20 이 너무 센가 — K = 5/10/20 세 판 (2) 국내 리그 Elo
> 척도가 리그마다 달라 오프셋이 그 차를 떠안는가 (3) 대륙 표본이 상위 팀 위주라
> 생기는 치우침. 네 리그의 **상대 리그별 승무패표**도 함께.

🔴 외부 순위는 **받아서 읽는다** — 위키백과 `UEFA_coefficient` ·
   `AFC_club_competitions_ranking` 의 **협회 순위 표**다(손으로 적지 않는다).
🔴 리그 → 나라는 **자동 등록 파일의 `ccode`**(FIFA) → `data/fifa_to_iso.yaml`
   → CLDR 나라 이름으로 잇는다(사본 금지).
⚠️ 이 도구는 **확률을 바꾸지 않는다** — 재고 보고만 한다.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

UEFA_URL = "https://en.wikipedia.org/wiki/UEFA_coefficient"
AFC_URL = "https://en.wikipedia.org/wiki/AFC_club_competitions_ranking"


def _cells(row: str) -> list[str]:
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def _tables(text: str) -> list[str]:
    return re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        text, re.S)


def _country(said: str) -> str:
    """🔴 `England (L, C, LC[c])` → `England`."""
    got = re.sub(r"\(.*$", "", str(said or "")).strip()
    return got.replace("\xa0", " ").replace("\u00a0", " ").strip()


async def uefa_ranks(net) -> tuple[dict, str]:
    """🔴 UEFA **협회 순위**(5시즌 계수 표) — `{나라: 순위}`."""
    got = await net.get(UEFA_URL)
    if not getattr(got, "ok", False):
        return {}, f"🔴 UEFA 표를 못 받았다({getattr(got, 'reason', '')})"
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", _tables(
        getattr(got, "text", "") or "")[1], re.S)
    out: dict[str, int] = {}
    for r in rows[1:]:
        said = _cells(r)
        if len(said) >= 4 and said[0].isdigit():
            name = _country(said[3])
            if name:
                out.setdefault(name, int(said[0]))
    return out, f"위키 `UEFA_coefficient` 협회 순위 {len(out)}개"


async def afc_ranks(net) -> tuple[dict, str]:
    """🔴 AFC **협회 순위**(클럽 대회 순위 표) — `{나라: 순위}`."""
    got = await net.get(AFC_URL)
    if not getattr(got, "ok", False):
        return {}, f"🔴 AFC 표를 못 받았다({getattr(got, 'reason', '')})"
    out: dict[str, int] = {}
    for tb in _tables(getattr(got, "text", "") or ""):
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            said = _cells(r)
            if (len(said) >= 5 and re.match(r"^[EW]\d+$", said[0])
                    and said[1].isdigit()):
                name = _country(said[4])
                if name:
                    out.setdefault(name, int(said[1]))
    return out, f"위키 `AFC_club_competitions_ranking` 협회 순위 {len(out)}개"


def league_country(key: str) -> tuple[str, str]:
    """🔴 리그 열쇠 → **나라 이름**(ccode → ISO → CLDR)."""
    import yaml

    from app.core import autoleague as _al
    box = dict(_al.load(str(key) or "") or {})
    ccode = str(box.get("ccode") or "")
    if not ccode:
        # 🔴 손 표 리그(J1·KL1·PL…) — 대회 표의 `ccode` 가 없으면 이름표를 본다
        said = {"league:J1": "JPN", "league:KL1": "KOR", "league:PL": "ENG",
                "league:PD": "ESP", "league:SA": "ITA", "league:BL1": "GER",
                "league:FL1": "FRA", "league:DED": "NED", "league:PPL": "POR",
                "league:ELC": "ENG", "league:MLS": "USA"}
        ccode = said.get(str(key), "")
        if not ccode:
            return "", f"⬜ `{key}` 나라 코드가 없다"
    # 🔴 **영국 네 협회는 ISO 나라가 아니다** — 외부 표가 적은 그 이름을 쓴다
    #    (`fifa_to_iso.yaml` 머리말도 그 넷을 따로 말한다). 지어낸 이름이 아니라
    #    **그 표의 협회 이름**이다.
    uk = {"ENG": "England", "SCO": "Scotland", "WAL": "Wales",
          "NIR": "Northern Ireland"}
    if ccode in uk:
        return uk[ccode], f"{ccode}→{uk[ccode]}(영국 협회 · ISO 나라 아님)"
    iso = dict(yaml.safe_load(
        (ROOT / "data/fifa_to_iso.yaml").read_text(encoding="utf-8")) or {})
    a2 = str(dict(iso.get("iso") or {}).get(ccode) or "")
    if not a2:
        return "", f"⬜ `{ccode}` 를 ISO 로 못 바꿨다(`fifa_to_iso.yaml`)"
    from babel import Locale
    name = str(Locale("en").territories.get(a2.upper()) or "")
    return name, f"{ccode}→{a2}→{name or '⬜'}"


def spearman(pairs: list[tuple[float, float]]) -> float:
    """🔴 스피어만 ρ — 순위로 바꾼 뒤 피어슨."""
    if len(pairs) < 3:
        return float("nan")

    def ranks(xs: list[float]) -> list[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        out = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            said = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = said
            i = j + 1
        return out
    a = ranks([p[0] for p in pairs])
    b = ranks([p[1] for p in pairs])
    n = len(pairs)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return (num / (da * db)) if da and db else float("nan")


def head_to_head(comp_keys: list[str], *, leagues: list[str]) -> None:
    """🔴 그 리그의 **상대 리그별 승무패**(치우침 점검 · 1번 넷째 조항)."""
    from fit_offsets import box_of
    rows: list[dict] = []
    for key in comp_keys:
        path = box_of(key)
        if path.exists():
            rows += json.loads(path.read_text(encoding="utf-8"))
    for mine in leagues:
        box: dict[str, list[int]] = {}
        for r in rows:
            lh, la = str(r.get("home_league") or ""), str(r.get("away_league")
                                                          or "")
            if mine not in (lh, la) or not (lh and la) or lh == la:
                continue
            them = la if lh == mine else lh
            hg, ag = int(r.get("hg") or 0), int(r.get("ag") or 0)
            gf, ga = (hg, ag) if lh == mine else (ag, hg)
            one = box.setdefault(them, [0, 0, 0, 0, 0])
            one[0 if gf > ga else (1 if gf == ga else 2)] += 1
            one[3] += gf
            one[4] += ga
        print()
        name, _why = league_country(mine)
        print(f"#### `{mine}`({name or '나라 미상'}) — 상대 리그별")
        print()
        print("| 상대 리그 | 승 | 무 | 패 | 득 | 실 |")
        print("|---|---|---|---|---|---|")
        for them, one in sorted(box.items(), key=lambda kv: -sum(kv[1][:3])):
            nm2, _w2 = league_country(them)
            print(f"| `{them}`({nm2 or '?'}) | {one[0]} | {one[1]} | "
                  f"{one[2]} | {one[3]} | {one[4]} |")


async def main(argv: list[str]) -> int:
    import contextlib
    import io

    from fit_offsets import fit
    from app.core import offsets as off
    from app.net import Net
    net = Net(cache=True, day_cache=True)
    print("# 🔴🔴 1번 오프셋 검증 — 외부 순위 상관 · K 비교 · 치우침")
    print()
    got_u, why_u = await uefa_ranks(net)
    got_a, why_a = await afc_ranks(net)
    print(f"- 외부 순위 — {why_u} · {why_a}")
    for conf, ext, comps in (("UEFA", got_u, ["league:UCL"]),
                             ("AFC", got_a, ["league:ACLE", "league:ACL2"])):
        box, why = off.latest_plate(conf)
        rows = dict(box.get("leagues") or {})
        print()
        print(f"## {conf} — {why}")
        print()
        print("| 리그 | 나라 | 우리 오프셋 | 맞대결 | 외부 순위 |")
        print("|---|---|---|---|---|")
        pairs: list[tuple[float, float]] = []
        for key, one in sorted(rows.items(),
                               key=lambda kv: -(dict(kv[1]).get("value")
                                                or -9e9)):
            said = dict(one)
            name, _why = league_country(key)
            rank = ext.get(name)
            print(f"| `{key}` | {name or '⬜'} | "
                  + (f"**{float(said['value']):+.1f}**"
                     if said.get("value") is not None else "⬜ 미산출")
                  + f" | {int(said.get('n') or 0)} | "
                  + (f"{rank}위" if rank else "⬜ 외부 순위 없다") + " |")
            if said.get("value") is not None and rank:
                # 🔴 외부는 **낮은 수가 강팀**이다 → 부호를 뒤집어 짝지운다
                pairs.append((float(said["value"]), -float(rank)))
        said_rho = spearman(pairs)
        print()
        print(f"🔴 **스피어만 ρ = {said_rho:.3f}**(짝 {len(pairs)}개) — "
              + ("✅ **0.6 이상**(적합 방식을 의심하지 않는다)"
                 if said_rho >= 0.6 else
                 "🔴 **0.6 미만 — 적합 방식부터 의심한다**"))
        # 🔴🔴 **ρ 를 판에 적는다**(카드가 그 수를 읽어 🟡 꼬리표를 떼거나 붙인다)
        import yaml as _yaml
        said_path = off.BOX / conf / "verify.yaml"
        said_path.parent.mkdir(parents=True, exist_ok=True)
        said_path.write_text(_yaml.safe_dump(
            {"conf": conf, "rho": round(float(said_rho), 3),
             "pairs": len(pairs), "cut": 0.6,
             "ok": bool(said_rho >= 0.6),
             "source": [UEFA_URL if conf == "UEFA" else AFC_URL],
             "왜": ("외부 협회 순위(위키)와 우리 오프셋의 스피어만 ρ — "
                    "0.6 미만이면 적합 방식부터 의심한다(후속 지시 1번)")},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"🔴 판을 적었다 — `{said_path.relative_to(ROOT)}`")
        # ── 원인 점검 (2) — 리그마다 **Elo 폭**이 다른가
        print()
        print("### 원인 점검 (2) — 국내 리그 Elo 척도(평균 1500 고정)")
        print()
        print("| 리그 | 팀 | Elo 폭(표준편차) | 최고−최저 |")
        print("|---|---|---|---|")
        import statistics as _st
        import yaml as _y2
        for key in sorted(rows):
            path2 = (ROOT / "data/league_elo_auto"
                     / f"{key.replace(':', '_')}.yaml")
            if not path2.exists():
                print(f"| `{key}` | ⬜ | ⬜ 자동 판 없다(재생 덤프로 굴렸다) | ⬜ |")
                continue
            box2 = _y2.safe_load(path2.read_text(encoding="utf-8")) or {}
            vals = [float(v) for v in dict(box2.get("teams") or {}).values()]
            if len(vals) < 3:
                print(f"| `{key}` | {len(vals)} | ⬜ 표본 적다 | ⬜ |")
                continue
            print(f"| `{key}` | {len(vals)} | {_st.pstdev(vals):.0f} | "
                  f"{max(vals) - min(vals):.0f} |")
        # ── K 비교(원인 점검 1)
        print()
        print("### K 비교(수축 벌) — 원인 점검 (1)")
        print()
        print("| K | 적합 손실 | 쓴 경기 | 보기: 가장 센 리그 · 가장 약한 리그 |")
        print("|---|---|---|---|")
        for k in (5, 10, 20):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                said_fit = fit(comps[0], as_of="2026-10-13", ridge_k=k,
                               write=False)
            if not said_fit:
                print(f"| {k} | 🔴 적합 못 했다 | — | — |")
                continue
            vals = dict(said_fit["values"])
            top = max(vals.items(), key=lambda kv: kv[1])
            low = min(vals.items(), key=lambda kv: kv[1])
            print(f"| {k} | {said_fit['loss']:.4f} | {said_fit['used']} | "
                  f"`{top[0]}` {top[1]:+.1f} · `{low[0]}` {low[1]:+.1f} |")
        if conf == "AFC":
            head_to_head(comps, leagues=["league:fotmob536", "league:J1"])
        else:
            head_to_head(comps, leagues=["league:PD", "league:BL1"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
