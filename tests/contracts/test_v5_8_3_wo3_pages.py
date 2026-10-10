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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **상한 계약을 걷었다 — 사용자 결정 2026-10-10 §1**
# ══════════════════════════════════════════════════════════════════
#
#  > 모든 경기를 찾아 분석까지 해야 한다. **리그 수동 선언·상한 방식을 자동
#  > 등록으로 바꾼다.** `questions/2026-10-10_register_leagues_for_findgame.md`
#  > 는 이 지시로 닫는다.
#
#  ⚠️ 여기 있던 `test_wo3_2_슬러그_표는_리그_선언이_아니다`(선언된 리그 **7개
#     불변**)를 **지웠다**. 그 계약이 막던 것은 *"리그를 넣어 인수 테스트를
#     우회하는 것"* 이고, 🔴 **금지 자체는 사라지지 않았다** — 바뀐 것은 막는
#     방법이다(아래 두 계약).
#  🔴 실사고 2026-10-10: 그 계약이 빨개져서 아르헨티나 경기를 못 넣었고, 나는
#     `questions/` 에 적고 멈췄다. 사용자가 **자동 등록으로 바꾸라**고 답했다.


def test_v6_자동등록_리그는_data_에만_쌓인다():
    """🔴🔴 §1 — 자동 등록 리그는 **`data/leagues_auto/*.json` 에만** 있다.

    > 코드도 config 도 아니다.

    ⚠️ 돌연변이: 자동 등록한 리그를 `config/leagues.yaml` 에 적으면 — 그것이
       **수동 선언으로 테스트를 우회하는 것**이고, 이 계약이 잡는다.
    """
    from app.core import autoleague
    from app import league_index
    hand = {str(dict(x).get("key") or "") for x in league_index.leagues()}
    auto = set(autoleague.registered())
    both = sorted(x for x in auto
                  if autoleague.short_of(x) in hand or x in hand)
    assert not both, (
        f"🔴 자동 등록한 리그가 **손 선언에도** 있다 {both} — §1 이 금지한 "
        f"*수동 선언*이다. `config/leagues.yaml` 은 기준 모델·분할 규칙이 "
        f"필요한 리그만 남긴다")


def test_v6_자동등록_파일은_필수칸이_다_있다():
    """🔴🔴 §1 — *"필수 칸이 하나라도 없으면 **등록 실패**"*.

    출처(리그 id·URL) · 확인일 · 나라 · 팀 목록 출처 · 언어 · 팀.

    ⚠️ 돌연변이: `langs` 를 빈 목록으로 두고 저장하면 — `save` 가 막아야 하고
       이미 쌓인 파일에도 빈 칸이 없어야 한다. 🔴 **둘 다** 본다.
    """
    from app.core import autoleague as al
    bad: list[str] = []
    for key in al.registered():
        box = al.load(key)
        miss = [k for k in al.NEED if not box.get(k)]
        if miss:
            bad.append(f"{key} — 없는 칸 {miss}")
    assert not bad, ("🔴 자동 등록 파일에 필수 칸이 없다(§1):\n  "
                     + "\n  ".join(bad))
    # 🔴 `save` 가 **막는지**를 돌연변이로 본다 — 한 칸을 비워 넣어 본다
    for drop in al.NEED:
        box = {k: (["x"] if k in ("langs", "teams") else "x") for k in al.NEED}
        box[drop] = [] if drop in ("langs", "teams") else ""
        p, why = al.save(box)
        assert p is None and drop in why, (
            f"🔴 `{drop}` 가 비었는데 `save` 가 받았다 — §1 위반")


def test_v6_인수테스트는_자동등록_경로를_지난다():
    """🔴 §1 — *"인수 테스트는 **자동 등록 경로를 통과**해야 한다"*.

    ⚠️ 돌연변이: `findgame` 이 색인 사다리를 안 부르고 검색 단만 쓰면 — 그러면
       리그 등록이 **안 걸리고** 그 사실을 아무도 모른다. 🔴 호출을 AST 로 본다.
    """
    import ast
    said = ast.parse((ROOT / "app" / "findgame.py").read_text(encoding="utf-8"))
    calls = {ast.unparse(n.func) for n in ast.walk(said)
             if isinstance(n, ast.Call)}
    assert "discover.find" in calls, (
        "🔴 `findgame` 이 색인 사다리(`discover.find`)를 안 부른다 — §2 ②③ 이 "
        "없으면 리그 자동 등록도 안 걸린다")
    assert "discover.register" in calls, (
        "🔴 `findgame` 이 자동 등록(`discover.register`)을 안 건다 — §2 마지막 줄")


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











def test_v6_리그id가_어긋나면_대회_글자는_결정권이_없다():
    """🔴🔴 실사고 2026-10-10 — **엘살바도르 리그가 라리가로 붙었다**.

    `Primera Division - Apertura`(fotmob 335)가 `league:PD`(라리가 · fotmob 87)로
    판정됐다 — 그 줄의 `football_data_names` 에 `Primera Division` 이 있어
    **품는 일치**가 걸렸다. 자동 등록이 **라리가 열쇠로 파일을 썼다.**

    ⚠️ 돌연변이: `key_of` ③ 에서 `if lid and ids and lid not in ids: continue`
       를 지우면 — 이 계약이 잡는다.
    🔴 그 리그의 기준 모델로 판정하면 카드가 **통째로 거짓**이 된다(M14).
    """
    from app.core import competition as comp
    key, why = comp.key_of(competition="Primera Division - Apertura",
                           league_id=335)
    assert not key.startswith("league:PD"), (
        f"🔴 엘살바도르 리그(fotmob 335)가 라리가 열쇠로 붙었다 — {key} · {why}")
    # 🔴 라리가 자신은 **그대로** 서야 한다(고치다 깨뜨리지 않았나)
    got, _ = comp.key_of(competition="LaLiga", league_id=87)
    assert got == "league:PD", got


def test_v6_자동등록은_손표_열쇠로_쓰지_않는다():
    """🔴🔴 §1 — 자동 등록은 **`league:fotmob{id}`** 열쇠로만 쓴다.

    > `config/competitions.yaml` 은 **사용자 영역**이다(기준 모델·분할 규칙).

    ⚠️ 돌연변이: `discover.register` 에서 손 표 열쇠를 거르는 줄을 지우면 —
       자동 등록이 라리가 파일을 덮어쓴다. 🔴 호출을 AST 로 보지 않고 **결과**를
       본다: 쌓인 파일의 열쇠가 전부 `league:fotmob` 로 시작한다.
    """
    from app.core import autoleague as al
    bad = [k for k in al.registered() if not k.startswith("league:fotmob")]
    assert not bad, (
        f"🔴 자동 등록 파일이 **손 표 꼴의 열쇠**로 쌓였다 {bad} — "
        f"`config/competitions.yaml` 의 열쇠를 덮으면 그 리그 판정이 거짓이 된다")


def test_v6_대회_글자가_겹치면_고르지_않는다():
    """🔴🔴 실사고 2026-10-10(두 번째) — **인도네시아 경기가 스위스 리그로 붙었다**.

    둘 다 대회 이름이 `Super League` 다. 🔴 대회 이름은 **나라를 넘어 겹친다**
    (첫 번째 사고는 엘살바도르 `Primera Division` ↔ 스페인 라리가였다).

    | 증거 | 무엇을 한다 |
    |---|---|
    | **리그 번호**가 있다 | 번호가 글자를 **이긴다** |
    | 글자뿐이고 **한 곳**에 걸린다 | 그 열쇠로 선다 |
    | 글자뿐이고 **여러 곳**에 걸린다 | 🔴 **고르지 않는다**(빈 글자) |

    ⚠️ 돌연변이: `autoleague.key_by_seen` 에서 애매함 검사를 지우면 — 두 리그 중
       **먼저 읽힌 쪽**이 이기고, 그 리그의 기준·홈 이점으로 남의 경기를 판정한다.
    🔴 빈 글자가 **맞다** — 카드가 *"대회를 알아보지 못했다"* 를 띄우고 등급을
       보류하는 쪽이, 틀린 기준으로 판정하는 것보다 낫다.
    """
    from app.core import autoleague as al
    from app.core import competition as comp
    rows = [(k, al.load(k)) for k in al.registered()]
    seen: dict[str, set[str]] = {}
    for key, box in rows:
        for s in (box.get("seen") or []):
            seen.setdefault(comp._norm(s), set()).add(key)
    if not seen:
        import pytest
        pytest.skip("🔴 자동 등록 파일이 아직 없다 — 셀 것이 없다(인수 실행 전)")
    bad: list[str] = []
    for said, keys in seen.items():
        got, why = comp.key_of(competition=said)
        if len(keys) == 1:
            want = next(iter(keys))
            # ⚠️ 손 표가 그 글자를 **더 좁게** 아는 경우는 손 표가 이긴다 —
            #    그때는 자동 등록 열쇠가 아니어도 틀린 것이 아니다.
            if got and got != want and got.startswith("league:fotmob"):
                bad.append(f"`{said}` → {got} (기대 {want} · {why})")
        elif got:
            bad.append(f"🔴 `{said}` 는 {len(keys)}곳에 걸리는데 {got} 를 "
                       f"골랐다 — 고르지 말아야 한다({sorted(keys)})")
    assert not bad, ("🔴 대회 글자 판정이 틀렸다:\n  " + "\n  ".join(bad))


def test_v6_번호가_글자를_이긴다():
    """🔴 §2 — **리그 번호가 있으면 번호가 판정한다**(이름은 겹친다).

    ⚠️ 돌연변이: `s5_verify.comp_kind` 에서 `league_id=` 인자를 지우면 —
       인도네시아 경기가 다시 스위스 리그로 붙는다. 🔴 `Facts.league_id` 가
       그 번호를 들고 오는 칸이고, 그 칸이 **있어야** 한다.
    """
    from app.core import schema
    assert "league_id" in schema.Facts.model_fields, (
        "🔴 `Facts.league_id` 가 없다 — 대회 판정이 글자로만 간다")
    import ast
    said = ast.parse((ROOT / "app" / "core" / "stages"
                      / "s5_verify.py").read_text(encoding="utf-8"))
    hit = [n for n in ast.walk(said) if isinstance(n, ast.Call)
           and ast.unparse(n.func).endswith("kind_of")
           and any(k.arg == "league_id" for k in n.keywords)]
    assert hit, ("🔴 `comp_kind` 가 `kind_of` 에 `league_id` 를 안 넘긴다 — "
                 "대회 이름은 나라를 넘어 겹친다(실사고 2026-10-10)")
    # 🔴 번호가 **거기까지 오려면** `facts_of` 가 실어야 한다(실측: 이 줄이 없어
    #    카드가 두 번 연속 "대회를 알아보지 못했다"를 띄웠다).
    said2 = ast.parse((ROOT / "app" / "core"
                       / "adapt.py").read_text(encoding="utf-8"))
    fns = [n for n in ast.walk(said2) if isinstance(n, ast.FunctionDef)
           and n.name == "facts_of"]
    assert fns and "league_id=" in ast.unparse(fns[0]), (
        "🔴 `adapt.facts_of` 가 `league_id` 를 `Facts` 에 안 싣는다 — "
        "`s2_facts` 가 담아도 판정까지 오지 않는다")
