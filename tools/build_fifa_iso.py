"""🔴🔴 **`data/fifa_to_iso.yaml` 을 만든다** — 사용자 지시 2026-10-10(재작성) §1-5.

> 나라 FIFA 코드 → `data/fifa_to_iso.yaml`(**공개 목록**, 출처·확인일 머리에)
> → ISO → CLDR 언어.

```
PYTHONPATH=. python tools/build_fifa_iso.py          # 받아서 다시 만든다
PYTHONPATH=. python tools/build_fifa_iso.py --check  # 바뀐 것만 찍는다(안 쓴다)
```

🔴 **손으로 표를 유지하지 않는다**(CLAUDE.md #1 사본 금지) — 이 도구가 원본이고
   파일은 그 산출물이다. 출처가 바뀌면 다시 돌린다.
🔴 ISO 로 바꾸는 길은 **CLDR 둘뿐**이다: `territory_aliases`(ISO3→ISO2)와 영어
   지역명 **정확 일치**. ⚠️ **부분 일치는 쓰지 않는다** — 실측 2026-10-10에
   `NIR`(북아일랜드)이 `IE`(아일랜드)에 붙었다(`"ireland" in "northernireland"`).
⚠️ 못 맞춘 코드는 **지어내지 않고** `unmatched:` 에 이름으로 남긴다(#3).
"""
from __future__ import annotations

import asyncio
import html
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fifa_to_iso.yaml"
SOURCE = "https://en.wikipedia.org/wiki/List_of_FIFA_country_codes"
#: 🔴 ISO 국가가 아닌 **축구협회 넷** — 사용자가 언어를 지정했다(§1-5)
ASSOC_LANGS = {"ENG": ["en"], "SCO": ["en"], "WAL": ["en"], "NIR": ["en"]}


def _norm(said: object) -> str:
    """🔴 지역명 대조용 꼴 — 악센트·기호를 벗기고 `&`·`st.` 를 펼친다."""
    low = unicodedata.normalize("NFKD", str(said or "").lower())
    low = "".join(c for c in low if not unicodedata.combining(c))
    low = low.replace("&", " and ").replace("st.", "saint")
    return re.sub(r"[^a-z]", "", low)


def rows_of(text: str) -> list[tuple[str, str]]:
    """🔴 공개 목록 HTML → `[(FIFA 코드, 나라 이름)]`.

    ⚠️ 표의 칸 순서는 **`나라 … 코드`** 다(실측 2026-10-10) — 코드는 **마지막**
       칸이다. 🔴 세 대문자가 아닌 칸은 코드가 아니다(건너뛴다).
    """
    out: list[tuple[str, str]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 2:
            continue
        code = html.unescape(re.sub(r"<[^>]+>", "", cells[-1])).strip()
        if not re.fullmatch(r"[A-Z]{3}", code):
            continue
        name = html.unescape(re.sub(r"<[^>]+>", "", cells[0])).strip()
        name = re.sub(r"\s+", " ", name)
        if name:
            out.append((code, name))
    return out


def map_iso(rows: list[tuple[str, str]]) -> tuple[dict, list]:
    """🔴 `(코드→(ISO2, 어느 CLDR 표가 맞혔나), 못 맞춘 것들)`."""
    from babel import Locale
    from babel.core import get_global
    alias = get_global("territory_aliases") or {}
    rev: dict[str, str] = {}
    for cc, nm in Locale("en").territories.items():
        if len(cc) == 2:
            rev.setdefault(_norm(nm), cc)
    got: dict[str, tuple[str, str]] = {}
    miss: list[tuple[str, str]] = []
    for code, name in rows:
        two = [str(x) for x in (alias.get(code) or []) if len(str(x)) == 2]
        if two:
            got[code] = (two[0], "CLDR territory_aliases")
            continue
        cc = rev.get(_norm(name))
        if cc:
            got[code] = (cc, "CLDR 영어 지역명(정확)")
            continue
        miss.append((code, name))
    return got, miss


async def main(argv: list[str]) -> int:
    from app import net as _net_mod
    net = _net_mod.Net()
    page = await net.get(SOURCE)
    text = getattr(page, "text", "") or ""
    if not text:
        print(f"🔴 받지 못했다 — {getattr(page, 'reason', '?')}")
        return 1
    rows = rows_of(text)
    got, miss = map_iso(rows)
    print(f"행 {len(rows)} · 매핑 {len(got)} · 못 맞춘 {len(miss)}")
    if "--check" in argv:
        import yaml
        old = yaml.safe_load(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        now = {k: v[0] for k, v in got.items()}
        was = dict((old.get("iso") or {}))
        for k in sorted(set(now) | set(was)):
            if now.get(k) != was.get(k):
                print(f"  🔴 {k}: {was.get(k)} → {now.get(k)}")
        return 0
    print("⚠️ 파일 쓰기는 사람이 확인한 뒤에 한다 — `--check` 로 바뀐 것만 본다")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
