"""[2026-09-06] 모델명 로그 진실성 + RSS 중복 제거.

🔴 모델명: 무료 사슬로 옮긴 뒤 `[matchup]` 로그가 **설정값**을 찍고 있었다.
   시뮬 실측 2026-09-05 —
     free provider=nvidia model=nvidia/nemotron-3-ultra-550b-a55b ok=True
     [matchup] … model=claude-sonnet-5      ← 로그와 원장이 다른 말
   폴백이 일어나면 어느 모델이 그 판정을 했는지 사라진다.

🔴 중복: 같은 기사가 여러 매체 URL 로 들어와 태그가 두 번 나왔다.
   실측 2026-09-05 KIA 뉴스태그 2개가 같은 기사였다(v.daum / xportsnews).
   판정은 그것을 두 신호로 읽는다 — 없는 반복을 근거로 삼는 것이다.
"""
import pytest

A = ("'4G ERA 15.00' KIA 이대로 괜찮나, 정말 계속 믿어도 될까…"
     '"겪고 넘어가야 할 상황" - v.daum.net')
B = ("'4G ERA 15.00' KIA 이대로 괜찮나, 정말 계속 믿어도 될까…"
     '"겪고 넘어가야 할 상황" - xportsnews.com')
C = "KT 위즈, 2026 정조대왕 유니폼 출시 - 조선일보"


# ─────────────────── 중복 제거 ───────────────────

def test_same_article_from_two_outlets_is_one():
    """어제 실사례 그대로."""
    from app.collectors.news_rss import dedupe_by_title, title_key

    assert title_key(A) == title_key(B)
    assert len(dedupe_by_title([{"title": A}, {"title": B}, {"title": C}])) == 2


def test_different_articles_stay_separate():
    from app.collectors.news_rss import title_key

    assert title_key(A) != title_key(C)


def test_dedupe_keeps_the_first_which_is_the_newest():
    """`for_game` 이 최신순으로 준다 — 먼저 온 것을 남긴다."""
    from app.collectors.news_rss import dedupe_by_title

    out = dedupe_by_title([{"title": A, "url": "u1"}, {"title": B, "url": "u2"}])
    assert out[0]["url"] == "u1"


def test_dedupe_only_strips_outlet_and_punctuation():
    """🔴 단어를 건드리면 다른 기사가 같은 것으로 뭉친다."""
    from app.collectors.news_rss import title_key

    assert title_key("KIA 5연승 - 조선") != title_key("KIA 5연패 - 조선")
    assert title_key("") == ""


@pytest.mark.asyncio
async def test_dedupe_runs_before_tag_generation(monkeypatch):
    """태그를 만든 뒤에 지우면 이미 두 신호가 된 뒤다."""
    import app.collectors.news_rss as nr

    async def _fake(jg, redis=None, *, limit=12):
        return [{"title": A, "url": "u1", "team": "Kia Tigers"},
                {"title": B, "url": "u2", "team": "Kia Tigers"}]

    monkeypatch.setattr(nr, "for_game", _fake)
    out = await nr.by_side({"sport": "kbo", "home": "Kia Tigers",
                            "away": "KT Wiz"}, None)
    assert len(out["home"]) == 1


# ─────────────────── 모델명 ───────────────────

def test_actual_model_wins_over_the_configured_one(monkeypatch):
    from app.engine import team_form
    from app.engine.matchup import _real_model

    team_form.LAST_USAGE.clear()
    team_form.LAST_USAGE.update({"role": "matchup",
                                 "model": "nvidia/nemotron-3-ultra-550b-a55b"})
    assert _real_model("claude-sonnet-5") == "nvidia/nemotron-3-ultra-550b-a55b"


def test_falls_back_to_configured_when_role_differs():
    """🔴 `LAST_USAGE` 는 직전 호출이다 — 폼이 끼면 그 모델이 잡힌다."""
    from app.engine import team_form
    from app.engine.matchup import _real_model

    team_form.LAST_USAGE.clear()
    team_form.LAST_USAGE.update({"role": "form", "model": "groq/qwen"})
    assert _real_model("claude-sonnet-5") == "claude-sonnet-5"

    team_form.LAST_USAGE.clear()
    assert _real_model("claude-sonnet-5") == "claude-sonnet-5"


def test_log_line_uses_the_actual_model():
    from pathlib import Path

    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "_actual = _real_model(" in src
    assert '_jm.get("확신도"), _actual))' in src


def test_report_carries_the_inaccuracy_footnote():
    """소급 정정이 불가하니 리포트가 그 사실을 말한다."""
    from pathlib import Path

    src = Path("app/engine/glass_report.py").read_text(encoding="utf-8")
    assert "2026-09-06 이전 기록은 모델명 표기가 부정확" in src


def test_engineering_rule_cites_a_real_commit():
    """🔴 없는 해시로 규율을 적으면 없는 사고를 기록하는 것이다."""
    import subprocess
    from pathlib import Path

    doc = Path("docs/ENGINEERING.md").read_text(encoding="utf-8")
    assert "경로 테스트로 완결한다" in doc
    assert "874ddbe" in doc
    r = subprocess.run(["git", "cat-file", "-t", "874ddbe"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "commit", "인용한 해시가 저장소에 없다"
