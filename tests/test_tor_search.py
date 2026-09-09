"""[SAT-7] 토르 경유 검색 — 계약 테스트.

토르는 **순수 보강**이다(기본 꺼짐). 세 리그 모두 직접 경로로 재료를 얻고,
토르는 AWS IP 로 막힌 DDG/Bing 을 출구노드로 되살려 추가 기사를 발굴할 뿐이다.
이 테스트가 잠그는 것:
- DDG lite 결과 파싱(외부 링크·제목·스니펫).
- 토르 바이너리가 없으면 **크래시 없이 False** (보강 생략).
- 한국어 질의는 토르로 보내지 않는다(한국 사이트가 출구노드를 의심해 깨진다).
"""
from __future__ import annotations

import pytest

from app.collectors import tor_search


_DDG_HTML = '''
<table>
<tr><td><a rel="nofollow" class="result-link" href="https://www.mlb.com/news/story-1">Buxton injury update</a></td></tr>
<tr><td class="result-snippet">Byron Buxton placed on the 10-day IL with a hamstring strain.</td></tr>
<tr><td><a rel="nofollow" class="result-link" href="https://duckduckgo.com/y.js?ad">ad</a></td></tr>
<tr><td><a rel="nofollow" class="result-link" href="https://www.espn.com/story-2">Rotation shuffle</a></td></tr>
<tr><td class="result-snippet">Team reshuffles rotation ahead of series.</td></tr>
</table>
'''


def test_parse_ddg_lite_extracts_external_results():
    """외부 결과 링크·제목·스니펫을 뽑고, duckduckgo 내부 링크(광고)는 버린다."""
    out = tor_search.parse_ddg_lite(_DDG_HTML)
    urls = [r["url"] for r in out]
    assert "https://www.mlb.com/news/story-1" in urls
    assert "https://www.espn.com/story-2" in urls
    assert not any("duckduckgo.com" in u for u in urls)   # 광고 제외
    first = out[0]
    assert first["title"] == "Buxton injury update"
    assert "hamstring" in first["snippet"]


@pytest.mark.asyncio
async def test_ensure_tor_no_binary_returns_false(monkeypatch):
    """토르 바이너리가 없으면 크래시하지 않고 False — 보강만 생략된다."""
    monkeypatch.setattr(tor_search.shutil, "which", lambda name: None)
    ok = await tor_search.ensure_tor(timeout=1)
    assert ok is False


@pytest.mark.asyncio
async def test_search_returns_empty_when_tor_unavailable(monkeypatch):
    """토르가 없으면 search 는 빈 리스트(회귀 없음)."""
    async def no_tor(timeout=60):
        return False
    monkeypatch.setattr(tor_search, "ensure_tor", no_tor)
    out = await tor_search.search("Byron Buxton injury")
    assert out == []


def test_korean_query_is_rejected():
    """한국어 질의는 토르로 보내지 않는다 — 출구노드가 한국 사이트에서 깨진다."""
    assert tor_search.is_tor_safe_query("Byron Buxton injury") is True
    assert tor_search.is_tor_safe_query("西武 菅井 先発") is True      # 일본어 허용
    assert tor_search.is_tor_safe_query("한화 이글스 부상") is False   # 한국어 거부
