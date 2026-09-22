"""[LOC-3] 리그앙·에레디비시는 **검색이 한 번도 안 나갔다.**

사용자 2026-09-22: "각 리그 그 나라의 언어로 뉴스 검색을 하고 있는지 확인해봐"

🔴 실측 — 검색어는 현지어인데 **로케일이 없었다**:
```
ligue1      검색어 "blessés aujourd'hui"(불어)     로케일 없음
eredivisie  검색어 "blessures vandaag"(네덜란드어)  로케일 없음
denmark     검색어 "forventet startopstilling"(덴마크어)  로케일 en/DK ← 어긋남
```
`rss_hits` 는 로케일이 없으면 **그 자리에서 빈손으로 반환**한다:
```python
loc = locale(league)
if not loc or not query:
    return []
```
즉 두 리그는 기사 검색이 **한 번도 나가지 않았다.**

⚠️ 설정 주석이 "우리 시스템에 리그가 없다"고 적고 있었는데 **틀렸다** —
   `league_labels()` 실측: `리그앙 → ligue1` · `에레디비시 → eredivisie`.
   최근 30일 리그앙 49경기 · 에레디비시 53경기.
"""
from __future__ import annotations

from app.engine import scout_config as SC
from app.leagues import league_labels


def test_세_리그에_로케일이_생겼다():
    """🔴 없으면 `rss_hits` 가 빈손으로 즉시 반환한다."""
    for key in ("ligue1", "eredivisie", "denmark"):
        loc = SC.locale(key)
        assert loc is not None, f"{key} 로케일이 없다 — 검색이 안 나간다"
        assert loc["hl"] and loc["gl"]


def test_검색어_언어와_로케일이_맞는다():
    """🔴 이것이 이 단위의 요점이다 — 불어로 물으면서 hl=en 이면 회수가 준다."""
    want = {"ligue1": "fr", "eredivisie": "nl", "denmark": "da",
            "la_liga": "es", "serie_a": "it", "bundesliga": "de",
            "j1": "ja", "kleague1": "ko", "kbo": "ko", "npb": "ja"}
    for key, hl in want.items():
        loc = SC.locale(key)
        assert loc and loc["hl"] == hl, f"{key}: {loc} (기대 hl={hl})"


def test_우리가_실제로_쓰는_리그에_로케일이_있다():
    """🔴 `league_labels()` 가 원본이다 — 거기 있는 리그는 검색이 나가야 한다.

    ⚠️ UCL·UEL 은 **아직 없다**(D58). 참가국이 섞여 어느 언어로 물을지가
       갈림길이라 지시 없이 정하지 않았다. 이 계약은 그 둘을 **알고 뺀다** —
       모르는 채 빠지는 것과 알고 빼는 것은 다르다.
    """
    known_missing = {"ucl", "uel"}
    missing = []
    for label, key in (league_labels() or {}).items():
        if not key or key in known_missing:
            continue
        if SC.locale(key) is None:
            missing.append(f"{label}({key})")
    assert missing == [], f"로케일 없는 리그: {missing}"


def test_UCL_UEL_은_아직_없다는_사실을_잠근다():
    """⚠️ 누군가 임의로 채우면 여기서 걸린다 — 어느 언어로 물을지는 결정 사항."""
    assert SC.locale("ucl") is None
    assert SC.locale("uel") is None


def test_ceid_를_표에_적지_않았다():
    """🔴 `{gl}:{hl 앞 2자}` 로 코드가 만든다(사본 금지)."""
    import pathlib

    y = (pathlib.Path(__file__).resolve().parents[1]
         / "config" / "search_terms.yaml").read_text(encoding="utf-8")
    block = y[y.index("locales:"):]
    assert "ceid" not in block, "로케일 표에 ceid 를 적었다"
    assert SC.locale("ligue1")["ceid"] == "FR:fr"


def test_종전_리그는_안_바뀌었다():
    """⚠️ 반대 위험 — 3줄 추가가 기존 리그를 건드리면 안 된다."""
    assert SC.locale("epl") == {"hl": "en", "gl": "GB", "ceid": "GB:en"}
    assert SC.locale("acl") == {"hl": "en", "gl": "SG", "ceid": "SG:en"}
    assert SC.locale("mlb") == {"hl": "en", "gl": "US", "ceid": "US:en"}
