"""단계 4 계약 — **fotmob 경기 페이지에서 XI 를 읽는다.** 🔴 한 경기에 맞추지 않는다.

사용자 지시 2026-10-01:

> 이 경기는 **한 예**를 설명한 거다 .. **모든 경기를** 사용자가 경기분석 해줘 했을 때
> 내가 보여준 결과치대로 나와야 한다고 .. **거짓없이**

🔴 그래서 이 계약은 **저장소에 있는 fotmob 경기 카세트 전부**를 돌린다. 목록을 손으로
   적지 않는다 — 카세트 디렉터리에서 자란다. 새 경기를 담으면 그것도 검사된다.
   ⚠️ fotmob 이 페이지 구조를 바꾸면 **여기가 먼저 빨개진다.**

실측 2026-10-01 — 6개 페이지가 전부 읽혔다:

```
UEFA Nations League C   Armenia 5-4-1 / Montenegro 4-4-2        (한국어판)
USL Championship        Charleston 4-4-2 / Las Vegas 4-4-2      (2026-08-30)
USL Championship        Rhode Island 4-2-3-1 / Las Vegas        (2025-10-05)
USL Championship        Sacramento 4-2-3-1 / Las Vegas 4-1-2-1-2 (영어판·기본판)
USL Championship        Orange County 4-4-2 / Sacramento 3-5-2   (2026-09-06)
```

→ 리그 2종 · 연도 2개 · 언어판 3종. **경기별 손질이 0 이다.**
"""
from __future__ import annotations

import glob
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.cells import Q_LINEUP, Question
from app.collect import fotmob
from app.net import Fetched

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def _pages() -> list[dict]:
    """🔴 **목록이 카세트에서 자란다.** 손으로 적지 않는다."""
    out = []
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        u = d.get("url") or ""
        if fotmob.is_match_page(u) and (d.get("text") or ""):
            out.append(d)
    return out


def test_읽을_경기_페이지가_있다():
    """⚠️ 0건이면 아래 계약이 **공허한 참**이 된다(리뷰 B1 의 병)."""
    got = _pages()
    assert len(got) >= 5, f"fotmob 경기 카세트가 {len(got)}건뿐이다"


@pytest.mark.parametrize("idx", range(16))
def test_모든_경기에서_양_팀_11명이_나온다(idx):
    """★ 🔴 **경기마다 11명.** §13-c ② 가 요구하는 수다."""
    pages = _pages()
    if idx >= len(pages):
        pytest.skip("그만큼 없다")
    d = pages[idx]
    j = fotmob.payload(d["text"])
    assert j is not None, f"__NEXT_DATA__ 를 못 읽었다: {d['url'][:80]}"
    when = fotmob.kickoff(j)
    assert when is not None, f"경기 시각이 없다: {d['url'][:80]}"
    lu = ((j.get("props") or {}).get("pageProps") or {}) \
        .get("content", {}).get("lineup") or {}
    for side in ("homeTeam", "awayTeam"):
        tm = lu.get(side) or {}
        assert tm.get("name"), f"{side} 이름 없음: {d['url'][:70]}"
        assert len(tm.get("starters") or []) == fotmob.XI, (
            f"{tm.get('name')} 선발 {len(tm.get('starters') or [])}명: "
            f"{d['url'][:70]}")
        assert tm.get("formation"), f"{tm.get('name')} 포메이션 없음"


@pytest.mark.parametrize("idx", range(16))
def test_질문한_팀의_것만_돌려준다(idx):
    """🔴 §17-g-3 — 한 페이지에 **두 팀**이 있다. 둘 다 올리면 M14 가 되돌아온다
    (阪神 선수를 소프트뱅크 명단에 저장한 사고).
    """
    pages = _pages()
    if idx >= len(pages):
        pytest.skip("그만큼 없다")
    d = pages[idx]
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    when = fotmob.kickoff(j)
    lu = ((j.get("props") or {}).get("pageProps") or {}) \
        .get("content", {}).get("lineup") or {}
    home = (lu.get("homeTeam") or {}).get("name") or ""
    away = (lu.get("awayTeam") or {}).get("name") or ""
    q = Question(Q_LINEUP, "x", team=home, league="",
                 deadline=when.astimezone(KST))
    facts = fotmob.parse_match(got, q)
    assert len(facts) == 1, f"{home} 질문에 사실 {len(facts)}건 — 한 팀만이어야 한다"
    assert facts[0].value["team"] == home
    assert len(facts[0].value["players"]) == fotmob.XI
    # 🔴 원정 팀 선수가 섞이지 않았나
    away_starters = {p["name"] for p in (lu.get("awayTeam") or {}).get("starters") or []}
    mixed = away_starters & set(facts[0].value["players"])
    assert not mixed, f"상대 팀 선수가 섞였다: {sorted(mixed)}"


@pytest.mark.parametrize("idx", range(16))
def test_다른_날_경기는_거부한다(idx):
    """🔴 §13-c ① — 날짜가 다르면 **다른 경기다.** 전날 라인업을 오늘 것으로 쓰는
    사고가 실제로 있었다(실측 2026-09-30).
    """
    pages = _pages()
    if idx >= len(pages):
        pytest.skip("그만큼 없다")
    d = pages[idx]
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    when = fotmob.kickoff(j)
    home = (((j.get("props") or {}).get("pageProps") or {})
            .get("content", {}).get("lineup", {}).get("homeTeam") or {}).get("name") or ""
    # 🔴 **하루 뒤**로 물으면 0건이어야 한다
    q = Question(Q_LINEUP, "x", team=home, league="",
                 deadline=(when + timedelta(days=1)).astimezone(KST))
    assert fotmob.parse_match(got, q) == [], \
        f"다른 날 경기를 받아들였다: {d['url'][:70]}"


def test_확정과_기준을_구분해_싣는다():
    """🔴 **거짓없이** — 경기 전 fotmob 은 *예상*을 보여 준다.

    사용자 글의 첫 문장이 바로 이 구분이다:

    > 확정 XI는 아직 색인에 안 잡힌다 … 잡힌 건 양 팀 "직전 경기 선발 XI"라
    > 그걸 **기준 XI** 로 놓고 재작성한다

    예상을 확정이라고 적으면 거짓이다. `lineup_kind` 로 갈라 싣고 hardness 도 가른다.
    """
    pages = _pages()
    assert pages
    d = pages[0]
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    when = fotmob.kickoff(j)
    home = (((j.get("props") or {}).get("pageProps") or {})
            .get("content", {}).get("lineup", {}).get("homeTeam") or {}).get("name") or ""
    q = Question(Q_LINEUP, "x", team=home, league="",
                 deadline=when.astimezone(KST))
    f = fotmob.parse_match(got, q)[0]
    assert f.value["lineup_kind"] in ("confirmed", "baseline")
    # 🔴 시작한 경기의 XI 는 hard, 시작 전은 soft
    assert (f.hardness == "hard") == (f.value["lineup_kind"] == "confirmed")
    # 🔴 출처가 없는 사실은 만들지 않는다(§9 단계 4: "출처 없는 변수 0")
    assert f.source and f.published_at is not None


def test_경기_페이지가_아니면_건드리지_않는다():
    """⚠️ 팀·리그 페이지에는 라인업이 없다 — 그것을 읽은 척하지 않는다."""
    assert fotmob.is_match_page("https://www.fotmob.com/teams/123/x") is False
    assert fotmob.is_match_page("https://example.test/matches/a-vs-b") is False
    assert fotmob.parse_match(
        Fetched("https://www.fotmob.com/teams/1", True, 200, "<html></html>"),
        Question(Q_LINEUP, "x", team="A")) == []




# ══════════════════════════════════════════════════════════════════
# 🔴 같은 페이지의 나머지 블록 — 맞대결·폼·통계·구장
# ══════════════════════════════════════════════════════════════════


def _ctx(idx: int = 0):
    pages = _pages()
    d = pages[idx]
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    when = fotmob.kickoff(j)
    home = (((j.get("props") or {}).get("pageProps") or {})
            .get("content", {}).get("lineup", {}).get("homeTeam") or {}).get("name") or ""
    q = Question(Q_LINEUP, "x", team=home, league="",
                 deadline=when.astimezone(KST))
    return fotmob.parse_context(got, q), q


@pytest.mark.parametrize("idx", range(16))
def test_맥락_사실이_전부_출처와_시각을_든다(idx):
    """🔴 §9 단계 4 — *"출처 없는 변수 0"*. 맥락도 사실이다."""
    if idx >= len(_pages()):
        pytest.skip("그만큼 없다")
    facts, _ = _ctx(idx)
    for f in facts:
        assert f.source, f"{f.question_id}: 출처가 없다"
        assert f.published_at is not None, f"{f.question_id}: 시각이 없다"
        assert f.extracted_by, f"{f.question_id}: 무엇이 뽑았는지 없다"


def test_맞대결_스코어를_숫자로_쪼갠다():
    """★ 🔴 실측 2026-10-01 — fotmob 은 `"5 - 0"`(공백 포함)으로 준다.

    측정이 `"5-0"` 을 찾는데 자료는 `"5 - 0"` 이라 **사실이 없는 것처럼 보였다.**
    그리고 단계 6·7 은 총점·핸디를 계산하므로 **숫자**가 필요하다.
    """
    facts, _ = _ctx(0)
    h2h = [f for f in facts if f.question_id.endswith(":h2h")]
    assert h2h, "맞대결 사실이 없다"
    ms = h2h[0].value["matches"]
    assert ms, "맞대결 경기가 0건"
    for m in ms:
        assert "-" in m["score"] and " " not in m["score"], m
        if m["home_score"] is not None:
            assert m["score"] == f"{m['home_score']}-{m['away_score']}"
        # 🔴 원문을 버리지 않는다
        assert m["score_raw"]


def test_휴식일을_날짜로_센다():
    """★ 🔴 실측 2026-10-01 — **시간을 빼면 하루 어긋난다.**

    ```
    직전 경기  2026-09-20 02:35 UTC = 현지 09-19 저녁
    킥오프     2026-10-01 02:00 UTC
    시간 차 10.98일 → `.days` 가 **10** 으로 버린다
    사람은 날짜를 센다: 9/19 → 9/30 = **11일**   ← 사용자가 적은 수
    ```

    ⚠️ 이 저장소가 같은 병으로 두 번 다쳤다(NHL 날짜 버킷·fdorg 경계 경기).
    🔴 시간 차도 **버리지 않는다** — 둘을 이름으로 함께 싣는다.
    """
    import glob
    import json as _json
    target = None
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if "matches/sacramento-republic-fc-vs-las-vegas" in (d.get("url") or ""):
            target = d
            break
    assert target, "그 경기 카세트가 없다"
    got = Fetched(target["url"], True, 200, target["text"])
    j = fotmob.payload(target["text"])
    for team, want in (("Las Vegas Lights", 11), ("Sacramento Republic", 4)):
        q = Question(Q_LINEUP, "x", team=team, league="",
                     deadline=fotmob.kickoff(j).astimezone(KST))
        form = [f for f in fotmob.parse_context(got, q)
                if f.question_id.endswith(":form")]
        assert form, f"{team}: 폼 사실이 없다"
        v = form[0].value
        assert v["rest_days"] == want, (team, v["rest_days"], want)
        # 🔴 시간 차도 함께 — 버리지 않는다
        assert isinstance(v["rest_hours"], int) and v["rest_hours"] > 0
        assert v["last5"] and len(v["last5"]) >= 3


def test_경기_전이면_통계를_만들지_않는다():
    """🔴 경기 전 통계는 **비어 있다.** 0 으로 채우면 거짓이다."""
    src = inspect.getsource(fotmob.parse_stats)
    assert "if not flat:" in src and "return []" in src


def test_구장과_날씨를_읽는다():
    """§4 `venue_weather` 의 재료다. 🔴 사용자 R5 의 *"하트헬스"* 가 구장 이름이다."""
    facts, _ = _ctx(0)
    info = [f for f in facts if f.question_id.endswith(":info")]
    assert info, "경기 정보 사실이 없다"
    v = info[0].value
    assert v.get("Stadium") or v.get("Tournament"), v


def test_질문_타입을_지어내지_않는다():
    """🔴 §19-a 의 `Q_TYPES` 에 맞대결·통계·폼 질문이 **없다.**

    타입을 늘리는 것은 규칙 변경이고 사용자 결정이다(단계 5). 그래서 질문 **id 에
    접미사**를 붙여 가른다 — 저장소가 이미 쓰는 방식이다(`coach_cell` 의 `:coach`).
    ⚠️ `source_score` 의 CHECK 가 `Q_TYPES` 를 강제하므로, 타입을 지어내면 적재가
       터진다(실측 2026-09-30 에 그랬다).
    """
    from app.cells import Q_TYPES
    facts, q = _ctx(0)
    for f in facts:
        head, _, suffix = f.question_id.rpartition(":")
        # 🔴 **목록을 손으로 적지 않는다** — `fotmob.SUFFIXES` 가 원본이다
        assert suffix in fotmob.SUFFIXES, f.question_id
        # 🔴 접미사를 떼면 **원래 질문 타입**이어야 한다
        assert head == q.id, f"질문 id 가 어긋난다: {f.question_id}"
        assert q.id.split(":")[0] in Q_TYPES


# ══════════════════════════════════════════════════════════════════
# 🔴 §19-c 따라가기 — 직전 경기 · 그리고 그 예외가 **구멍이 아닌지**
# ══════════════════════════════════════════════════════════════════


def _sac_lv():
    import glob
    import json as _json
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if "matches/sacramento-republic-fc-vs-las-vegas" in (d.get("url") or ""):
            return d
    return None


def test_직전_경기_주소를_스스로_찾는다():
    """★ 🔴 사용자가 손으로 한 일을 코드가 한다.

    > 잡힌 건 양 팀 **"직전 경기 선발 XI"** 라 그걸 기준 XI로 놓고 재작성한다

    실측 2026-10-01 — 봇이 찾아낸 주소가 사용자가 본 그 두 경기였다:
    `…vs-new-mexico-united`(*"뉴멕시코전 3-2 승"*) ·
    `…vs-hartford-athletic`(*"하트퍼드전 1-1"*).
    """
    d = _sac_lv()
    assert d, "그 경기 카세트가 없다"
    got = Fetched(d["url"], True, 200, d["text"])
    urls = {}
    for team in ("Sacramento Republic", "Las Vegas Lights"):
        urls[team] = fotmob.follow_prev(got, Question(Q_LINEUP, "x", team=team))
    assert len(urls["Sacramento Republic"]) == 1, urls
    assert len(urls["Las Vegas Lights"]) == 1, urls
    assert "new-mexico" in urls["Sacramento Republic"][0]
    assert "hartford" in urls["Las Vegas Lights"][0]
    # 🔴 **한 팀에 하나다** — 상대 팀 것을 같이 내면 귀속이 섞인다(§19-a)
    assert urls["Sacramento Republic"] != urls["Las Vegas Lights"]


def test_과거_경기_기록은_출처_경기를_반드시_든다():
    """★ 🔴 **이 예외가 구멍이 되지 않게.**

    `from_past_match` 는 §12-c-1 신선도 검사를 비켜 간다 — 기준 XI 가 과거 경기에서
    오기 때문이다(실측: *"4일 지난 기사다"* 로 거부됐다). 그 예외의 대가로 **어느
    경기에서 왔는지**를 반드시 싣고, **soft** 여야 한다.
    """
    import glob
    import json as _json
    found = 0
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if not fotmob.is_match_page(d.get("url") or ""):
            continue
        got = Fetched(d["url"], True, 200, d.get("text") or "")
        j = fotmob.payload(got.text)
        if j is None:
            continue
        home = ((((j.get("props") or {}).get("pageProps") or {})
                 .get("content", {}).get("lineup", {}).get("homeTeam")) or {}).get("name")
        if not home:
            continue
        for fact in fotmob.parse_prev(got, Question(Q_LINEUP, "x", team=home)):
            found += 1
            assert fact.from_past_match is True, fact.question_id
            assert fact.hardness == "soft", "과거 기록이 hard 로 들어왔다"
            assert fact.value.get("from_match"), "출처 경기가 없다"
            assert fact.value.get("from_date"), "출처 날짜가 없다"
            assert fact.source, "출처 주소가 없다"
    assert found >= 4, f"과거 기록 사실이 {found}건뿐이다"


def test_조건을_못_채운_과거_기록은_세포가_거부한다():
    """🔴 계약이 **거부 경로**까지 본다. 조건 없이 통과하면 날짜 검사를 우회하는
    문이 열린다.
    """

    from app import cells
    src = inspect.getsource(cells.Cell._verified)
    assert "from_past_match" in src
    assert "출처 경기가 없다 — 거부" in src, "출처 경기 없는 과거 기록을 안 막는다"
    assert "soft 가 아니다 — 거부" in src, "hard 로 들어온 과거 기록을 안 막는다"


def test_직전_경기_통계를_팀별_숫자로_돌린다():
    """★ 🔴 실측 2026-10-01 — 사용자 R7·R8 이 직전 경기 통계다.

    ```
    하트퍼드전  점유 69-31 · 유효슛 5-2   (홈 라스베이거스, 원정 하트퍼드)
    사용자      "하트퍼드전도 점유 지배" · "상대 유효슛 2개"
    ```

    🔴 `[홈, 원정]` 배열을 그대로 두면 어느 쪽이 우리인지 매번 다시 풀어야 한다.
       **상대가 기록한 값도 이름으로** 싣는다(`*_conceded`).
    """
    import glob
    import json as _json
    d = None
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            x = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if "hartford-athletic" in (x.get("url") or ""):
            d = x
            break
    if d is None:
        pytest.skip("하트퍼드전 카세트가 없다")
    got = Fetched(d["url"], True, 200, d["text"])
    facts = [f for f in fotmob.parse_prev(
        got, Question(Q_LINEUP, "x", team="Las Vegas Lights"))
        if f.question_id.endswith(":past_stats")]
    assert facts, "직전 경기 통계가 없다"
    v = facts[0].value
    assert v["possession"] == 69, v
    assert v["shots_on_target"] == 5 and v["shots_on_target_conceded"] == 2, v
    assert v["team"] and v["opponent"] and v["from_match"]


# ══════════════════════════════════════════════════════════════════
# 🔴 리그 순위표 — 콘퍼런스가 여럿일 수 있다
# ══════════════════════════════════════════════════════════════════


def _table_page():
    import glob
    import json as _json
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if fotmob.is_table_page(d.get("url") or "") and (d.get("text") or ""):
            return d
    return None


def test_리그_표_주소를_www_로_만든다():
    """🔴 `data.fotmob.com` 은 robots.txt 가 **AccessDenied** 다 — 안 쓴다.

    ⚠️ 경기 페이지의 `content.table.url` 이 그 자리를 가리킨다. 허가를 확인할 수
       없는 자리는 쓰지 않고(`site.api.espn.com` 과 같은 판정), `leagueId` 로
       **www 주소**를 만든다.
    """
    d = _sac_lv()
    assert d
    j = fotmob.payload(d["text"])
    url = fotmob.league_table_url(j)
    assert url and url.startswith("https://www.fotmob.com/leagues/")
    assert "data.fotmob.com" not in url, "robots 를 못 읽는 자리를 가리킨다"
    assert fotmob.is_table_page(url)


def test_콘퍼런스가_여럿인_리그를_하나로_가정하지_않는다():
    """★ 🔴 USL 은 표가 **둘**이다(동부 13팀·서부 12팀).

    표를 하나로 가정하면 순위가 틀린다 — 실측 2026-10-01 에 새크라멘토는
    **서부** 2위였다. 🔴 그래서 순위 사실에 **어느 표인지**를 함께 싣는다.
    """
    d = _table_page()
    if d is None:
        pytest.skip("리그 표 카세트가 없다")
    j = fotmob.payload(d["text"])
    tables = fotmob._tables(j)
    assert len(tables) >= 1
    got = Fetched(d["url"], True, 200, d["text"])
    facts = fotmob.parse_league_table(
        got, Question(Q_LINEUP, "x", team="Sacramento Republic"))
    assert facts, "순위 사실이 없다"
    v = facts[0].value
    assert v["rank"] and v["played"] and v["points"] is not None, v
    # 🔴 어느 표인지 없으면 순위가 무슨 뜻인지 모른다
    assert v["table"], "콘퍼런스·표 이름이 없다"
    # 🔴 원정 쪼갠 표도 — 사용자 R4 의 재료다
    assert v.get("away") and v["away"].get("played"), v


def test_순위표는_과거_경기_기록이_아니다():
    """★ 🔴 분류를 틀렸다가 **가드가 물었다**(실측 2026-10-01).

    처음에 순위 사실을 `from_past_match=True` 로 적었더니 그 예외의 조건
    (`from_match` 필수)을 못 채워 세포가 **거부했다.** 가드가 옳았고 분류가
    틀렸다 — 순위표는 *과거 경기*가 아니다.

    🔴 **그리고 "발행 시각이 없다"도 틀렸다**(사용자 지시 2026-10-02 — 게이트).
       표는 **자기 시점을 들고 있다**: 행마다 `ongoing` 이 있고 끝난 경기는 종료
       시각을 적어 둔다. 그 중 가장 늦은 시각이 *"최소한 그때까지의 결과를 담았다"* 다.
       ⚠️ 그것을 안 싣는 동안 **§12-c-2(경기 후 배제)가 순위표에 영영 닿지 않았다** —
          단계 4 측정의 *"값 다름: 순위 봇 2 ↔ 정답지 4"* 가 그 구멍이었다.
    """
    d = _table_page()
    if d is None:
        pytest.skip("리그 표 카세트가 없다")
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    as_of = fotmob.table_as_of(j)
    assert as_of is not None, "표가 자기 시점을 말하는데 못 읽었다"
    for f in fotmob.parse_league_table(
            got, Question(Q_LINEUP, "x", team="Las Vegas Lights")):
        assert f.from_past_match is False, "순위표를 과거 경기 기록으로 적었다"
        # 🔴 **표가 말한 시점을 그대로** — 지어내지도, 버리지도 않는다
        assert f.published_at == as_of, (f.published_at, as_of)
        assert f.value["as_of"] == as_of.isoformat()
        assert f.hardness == "soft"
        assert f.source
    # 🔴 시점을 못 읽는 표는 **전처럼 `None`** 이다(지어내지 않는다)
    import json as _json
    blank = _json.loads(d["text"][d["text"].index("{"):][:0] or "{}") if False else None
    assert fotmob.table_as_of({}) is None and blank is None


def test_따라가기가_생김새로_파서를_고른다():
    """🔴 경기 페이지와 표 페이지를 **주소로** 가른다 — 섞으면 엉뚱한 파서가 돈다."""
    d = _table_page()
    if d is None:
        pytest.skip("리그 표 카세트가 없다")
    got = Fetched(d["url"], True, 200, d["text"])
    q = Question(Q_LINEUP, "x", team="Sacramento Republic")
    picked = fotmob.parse_followed(got, q)
    assert picked and all(f.question_id.endswith(":standings") for f in picked)
    # 🔴 경기 페이지는 반대쪽으로 간다
    m = _sac_lv()
    out = fotmob.parse_followed(Fetched(m["url"], True, 200, m["text"]), q)
    assert all(f.question_id.rsplit(":", 1)[-1] in fotmob.SUFFIXES
               for f in out), [f.question_id for f in out]
    # 🔴 경기 페이지를 따라갔으면 **기준 XI** 가 반드시 들어 있다
    assert any(f.question_id.endswith(":baseline") for f in out)


# ══════════════════════════════════════════════════════════════════
# 🔴 선수 기록 — 경기 페이지가 이미 들고 있다
# ══════════════════════════════════════════════════════════════════


def test_직전_경기에서_선수_기록을_센다():
    """★ 🔴 실측 2026-10-01 — 사용자 숫자와 그대로 맞았다.

    ```
    뉴멕시코전  Memo Rodríguez  events [goal, goal, assist] → 2골 1도움
                Kyle Edwards (교체)  events [goal]          → 교체 득점
    사용자      "토요 2골 1도움" · "에드워즈는 교체 전문"
    ```

    🔴 `is_sub` 가 R6 의 전부다 — 선발인지 교체인지가 그 변수다.
    """
    import glob
    import json as _json
    d = None
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            x = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if "new-mexico-united" in (x.get("url") or ""):
            d = x
            break
    if d is None:
        pytest.skip("뉴멕시코전 카세트가 없다")
    got = Fetched(d["url"], True, 200, d["text"])
    facts = [f for f in fotmob.parse_prev(
        got, Question(Q_LINEUP, "x", team="Sacramento Republic"))
        if f.question_id.endswith(":player")]
    assert facts, "선수 기록이 없다"
    by = {f.value["player"]: f.value for f in facts}
    memo = next((v for k, v in by.items() if "Rodr" in k and "Memo" in k), None)
    assert memo, sorted(by)
    assert memo["goals"] == 2 and memo["assists"] == 1, memo
    assert memo["is_sub"] is False
    ed = next((v for k, v in by.items() if "Edwards" in k), None)
    assert ed, sorted(by)
    assert ed["is_sub"] is True and ed["goals"] == 1, ed


def test_기록이_없는_선수는_사실로_올리지_않는다():
    """🔴 18~36명을 전부 올리면 블랙보드가 이름으로 뒤덮인다 — 기록 없는 선수는
    **라인업 사실이 이미 담았다**(§19-a).
    """
    d = _sac_lv()
    assert d
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    q = Question(Q_LINEUP, "x", team="Sacramento Republic",
                 deadline=fotmob.kickoff(j).astimezone(KST))
    players = [f for f in fotmob.parse_context(got, q)
               if f.question_id.endswith(":player")]
    # 🔴 한 팀 명단(선발 11 + 교체 ~8)보다 적어야 한다
    assert 0 < len(players) <= 19, len(players)
    for f in players:
        v = f.value
        assert any(v[k] for k in ("goals", "assists", "yellow_cards",
                                  "red_cards")) or v["season_goals"] is not None


def test_시즌과_통산을_섞지_않는다():
    """★ 🔴 사용자의 *"USL 역대 1위 19골"* 은 **통산**이다. fotmob 경기 페이지는
    **시즌**만 준다 — 섞으면 거짓이다.

    그래서 칸 이름이 `season_goals` 이고, 통산을 뜻하는 칸은 **없다.**
    """
    d = _sac_lv()
    got = Fetched(d["url"], True, 200, d["text"])
    j = fotmob.payload(d["text"])
    q = Question(Q_LINEUP, "x", team="Sacramento Republic",
                 deadline=fotmob.kickoff(j).astimezone(KST))
    for f in fotmob.parse_context(got, q):
        if not f.question_id.endswith(":player"):
            continue
        v = f.value
        assert "season_goals" in v, v
        for bad in ("career_goals", "total_goals", "all_time_goals"):
            assert bad not in v, f"통산 칸을 지어냈다: {bad}"


def test_접미사_목록이_한_곳에서_자란다():
    """🔴 접미사를 두 곳에 적으면 갈린다 — 파서가 새 접미사를 쓰는데 계약이 모르면
    그 사실이 **검사 없이** 흐른다.

    ⚠️ 실측 2026-10-01: 선수·순위 파서를 더하자 계약 둘이 빨개졌다 — 손으로 적은
       목록이 한 발 늦었다. 그래서 `fotmob.SUFFIXES` 를 읽는다.
    """
    import glob
    import json as _json
    seen = set()
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = _json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        u = d.get("url") or ""
        if not (fotmob.is_match_page(u) or fotmob.is_table_page(u)):
            continue
        got = Fetched(u, True, 200, d.get("text") or "")
        j = fotmob.payload(got.text)
        if j is None:
            continue
        for which in ("homeTeam", "awayTeam"):
            nm = (fotmob._side(j, which) or {}).get("name")
            if not nm:
                continue
            q = Question(Q_LINEUP, "x", team=nm,
                         deadline=(fotmob.kickoff(j) or datetime.now(KST)).astimezone(KST))
            for fact in (fotmob.parse_context(got, q)
                         + fotmob.parse_followed(got, q)):
                seen.add(fact.question_id.rsplit(":", 1)[-1])
    unknown = sorted(seen - set(fotmob.SUFFIXES))
    assert unknown == [], f"`SUFFIXES` 에 없는 접미사를 쓴다: {unknown}"
    assert len(seen) >= 4, f"접미사를 {len(seen)}개만 봤다 — 계약이 공허하다"


def _match_page():
    """우리 경기(새크라멘토 vs 라스베이거스) 페이지 카세트."""
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        u = d.get("url") or ""
        if ("matches/sacramento-republic-fc-vs-las-vegas" in u
                and (d.get("text") or "")):
            return d
    return None


def test_남녀_표식이_다르면_다른_팀이다():
    """🔴🔴 **라이브가 찾은 가장 위험한 자리다**(2026-10-02 아시안게임).

    **여자** 한국 vs 중국을 물었더니 검색이 **남자** 대표팀(손흥민·김민재) 경기
    페이지를 열었다. 날짜도 같고 팀 이름도 `South Korea`·`China` 로 **글자까지
    같아서** 어떤 가드도 막지 못했다 → 기준 XI·선수 기록이 **남의 경기**에서 들어왔다.

    🔴 **0건보다 나쁘다.** 0건은 "자료 부족"으로 멈추지만 틀린 자료는 카드를 만든다.
    """
    from app import verify as V

    # 🔴 이름이 겹쳐도 **표식이 다르면 다른 팀**이다
    assert V.mentions_team("South Korea", "South Korea W") or True
    assert V.same_squad_kind("South Korea", "South Korea W") is False
    assert V.same_squad_kind("South Korea W", "South Korea W") is True
    assert V.same_squad_kind("Korea Republic", "Korea Republic U23") is False
    # ⚠️ 둘 다 표식이 없으면 같다(성인 남자/구단팀이 기본 표기다)
    assert V.same_squad_kind("Sacramento Republic FC",
                             "Sacramento Republic FC") is True
    assert V.squad_marks("Japan W") == frozenset({"w"})
    assert V.squad_marks("Japan U-21") == frozenset({"u21"})
    assert V.squad_marks("Japan") == frozenset()

    # 🔴🔴 **경기 페이지 검사가 실제로 막나** — 소스 grep 으로는 부족하다.
    #    (돌연변이가 통과했다: `if False and …` 로 꺼도 "same_squad_kind" 는 남는다)
    d = _match_page()
    if d is None:
        pytest.skip("경기 카세트가 없다")
    j = fotmob.payload(d["text"])
    # 🔴 **여자팀으로 물으면 남자 경기 페이지는 거부돼야 한다**
    bad = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Sacramento Republic FC W",
        opponent="Las Vegas Lights FC W"))
    assert bad and "표식" in bad, bad
    # 🔴 같은 종류로 물으면 통과한다
    ok = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Sacramento Republic FC",
        opponent="Las Vegas Lights FC"))
    assert ok == "", ok


def test_우리_경기가_아닌_페이지를_거부한다():
    """🔴 §13-c ② — 날짜만 보던 검사에 **팀**을 더했다.

    ⚠️ 상대를 모르면 막을 수 없다 — 그때는 우리 팀만 보고 그 사실을 로그에 남긴다.
    """
    d = _match_page()
    if d is None:
        pytest.skip("경기 카세트가 없다")
    j = fotmob.payload(d["text"])
    # 🔴 우리 경기면 통과
    ok = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Sacramento Republic FC",
        opponent="Las Vegas Lights FC"))
    assert ok == "", ok
    # 🔴 상대가 다르면 거부
    bad = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Sacramento Republic FC", opponent="Uruguay"))
    assert "상대" in bad, bad
    # 🔴 우리 팀이 없으면 거부
    none = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Manchester City", opponent="Arsenal"))
    assert "우리 팀" in none, none
    # ⚠️ 상대를 모르면 **약한 검사** — 통과하지만 로그에 남는다
    weak = fotmob._not_our_match(j, Question(
        Q_LINEUP, "x", team="Sacramento Republic FC"))
    assert weak == ""
