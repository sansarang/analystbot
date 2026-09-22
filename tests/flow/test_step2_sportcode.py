"""[STEP2-1] `_sport_code` 가 **리그를 종목으로** 쓴다 — 축구가 통째로 막혔다.

사용자 2026-09-23: "step 2로 가라..대신에 **모든 스포츠 적용**이라는 것을 명심해라"

🔴 실측 (운영, 최근 3일 `n06_verdict`):
```
종목     변수              확인  반증  미상
soccer  form_recent5        0    0   112     ← 전멸
soccer  xi_confirmed        0    0   305
soccer  rotation_risk       0    0   305
soccer  travel / motivation 0    0   112
mlb     lineup_out        976    0   137     ← 야구는 된다
```
**자료가 없어서가 아니다.** 같은 시각 DB 에는 축구 결과가 리그별로 다 있었다
(EPL 82 · 라리가 127 · 세리에A 97 · … 전부 09-20 까지).

🔴 원인은 한 줄이다:
```python
def _sport_code(state) -> str:
    return (state.league or state.sport or "").lower()   # ← 리그가 먼저다
```
그런데 이 값을 쓰는 **네 곳이 전부 `games.sport`** 를 원한다:
```
125  redis  f"analysis:{sport}:{day}"        ← 구경로가 sport 로 쓴다
193  read_extract(redis, sport, game_id)     ← 위성이 sport 로 쓴다
312  {"kbo": …, "npb": …}[code]              ← 키가 종목이다
410  _LAST3_SQL  WHERE sport = $1            ← games.sport 다
```
야구는 **리그명이 곧 종목코드**라(KBO→kbo) 우연히 맞았고, 축구만 어긋났다
(EPL→"epl" ≠ "soccer").

실측으로 확정:
```
_LAST3_SQL sport='epl'    team='Fulham FC' → 0행
_LAST3_SQL sport='soccer' team='Fulham FC' → 3행 ['09-20 무 1-1', …]
```
"""
from __future__ import annotations

import inspect

from app.flow.nodes import n05_evidence as N5


class _S:
    """흐름 상태 대역.

    🔴 **운영 실측값을 쓴다.** 흐름 스냅샷의 `sport` 는 정규화된
       `"baseball"`(3,464건) · `"soccer"`(536건)이다 — `games.sport` 가
       아니다. 이 사실을 모르고 "sport 를 먼저 보면 된다"고 고쳤다가
       `test_캐시에서_결장을_읽어_증거로_만든다` 에 걸려 되돌렸다.
    """

    def __init__(self, sport, league):
        self.sport, self.league = sport, league


def test_축구는_리그가_아니라_종목이다():
    """🔴 이것이 이 단위의 전부다 — 축구는 리그가 12개인데 sport 는 하나다."""
    for lg in ("EPL", "리그앙", "J1 리그", "에레디비시", "라리가", "K리그1"):
        assert N5._sport_code(_S("soccer", lg)) == "soccer", lg


def test_야구는_달라지지_않는다():
    """⚠️ 반대 위험 — 야구는 **리그명이 곧 종목코드**다. 바뀌면 안 된다.

    🔴 `state.sport` 는 야구에서 `"baseball"` 하나라 kbo/mlb/npb 를 못 가른다.
       그래서 야구는 리그를 쓴다 — `analysis:kbo:…` 캐시 키가 그 증거다.
    """
    for lg, want in (("KBO", "kbo"), ("MLB", "mlb"), ("NPB", "npb")):
        assert N5._sport_code(_S("baseball", lg)) == want


def test_값이_비어도_터지지_않는다():
    """⚠️ 옛 행·픽스처는 칸이 빌 수 있다."""
    assert N5._sport_code(_S("", "KBO")) == "kbo"
    assert N5._sport_code(_S("soccer", "")) == "soccer"
    assert N5._sport_code(_S(None, None)) == ""


def test_구경로_캐시_키와_맞는다():
    """🔴 실측 키 그대로다 — `analysis:kbo:2026-09-22` · `analysis:mlb:…`."""
    assert f"analysis:{N5._sport_code(_S('baseball', 'KBO'))}:2026-09-22" == \
        "analysis:kbo:2026-09-22"


def test_네_곳이_같은_함수를_쓴다():
    """🔴 사본 금지 — 한 곳만 고치면 나머지 셋이 남는다.

    ⚠️ 주석을 뗀다(D46, 이 저장소 9회).
    """
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N5).splitlines())
    assert src.count("_sport_code(state)") >= 4, "쓰는 곳이 줄었다"
    # ⚠️ 원문 훑기는 여기까지다. 더 조이려다 **내 독스트링에 걸렸다**
    #    (`analysis:mlb:2026-09-19` 예시 문장) — D46, 이 저장소 10회째다.
    #    실제 동작은 아래 `test_last3_질의가_종목으로_나간다` 와 위
    #    `test_축구는_리그가_아니라_종목이다` 가 **호출해서** 잡는다.


def test_last3_질의가_종목으로_나간다():
    """🔴 배선의 끝 — `_LAST3_SQL` 은 `WHERE sport = $1` 이다."""
    from app.engine.pick_ledger import _LAST3_SQL

    assert "sport = $1" in _LAST3_SQL
    code = "\n".join(ln.split("#", 1)[0]
                     for ln in inspect.getsource(N5._last3).splitlines())
    assert "_sport_code(state)" in code
