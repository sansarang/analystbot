"""[DS-2] 변화 감지를 **스케줄러에 잇는다.**

🔴 09-21 에 우리가 늦게 안 셋이 전부 타이밍 실패였다:
     08:30 마린스 세이부전 중지 · 11:06 라쿠텐 등록 공시 · 12:40경 우천 중지.
   `watch.py` 는 DS-2a 에서 만들었지만 **아무도 부르지 않았다.**

⚠️ **감시 대상은 `config/source_map.yaml` 이 원본**이다(`watch: true`).
   코드에 URL 목록을 적지 않는다(사본 금지).
⚠️ **robots 가 거부하는 행은 감시하지 않는다** — 차단을 우회하지 않는다.
   ⚠️ `fotmob` 행의 `robots: "**허용**"` 은 **내가 틀리게 적은 값**이었다
      (stdlib 와일드카드 버그). [3] 감사에서 `/api/*` 거부로 정정됐다.
"""
from __future__ import annotations

import pytest


def test_감시_대상은_source_map_이_정한다():
    from app.deepsearch.watch import watch_rows

    rows = watch_rows()
    assert rows, "감시 대상이 하나도 없다"
    urls = [r["url"] for r in rows]
    # 09-21 에 놓친 셋의 출처가 대상이어야 한다
    assert any("npb.jp/announcement/roster" in u for u in urls), urls
    assert any("marines.co.jp" in u for u in urls), urls


def test_robots_거부_행은_감시하지_않는다():
    """🔴 차단을 우회하지 않는다."""
    from app.deepsearch.watch import watch_rows

    urls = [r["url"] for r in watch_rows()]
    for bad in ("koreabaseball.com", "sports.news.naver.com", "fotmob.com"):
        assert not [u for u in urls if bad in u], f"{bad} 가 감시 대상이다"


def test_source_map_이_fotmob_을_허용으로_적지_않는다():
    """🔴 내가 틀리게 적은 값이다 — stdlib `robotparser` 가 `*` 를 못 읽어
    `Disallow: /api/*` 를 '허용'으로 답했다. [3] 감사가 정정했다."""
    import yaml

    d = yaml.safe_load(open("config/source_map.yaml", encoding="utf-8"))
    for r in (d.get("sources") or []):
        if "fotmob.com/api" in str(r.get("url") or ""):
            assert "허용" not in str(r.get("robots") or ""), r
            assert r.get("blocked") is True, r
            return
    raise AssertionError("fotmob 행이 없다")


def test_템플릿_행은_채울_수_있을_때만_본다():
    """⚠️ `{yahoo_id}` 를 못 채우면 그 행은 **건너뛴다** — 빈 자리를 빈
    문자열로 채우면 엉뚱한 주소를 친다(`scout_config.queries` 와 같은 규칙)."""
    from app.deepsearch.watch import fill_url

    assert fill_url("https://x/{yahoo_id}/top", {"yahoo_id": "202103"}) \
        == "https://x/202103/top"
    assert fill_url("https://x/{yahoo_id}/top", {}) is None
    assert fill_url("https://x/static", {}) == "https://x/static"


@pytest.mark.asyncio
async def test_스케줄러_잡이_예외로_죽지_않는다(monkeypatch):
    """⚠️ 워치독과 같은 규약 — 감시가 스케줄러를 죽이면 감시가 아니라 고장이다."""
    from app import scheduler

    async def boom(*a, **k):
        raise RuntimeError("망")

    monkeypatch.setattr("app.deepsearch.watch.run_watch", boom)
    await scheduler.watch_job()          # 예외가 밖으로 나오면 실패다


def test_스케줄러가_실제로_부른다():
    """🔴 **만들어 놓고 안 이으면 없는 것과 같다** — 이 저장소의 반복 결함이다."""
    import inspect

    from app import scheduler

    assert hasattr(scheduler, "watch_job")
    # ⚠️ 잡 목록의 원본은 `_job_specs()` 다 — `build_scheduler` 는 그것을
    #    읽을 뿐이다. 처음에 `build_scheduler` 본문을 봤다가 틀렸다.
    ids = [j[0] for j in scheduler._job_specs()]
    assert "watch_10m" in ids, ids
    fn = dict((j[0], j[1]) for j in scheduler._job_specs())["watch_10m"]
    assert fn is scheduler.watch_job
    assert "run_watch" in inspect.getsource(scheduler.watch_job)


@pytest.mark.asyncio
async def test_변화가_있으면_원장에_남는다():
    """🔴 인지 지연을 재려면 **언제 알았는지**가 남아야 한다."""
    from app.deepsearch.watch import Watcher

    rows_written: list = []

    class _Store:
        def __init__(self):
            self.d = {}

        async def get(self, k):
            return self.d.get(k)

        async def set(self, k, v, ex=None):
            self.d[k] = v

    class _RT:
        def __init__(self):
            self.i = 0

        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            self.i += 1
            body = f"<p>본문 {self.i}</p>".encode()
            return Fetched(url=url, status=200, body=body)

    async def on_event(ev):
        rows_written.append(ev)

    w = Watcher(runtime=_RT(), store=_Store(), parse=lambda h, r: {"ok": 1},
                on_event=on_event)
    row = {"url": "https://x/a", "kind": "notice", "ignore_selectors": []}
    await w.check(row)
    await w.check(row)
    assert len(rows_written) == 2
    assert rows_written[0]["kind"] == "notice"
    assert rows_written[0]["parsed_ok"] is True
