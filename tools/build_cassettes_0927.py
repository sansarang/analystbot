"""09-27 실측 응답 → §19-g 게이트 카세트.

`tests/fixtures/2026-09-27/searx_*.json` 은 2026-09-27 에 **실제로 받은** SearXNG
응답이다. §19-g 게이트는 그것을 *"실제 네트워크 없이"* 재현하라고 요구하므로,
이 스크립트가 그 응답을 카세트 열쇠(`sha(kind+url+query)`)로 옮겨 놓는다.

🔴 **투명하게 적는다** — 이 옮김에는 한 가지 근사가 있다:

| 픽스처 | 그날 던진 질의 | 지금 코드가 던지는 질의 | 같나 |
|---|---|---|---|
| `searx_sb` | `ソフトバンク スタメン 9月27日` | `ソフトバンク スタメン 9月27日` | ✅ 같다 |
| `searx_hiroshima` | `広島 スタメン 9月27日 横浜` | `広島 スタメン 9月27日 横浜` | ✅ 같다 |
| `searx_astros` | `Astros probable pitcher September 27` | `Houston Astros probable pitcher Sep 27` | ⚠️ **다르다** |

⚠️ 세 번째는 **같은 날의 응답을 다른 질의의 답으로 저장**한다. 진짜 그 질의를
   던졌다면 결과가 달랐을 수 있다 — 그러므로 그 카세트로 통과한 게이트는
   *"파서가 그날의 스니펫에서 사실을 뽑는다"* 까지만 증명하고, *"우리 검색어가
   그 스니펫을 찾아낸다"* 는 증명하지 못한다. 카세트 파일에 그 사실을 적어 둔다
   (`approx` 칸). 2026-09-27 페이지는 다시 녹음할 수 없다.

돌리는 법:
    PYTHONPATH=. uv run python tools/build_cassettes_0927.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app import cassette
from app.search import SEARXNG_URL, _lang

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 9, 27)
SRC = ROOT / "tests" / "fixtures" / "2026-09-27"

#: (픽스처, 코드가 던지는 질의, 언어, 그날 던진 질의)
#: 🔴 두 질의가 다르면 `approx=True` 로 표시된다 — 게이트 보고가 그것을 읽는다.
PLAN = [
    ("searx_sb.json", "ソフトバンク スタメン 9月27日", "ja", None),
    ("searx_hiroshima.json", "広島 スタメン 9月27日 横浜", "ja", None),
    ("searx_astros.json", "Houston Astros probable pitcher Sep 27", "en",
     "Astros probable pitcher September 27"),
]


def main() -> None:
    made = []
    for name, query, lang, original in PLAN:
        raw = json.loads((SRC / name).read_text(encoding="utf-8"))
        asked = raw.get("query")
        params = {"q": query, "format": "json", "language": _lang(lang)}
        payload = dict(raw)
        payload["fixture"] = name
        if original or (asked and asked != query):
            payload["approx"] = {
                "그날 던진 질의": asked,
                "이 카세트가 답하는 질의": query,
                "뜻": "같은 날의 응답이지만 질의가 다르다 — 이 카세트로 통과한 "
                      "게이트는 파서만 증명하고 검색어는 증명하지 않는다",
            }
        p = cassette.save("search", f"{SEARXNG_URL}/search",
                          cassette.query_string(params), payload, when=DAY)
        made.append((p.name, query, "근사" if "approx" in payload else "정확"))

    print(f"\n{len(made)}건 저장 → tests/fixtures/cassettes/{DAY}/")
    for fn, q, kind in made:
        print(f"  [{kind}] {fn}  ←  {q}")


if __name__ == "__main__":
    main()
