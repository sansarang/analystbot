"""🔴🔴 **지시서 §3 — 구조 자료 없는 리그의 자료 확보.**

작업 지시서(오픈월드) §3:

> **3-1 경기 페이지 자체** — ⑥-3 에서 받은 경기 페이지에 이미 대회·구장·심판·
> 예상/확정 XI·최근 폼·상대전이 있는 경우가 많다(fotmob HTML 경기 페이지는
> 포르투갈 카드에서 감독·포메이션·last5·h2h 를 줬다). 그 페이지를 **기존
> fotmob HTML 파서로 그대로 읽어** `Fact`(v5 §8-3)로 만든다. **새 파서를 짓지
> 않는다.**
>
> **3-2 ESPN 리그 슬러그 실측** — ESPN 어댑터가 이미 있다. ESPN 이 콜롬비아
> Primera A 같은 리그를 슬러그로 제공하는지, 그 경로가 robots 허용인지
> **실측해서 결과를 `questions/` 에 적는다.** … 이 표에 리그를 넣는 것은
> **데이터 추가이지 리그 선언이 아니다**(`leagues.yaml` 불변).
>
> **3-3 에이전트 보강** — 구조 자료가 비면 `AgentInput.gaps` 에 그 칸
> (순위·최근 5경기·상대전·XI·결장)을 넣고, 시스템 프롬프트에 **"gaps 의 구조
> 칸은 카탈로그 유형보다 먼저 찾아라"** 를 둔다.
>
> **3-4 예고·확정 XI** — T-60 재실행(v5 §7-1)은 오픈월드 경기도 같다.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import pytest

UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════
# 3-1 — 경기 페이지를 **기존 파서로** 읽는다(새 파서 금지)
# ══════════════════════════════════════════════════════════════════

def test_wo3_1_새_파서를_짓지_않는다():
    """🔴 ⑥-3 은 **`fotmob.slate_row`·`espn` 을 부른다** — 제 파서를 안 만든다."""
    import inspect

    from app import openworld
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(openworld))
    # 🔴 HTML·JSON 을 **직접 파싱하는 꼴**이 없어야 한다
    for bad in ("BeautifulSoup", "re.findall(r'<", 'json.loads(html',
                "__NEXT_DATA__"):
        assert bad not in body, (
            f"🔴 오픈월드가 **제 파서를 짓는다**(`{bad}`) — 지시서 §3-1 은 "
            f"*'기존 fotmob HTML 파서로 그대로 읽어라'* 고 했다")
    assert "slate_row" in body or "fotmob" in body, (
        "🔴 기존 파서를 **안 부른다** — ⑥-3 이 경기 페이지를 못 읽는다")


def test_wo3_1_경기_페이지에서_후보를_만든다():
    """🔴🔴 ⑥-2·⑥-3 배선 — URL 목록 → **후보 경기들**.

    ⚠️ 고정물은 **실측 저장**이다(지시서 §5: 라이브 웹에 기대는 테스트는 계약이
       아니다). 🔴 §6 인수 테스트가 저장한다.
    """
    from app import openworld
    assert hasattr(openworld, "pages_from"), (
        "🔴 ⑥-2 결과(URL)를 ⑥-3 후보로 바꾸는 자리가 없다 — "
        "`openworld.pages_from`")


def test_wo3_1_robots_와_도메인_등급을_본다():
    """🔴 **§5 M58** — 오픈월드가 받은 페이지도 robots·도메인 등급을 지난다."""
    import inspect

    from app import openworld
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(openworld))
    assert "domains" in body or "verdict" in body, (
        "🔴 도메인 등급(§4-3)을 **안 본다** — 팁 사이트가 근거가 된다(M58)")
    assert "net" in body, "🔴 `net` 을 안 쓴다 — robots 를 **누가** 보나(M58)"


# ══════════════════════════════════════════════════════════════════
# 3-2 ESPN 슬러그 — **실측 결과를 `questions/` 에 적는다**
# ══════════════════════════════════════════════════════════════════

def test_wo3_2_실측_결과가_questions_에_있다():
    """🔴 *"실측해서 결과를 `questions/` 에 적는다"* — 안 적으면 다음 세션이 모른다."""
    got = sorted((ROOT / "docs" / "fable" / "questions").glob(
        "*espn_slug*.md"))
    assert got, (
        "🔴 ESPN 슬러그 실측 결과가 `questions/` 에 **없다**(지시서 §3-2)")
    said = got[-1].read_text(encoding="utf-8")
    for want in ("robots", "콜롬비아"):
        assert want in said, f"🔴 실측 기록에 `{want}` 가 없다"


#: 🔴 선언된 리그 수 — **불변**이다(지시서 금지 1번).
#  ⚠️ 늘리려면 **사용자 결정**이 먼저다(`config/leagues.yaml` 은 사용자 영역).
LEAGUE_COUNT = 7


def test_wo3_2_슬러그_표는_리그_선언이_아니다():
    """🔴 *"이 표에 리그를 넣는 것은 **데이터 추가이지 리그 선언이 아니다**"*.

    ⚠️ `leagues.yaml` 은 **불변**이다 — 그것을 건드려 인수 테스트를 우회하는
       것이 지시서 **금지 1번**이다.
    """
    # 🔴 **금지의 뜻으로 본다** — *"리그를 넣어 인수 테스트를 우회"* 다.
    #    ⚠️ 종전엔 `git diff HEAD~12` 를 봤다. 커밋이 쌓이자 그 고정 창이
    #       **옛 변경**을 잡아 거짓 양성이 났다(실측 2026-10-05) — 창이 커밋
    #       수에 따라 뜻이 변하는 **사본**이었다(#1).
    #    🔴 그래서 **리그 수**를 본다: 그것이 늘지 않았으면 우회가 없다.
    from app import league_index
    said = league_index.leagues()
    assert len(said) == LEAGUE_COUNT, (
        f"🔴 선언된 리그가 **{len(said)}개**다(기준 {LEAGUE_COUNT}) — 리그를 "
        f"넣어 인수 테스트를 우회하는 것이 지시서 금지 1번이다. 늘리려면 "
        f"사용자 결정이 먼저다")


def test_wo3_2_슬러그_표가_있으면_모양이_맞다():
    """⚠️ 표는 **실측이 허용일 때만** 생긴다 — 없으면 그 사실이 기록에 있다."""
    p = ROOT / "config" / "espn_slugs.yaml"
    if not p.exists():
        said = sorted((ROOT / "docs" / "fable" / "questions").glob(
            "*espn_slug*.md"))[-1].read_text(encoding="utf-8")
        assert "표를 **만들지 않았다**" in said or "표를 만들지" in said, (
            "🔴 표가 없는 **까닭**이 기록에 없다(#3)")
        return
    import yaml
    box = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(box, dict) and box.get("slugs"), box


# ══════════════════════════════════════════════════════════════════
# 3-3 — `gaps` 구조 칸 **우선** 프롬프트
# ══════════════════════════════════════════════════════════════════









