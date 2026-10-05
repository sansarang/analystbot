"""🔴🔴 **§5 카세트 — 녹화·재생·replay_miss** (지시서 2026-10-06 §5 · M134).

> 녹화 — 라이브 실행 때 외부 호출을 **전부** 기록한다: SearXNG·Bing·GDELT 응답,
> fetch 본문(원문 HTML), **Solar·DeepSeek 요청·응답**. 저장 위치
> `cassettes/{경기 id}/{실행 id}/`, 요청 해시 → 응답.
> 재생 — `--replay {실행 id}` 플래그. 요청 해시가 카세트에 있으면 응답을 그대로
> 돌려주고, 없으면 기본은 **실패**(`replay_miss` 사유와 요청 내용을 출력).
> `--replay-fallthrough` 를 줄 때만 없는 요청을 라이브로 보내고 카세트에 추가한다.

🔴 **왜** — 오늘 하루 예산 $5 중 $4.88 을 수정 확인용 재실행에 썼다
   (한 번에 $0.34 · 26분). 이 문서의 수정 대부분은 **같은 입력으로 공짜로**
   확인할 수 있다.

⚠️ 전부 **행동 검사**다(지시서 §7: 글자 검사 금지 — 이번 세션에 글자 검사 계약이
   돌연변이를 다섯 번 통과시켰다).
"""
from __future__ import annotations

import pytest


def _env(monkeypatch, tmp_path, **kw):
    from app import cassette
    monkeypatch.setenv(cassette.DIR_ENV, str(tmp_path))
    for k, v in kw.items():
        name = getattr(cassette, k)
        if v is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, str(v))


# ══════════════════════════════════════════════════════════════════
# ① 실행 id 로 칸을 나눈다 — `cassettes/{경기 id}/{실행 id}/`
# ══════════════════════════════════════════════════════════════════

def test_wo5_실행_id_로_칸이_갈린다(monkeypatch, tmp_path):
    from app import cassette
    _env(monkeypatch, tmp_path, MODE_ENV="record",
         MATCH_ENV="fotmob:5181806", RUN_ENV="r1")
    p1 = cassette.save("search", "https://x/search", "q=a", {"ok": 1})
    assert "fotmob_5181806" in str(p1) and "r1" in str(p1), p1
    # 🔴 다른 실행은 **다른 칸**이다 — 같은 요청이라도 덮지 않는다
    _env(monkeypatch, tmp_path, MODE_ENV="record",
         MATCH_ENV="fotmob:5181806", RUN_ENV="r2")
    p2 = cassette.save("search", "https://x/search", "q=a", {"ok": 2})
    assert p1 != p2, (p1, p2)
    _env(monkeypatch, tmp_path, MODE_ENV="replay",
         MATCH_ENV="fotmob:5181806", RUN_ENV="r1")
    assert cassette.load("search", "https://x/search", "q=a")["ok"] == 1


def test_wo5_실행_id_가_없으면_종전_날짜_칸이다(monkeypatch, tmp_path):
    """🔴 **사본 금지** — 기존 고정물(`{날짜}/{sha}.json`)이 그대로 돌아야 한다.

    ⚠️ 경로 꼴을 바꾸면 녹음해 둔 고정물이 한꺼번에 미스가 되고, 그 녹음은
       **다시 만들 수 없다**(CLAUDE.md 의 경고).
    """
    from app import cassette
    _env(monkeypatch, tmp_path, MODE_ENV="record", MATCH_ENV=None, RUN_ENV=None,
         DAY_ENV="2026-10-06")
    p = cassette.save("search", "https://x/search", "q=a", {"ok": 1})
    assert p.parent.name == "2026-10-06", p


# ══════════════════════════════════════════════════════════════════
# ② replay_miss — 기본은 **실패**다(M134)
# ══════════════════════════════════════════════════════════════════

def test_wo5_M134_없는_요청은_replay_miss_로_실패한다(monkeypatch, tmp_path):
    from app import cassette
    _env(monkeypatch, tmp_path, MODE_ENV="replay", MATCH_ENV="m1", RUN_ENV="r1",
         FALLTHROUGH_ENV=None)
    assert cassette.fallthrough() is False
    with pytest.raises(cassette.CassetteMiss) as got:
        cassette.load("search", "https://x/search", "q=없다")
    said = str(got.value)
    # 🔴 사유 **이름**이 `replay_miss` 다(§8-6: 사유는 이름으로)
    assert cassette.REPLAY_MISS in said, said
    # 🔴 **요청 내용을 출력한다** — 무엇이 없는지 모르면 고칠 수 없다(#3)
    assert "https://x/search" in said and "q=없다" in said, said


def test_wo5_M134_fallthrough_를_줄_때만_라이브로_간다(monkeypatch, tmp_path):
    """🔴 그 플래그가 **없으면** 어떤 통로도 라이브로 넘어가지 않는다."""
    from app import cassette
    _env(monkeypatch, tmp_path, MODE_ENV="replay", MATCH_ENV="m1", RUN_ENV="r1",
         FALLTHROUGH_ENV="1")
    assert cassette.fallthrough() is True
    # ⚠️ `load` 는 그래도 미스를 던진다 — 라이브로 가는 결정은 **호출부**가 한다.
    #    🔴 그 결정이 `fallthrough()` 하나를 보는지가 M134 의 본체다.
    with pytest.raises(cassette.CassetteMiss):
        cassette.load("search", "https://x/search", "q=없다")


def test_wo5_M134_통로마다_fallthrough_를_본다(monkeypatch, tmp_path):
    """🔴🔴 **행동 검사** — 통로를 실제로 돌려서 라이브로 가는지 본다.

    ⚠️ 글자 검사(`"fallthrough" in src`)로는 한 통로가 빠져도 통과한다.
    """
    import asyncio

    from app import cassette, net, search
    _env(monkeypatch, tmp_path, MODE_ENV="replay", MATCH_ENV="m1", RUN_ENV="r1",
         FALLTHROUGH_ENV=None)
    hits = {"n": 0}

    def _boom(*a, **k):
        hits["n"] += 1
        raise AssertionError("🔴 재생 모드인데 **라이브로 나갔다**")

    monkeypatch.setattr(search.httpx, "AsyncClient", _boom)
    monkeypatch.setattr(net.httpx, "AsyncClient", _boom, raising=False)
    # ── SearXNG·Bing·GDELT 셋 다
    for ch in (search.SearxSearch(), search.BingNewsSearch(),
               search.GdeltSearch()):
        cassette.GdeltSearch_reset = None          # noqa: B010
        with pytest.raises(search.SearchUnavailable) as got:
            asyncio.run(ch.query("없는 질의", lang="en"))
        assert cassette.REPLAY_MISS in str(got.value) or "카세트" in str(got.value), (
            type(ch).__name__, got.value)
    assert hits["n"] == 0, "🔴 라이브로 나간 통로가 있다"


# ══════════════════════════════════════════════════════════════════
# ③ LLM 요청·응답도 녹화한다 — 그것이 없으면 재생이 공짜가 아니다
# ══════════════════════════════════════════════════════════════════

def test_wo5_Solar_요청_응답을_녹화하고_재생한다(monkeypatch, tmp_path):
    from app import cassette, solar
    _env(monkeypatch, tmp_path, MODE_ENV="record", MATCH_ENV="m1", RUN_ENV="r1")
    body = {"model": "solar-pro4", "messages": [{"role": "user", "content": "x"}],
            "max_tokens": 10}
    calls = {"n": 0}

    def _live(*_a, **_k):
        calls["n"] += 1
        return {"id": "live", "usage": {"completion_tokens": 3}}

    monkeypatch.setattr(solar, "_post_live", _live, raising=False)
    got = solar._post("https://api.x", "k", body, 5, 0)
    assert got["id"] == "live" and calls["n"] == 1
    # 🔴 **재생에서는 망에 안 간다** — 같은 요청이면 같은 응답
    _env(monkeypatch, tmp_path, MODE_ENV="replay", MATCH_ENV="m1", RUN_ENV="r1")
    again = solar._post("https://api.x", "k", body, 5, 0)
    assert again["id"] == "live", again
    assert calls["n"] == 1, "🔴 재생인데 라이브를 또 때렸다"
    # 🔴 다른 요청이면 **replay_miss** 다
    with pytest.raises(solar.SolarUnavailable) as miss:
        solar._post("https://api.x", "k", {**body, "max_tokens": 11}, 5, 0)
    assert cassette.REPLAY_MISS in str(miss.value), miss.value


def test_wo5_녹화에_비밀이_안_들어간다(monkeypatch, tmp_path):
    """🔴 요청 본문을 저장하므로 **열쇠·토큰이 섞여 들어갈 자리**다."""
    from app import cassette, solar
    _env(monkeypatch, tmp_path, MODE_ENV="record", MATCH_ENV="m1", RUN_ENV="r1")
    monkeypatch.setattr(solar, "_post_live",
                        lambda *a, **k: {"id": "x", "usage": {}}, raising=False)
    solar._post("https://api.x?key=SECRET123", "TOKEN456",
                {"model": "m", "messages": []}, 5, 0)
    blob = "\n".join(p.read_text(encoding="utf-8")
                     for p in tmp_path.rglob("*.json"))
    assert "SECRET123" not in blob and "TOKEN456" not in blob, blob[:300]
