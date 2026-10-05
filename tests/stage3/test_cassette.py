"""단계 3 계약 — **카세트**(v4 §9 게이트의 전제).

§19-g 원문: *"일곱 건이 **실제 네트워크 없이** 저장된 응답(cassette)으로 재현되고,
그다음 카세트 없이 라이브로 같은 결과가 나와야 단계 통과."*

🔴 그러므로 이 파일이 지켜야 할 것은 하나다: **`replay` 에서 네트워크에 가지
   않는다.** 몰래 가면 CI 가 조용히 라이브를 때리고, 그 실패가 "코드 결함"으로
   읽힌다 — 그리고 "네트워크 없이 재현"이라는 게이트의 근거가 거짓이 된다.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app import cassette
from app.net import Net
from app.search import SearxSearch
from app.net import SearchUnavailable


@pytest.fixture
def cass(tmp_path, monkeypatch):
    """카세트를 임시 폴더로 옮긴다. 🔴 저장소 픽스처를 건드리지 않는다."""
    monkeypatch.setenv(cassette.DIR_ENV, str(tmp_path))
    monkeypatch.setenv(cassette.DAY_ENV, "2026-09-27")
    return tmp_path


# ══════════════════════════════════════════════════════════════════
# 모드
# ══════════════════════════════════════════════════════════════════

def test_기본은_off다(monkeypatch):
    """🔴 **몰래 replay 로 가지 않는다.** 모르는 값도 off 다.

    ⚠️ 오타(`CASSETTE_MODE=relay`)를 replay 로 읽으면 운영이 저장된 응답으로
       돌면서 성공처럼 보인다 — 그것이 가장 나쁜 실패다.
    """
    monkeypatch.delenv(cassette.MODE_ENV, raising=False)
    assert cassette.mode() == cassette.OFF
    monkeypatch.setenv(cassette.MODE_ENV, "relay")     # 오타
    assert cassette.mode() == cassette.OFF
    monkeypatch.setenv(cassette.MODE_ENV, "REPLAY")    # 대문자는 받는다
    assert cassette.mode() == cassette.REPLAY


def test_날짜를_고정할_수_있다(monkeypatch):
    """🔴 §19-g 는 **2026-09-27 실측**이다 — 오늘로 삼으면 영영 못 찾는다."""
    monkeypatch.setenv(cassette.DAY_ENV, "2026-09-27")
    assert str(cassette.day()) == "2026-09-27"
    monkeypatch.setenv(cassette.DAY_ENV, "엉망")
    from datetime import datetime, timedelta, timezone
    # 못 읽으면 오늘 — 🔴 조용히 엉뚱한 날짜로 가지 않는다
    assert cassette.day() == datetime.now(timezone(timedelta(hours=9))).date()


# ══════════════════════════════════════════════════════════════════
# 열쇠
# ══════════════════════════════════════════════════════════════════

def test_열쇠가_url과_질의로_갈린다():
    """🔴 §9 원문: `sha(url+query)`."""
    a = cassette.key("fetch", "https://x/a", "q=1")
    assert a != cassette.key("fetch", "https://x/a", "q=2")
    assert a != cassette.key("fetch", "https://x/b", "q=1")
    # 🔴 열기와 검색을 가른다 — 같은 주소를 두 뜻으로 쓰는 일이 있다
    assert a != cassette.key("search", "https://x/a", "q=1")
    assert a == cassette.key("fetch", "https://x/a", "q=1"), "같은 입력이 달라졌다"


def test_질의_순서가_열쇠를_바꾸지_않는다():
    """⚠️ dict 순서가 열쇠를 바꾸면 **같은 요청이 두 카세트**가 된다."""
    assert cassette.query_string({"a": 1, "b": 2}) \
        == cassette.query_string({"b": 2, "a": 1})


def test_열쇠에_키가_담기지_않는다():
    """🔴 **파일 이름의 재료에 API 키를 넣지 않는다.**

    `?key=AIza…` 가 열쇠에 들어가면 (a) 기계마다 열쇠가 달라져 카세트를 공유할 수
    없고 (b) 무엇보다 그 값이 **저장소에 커밋되는 경로**가 된다(`secrets_mask` 가
    로그를 막는 것과 같은 이유다).
    """
    q = cassette.query_string({"q": "x", "key": "AIzaSECRET123456",
                               "cx": "cx-1", "token": "tok-abcdefgh"})
    for secret in ("AIzaSECRET123456", "cx-1", "tok-abcdefgh"):
        assert secret not in q, f"{secret} 가 열쇠에 담겼다"
    assert "key=" in q and "가림" in q, "무엇이 있었는지는 남아야 한다"


# ══════════════════════════════════════════════════════════════════
# 🔴 replay 는 네트워크에 가지 않는다
# ══════════════════════════════════════════════════════════════════

def _explode(*a, **k):
    raise AssertionError("🔴 replay 인데 네트워크에 갔다")


def test_replay는_열기에서_네트워크에_가지_않는다(cass, monkeypatch):
    """🔴 게이트의 근거다 — 여기가 초록이어야 "네트워크 없이 재현"이 참이다."""
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    cassette.save("fetch", "https://npb.jp/x", "",
                  {"ok": True, "status": 200, "text": "<html>본문</html>"})
    got = asyncio.run(Net().get("https://npb.jp/x"))
    assert got.ok and "본문" in got.text


def test_카세트가_없으면_없다고_적는다(cass, monkeypatch):
    """🔴 **몰래 라이브로 넘어가지 않는다.** 없는 것은 없다고 한다(§19-b-6).

    ⚠️ 여기서 네트워크로 폴백하면 CI 가 조용히 외부를 때리고, 그 실패가 코드
       결함으로 읽힌다. 그리고 게이트가 무엇을 증명했는지 아무도 모르게 된다.
    """
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    got = asyncio.run(Net().get("https://없는곳/x"))
    assert not got.ok
    assert "카세트 없음" in got.reason, got.reason


def test_replay는_robots도_읽지_않는다(cass, monkeypatch):
    """🔴 robots.txt 를 읽으러 가면 **그 순간 네트워크에 간 것**이다.

    ⚠️ 이것이 §19-g 의 *"실제 네트워크 없이"* 를 깨는 가장 조용한 경로다 —
       본문은 카세트에서 오는데 robots 만 라이브로 나간다.
    """
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    net = Net()
    cassette.save("fetch", "https://npb.jp/y", "",
                  {"ok": True, "status": 200, "text": "x"})
    asyncio.run(net.get("https://npb.jp/y"))
    assert net._robots == {}, "robots 를 읽으러 나갔다"


def test_replay는_검색에서도_네트워크에_가지_않는다(cass, monkeypatch):
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    s = SearxSearch("http://127.0.0.1:8888")
    params = {"q": "ソフトバンク スタメン 9月27日", "format": "json",
              "language": "ja-JP"}
    cassette.save("search", "http://127.0.0.1:8888/search",
                  cassette.query_string(params),
                  {"results": [{"title": "t", "url": "https://u",
                                "content": "中村晃 6番"}]})
    hits = asyncio.run(s.query("ソフトバンク スタメン 9月27日", lang="ja"))
    assert len(hits) == 1 and "中村晃" in hits[0].snippet


def test_검색_카세트가_없으면_사유를_낸다(cass, monkeypatch):
    """🔴 세포가 받을 수 있는 예외여야 한다 — `SearchUnavailable`.

    ⚠️ `CassetteMiss` 를 그대로 올리면 세포의 `except SearchUnavailable` 을
       통과해 사이클이 통째로 죽는다(사유도 안 남는다).
    """
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    s = SearxSearch()
    with pytest.raises(SearchUnavailable, match="카세트 없음"):
        asyncio.run(s.query("없는 질의"))
    # 🔴 SearXNG 가 죽은 것이 **아니다** — 내리면 카오스 테스트가 오염된다
    assert s.alive is not False


def test_구글_카세트_재생이_예산을_쓰지_않는다(cass, monkeypatch):
    """🔴 `replay` 는 구글에 가지 않으므로 **할당량을 쓰지 않는다.**

    ⚠️ 예산을 먼저 세면 카세트 재현 100건이 그날 CSE 예산을 통째로 먹은 것처럼
       기록되고, 그 기록을 보고 다음 사람이 "상한을 넘겼다"고 오독한다.
    """
    from app.search import GoogleSearch
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    g = GoogleSearch(api_key="k", cx="c")
    before = g.cap.left
    with pytest.raises(SearchUnavailable, match="카세트 없음"):
        asyncio.run(g.query("x", qtype="counter"))
    assert g.cap.left == before, "재생이 구글 예산을 먹었다"


# ══════════════════════════════════════════════════════════════════
# record
# ══════════════════════════════════════════════════════════════════

def test_record가_실패도_저장한다(cass, monkeypatch):
    """⚠️ 404·거부가 재현되지 않으면 §19-b-4(막히면 **대체**)를 시험할 수 없다."""
    monkeypatch.setenv(cassette.MODE_ENV, cassette.RECORD)

    class _R:
        status_code = 404
        text = ""

    async def _get(self, url, **k):
        return _R()

    monkeypatch.setattr("httpx.AsyncClient.get", _get)
    got = asyncio.run(Net().get("https://x/404"))
    assert not got.ok
    saved = json.loads(cassette.path("fetch", "https://x/404", "")
                       .read_text(encoding="utf-8"))
    assert saved["ok"] is False and saved["status"] == 404


def test_카세트_목록이_무엇인지_말한다(cass, monkeypatch):
    """🔴 조용한 0 금지 — 무엇이 담겼는지 **이름으로** 보인다."""
    monkeypatch.setenv(cassette.MODE_ENV, cassette.RECORD)
    cassette.save("fetch", "https://a", "", {"ok": True, "text": ""})
    cassette.save("search", "https://b/search", "q=x", {"results": []})
    rows = cassette.index()
    assert {r["kind"] for r in rows} == {"fetch", "search"}
    assert any(r["query"] == "q=x" for r in rows)
