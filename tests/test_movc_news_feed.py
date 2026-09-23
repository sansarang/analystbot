"""[MOV-C] 1·2단계 — 검색을 Go 로 앞당긴다. **LLM 0 을 지킨 채로.**

사용자 2026-09-23: "bing duck duck go 등을 초기에 고랭과 같이 서치의 단계를
옮기면 어떻게 되냐" · "이유 미상은 없다" · "배당률 분석은 초기부터"

🔴 **검색은 LLM 이 아니다.** `bing_news_rss` 는 RSS 라 제목·URL·발행시각을
   **구조화해서** 준다. LLM 은 기사 본문에서 칸을 뽑을 때만 필요하고, 그
   단계는 여기서 하지 않는다 — `llm.enabled: false` 가 그대로 지켜진다.

🔴 실측이 이것을 요구했다 (2026-09-22~23):
```
Go 변화(선발·라인업) × 배당 이동 시각 맞추기
  창 ±30분   2%p 이상 이동 15건 중 7건만 설명 (46.7%)
```
나머지를 설명할 채널이 뉴스다.

🔴 **Go 모듈에 YAML 파서를 넣지 않는다.** 파이썬이 `search_terms.yaml` 을
   풀어 Redis 에 싣고 Go 는 읽기만 한다 — 질의의 원본은 한 곳 그대로다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.collectors import crawler_feed as CF

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _R:
    def __init__(self):
        self.sets = []

    async def set(self, k, v, ex=None):
        self.sets.append((k, v, ex))


# ── 발행 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_리그별_질의와_로케일을_싣는다():
    r = _R()
    n = await CF.publish_news_feeds(r)
    assert n >= 3, n
    k, raw, ttl = r.sets[0]
    assert k == CF.NEWS_FEEDS_KEY and ttl == CF.NEWS_FEEDS_TTL_SEC
    doc = json.loads(raw)
    for lg in ("kbo", "npb", "mlb"):
        assert set(doc[lg]) == {"q", "hl", "gl"}, doc[lg]
        assert doc[lg]["q"] and doc[lg]["hl"] and doc[lg]["gl"]


@pytest.mark.asyncio
async def test_로케일이_없으면_싣지_않는다(monkeypatch):
    """🔴 언어 없이 던지면 엉뚱한 나라 기사가 온다 — 실측 2026-09-12
    (맥도날드·연예 기사). 지어내지 않고 **뺀다.**"""
    import app.engine.scout_config as SC

    monkeypatch.setattr(SC, "NEWS_FEEDS", {"kbo": "q", "zzz": "q2"})
    monkeypatch.setattr(SC, "LOCALES", {"kbo": {"hl": "ko", "gl": "KR"}})
    r = _R()
    assert await CF.publish_news_feeds(r) == 1
    assert set(json.loads(r.sets[0][1])) == {"kbo"}


@pytest.mark.asyncio
async def test_실패해도_예외를_올리지_않는다():
    """🔴 뉴스는 부가 채널이다. 이것 때문에 스케줄러 기동이 죽으면 안 된다."""
    class _Boom:
        async def set(self, *a, **k):
            raise RuntimeError("redis 없음")

    assert await CF.publish_news_feeds(_Boom()) == 0
    assert await CF.publish_news_feeds(None) == 0


@pytest.mark.asyncio
async def test_질의가_비면_싣지_않는다(monkeypatch):
    import app.engine.scout_config as SC

    monkeypatch.setattr(SC, "NEWS_FEEDS", {"kbo": ""})
    assert await CF.publish_news_feeds(_R()) == 0


# ── 원본이 하나다 ───────────────────────────────────────────────────

def test_질의의_원본은_yaml_한_곳이다():
    """🔴 사본 금지 — 코드에 질의를 손으로 적지 않는다."""
    import inspect

    from app.engine.scout_config import NEWS_FEEDS

    assert NEWS_FEEDS, "config/search_terms.yaml 의 feed: 가 비었다"
    src = inspect.getsource(CF.publish_news_feeds)
    for lg, q in NEWS_FEEDS.items():
        assert q not in src, f"질의를 코드에 적었다: {lg}"


def test_go_와_파이썬이_같은_키를_쓴다():
    """🔴 **양쪽에 문자열이 있으니 사본이다.** 한쪽만 바뀌면 Go 가 영영 빈
    설정을 읽고 뉴스가 **조용히 0** 이 된다. 여기서 대조해 잠근다."""
    go = (ROOT / "crawler/internal/store/store.go").read_text(encoding="utf-8")
    assert f'newsFeedsKey = "{CF.NEWS_FEEDS_KEY}"' in go, CF.NEWS_FEEDS_KEY


def test_go_가_쓰는_칸_이름이_파이썬과_같다():
    """⚠️ `q`·`hl`·`gl` — Go 구조체 태그와 발행 모양이 어긋나면 전건 빈 값이다."""
    go = (ROOT / "crawler/internal/source/news.go").read_text(encoding="utf-8")
    for tag in ('json:"q"', 'json:"hl"', 'json:"gl"'):
        assert tag in go, tag


# ── 분리 ────────────────────────────────────────────────────────────

def test_뉴스가_라인업과_다른_키에_쌓인다():
    """🔴 검색이 막혀도 라인업 크롤은 살아야 한다(2단계). 같은 종목 키를
    쓰면 스냅샷이 섞이고 게이트가 기사 제목을 검사하게 된다."""
    go = (ROOT / "crawler/internal/source/news.go").read_text(encoding="utf-8")
    assert 'return "news_" + league' in go

    main = (ROOT / "crawler/cmd/crawler/main.go").read_text(encoding="utf-8")
    assert "onceNews" in main, "크롤러가 뉴스를 긁지 않는다"
    i_news = main.index("func onceNews")
    seg = main[i_news:main.index("func once(", i_news)]
    assert "gate.Apply" not in seg, "뉴스에 라인업 게이트를 태운다"
    assert "continue" in seg, "한 리그 실패가 전체를 멈춘다"


def test_스케줄러가_기동에_발행한다():
    """🔴 배선의 끝 — 안 부르면 Go 는 영영 빈 설정을 읽는다.
    이 저장소가 반복한 '만들어 놓고 안 이음'이 바로 이 자리다."""
    import inspect

    from app import scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S.main).splitlines())
    assert "publish_news_feeds" in src


def test_예산을_넘지_않는_주기다():
    """⚠️ 리그 3 × (24h / 20m = 72) = 216/일 < 상한 400.
    10분이면 432/일로 넘는다."""
    import yaml

    doc = yaml.safe_load((ROOT / "config/deepsearch.yaml").read_text(encoding="utf-8"))
    cap = int(doc["search"]["providers"]["bing_news_rss"]["daily_query_cap"])
    main = (ROOT / "crawler/cmd/crawler/main.go").read_text(encoding="utf-8")
    assert '"news-interval", 20*time.Minute' in main, "뉴스 주기가 20분이 아니다"
    from app.engine.scout_config import NEWS_FEEDS
    assert len(NEWS_FEEDS) * (24 * 60 // 20) <= cap, "질의 상한을 넘는다"
